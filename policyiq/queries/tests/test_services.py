from unittest import mock

import requests
from django.test import SimpleTestCase, override_settings

from queries.services.citations import build_citations
from queries.services.generator import _generate_anthropic, _generate_ollama, build_prompt, generate_response
from queries.services.retriever import retrieve_chunks


class BuildCitationsTests(SimpleTestCase):
    def test_build_citations_maps_chunks_to_citation_dicts(self):
        chunks = [
            {
                "text": "This is a long chunk of text that should be truncated for the preview.",
                "page_number": 3,
                "document_name": "Policy A.pdf",
                "similarity_score": 0.85,
            },
            {
                "text": "Short.",
                "page_number": 5,
                "document_name": "Policy B.pdf",
                "similarity_score": 0.72,
            },
        ]
        citations = build_citations(chunks)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["document_name"], "Policy A.pdf")
        self.assertEqual(citations[0]["page_number"], 3)
        self.assertEqual(citations[0]["similarity_score"], 0.85)
        self.assertEqual(citations[0]["text_preview"], "This is a long chunk of text that should be truncated for the preview."[:150])
        self.assertEqual(citations[1]["text_preview"], "Short.")

    def test_build_citations_defaults_to_unknown_document_name(self):
        chunks = [
            {
                "text": "No document name here.",
                "page_number": 1,
                "similarity_score": 0.9,
            }
        ]
        citations = build_citations(chunks)
        self.assertEqual(citations[0]["document_name"], "Unknown")
        self.assertEqual(citations[0]["page_number"], 1)

    def test_build_citations_returns_empty_for_empty_chunks(self):
        self.assertEqual(build_citations([]), [])


class RetrieveChunksTests(SimpleTestCase):
    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retrieve_chunks_returns_ordered_results_with_scores(
        self, mock_embed_query, mock_get_collection
    ):
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": [["doc-1:0", "doc-1:50"]],
            "documents": [["first chunk text", "second chunk text"]],
            "metadatas": [
                [
                    {"document_id": "doc-1", "document_name": "Test Policy.pdf", "page_number": 1, "token_offset": 0},
                    {"document_id": "doc-1", "document_name": "Test Policy.pdf", "page_number": 2, "token_offset": 50},
                ]
            ],
            "distances": [[0.2, 0.5]],
        }
        mock_get_collection.return_value = mock_collection

        result = retrieve_chunks("test question", top_k=5)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "first chunk text")
        self.assertEqual(result[0]["page_number"], 1)
        self.assertEqual(result[0]["document_id"], "doc-1")
        self.assertEqual(result[0]["document_name"], "Test Policy.pdf")
        self.assertEqual(result[0]["similarity_score"], 0.9)
        self.assertEqual(result[1]["similarity_score"], 0.75)
        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2, 0.3]], n_results=5, where=None
        )

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retrieve_chunks_filters_by_document_id(
        self, mock_embed_query, mock_get_collection
    ):
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": [["doc-1:0"]],
            "documents": [["filtered chunk"]],
            "metadatas": [[{"document_id": "doc-1", "document_name": "Test Policy.pdf", "page_number": 1, "token_offset": 0}]],
            "distances": [[0.1]],
        }
        mock_get_collection.return_value = mock_collection

        result = retrieve_chunks("test question", document_id="doc-1", top_k=1)

        self.assertEqual(len(result), 1)
        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2, 0.3]],
            n_results=1,
            where={"document_id": "doc-1"},
        )

    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retrieve_chunks_returns_empty_when_no_results(
        self, mock_embed_query, mock_get_collection
    ):
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        mock_get_collection.return_value = mock_collection

        result = retrieve_chunks("test question", top_k=5)

        self.assertEqual(result, [])


class BuildPromptTests(SimpleTestCase):
    def test_build_prompt_returns_none_when_no_chunk_meets_threshold(self):
        chunks = [
            {"text": "low relevance", "page_number": 1, "document_name": "A.pdf", "similarity_score": 0.3}
        ]
        result = build_prompt("question?", chunks, similarity_threshold=0.5)
        self.assertIsNone(result)

    def test_build_prompt_returns_none_for_empty_chunks(self):
        result = build_prompt("question?", [], similarity_threshold=0.5)
        self.assertIsNone(result)

    def test_build_prompt_includes_context_and_question(self):
        chunks = [
            {"text": "Coverage is approved.", "page_number": 3, "document_name": "Policy A.pdf", "similarity_score": 0.85},
            {"text": "PA required.", "page_number": 5, "document_name": "Policy A.pdf", "similarity_score": 0.72},
        ]
        prompt = build_prompt("Is prior auth needed?", chunks, similarity_threshold=0.5)
        self.assertIsNotNone(prompt)
        self.assertIn("Coverage is approved.", prompt)
        self.assertIn("PA required.", prompt)
        self.assertIn("Policy A.pdf", prompt)
        self.assertIn("page 3", prompt)
        self.assertIn("page 5", prompt)
        self.assertIn("Is prior auth needed?", prompt)
        self.assertIn("Answer only from the provided context", prompt)
        self.assertIn("do not speculate", prompt.lower())


