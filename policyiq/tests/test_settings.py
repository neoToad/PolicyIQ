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


class SimilarityContextProcessorTests(SimpleTestCase):
    """The similarity context processor must inject the two threshold settings.

    The citations panel JS in ``templates/queries/ask.html:69`` reads these
    to colour-code the bar — hardcoding them in the template would drift
    from the server-side thresholds in ``settings.py`` (audit L13).
    """

    def test_processor_injects_both_thresholds(self):
        from policyiq.context_processors import similarity_thresholds

        ctx = similarity_thresholds(request=None)
        self.assertEqual(ctx["SIMILARITY_THRESHOLD"], settings.SIMILARITY_THRESHOLD)
        self.assertEqual(ctx["SIMILARITY_BAR_HIGH"], settings.SIMILARITY_BAR_HIGH)

    def test_processor_picks_up_override_settings(self):
        from policyiq.context_processors import similarity_thresholds

        with self.settings(SIMILARITY_THRESHOLD=0.42, SIMILARITY_BAR_HIGH=0.81):
            ctx = similarity_thresholds(request=None)
        self.assertEqual(ctx["SIMILARITY_THRESHOLD"], 0.42)
        self.assertEqual(ctx["SIMILARITY_BAR_HIGH"], 0.81)

    def test_processor_is_wired_in_settings(self):
        """The processor must be listed under TEMPLATES.OPTIONS.context_processors."""
        from django.template.engine import Engine

        processors = Engine.get_default().context_processors
        self.assertIn("policyiq.context_processors.similarity_thresholds", processors)


class AskTemplateThresholdInjectionTests(SimpleTestCase):
    """The ask page template must read the threshold values from context,
    not hardcode them (audit L13)."""

    def _render_ask_html(self):
        """Render templates/queries/ask.html with a request so context
        processors run (render_to_string without a request skips them)."""
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get("/ask/")
        return render_to_string("queries/ask.html", context={"documents": []}, request=request)

    def test_ask_html_default_does_not_have_hardcoded_high_threshold(self):
        """The default 0.75 must not appear as a literal in the rendered JS.

        With settings at their defaults, the threshold is 0.75 — the literal
        can be present in the page only as the rendered ``{{ SIMILARITY_BAR_HIGH }}``,
        so we check for the *numeric* form ``> 0.75`` (the bar boundary
        comparison) does not appear in the JS.
        """
        rendered = self._render_ask_html()
        self.assertNotIn("> 0.75", rendered)

    def test_ask_html_picks_up_overridden_high_threshold(self):
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get("/ask/")
        with self.settings(SIMILARITY_BAR_HIGH=0.81):
            rendered = render_to_string("queries/ask.html", context={"documents": []}, request=request)
        # 0.81 must appear as the bar boundary; the old 0.75 must not.
        self.assertIn("0.81", rendered)
        self.assertNotIn("0.75", rendered)

    def test_ask_html_picks_up_overridden_low_threshold(self):
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        request = RequestFactory().get("/ask/")
        with self.settings(SIMILARITY_THRESHOLD=0.42):
            rendered = render_to_string("queries/ask.html", context={"documents": []}, request=request)
        # The 0.42 low threshold must appear; the old 0.5 must not.
        self.assertIn("0.42", rendered)
        self.assertNotIn("0.5", rendered)
