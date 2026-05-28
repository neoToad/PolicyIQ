from unittest import mock

from django.test import SimpleTestCase

from queries.services.generator import build_prompt
from queries.services.retriever import retrieve_chunks


class RetrieveChunksTests(SimpleTestCase):
    @mock.patch("queries.services.retriever.Document.objects.filter")
    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retrieve_chunks_returns_ordered_results_with_scores(
        self, mock_embed_query, mock_get_collection, mock_doc_filter
    ):
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": [["doc-1:0", "doc-1:50"]],
            "documents": [["first chunk text", "second chunk text"]],
            "metadatas": [
                [
                    {"document_id": "doc-1", "page_number": 1, "token_offset": 0},
                    {"document_id": "doc-1", "page_number": 2, "token_offset": 50},
                ]
            ],
            "distances": [[0.2, 0.5]],
        }
        mock_get_collection.return_value = mock_collection
        mock_doc = mock.Mock()
        mock_doc.id = "doc-1"
        mock_doc.name = "Test Policy.pdf"
        mock_doc_filter.return_value = [mock_doc]

        result = retrieve_chunks("test question", top_k=5)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["text"], "first chunk text")
        self.assertEqual(result[0]["page_number"], 1)
        self.assertEqual(result[0]["document_id"], "doc-1")
        self.assertEqual(result[0]["document_name"], "Test Policy.pdf")
        self.assertEqual(result[0]["similarity_score"], 0.8)
        self.assertEqual(result[1]["similarity_score"], 0.5)
        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2, 0.3]], n_results=5, where=None
        )

    @mock.patch("queries.services.retriever.Document.objects.filter")
    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retrieve_chunks_filters_by_document_id(
        self, mock_embed_query, mock_get_collection, mock_doc_filter
    ):
        mock_embed_query.return_value = [0.1, 0.2, 0.3]
        mock_collection = mock.Mock()
        mock_collection.query.return_value = {
            "ids": [["doc-1:0"]],
            "documents": [["filtered chunk"]],
            "metadatas": [[{"document_id": "doc-1", "page_number": 1, "token_offset": 0}]],
            "distances": [[0.1]],
        }
        mock_get_collection.return_value = mock_collection
        mock_doc = mock.Mock()
        mock_doc.id = "doc-1"
        mock_doc.name = "Test Policy.pdf"
        mock_doc_filter.return_value = [mock_doc]

        result = retrieve_chunks("test question", document_id="doc-1", top_k=1)

        self.assertEqual(len(result), 1)
        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.1, 0.2, 0.3]],
            n_results=1,
            where={"document_id": "doc-1"},
        )

    @mock.patch("queries.services.retriever.Document.objects.filter")
    @mock.patch("queries.services.retriever.get_collection")
    @mock.patch("queries.services.retriever.embed_query")
    def test_retrieve_chunks_returns_empty_when_no_results(
        self, mock_embed_query, mock_get_collection, mock_doc_filter
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
        mock_doc_filter.assert_not_called()


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