class GenerateResponseTests(SimpleTestCase):
    @mock.patch("queries.services.generator.requests.post")
    def test_generate_response_yields_tokens_from_stream(self, mock_post):
        mock_response = mock.Mock()
        mock_response.iter_lines.return_value = [
            b'{"response":"Hello"}',
            b'{"response":" world"}',
            b'{"response":"","done":true}',
        ]
        mock_response.raise_for_status = mock.Mock()
        mock_post.return_value = mock_response

        tokens = list(generate_response("test prompt"))

        self.assertEqual(tokens, ["Hello", " world"])
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["json"]["model"], "llama3.2")
        self.assertTrue(call_kwargs["json"]["stream"])
        self.assertEqual(call_kwargs["stream"], True)

    @mock.patch("queries.services.generator.time.sleep")
    @mock.patch("queries.services.generator.requests.post")
    def test_generate_response_retries_then_succeeds(self, mock_post, mock_sleep):
        mock_response = mock.Mock()
        mock_response.iter_lines.return_value = [b'{"response":"ok"}']
        mock_response.raise_for_status = mock.Mock()
        mock_post.side_effect = [
            requests.RequestException("connection dropped"),
            mock_response,
        ]

        tokens = list(generate_response("test prompt"))

        self.assertEqual(tokens, ["ok"])
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("queries.services.generator.time.sleep")
    @mock.patch("queries.services.generator.requests.post")
    def test_generate_response_raises_clear_error_when_ollama_unreachable(
        self, mock_post, mock_sleep
    ):
        mock_post.side_effect = requests.RequestException("unreachable")

        with self.assertRaisesRegex(RuntimeError, "Ollama"):
            list(generate_response("test prompt"))

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)


class DispatchTests(SimpleTestCase):
    @mock.patch("queries.services.generator._generate_ollama")
    @override_settings(LLM_BACKEND="ollama")
    def test_generate_response_dispatches_to_ollama_by_default(self, mock_ollama):
        mock_ollama.return_value = iter(["token1", "token2"])
        tokens = list(generate_response("prompt"))
        self.assertEqual(tokens, ["token1", "token2"])
        mock_ollama.assert_called_once_with("prompt")

    @mock.patch("queries.services.generator._generate_anthropic")
    @override_settings(LLM_BACKEND="anthropic")
    def test_generate_response_dispatches_to_anthropic_when_configured(self, mock_anthropic):
        mock_anthropic.return_value = iter(["tokenA", "tokenB"])
        tokens = list(generate_response("prompt"))
        self.assertEqual(tokens, ["tokenA", "tokenB"])
        mock_anthropic.assert_called_once_with("prompt")

    @override_settings(LLM_BACKEND="unknown")
    def test_generate_response_raises_for_unsupported_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported LLM_BACKEND"):
            list(generate_response("prompt"))


class AnthropicGenerationTests(SimpleTestCase):
    @mock.patch("queries.services.generator.settings")
    @mock.patch("queries.services.generator.anthropic.Anthropic")
    def test_generate_anthropic_yields_tokens_from_stream(self, mock_client_cls, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_stream = mock.Mock()
        mock_stream.__iter__ = mock.Mock(
            return_value=iter([
                mock.Mock(type="content_block_delta", delta=mock.Mock(text="Hello")),
                mock.Mock(type="content_block_delta", delta=mock.Mock(text=" world")),
                mock.Mock(type="message_stop"),
            ])
        )
        mock_client = mock.Mock()
        mock_client.messages.stream.return_value.__enter__ = mock.Mock(return_value=mock_stream)
        mock_client.messages.stream.return_value.__exit__ = mock.Mock(return_value=False)
        mock_client_cls.return_value = mock_client

        tokens = list(_generate_anthropic("test prompt"))

        self.assertEqual(tokens, ["Hello", " world"])
        mock_client_cls.assert_called_once_with(api_key="test-key")
        call_kwargs = mock_client.messages.stream.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-20250514")
        self.assertEqual(call_kwargs["max_tokens"], 1024)
        self.assertIn("test prompt", call_kwargs["messages"][0]["content"])

    @mock.patch("queries.services.generator.settings")
    @mock.patch("queries.services.generator.anthropic.Anthropic")
    def test_generate_anthropic_raises_clear_error_on_failure(self, mock_client_cls, mock_settings):
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        mock_client = mock.Mock()
        mock_client.messages.stream.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        with self.assertRaisesRegex(RuntimeError, "Anthropic"):
            list(_generate_anthropic("test prompt"))
