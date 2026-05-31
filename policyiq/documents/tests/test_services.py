from unittest import mock

import requests
from django.test import SimpleTestCase

from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks, embed_query
from documents.services.indexer import delete_document, get_collection, index_document


class FakeEncoding:
    def encode(self, text):
        return [token for token in text.split(" ") if token]

    def decode(self, tokens):
        return " ".join(tokens)


class ChunkPagesTests(SimpleTestCase):
    @mock.patch("documents.services.chunker.tiktoken.get_encoding")
    def test_chunk_pages_splits_with_overlap_and_offsets(self, mock_get_encoding):
        mock_get_encoding.return_value = FakeEncoding()
        pages = [{"page_number": 1, "cleaned_text": "a b c d e f"}]

        result = chunk_pages(pages, chunk_size=4, overlap=1)

        self.assertEqual(
            result,
            [
                {"text": "a b c d", "page_number": 1, "token_offset": 0},
                {"text": "d e f", "page_number": 1, "token_offset": 3},
            ],
        )

    @mock.patch("documents.services.chunker.tiktoken.get_encoding")
    def test_chunk_pages_uses_start_page_when_chunk_spans_pages(self, mock_get_encoding):
        mock_get_encoding.return_value = FakeEncoding()
        pages = [
            {"page_number": 1, "cleaned_text": "a b"},
            {"page_number": 2, "cleaned_text": "c d e"},
        ]

        result = chunk_pages(pages, chunk_size=4, overlap=1)

        self.assertEqual(
            result,
            [
                {"text": "a b c d", "page_number": 1, "token_offset": 0},
                {"text": "d e", "page_number": 2, "token_offset": 3},
            ],
        )

    @mock.patch("documents.services.chunker.tiktoken.get_encoding")
    def test_chunk_pages_returns_empty_list_when_no_tokens(self, mock_get_encoding):
        mock_get_encoding.return_value = FakeEncoding()
        pages = [{"page_number": 1, "cleaned_text": "   "}]

        result = chunk_pages(pages)

        self.assertEqual(result, [])


class EmbedderTests(SimpleTestCase):
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_chunks_adds_embedding_to_each_chunk(self, mock_post):
        mock_post.side_effect = [
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embedding": [3.0, 4.0]}),
            ),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embedding": [0.0, 1.0]}),
            ),
        ]
        chunks = [
            {"text": "first", "page_number": 1, "token_offset": 0},
            {"text": "second", "page_number": 1, "token_offset": 50},
        ]

        result = embed_chunks(chunks)

        self.assertEqual(result[0]["embedding"], [0.6, 0.8])
        self.assertEqual(result[1]["embedding"], [0.0, 1.0])
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("documents.services.embedder.time.sleep")
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_query_retries_then_succeeds(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.RequestException("connection dropped"),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embedding": [1.0]}),
            ),
        ]

        result = embed_query("policy question")

        self.assertEqual(result, [1.0])
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @mock.patch("documents.services.embedder.time.sleep")
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_query_raises_clear_error_when_ollama_unreachable(self, mock_post, mock_sleep):
        mock_post.side_effect = requests.RequestException("unreachable")

        with self.assertRaisesRegex(RuntimeError, "Ollama"):
            embed_query("policy question")

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)


class IndexerTests(SimpleTestCase):
    def setUp(self):
        # Ensure the singleton client cache is cleared between tests.
        from documents.services.indexer import get_chroma_client

        get_chroma_client.cache_clear()

    @mock.patch("documents.services.indexer.chromadb.PersistentClient")
    @mock.patch("documents.services.indexer.settings")
    def test_get_collection_uses_persist_dir_and_returns_named_collection(self, mock_settings, mock_persistent_client):
        mock_settings.CHROMA_PERSIST_DIR = "/tmp/chroma"
        mock_collection = mock.Mock()
        mock_client = mock.Mock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_persistent_client.return_value = mock_client

        collection = get_collection("policies")

        self.assertIs(collection, mock_collection)
        mock_persistent_client.assert_called_once_with(path="/tmp/chroma")
        mock_client.get_or_create_collection.assert_called_once_with(name="policies")

    @mock.patch("documents.services.indexer.get_collection")
    def test_index_document_adds_all_chunks_with_expected_ids_metadata(self, mock_get_collection):
        mock_collection = mock.Mock()
        mock_get_collection.return_value = mock_collection
        chunks = [
            {
                "text": "chunk one",
                "embedding": [0.1, 0.2],
                "page_number": 1,
                "token_offset": 0,
            },
            {
                "text": "chunk two",
                "embedding": [0.3, 0.4],
                "page_number": 2,
                "token_offset": 128,
            },
        ]

        count = index_document("doc-123", chunks, document_name="Test Policy.pdf")

        self.assertEqual(count, 2)
        mock_collection.add.assert_called_once_with(
            ids=["doc-123:0", "doc-123:128"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            documents=["chunk one", "chunk two"],
            metadatas=[
                {"document_id": "doc-123", "document_name": "Test Policy.pdf", "page_number": 1, "token_offset": 0},
                {"document_id": "doc-123", "document_name": "Test Policy.pdf", "page_number": 2, "token_offset": 128},
            ],
        )

    @mock.patch("documents.services.indexer.get_collection")
    def test_delete_document_removes_chunks_by_document_id(self, mock_get_collection):
        mock_collection = mock.Mock()
        mock_get_collection.return_value = mock_collection

        delete_document("doc-456")

        mock_collection.delete.assert_called_once_with(where={"document_id": "doc-456"})
