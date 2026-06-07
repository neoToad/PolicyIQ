"""Tests for ``queries.services.query_pipeline`` (Phase 3.1).

The pipeline is the bridge between the two query views
(``AskPageView`` and ``QueryAPIView``) and the underlying retrieval +
generation services. ``run_query`` collapses the retrieve → prompt →
stream sequence into a single :class:`QueryResult` so the views become
thin adapters.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from queries.services.query_pipeline import QueryResult, run_query


class RunQueryTests(SimpleTestCase):
    def setUp(self):
        self.chunks = [
            {
                "text": "Coverage yes.",
                "page_number": 2,
                "document_name": "Policy.pdf",
                "document_id": "doc-1",
                "similarity_score": 0.85,
            },
        ]

    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_returns_no_information_when_retriever_returns_empty(self, mock_retrieve):
        """No chunks at all → ``QueryResult.kind == 'no_information'``.

        Only ``retrieve_chunks`` is mocked so the real ``build_prompt``
        runs against an empty list — it should return ``None`` and
        short-circuit before ``generate_response`` is called.
        """
        mock_retrieve.return_value = []

        result = run_query("Is it covered?", None, top_k=5, threshold=0.5)

        self.assertIsInstance(result, QueryResult)
        self.assertEqual(result.kind, "no_information")
        self.assertIsNone(result.answer_stream)
        self.assertEqual(result.citations, [])

    @mock.patch("queries.services.query_pipeline.generate_response")
    @mock.patch("queries.services.query_pipeline.build_prompt")
    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_returns_no_information_when_chunks_below_threshold(
        self, mock_retrieve, mock_build_prompt, mock_generate
    ):
        """Chunks exist but all below the similarity threshold → 'no_information'.

        ``build_prompt`` returns ``None`` to signal that no chunk clears
        the bar; ``run_query`` translates that into a no-information
        result without ever calling ``generate_response``.
        """
        mock_retrieve.return_value = [
            {
                "text": "irrelevant",
                "page_number": 1,
                "document_name": "X.pdf",
                "document_id": "doc-1",
                "similarity_score": 0.3,
            },
        ]
        mock_build_prompt.return_value = None

        result = run_query("Is it covered?", None, top_k=5, threshold=0.5)

        self.assertEqual(result.kind, "no_information")
        mock_generate.assert_not_called()

    @mock.patch("queries.services.query_pipeline.generate_response")
    @mock.patch("queries.services.query_pipeline.build_prompt")
    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_streams_tokens_and_carries_citations(self, mock_retrieve, mock_build_prompt, mock_generate):
        """Two chunks above threshold + a 3-token generator → QueryResult
        with ``kind == 'answer'``, an iterator yielding the 3 tokens, and
        citations populated from the chunks."""
        chunks = [
            {
                "text": "Coverage yes.",
                "page_number": 2,
                "document_name": "Policy.pdf",
                "document_id": "doc-1",
                "similarity_score": 0.85,
            },
            {
                "text": "PA not needed.",
                "page_number": 5,
                "document_name": "Policy.pdf",
                "document_id": "doc-1",
                "similarity_score": 0.72,
            },
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Answer", " is", " yes."])

        result = run_query("Is it covered?", None, top_k=5, threshold=0.5)

        self.assertEqual(result.kind, "answer")
        # The answer_stream iterator yields the 3 tokens.
        self.assertEqual(list(result.answer_stream), ["Answer", " is", " yes."])
        # Citations are built from the chunks.
        self.assertEqual(len(result.citations), 2)
        self.assertEqual(result.citations[0]["document_name"], "Policy.pdf")
        self.assertEqual(result.citations[0]["page_number"], 2)

    @mock.patch("queries.services.query_pipeline.generate_response")
    @mock.patch("queries.services.query_pipeline.build_prompt")
    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_wraps_generate_response_with_safe_stream(self, mock_retrieve, mock_build_prompt, mock_generate):
        """``run_query`` wraps ``generate_response`` with ``safe_stream`` so
        mid-stream :class:`GenerationError` becomes a sentinel marker
        instead of truncating the response (audit H6)."""
        from queries.exceptions import GenerationError

        mock_retrieve.return_value = self.chunks
        mock_build_prompt.return_value = "prompt text"

        def gen():
            yield "partial"
            raise GenerationError("Ollama died")

        mock_generate.return_value = gen()

        result = run_query("Is it covered?", None, top_k=5, threshold=0.5)
        self.assertEqual(result.kind, "answer")
        tokens = list(result.answer_stream)
        self.assertEqual(tokens[0], "partial")
        # A sentinel marker was emitted.
        self.assertTrue(any("<!-- error:" in t for t in tokens))

    @mock.patch("queries.services.query_pipeline.generate_response")
    @mock.patch("queries.services.query_pipeline.build_prompt")
    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_uses_settings_for_top_k_when_unspecified(self, mock_retrieve, mock_build_prompt, mock_generate):
        """When ``top_k`` is None, ``run_query`` reads from
        ``settings.RETRIEVAL_TOP_K``."""
        mock_retrieve.return_value = []

        with override_settings(RETRIEVAL_TOP_K=12):
            run_query("q", None, top_k=None, threshold=0.5)

        self.assertEqual(mock_retrieve.call_args.kwargs["top_k"], 12)

    @mock.patch("queries.services.query_pipeline.generate_response")
    @mock.patch("queries.services.query_pipeline.build_prompt")
    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_passes_explicit_top_k_to_retriever(self, mock_retrieve, mock_build_prompt, mock_generate):
        """An explicit ``top_k`` argument overrides the setting."""
        mock_retrieve.return_value = []

        with override_settings(RETRIEVAL_TOP_K=12):
            run_query("q", None, top_k=3, threshold=0.5)

        self.assertEqual(mock_retrieve.call_args.kwargs["top_k"], 3)

    @mock.patch("queries.services.query_pipeline.generate_response")
    @mock.patch("queries.services.query_pipeline.build_prompt")
    @mock.patch("queries.services.query_pipeline.retrieve_chunks")
    def test_run_query_passes_explicit_threshold_to_build_prompt(self, mock_retrieve, mock_build_prompt, mock_generate):
        """The threshold argument is forwarded to ``build_prompt``."""
        mock_retrieve.return_value = self.chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["ok"])

        run_query("q", None, top_k=5, threshold=0.7)

        self.assertEqual(mock_build_prompt.call_args.kwargs["similarity_threshold"], 0.7)
