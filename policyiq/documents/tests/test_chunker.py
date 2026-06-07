"""Tests verifying the chunker reads CHUNK_SIZE / CHUNK_OVERLAP from settings."""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from documents.services.chunker import chunk_pages


class FakeEncoding:
    def encode(self, text):
        return [token for token in text.split(" ") if token]

    def decode(self, tokens):
        return " ".join(tokens)


class ChunkerSettingsTests(SimpleTestCase):
    @mock.patch("documents.services.chunker.tiktoken.get_encoding")
    def test_chunker_uses_settings_chunk_size(self, mock_get_encoding):
        """CHUNK_SIZE from settings controls the chunk size."""
        mock_get_encoding.return_value = FakeEncoding()
        pages = [{"page_number": 1, "cleaned_text": "a b c d e f g h"}]

        with override_settings(CHUNK_SIZE=2, CHUNK_OVERLAP=0):
            result = chunk_pages(pages)

        # With chunk_size=2, overlap=0, "a b c d e f g h" should produce 4 chunks
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]["text"], "a b")
        self.assertEqual(result[1]["text"], "c d")
        self.assertEqual(result[2]["text"], "e f")
        self.assertEqual(result[3]["text"], "g h")

    @mock.patch("documents.services.chunker.tiktoken.get_encoding")
    def test_chunker_uses_settings_chunk_overlap(self, mock_get_encoding):
        """CHUNK_OVERLAP from settings controls the overlap."""
        mock_get_encoding.return_value = FakeEncoding()
        pages = [{"page_number": 1, "cleaned_text": "a b c d e f"}]

        with override_settings(CHUNK_SIZE=3, CHUNK_OVERLAP=1):
            result = chunk_pages(pages)

        # chunk_size=3, overlap=1 -> step=2
        # tokens: a, b, c, d, e, f
        # chunks: [a,b,c] (offset 0), [c,d,e] (offset 2), [e,f] (offset 4)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["text"], "a b c")
        self.assertEqual(result[1]["text"], "c d e")
        self.assertEqual(result[2]["text"], "e f")

    def test_chunker_module_has_no_hardcoded_chunk_size_constant(self):
        """Audit H3 — chunk_size/overlap must not be hardcoded module constants."""
        # The chunker may or may not still expose CHUNK_SIZE/CHUNK_OVERLAP as
        # module-level names; the contract is that callers must read from
        # settings, not import a module constant. We check the call signature.
        import inspect

        import documents.services.chunker as chunker_mod

        sig = inspect.signature(chunker_mod.chunk_pages)
        # The chunk_size parameter should default to None (i.e., "use setting")
        self.assertIsNone(sig.parameters["chunk_size"].default)
        self.assertIsNone(sig.parameters["overlap"].default)
