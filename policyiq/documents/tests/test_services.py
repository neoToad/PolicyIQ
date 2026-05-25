from unittest import mock

from django.test import SimpleTestCase

from documents.services.chunker import chunk_pages


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
