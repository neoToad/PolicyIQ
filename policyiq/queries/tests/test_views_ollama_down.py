"""Tests for the Ollama-down failure path (audit H7).

When the local Ollama server is unreachable or returns an error envelope,
the query API and ask-page views must return a clear 502 Bad Gateway to
the client (with a human-readable error message) and log the failure at
ERROR level. The streaming response path is not safe to attempt when the
LLM backend is down: returning 200 with a partial stream would mislead
the client.

This test file pins down the failure-path contract:

- ``QueryAPIViewOllamaDownTests`` — JSON API path, status 502, no
  ``X-Citations`` header, ERROR log line.
- ``AskPageViewOllamaDownTests`` — HTML page path, status 502, error
  message in the body, ERROR log line, well-formed HTML.
- ``QueryAPIViewErrorEnvelopeTests`` — Ollama's 200+``{"error": "..."}``
  envelope is also treated as a downstream failure (audit M8).
"""

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from queries.views import AskPageView, QueryAPIView


def _user_mock():
    """Build a mock user suitable for ``force_authenticate``."""
    user = mock.Mock()
    user.is_authenticated = True
    user.pk = 1
    user.id = 1
    user.username = "alice"
    return user


def _collection_with_one_chunk():
    """Return a Mock that mimics a ChromaDB collection with one high-similarity chunk."""
    collection = mock.Mock()
    collection.query.return_value = {
        "ids": [["c1"]],
        "documents": [["Coverage approved."]],
        "metadatas": [[{"page_number": 1, "document_id": "d-1", "document_name": "Policy.pdf"}]],
        "distances": [[0.1]],  # squared L2 — high similarity
    }
    return collection


class QueryAPIViewOllamaDownTests(SimpleTestCase):
    """Audit H7: QueryAPIView returns 502 when Ollama is unreachable."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = QueryAPIView.as_view()
        self.user = _user_mock()

    @mock.patch("documents.services.embedder.ollama.embed_query")
    @mock.patch("queries.services.retriever.get_collection", return_value=_collection_with_one_chunk())
    def test_returns_502_when_embed_raises_ollama_error(self, mock_get_collection, mock_embed_query):
        """Ollama-down at the embed step (e.g., connection refused on /api/embed)
        surfaces as a 502 with a human-readable error message — NOT a 200 with
        a partial stream. The embedder raises ``OllamaError`` (the production
        behavior when the underlying HTTP call fails)."""
        from policyiq.ollama import OllamaError

        mock_embed_query.side_effect = OllamaError("connection refused")

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)

        with self.assertLogs("queries.views", level="ERROR") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        # No streaming happened, so no citations header should be set.
        self.assertNotIn("X-Citations", response)
        # Body contains a human-readable error string.
        body = response.data if hasattr(response, "data") else json.loads(response.content)
        self.assertIn("error", body)
        self.assertIn("Ollama", str(body["error"]))
        # The view's logger captured an ERROR line so operators can correlate.
        error_lines = [line for line in cm.output if "Ollama" in line or "unreachable" in line]
        self.assertGreaterEqual(len(error_lines), 1)

    @mock.patch("queries.services.generator.ollama.generate")
    @mock.patch("queries.services.retriever.get_collection", return_value=_collection_with_one_chunk())
    def test_returns_502_when_generation_raises_ollama_error(self, mock_get_collection, mock_generate):
        """Ollama-down at the LLM-generate step (e.g., connection refused on
        /api/generate) also surfaces as 502."""
        from policyiq.ollama import OllamaError

        mock_generate.side_effect = OllamaError("connection refused")

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)

        with self.assertLogs("queries.views", level="ERROR") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertNotIn("X-Citations", response)
        error_lines = [line for line in cm.output if "Ollama" in line or "unreachable" in line]
        self.assertGreaterEqual(len(error_lines), 1)


class QueryAPIViewErrorEnvelopeTests(SimpleTestCase):
    """Audit M8: Ollama's 200+``{"error": "..."}`` envelope must be treated as
    a downstream failure, not a successful empty response."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = QueryAPIView.as_view()
        self.user = _user_mock()

    @mock.patch("queries.services.generator.ollama.generate")
    @mock.patch("queries.services.retriever.get_collection", return_value=_collection_with_one_chunk())
    def test_returns_502_when_ollama_returns_error_envelope(self, mock_get_collection, mock_generate):
        """Ollama sometimes returns HTTP 200 with ``{"error": "model not found"}``
        — the shared client raises OllamaError in that case. The view must
        surface that as a 502, not a 200 empty stream."""
        from policyiq.ollama import OllamaError

        mock_generate.side_effect = OllamaError('{"error": "model llama3.2 not found"}')

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)

        with self.assertLogs("queries.views", level="ERROR") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertNotIn("X-Citations", response)
        error_lines = [line for line in cm.output if "Ollama" in line or "error" in line.lower()]
        self.assertGreaterEqual(len(error_lines), 1)


class AskPageViewOllamaDownTests(SimpleTestCase):
    """Audit H7 (HTML path): the HTMX ask page also returns 502 on Ollama down."""

    def setUp(self):
        self.factory = RequestFactory()
        self.view = AskPageView.as_view()

    @mock.patch("documents.services.embedder.ollama.embed_query")
    @mock.patch("queries.services.retriever.get_collection", return_value=_collection_with_one_chunk())
    def test_renders_error_in_html(self, mock_get_collection, mock_embed_query):
        """The HTML response is 502 with a human-readable error message and
        well-formed HTML (closing </div>) so the page is not half-rendered
        in the HTMX swap."""
        from policyiq.ollama import OllamaError

        mock_embed_query.side_effect = OllamaError("connection refused")

        request = self.factory.post("/ask/", {"question": "Is it covered?"})
        request.user = mock.Mock(username="alice", is_authenticated=True)

        with self.assertLogs("queries.views", level="ERROR") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, 502)
        # HTML body must be well-formed (closing </div>) and contain the error.
        body = response.content.decode()
        self.assertIn("</div>", body)
        self.assertIn("Ollama", body)
        error_lines = [line for line in cm.output if "Ollama" in line or "unreachable" in line]
        self.assertGreaterEqual(len(error_lines), 1)
