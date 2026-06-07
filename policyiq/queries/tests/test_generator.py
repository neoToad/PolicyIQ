"""Tests for the `queries.generator` logger and safe_stream wrapper.

The ask path's "Streaming from X" → "First token in T" → "Generated N tokens
in T" sequence is the operator's answer to "why was that answer so slow?".
These tests lock that narrative in place.

Phase 3.2 adds tests for `safe_stream`, the wrapper that surfaces
mid-stream ``GenerationError`` to the HTMX client via a sentinel marker
instead of truncating the response silently.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from queries.exceptions import GenerationError
from queries.services.generator import generate_response, safe_stream


class GeneratorLoggingTests(SimpleTestCase):
    @override_settings(LLM_BACKEND="ollama")
    @mock.patch("queries.services.generator.ollama.generate")
    def test_generator_logs_backend_and_prompt_size(self, mock_generate):
        """The 'Streaming from ollama (model=Y, prompt=N chars)' line fires
        before the first token — locks the backend-selection visibility."""
        mock_generate.return_value = iter(["hi"])

        with self.assertLogs("queries.generator", level="INFO") as cm:
            list(generate_response("What is the deductible?"))

        stream_lines = [line for line in cm.output if "Streaming from" in line]
        self.assertEqual(len(stream_lines), 1)
        self.assertIn("ollama", stream_lines[0])
        self.assertIn("llama3.2", stream_lines[0])
        self.assertIn("prompt=", stream_lines[0])
        # The prompt size should be the length of the prompt string (23 chars).
        self.assertIn("prompt=23 chars", stream_lines[0])

    @override_settings(LLM_BACKEND="ollama")
    @mock.patch("queries.services.generator.ollama.generate")
    def test_generator_logs_first_token_timing(self, mock_generate):
        """The 'First token in T.TTs' line fires after the first yield —
        this is the latency signal that matters most for streaming UX."""
        mock_generate.return_value = iter(["Hello", " world"])

        with self.assertLogs("queries.generator", level="INFO") as cm:
            list(generate_response("test prompt"))

        first_token_lines = [line for line in cm.output if "First token in" in line]
        self.assertEqual(len(first_token_lines), 1)
        # The line should include "in T.TTs" suffix (timing format).
        self.assertIn("in ", first_token_lines[0])
        # The format is "First token in 0.00s" (one decimal place per the
        # `%.2f` format spec in the log call).
        self.assertRegex(first_token_lines[0], r"First token in \d+\.\d{2}s")

    @override_settings(LLM_BACKEND="ollama")
    @mock.patch("queries.services.generator.ollama.generate")
    def test_generator_logs_completion_with_token_count(self, mock_generate):
        """The 'Generated N tokens in T.TTs (first-token=T.TTs, backend=X)'
        line fires after the iterator is fully exhausted — the operator's
        total-time signal."""
        mock_generate.return_value = iter(["one", " two", " three"])

        with self.assertLogs("queries.generator", level="INFO") as cm:
            list(generate_response("test prompt"))

        completion_lines = [line for line in cm.output if "Generated 3 tokens" in line]
        self.assertEqual(len(completion_lines), 1)
        # The completion line includes first-token and backend.
        self.assertIn("first-token=", completion_lines[0])
        self.assertIn("backend=ollama", completion_lines[0])

    @override_settings(LLM_BACKEND="ollama")
    @mock.patch("queries.services.generator.ollama.generate")
    def test_generator_logs_only_completion_for_empty_stream(self, mock_generate):
        """An empty stream produces no tokens — completion line shows 0 tokens
        and no 'First token' line (because t_first_token stays None)."""
        mock_generate.return_value = iter([])

        with self.assertLogs("queries.generator", level="INFO") as cm:
            tokens = list(generate_response("test prompt"))

        self.assertEqual(tokens, [])
        completion_lines = [line for line in cm.output if "Generated 0 tokens" in line]
        self.assertEqual(len(completion_lines), 1)
        first_token_lines = [line for line in cm.output if "First token in" in line]
        self.assertEqual(len(first_token_lines), 0)


class SafeStreamTests(SimpleTestCase):
    """Tests for ``safe_stream`` — the mid-stream error sentinel wrapper.

    The audit-H6 fix: when the underlying generator raises
    :class:`GenerationError` after some tokens have already been yielded,
    the ``StreamingHttpResponse`` truncates silently and HTMX shows a
    partial answer. ``safe_stream`` yields a structured sentinel marker
    so the client can render a "stream interrupted" indicator without
    crashing the page.
    """

    def test_safe_stream_passes_through_clean_iterators(self):
        """A generator that completes normally yields every token unchanged."""

        def gen():
            yield "Hello"
            yield " world"
            yield "!"

        result = list(safe_stream(gen()))
        self.assertEqual(result, ["Hello", " world", "!"])

    def test_safe_stream_yields_tokens_then_error_sentinel_on_generation_error(self):
        """When the inner generator yields 2 tokens then raises GenerationError,
        the wrapper yields those 2 tokens and then a sentinel marker.

        The sentinel format is ``<!-- error: <message> -->`` so the HTMX
        page can ``querySelector`` for it and display a user-visible
        error without breaking the surrounding HTML structure.
        """
        from queries.exceptions import GenerationError

        def gen():
            yield "Answer"
            yield " is"
            raise GenerationError("Ollama timed out")

        result = list(safe_stream(gen()))

        # First two tokens pass through unchanged.
        self.assertEqual(result[:2], ["Answer", " is"])
        # Then exactly one error sentinel.
        sentinel_lines = [r for r in result[2:] if r.startswith("<!-- error:")]
        self.assertEqual(len(sentinel_lines), 1)
        self.assertIn("Ollama timed out", sentinel_lines[0])

    def test_safe_stream_yields_error_sentinel_on_first_token_failure(self):
        """If the inner generator raises before yielding anything, the wrapper
        still yields one sentinel (not a token, then a sentinel)."""
        from queries.exceptions import GenerationError

        def gen():
            raise GenerationError("immediate failure")
            yield  # pragma: no cover — unreachable

        result = list(safe_stream(gen()))
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].startswith("<!-- error:"))
        self.assertIn("immediate failure", result[0])

    def test_safe_stream_does_not_swallow_non_generation_exceptions(self):
        """Non-GenerationError exceptions propagate uncaught — the wrapper
        only knows how to surface LLM-stream errors. A plain ``ValueError``
        is the inner generator's contract violation and should bubble up."""
        from queries.exceptions import GenerationError

        class UnexpectedError(Exception):
            pass

        def gen():
            yield "ok"
            raise UnexpectedError("something else broke")

        # safe_stream catches GenerationError (and QueryError base); for
        # unexpected exceptions it lets them propagate.
        with self.assertRaises(UnexpectedError):
            list(safe_stream(gen()))

    def test_safe_stream_logs_error_line_with_message(self):
        """When safe_stream catches an error, the queries.generator logger
        captures an ERROR line with the exception message so operators
        can correlate the user-visible failure with server-side context."""
        from queries.exceptions import GenerationError

        def gen():
            yield "partial"
            raise GenerationError("connection reset")

        with self.assertLogs("queries.generator", level="ERROR") as cm:
            list(safe_stream(gen()))

        # At least one ERROR line mentions the message.
        error_lines = [line for line in cm.output if "connection reset" in line]
        self.assertEqual(len(error_lines), 1)
