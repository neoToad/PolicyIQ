from unittest import mock

import requests
from django.test import SimpleTestCase

from documents.exceptions import EmbeddingError
from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks, embed_query
from documents.services.extractor import extract_pages
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
    def test_embed_chunks_sends_all_in_one_batch_when_under_batch_size(self, mock_post):
        """Chunks below batch_size are sent as a single batched request."""
        mock_response = mock.Mock(
            raise_for_status=mock.Mock(),
            json=mock.Mock(return_value={"embeddings": [[3.0, 4.0], [0.0, 1.0]]}),
        )
        mock_post.return_value = mock_response
        chunks = [
            {"text": "first", "page_number": 1, "token_offset": 0},
            {"text": "second", "page_number": 1, "token_offset": 50},
        ]

        result = embed_chunks(chunks, batch_size=32)

        self.assertEqual(result[0]["embedding"], [0.6, 0.8])
        self.assertEqual(result[1]["embedding"], [0.0, 1.0])
        self.assertEqual(mock_post.call_count, 1)
        # The batched request should send both texts in a single "input" list.
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["json"]["input"], ["first", "second"])
        self.assertEqual(kwargs["json"]["model"], "nomic-embed-text")

    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_chunks_splits_into_multiple_batches_when_above_batch_size(self, mock_post):
        """Chunks above batch_size are split into multiple batched requests."""
        mock_post.side_effect = [
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embeddings": [[1.0, 0.0]]}),
            ),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embeddings": [[0.0, 1.0]]}),
            ),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embeddings": [[1.0, 1.0]]}),
            ),
        ]
        chunks = [
            {"text": "a", "page_number": 1, "token_offset": 0},
            {"text": "b", "page_number": 1, "token_offset": 10},
            {"text": "c", "page_number": 1, "token_offset": 20},
        ]

        result = embed_chunks(chunks, batch_size=1)

        # Each chunk sent in its own batch of 1.
        self.assertEqual(mock_post.call_count, 3)
        # First chunk is unit-normalized (already unit length); others L2-normalized.
        self.assertEqual(result[0]["embedding"], [1.0, 0.0])
        self.assertEqual(result[1]["embedding"], [0.0, 1.0])
        self.assertEqual(result[2]["embedding"], [0.7071067811865475, 0.7071067811865475])

    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_chunks_returns_empty_list_for_empty_input(self, mock_post):
        """No chunks means no HTTP calls and an empty result."""
        result = embed_chunks([])

        self.assertEqual(result, [])
        self.assertEqual(mock_post.call_count, 0)

    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_chunks_falls_back_to_sequential_when_batch_fails(self, mock_post):
        """If the batch endpoint fails, fall back to per-chunk sequential calls."""
        # Batched path retries 3 times then raises; fallback path succeeds per-chunk.
        # 3 batched failures + 2 sequential successes = 5 calls.
        mock_post.side_effect = [
            requests.RequestException("batch endpoint broken"),
            requests.RequestException("batch endpoint broken"),
            requests.RequestException("batch endpoint broken"),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embeddings": [[3.0, 4.0]]}),
            ),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embeddings": [[0.0, 1.0]]}),
            ),
        ]
        chunks = [
            {"text": "first", "page_number": 1, "token_offset": 0},
            {"text": "second", "page_number": 1, "token_offset": 50},
        ]

        with mock.patch("documents.services.embedder.time.sleep"):
            result = embed_chunks(chunks, batch_size=32)

        # 3 batched retries + 2 fallback calls = 5 total calls.
        self.assertEqual(mock_post.call_count, 5)
        self.assertEqual(result[0]["embedding"], [0.6, 0.8])
        self.assertEqual(result[1]["embedding"], [0.0, 1.0])
        # The first 3 calls sent a list; the fallback calls sent single-element lists.
        first_kwargs = mock_post.call_args_list[0].kwargs
        fourth_kwargs = mock_post.call_args_list[3].kwargs
        fifth_kwargs = mock_post.call_args_list[4].kwargs
        self.assertEqual(first_kwargs["json"]["input"], ["first", "second"])
        self.assertEqual(fourth_kwargs["json"]["input"], "first")
        self.assertEqual(fifth_kwargs["json"]["input"], "second")

    @mock.patch("documents.services.embedder.time.sleep")
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_chunks_raises_clear_error_when_both_batch_and_fallback_fail(self, mock_post, mock_sleep):
        """If both batched and per-chunk fallback fail, raise EmbeddingError."""
        mock_post.side_effect = requests.RequestException("unreachable")

        with self.assertRaisesRegex(EmbeddingError, "Ollama"):
            embed_chunks([{"text": "only", "page_number": 1, "token_offset": 0}])

        # 3 batched retries + 3 fallback retries = 6 calls
        self.assertEqual(mock_post.call_count, 6)

    @mock.patch("documents.services.embedder.time.sleep")
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_query_retries_then_succeeds(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.RequestException("connection dropped"),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embeddings": [[1.0]]}),
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

        with self.assertRaisesRegex(EmbeddingError, "Ollama"):
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


class ExtractorLoggingTests(SimpleTestCase):
    @mock.patch("documents.services.extractor.fitz.open")
    def test_extractor_logs_pages_extracted_with_timing(self, mock_fitz_open):
        """Successful extraction emits an info line with page count and duration."""
        mock_doc = mock.MagicMock()
        mock_doc.__iter__.return_value = iter([])
        mock_fitz_open.return_value.__enter__.return_value = mock_doc

        with self.assertLogs("documents.extractor", level="INFO") as cm:
            extract_pages("/tmp/policy.pdf")

        info_lines = [line for line in cm.output if "Extracted" in line and "policy.pdf" in line]
        self.assertEqual(len(info_lines), 1)
        # The line includes a duration ("in T.TTs").
        self.assertIn("in ", info_lines[0])


class ChunkerLoggingTests(SimpleTestCase):
    @mock.patch("documents.services.chunker.tiktoken.get_encoding")
    def test_chunker_logs_chunks_created_with_stats(self, mock_get_encoding):
        """Successful chunking emits an info line with chunk count and stats."""
        mock_get_encoding.return_value = FakeEncoding()
        pages = [{"page_number": 1, "cleaned_text": "a b c d e f"}]

        with self.assertLogs("documents.chunker", level="INFO") as cm:
            chunk_pages(pages, chunk_size=4, overlap=1)

        info_lines = [line for line in cm.output if "Created" in line and "chunks" in line]
        self.assertEqual(len(info_lines), 1)
        # Stats: chunk count and a duration.
        self.assertIn("in ", info_lines[0])


class IndexerLoggingTests(SimpleTestCase):
    def setUp(self):
        # Ensure the singleton client cache is cleared between tests.
        from documents.services.indexer import get_chroma_client

        get_chroma_client.cache_clear()

    @mock.patch("documents.services.indexer.get_collection")
    def test_indexer_logs_vectors_indexed_with_timing(self, mock_get_collection):
        """Successful indexing emits an info line with vector count and duration."""
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

        with self.assertLogs("documents.indexer", level="INFO") as cm:
            index_document("doc-123", chunks, document_name="Test Policy.pdf")

        info_lines = [line for line in cm.output if "Indexed" in line and "doc-123" in line]
        self.assertEqual(len(info_lines), 1)
        # The line includes a duration.
        self.assertIn("in ", info_lines[0])

    @mock.patch("documents.services.indexer.get_collection")
    def test_indexer_logs_error_with_exception_type_on_failure(self, mock_get_collection):
        """When collection.add raises, the indexer logs an ERROR line with the exception type."""
        mock_collection = mock.Mock()
        mock_collection.add.side_effect = RuntimeError("ChromaDB write failed")
        mock_get_collection.return_value = mock_collection
        chunks = [
            {
                "text": "chunk one",
                "embedding": [0.1, 0.2],
                "page_number": 1,
                "token_offset": 0,
            },
        ]

        with self.assertLogs("documents.indexer", level="ERROR") as cm, self.assertRaises(RuntimeError):
            index_document("doc-fail", chunks, document_name="Test Policy.pdf")

        error_lines = [line for line in cm.output if "Failed to index" in line and "doc-fail" in line]
        self.assertEqual(len(error_lines), 1)
        self.assertIn("RuntimeError", error_lines[0])
