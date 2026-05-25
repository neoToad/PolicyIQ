from unittest import mock

import requests
from django.test import SimpleTestCase

from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks, embed_query


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
                json=mock.Mock(return_value={"embedding": [0.1, 0.2]}),
            ),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embedding": [0.3, 0.4]}),
            ),
        ]
        chunks = [
            {"text": "first", "page_number": 1, "token_offset": 0},
            {"text": "second", "page_number": 1, "token_offset": 50},
        ]

        result = embed_chunks(chunks)

        self.assertEqual(result[0]["embedding"], [0.1, 0.2])
        self.assertEqual(result[1]["embedding"], [0.3, 0.4])
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("documents.services.embedder.time.sleep")
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_query_retries_then_succeeds(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.RequestException("connection dropped"),
            mock.Mock(
                raise_for_status=mock.Mock(),
                json=mock.Mock(return_value={"embedding": [0.9]}),
            ),
        ]

        result = embed_query("policy question")

        self.assertEqual(result, [0.9])
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @mock.patch("documents.services.embedder.time.sleep")
    @mock.patch("documents.services.embedder.requests.post")
    def test_embed_query_raises_clear_error_when_ollama_unreachable(
        self, mock_post, mock_sleep
    ):
        mock_post.side_effect = requests.RequestException("unreachable")

        with self.assertRaisesRegex(RuntimeError, "Ollama"):
            embed_query("policy question")

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)
