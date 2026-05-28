from unittest import mock

from django.test import SimpleTestCase

from queries.services.retriever import retrieve_chunks


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
                    {"document_id": "doc-1", "page_number": 1, "token_offset": 0},
                    {"document_id": "doc-1", "page_number": 2, "token_offset": 50},
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
        self.assertEqual(result[0]["similarity_score"], 0.8)
        self.assertEqual(result[1]["similarity_score"], 0.5)
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
            "metadatas": [[{"document_id": "doc-1", "page_number": 1, "token_offset": 0}]],
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
