"""Tests for the centralized settings introduced in Phase 0.

The settings module is the single source of truth for tunables that were
previously hardcoded in service modules. These tests lock down the
required settings so a future refactor that drops one is caught here
before it breaks the service layer.
"""

from django.conf import settings
from django.test import SimpleTestCase


class RequiredSettingsTests(SimpleTestCase):
    """Verify all Phase 0 settings are present on the Django settings object."""

    def test_ollama_embed_model_default(self):
        self.assertEqual(settings.OLLAMA_EMBED_MODEL, "nomic-embed-text")

    def test_ollama_generate_model_default(self):
        self.assertEqual(settings.OLLAMA_GENERATE_MODEL, "llama3.2")

    def test_anthropic_model_default(self):
        self.assertEqual(settings.ANTHROPIC_MODEL, "claude-sonnet-4-20250514")

    def test_anthropic_max_tokens_default(self):
        self.assertEqual(settings.ANTHROPIC_MAX_TOKENS, 1024)

    def test_embedding_retry_attempts_default(self):
        self.assertEqual(settings.EMBEDDING_RETRY_ATTEMPTS, 3)

    def test_embedding_retry_delay_default(self):
        self.assertEqual(settings.EMBEDDING_RETRY_DELAY, 1)

    def test_embedding_batch_size_default(self):
        self.assertEqual(settings.EMBEDDING_BATCH_SIZE, 32)

    def test_embedding_batch_timeout_default(self):
        self.assertEqual(settings.EMBEDDING_BATCH_TIMEOUT, 60)

    def test_embedding_query_timeout_default(self):
        self.assertEqual(settings.EMBEDDING_QUERY_TIMEOUT, 30)

    def test_generation_timeout_default(self):
        self.assertEqual(settings.GENERATION_TIMEOUT, 60)

    def test_chunk_size_default(self):
        self.assertEqual(settings.CHUNK_SIZE, 500)

    def test_chunk_overlap_default(self):
        self.assertEqual(settings.CHUNK_OVERLAP, 50)

    def test_retrieval_top_k_default(self):
        self.assertEqual(settings.RETRIEVAL_TOP_K, 5)

    def test_similarity_threshold_default(self):
        self.assertEqual(settings.SIMILARITY_THRESHOLD, 0.5)

    def test_similarity_bar_high_default(self):
        self.assertEqual(settings.SIMILARITY_BAR_HIGH, 0.75)

    def test_pdf_max_bytes_default(self):
        self.assertEqual(settings.PDF_MAX_BYTES, 50 * 1024 * 1024)


class LlmConfigHelperTests(SimpleTestCase):
    """Verify the llm_config URL helpers derive Ollama URLs from OLLAMA_BASE_URL."""

    def test_get_ollama_embed_url_derives_from_base_url(self):
        from policyiq.llm_config import get_ollama_embed_url

        self.assertEqual(get_ollama_embed_url(), "http://localhost:11434/api/embed")

    def test_get_ollama_generate_url_derives_from_base_url(self):
        from policyiq.llm_config import get_ollama_generate_url

        self.assertEqual(get_ollama_generate_url(), "http://localhost:11434/api/generate")

    def test_get_ollama_tags_url_derives_from_base_url(self):
        from policyiq.llm_config import get_ollama_tags_url

        self.assertEqual(get_ollama_tags_url(), "http://localhost:11434/api/tags")

    def test_get_ollama_embed_url_strips_trailing_slash_on_base(self):
        from policyiq.llm_config import get_ollama_embed_url

        with self.settings(OLLAMA_BASE_URL="http://example.test:1234/"):
            self.assertEqual(get_ollama_embed_url(), "http://example.test:1234/api/embed")
