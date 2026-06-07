"""Tests for the shared Ollama HTTP client introduced in Phase 0.2.

The client is the single retry/envelope-detection boundary for every
service that talks to Ollama (``embedder``, ``generator``, ``health``).
These tests pin the contract so later refactors (Phase 1's atomicity
work, Phase 3's view-to-service extraction) can lean on a stable
foundation.

All tests mock ``requests`` at the import site used inside the client
module, so the network is never touched and the tests run in any
environment without Ollama running.
"""

from __future__ import annotations

from unittest import mock

import requests
from django.test import SimpleTestCase


def _ok_response(payload: dict | None = None, status: int = 200) -> mock.Mock:
    """Build a mock requests.Response with the given JSON payload and status.

    ``raise_for_status`` raises the real :class:`requests.HTTPError` so the
    client treats it like a real network call (the production code catches
    ``requests.RequestException``). The HTTPError is also tied to the mock
    response so tracebacks are readable.
    """
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {"ok": True}

    def _raise_for_status() -> None:
        if status >= 400:
            err = requests.HTTPError(f"HTTP {status}")
            err.response = resp
            raise err

    resp.raise_for_status = mock.Mock(side_effect=_raise_for_status)
    return resp


class PostJsonTests(SimpleTestCase):
    """``post_json`` is the workhorse: one POST, shared retry, parsed JSON back."""

    def test_post_json_returns_parsed_dict(self):
        from policyiq.ollama import post_json

        with mock.patch("policyiq.ollama.requests.post", return_value=_ok_response({"ok": True})):
            result = post_json("/api/embed", {"model": "nomic-embed-text", "input": ["x"]}, timeout=10)
        self.assertEqual(result, {"ok": True})

    def test_post_json_retries_on_request_exception(self):
        """Two failures then success → three calls total; backoff sleeps in between."""
        from policyiq.ollama import post_json

        side_effects = [
            requests.ConnectionError("boom 1"),
            requests.ConnectionError("boom 2"),
            _ok_response({"ok": True}),
        ]
        with (
            mock.patch("policyiq.ollama.requests.post", side_effect=side_effects),
            mock.patch("policyiq.ollama.time.sleep") as mock_sleep,
            mock.patch("policyiq.ollama.settings.EMBEDDING_RETRY_ATTEMPTS", 3),
            mock.patch("policyiq.ollama.settings.EMBEDDING_RETRY_DELAY", 1),
        ):
            result = post_json("/api/embed", {"input": ["x"]}, timeout=1)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(mock_sleep.call_count, 2)  # 2 sleeps between 3 attempts

    def test_post_json_raises_ollama_error_after_max_attempts(self):
        from policyiq.ollama import OllamaError, post_json

        with (
            mock.patch("policyiq.ollama.requests.post", side_effect=requests.ConnectionError("always fails")),
            mock.patch("policyiq.ollama.time.sleep"),
            mock.patch("policyiq.ollama.settings.EMBEDDING_RETRY_ATTEMPTS", 3),
            mock.patch("policyiq.ollama.settings.EMBEDDING_RETRY_DELAY", 0),
            self.assertRaises(OllamaError) as cm,
        ):
            post_json("/api/embed", {"input": ["x"]}, timeout=1)
        self.assertIn("unreachable", str(cm.exception).lower())
        self.assertIn("/api/embed", str(cm.exception))

    def test_post_json_raises_on_http_error_status(self):
        from policyiq.ollama import OllamaError, post_json

        with (
            mock.patch("policyiq.ollama.requests.post", return_value=_ok_response(status=500)),
            mock.patch("policyiq.ollama.settings.EMBEDDING_RETRY_ATTEMPTS", 1),
            self.assertRaises(OllamaError) as cm,
        ):
            post_json("/api/embed", {"input": ["x"]}, timeout=1)
        # 500 → wrapped as OllamaError
        self.assertIn("500", str(cm.exception))

    def test_post_json_raises_on_error_envelope(self):
        """Ollama returns 200 with ``{"error": "..."}`` for missing models etc."""
        from policyiq.ollama import OllamaError, post_json

        with (
            mock.patch("policyiq.ollama.requests.post", return_value=_ok_response({"error": "model 'nope' not found"})),
            mock.patch("policyiq.ollama.settings.EMBEDDING_RETRY_ATTEMPTS", 1),
            self.assertRaises(OllamaError) as cm,
        ):
            post_json("/api/embed", {"model": "nope", "input": ["x"]}, timeout=1)
        self.assertIn("model 'nope' not found", str(cm.exception))


