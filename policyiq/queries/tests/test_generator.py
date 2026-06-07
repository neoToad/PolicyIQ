"""Tests for the `queries.generator` logger.

The ask path's "Streaming from X" → "First token in T" → "Generated N tokens
in T" sequence is the operator's answer to "why was that answer so slow?".
These tests lock that narrative in place.
"""

from unittest import mock

from django.test import SimpleTestCase, override_settings

from queries.services.generator import generate_response


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