class PostStreamTests(SimpleTestCase):
    """``post_stream`` yields decoded JSON lines from an Ollama streaming response."""

    def _streaming_response(self, lines):
        resp = mock.Mock()
        resp.raise_for_status = mock.Mock(return_value=None)
        iterator = iter(lines)
        resp.iter_lines = mock.Mock(return_value=iterator)
        return resp

    def test_post_stream_yields_decoded_lines(self):
        from policyiq.ollama import post_stream

        lines = [
            b'{"response": "Hello"}',
            b'{"response": " world"}',
            b'{"response": "!"}',
        ]
        with mock.patch("policyiq.ollama.requests.post", return_value=self._streaming_response(lines)):
            result = list(post_stream("/api/generate", {"prompt": "hi"}, timeout=5))
        self.assertEqual(result, [{"response": "Hello"}, {"response": " world"}, {"response": "!"}])

    def test_post_stream_skips_blank_lines(self):
        """Some Ollama versions send keep-alive blank lines; ignore them."""
        from policyiq.ollama import post_stream

        lines = [
            b'{"response": "Hi"}',
            b"",
            b'{"response": " there"}',
        ]
        with mock.patch("policyiq.ollama.requests.post", return_value=self._streaming_response(lines)):
            result = list(post_stream("/api/generate", {"prompt": "hi"}, timeout=5))
        self.assertEqual(len(result), 2)

    def test_post_stream_raises_on_midstream_disconnect(self):
        """A ChunkedEncodingError mid-stream should surface as OllamaError (audit M10)."""
        from policyiq.ollama import OllamaError, post_stream
        from requests.exceptions import ChunkedEncodingError

        def _iter_then_broken():
            yield b'{"response": "first"}'
            raise ChunkedEncodingError("connection broken")

        resp = mock.Mock()
        resp.raise_for_status = mock.Mock(return_value=None)
        resp.iter_lines = mock.Mock(return_value=_iter_then_broken())
        with mock.patch("policyiq.ollama.requests.post", return_value=resp), self.assertRaises(OllamaError):
            list(post_stream("/api/generate", {"prompt": "hi"}, timeout=5))

    def test_post_stream_raises_on_error_envelope(self):
        """A streaming 200 with ``{"error": "..."}`` still surfaces as OllamaError."""
        from policyiq.ollama import OllamaError, post_stream

        lines = [b'{"error": "model not found"}']
        with (
            mock.patch("policyiq.ollama.requests.post", return_value=self._streaming_response(lines)),
            self.assertRaises(OllamaError) as cm,
        ):
            list(post_stream("/api/generate", {"prompt": "hi"}, timeout=5))
        self.assertIn("model not found", str(cm.exception))


class ValidateEmbeddingVectorTests(SimpleTestCase):
    """``validate_embedding_vector`` defends against malformed embeddings (audit M8)."""

    def test_accepts_list_of_floats(self):
        from policyiq.ollama import validate_embedding_vector

        vec = validate_embedding_vector([0.1, 0.2, 0.3])
        self.assertEqual(vec, [0.1, 0.2, 0.3])

    def test_accepts_list_of_ints_coerced_to_floats(self):
        from policyiq.ollama import validate_embedding_vector

        vec = validate_embedding_vector([1, 2, 3])
        self.assertEqual(vec, [1.0, 2.0, 3.0])

    def test_rejects_list_of_strings(self):
        from policyiq.ollama import OllamaError, validate_embedding_vector

        with self.assertRaises((OllamaError, TypeError, ValueError)):
            validate_embedding_vector(["a", "b"])

    def test_rejects_non_list(self):
        from policyiq.ollama import OllamaError, validate_embedding_vector

        with self.assertRaises((OllamaError, TypeError, ValueError)):
            validate_embedding_vector("not a list")


class IsErrorEnvelopeTests(SimpleTestCase):
    """Detect Ollama's 200-but-error response shape (audit M8)."""

    def test_detects_error_key(self):
        from policyiq.ollama import is_error_envelope

        self.assertTrue(is_error_envelope({"error": "model not found"}))

    def test_ignores_normal_payload(self):
        from policyiq.ollama import is_error_envelope

        self.assertFalse(is_error_envelope({"embeddings": [[0.1, 0.2]]}))
        self.assertFalse(is_error_envelope({"response": "hi"}))
        self.assertFalse(is_error_envelope({}))


class PingTests(SimpleTestCase):
    """``ping()`` is the GET /api/tags health probe (audit L20)."""

    def test_ping_returns_true_on_200(self):
        from policyiq.ollama import ping

        with mock.patch("policyiq.ollama.requests.get", return_value=_ok_response({"models": []})):
            self.assertTrue(ping())

    def test_ping_returns_false_on_connection_error(self):
        from policyiq.ollama import ping

        with mock.patch("policyiq.ollama.requests.get", side_effect=OSError("connection refused")):
            self.assertFalse(ping())

    def test_ping_returns_false_on_http_error(self):
        from policyiq.ollama import ping

        with mock.patch("policyiq.ollama.requests.get", return_value=_ok_response(status=503)):
            self.assertFalse(ping())


class ThinWrapperTests(SimpleTestCase):
    """The convenience wrappers around ``post_json`` / ``post_stream``."""

    @mock.patch("policyiq.ollama.post_json")
    def test_embed_texts_returns_parsed_embeddings(self, mock_post_json):
        from policyiq.ollama import embed_texts

        mock_post_json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        result = embed_texts("nomic-embed-text", ["a", "b"])
        self.assertEqual(result, [[0.1, 0.2], [0.3, 0.4]])
        # Args: full embed URL, payload includes model + input
        args, kwargs = mock_post_json.call_args
        self.assertTrue(args[0].endswith("/api/embed"))
        self.assertEqual(args[1]["model"], "nomic-embed-text")
        self.assertEqual(args[1]["input"], ["a", "b"])

    @mock.patch("policyiq.ollama.post_json")
    def test_embed_query_returns_single_vector(self, mock_post_json):
        from policyiq.ollama import embed_query

        mock_post_json.return_value = {"embeddings": [[0.5, 0.6]]}
        result = embed_query("nomic-embed-text", "what is X?")
        self.assertEqual(result, [0.5, 0.6])

    @mock.patch("policyiq.ollama.post_json")
    def test_generate_non_streaming_returns_full_string(self, mock_post_json):
        from policyiq.ollama import generate

        mock_post_json.return_value = {"response": "Hello world", "done": True}
        result = generate("llama3.2", "say hi", stream=False)
        self.assertEqual(result, "Hello world")

    @mock.patch("policyiq.ollama.post_stream")
    def test_generate_streaming_returns_token_iterator(self, mock_post_stream):
        from policyiq.ollama import generate

        mock_post_stream.return_value = iter([{"response": "Hi"}, {"response": " there"}])
        result = list(generate("llama3.2", "say hi", stream=True))
        self.assertEqual(result, ["Hi", " there"])
