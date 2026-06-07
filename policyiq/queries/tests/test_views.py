import json
from unittest import mock
from uuid import uuid4

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from queries.views import AskPageView, HealthCheckAPIView, QueryAPIView


class AskPageViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = AskPageView.as_view()

    @mock.patch("queries.views.Document.objects.order_by")
    def test_get_renders_form_with_documents(self, mock_order_by):
        dt = mock.Mock()
        doc1 = mock.Mock(id=uuid4(), uploaded_at=dt)
        doc1.name = "Policy A.pdf"
        doc2 = mock.Mock(id=uuid4(), uploaded_at=dt)
        doc2.name = "Policy B.pdf"
        mock_order_by.return_value = [doc1, doc2]

        request = self.factory.get("/ask/")
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Ask a Question", content)
        self.assertIn("Policy A.pdf", content)
        self.assertIn("Policy B.pdf", content)
        self.assertIn('hx-post="/ask/"', content)

    def test_post_with_empty_question_returns_400(self):
        request = self.factory.post("/ask/", {"question": "   "})
        response = self.view(request)

        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertIn("Please enter a question", content)

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_streams_answer_when_chunks_found(self, mock_retrieve, mock_build_prompt, mock_generate):
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Answer", " is", " yes."])

        request = self.factory.post("/ask/", {"question": "Is it covered?"})
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(content, '<div class="card"><p style="white-space: pre-wrap;">Answer is yes.</p></div>')
        mock_retrieve.assert_called_once_with("Is it covered?", document_id=None, top_k=settings.RETRIEVAL_TOP_K)
        # build_prompt defaults similarity_threshold to settings.SIMILARITY_THRESHOLD
        # — the view no longer hardcodes it.
        mock_build_prompt.assert_called_once_with("Is it covered?", chunks)
        mock_generate.assert_called_once_with("prompt text")

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_returns_message_when_no_relevant_chunks(self, mock_retrieve, mock_build_prompt, mock_generate):
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None

        request = self.factory.post("/ask/", {"question": "Is it covered?"})
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("No relevant information found", content)
        mock_generate.assert_not_called()

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_passes_document_id_to_retriever(self, mock_retrieve, mock_build_prompt, mock_generate):
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])

        request = self.factory.post(
            "/ask/",
            {"question": "Is it covered?", "document_id": "11111111-1111-1111-1111-111111111111"},
        )
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        mock_retrieve.assert_called_once_with(
            "Is it covered?", document_id="11111111-1111-1111-1111-111111111111", top_k=settings.RETRIEVAL_TOP_K
        )

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_includes_x_citations_header(self, mock_retrieve, mock_build_prompt, mock_generate):
        chunks = [
            {
                "text": "Coverage is approved for this procedure.",
                "page_number": 3,
                "document_name": "Policy.pdf",
                "similarity_score": 0.92,
            },
            {"text": "PA not needed.", "page_number": 5, "document_name": "Policy.pdf", "similarity_score": 0.78},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])

        request = self.factory.post("/ask/", {"question": "Is it covered?"})
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn("X-Citations", response)
        citations = json.loads(response["X-Citations"])
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["document_name"], "Policy.pdf")
        self.assertEqual(citations[0]["page_number"], 3)
        self.assertEqual(citations[0]["similarity_score"], 0.92)
        self.assertEqual(citations[0]["text_preview"], "Coverage is approved for this procedure."[:150])


class QueryAPIViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = QueryAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        # Set pk/id explicitly so the UserRateThrottle cache key uses the integer
        # value (avoiding Django's CacheKeyWarning about Mock objects in keys).
        self.user.pk = 1
        self.user.id = 1

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_returns_streaming_response_when_chunks_found(self, mock_retrieve, mock_build_prompt, mock_generate):
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Answer", " is", " yes."])

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertEqual(content, "Answer is yes.")
        mock_retrieve.assert_called_once_with("Is it covered?", document_id=None, top_k=settings.RETRIEVAL_TOP_K)
        # build_prompt defaults similarity_threshold to settings.SIMILARITY_THRESHOLD
        # — the view no longer hardcodes it.
        mock_build_prompt.assert_called_once_with("Is it covered?", chunks)
        mock_generate.assert_called_once_with("prompt text")

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_returns_json_when_no_relevant_chunks(self, mock_retrieve, mock_build_prompt, mock_generate):
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["answer"], "No relevant information found in the uploaded documents.")
        mock_generate.assert_not_called()

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_passes_document_id_to_retriever(self, mock_retrieve, mock_build_prompt, mock_generate):
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])

        request = self.factory.post(
            "/api/queries/",
            {"question": "Is it covered?", "document_id": "11111111-1111-1111-1111-111111111111"},
        )
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_retrieve.assert_called_once_with(
            "Is it covered?", document_id="11111111-1111-1111-1111-111111111111", top_k=settings.RETRIEVAL_TOP_K
        )

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_includes_x_citations_header(self, mock_retrieve, mock_build_prompt, mock_generate):
        chunks = [
            {
                "text": "Coverage is approved for this procedure.",
                "page_number": 3,
                "document_name": "Policy.pdf",
                "similarity_score": 0.92,
            },
            {"text": "PA not needed.", "page_number": 5, "document_name": "Policy.pdf", "similarity_score": 0.78},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])

        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)
        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("X-Citations", response)
        citations = json.loads(response["X-Citations"])
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0]["document_name"], "Policy.pdf")
        self.assertEqual(citations[0]["page_number"], 3)
        self.assertEqual(citations[0]["similarity_score"], 0.92)
        self.assertEqual(citations[0]["text_preview"], "Coverage is approved for this procedure."[:150])


class HealthCheckAPIViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = HealthCheckAPIView.as_view()

    @mock.patch("queries.views.health.check_ollama", return_value={"status": "up"})
    @mock.patch("queries.views.health.check_chromadb", return_value={"status": "up"})
    @mock.patch("queries.views.health.check_postgresql", return_value={"status": "up"})
    def test_returns_200_when_all_dependencies_healthy(self, mock_pg, mock_chroma, mock_ollama):
        request = self.factory.get("/api/health/")

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "healthy")
        self.assertEqual(
            response.data["dependencies"],
            {
                "postgresql": {"status": "up"},
                "chromadb": {"status": "up"},
                "ollama": {"status": "up"},
            },
        )

    @mock.patch("queries.views.health.check_ollama", return_value={"status": "down", "error": "refused"})
    @mock.patch("queries.views.health.check_chromadb", return_value={"status": "up"})
    @mock.patch("queries.views.health.check_postgresql", return_value={"status": "up"})
    def test_returns_503_when_any_dependency_down(self, mock_pg, mock_chroma, mock_ollama):
        request = self.factory.get("/api/health/")

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "unhealthy")
        self.assertEqual(response.data["dependencies"]["ollama"], {"status": "down", "error": "refused"})

    @mock.patch("queries.views.health.check_ollama", return_value={"status": "down", "error": "x"})
    @mock.patch("queries.views.health.check_chromadb", return_value={"status": "down", "error": "y"})
    @mock.patch("queries.views.health.check_postgresql", return_value={"status": "down", "error": "z"})
    def test_reports_all_failures(self, mock_pg, mock_chroma, mock_ollama):
        request = self.factory.get("/api/health/")

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        deps = response.data["dependencies"]
        self.assertEqual(deps["postgresql"]["error"], "z")
        self.assertEqual(deps["chromadb"]["error"], "y")
        self.assertEqual(deps["ollama"]["error"], "x")

    def test_does_not_require_authentication(self):
        """Health checks must be reachable by unauthenticated monitoring tools."""
        request = self.factory.get("/api/health/")

        with (
            mock.patch("queries.views.health.check_postgresql", return_value={"status": "up"}),
            mock.patch("queries.views.health.check_chromadb", return_value={"status": "up"}),
            mock.patch("queries.views.health.check_ollama", return_value={"status": "up"}),
        ):
            response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class QueryThrottleTests(SimpleTestCase):
    """Verify per-view throttling on the query endpoint."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # ensure no throttle state from previous tests
        self.factory = APIRequestFactory()
        self.view = QueryAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        self.user.pk = 1
        self.user.id = 1

    def _make_query_request(self):
        return self.factory.post("/api/queries/", {"question": "Is it covered?"})

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "rest_framework.authentication.SessionAuthentication",
                "rest_framework.authentication.TokenAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_THROTTLE_RATES": {
                "query_anon": "30/hour",
                "query_user": "2/minute",
                "upload_anon": "5/hour",
                "upload_user": "30/hour",
            },
        }
    )
    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_authenticated_user_is_throttled_after_limit(self, mock_retrieve, mock_build_prompt, mock_generate):
        """Authenticated users exceeding query_user rate get 429."""
        mock_retrieve.return_value = [
            {"text": "yes", "page_number": 1, "document_name": "p.pdf", "similarity_score": 0.9}
        ]
        mock_build_prompt.return_value = "prompt"
        mock_generate.return_value = iter(["Yes"])

        for _ in range(2):
            request = self._make_query_request()
            force_authenticate(request, user=self.user)
            response = self.view(request)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Third request should be throttled.
        request = self._make_query_request()
        force_authenticate(request, user=self.user)
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_view_exposes_throttle_classes(self):
        """QueryAPIView must declare the query throttles for protection."""
        from queries.throttles import QueryAnonRateThrottle, QueryUserRateThrottle

        self.assertIn(QueryAnonRateThrottle, QueryAPIView.throttle_classes)
        self.assertIn(QueryUserRateThrottle, QueryAPIView.throttle_classes)

    def test_health_check_is_not_throttled(self):
        """The health-check endpoint must remain unthrottled so monitors can poll it."""
        # HealthCheckAPIView explicitly sets throttle_classes = [] so monitors
        # can poll freely without consuming any user/anon throttle budget.
        self.assertEqual(HealthCheckAPIView.throttle_classes, [])


class AskPageViewLoggingTests(SimpleTestCase):
    """Tests for the `queries.views` logger on AskPageView."""

    def setUp(self):
        self.factory = RequestFactory()
        self.view = AskPageView.as_view()

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_logs_received_line_with_truncated_question(self, mock_retrieve, mock_build_prompt, mock_generate):
        """`Query received: "..."` line includes the truncated question and username."""
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None
        request = self.factory.post("/ask/", {"question": "What is the deductible?"})
        request.user = mock.Mock(username="alice", is_authenticated=True)

        with self.assertLogs("queries.views", level="INFO") as cm:
            self.view(request)

        receipt_lines = [line for line in cm.output if "Query received:" in line]
        self.assertEqual(len(receipt_lines), 1)
        self.assertIn("What is the deductible?", receipt_lines[0])
        self.assertIn("user=alice", receipt_lines[0])
        self.assertIn(f"top_k={settings.RETRIEVAL_TOP_K}", receipt_lines[0])

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_logs_no_relevant_info_path(self, mock_retrieve, mock_build_prompt, mock_generate):
        """No-chunks path emits the "Returned 'no relevant information' response" line."""
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None
        request = self.factory.post("/ask/", {"question": "What is the deductible?"})
        request.user = mock.Mock(username="bob", is_authenticated=True)

        with self.assertLogs("queries.views", level="INFO") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, 200)
        # The view-level "Returned 'no relevant information' response in T s" line.
        no_info_lines = [line for line in cm.output if "no relevant information" in line]
        self.assertEqual(len(no_info_lines), 1)
        # Generate was never called.
        mock_generate.assert_not_called()

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_logs_streaming_response_with_prompt_size(self, mock_retrieve, mock_build_prompt, mock_generate):
        """Streaming path emits a "Streamed answer" line with prompt size and citation count."""
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])
        request = self.factory.post("/ask/", {"question": "Is it covered?"})
        request.user = mock.Mock(username="alice", is_authenticated=True)

        with self.assertLogs("queries.views", level="INFO") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, 200)
        stream_lines = [line for line in cm.output if "Streamed answer" in line]
        self.assertEqual(len(stream_lines), 1)
        # prompt=11 chars (length of "prompt text"), 1 citation
        self.assertIn("prompt=11 chars", stream_lines[0])
        self.assertIn("citations=1", stream_lines[0])

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_post_truncates_long_questions_in_log(self, mock_retrieve, mock_build_prompt, mock_generate):
        """Long questions are truncated at 80 chars in the view-level log line
        (PII / log volume protection)."""
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None
        long_question = "x" * 200
        request = self.factory.post("/ask/", {"question": long_question})
        request.user = mock.Mock(username="alice", is_authenticated=True)

        with self.assertLogs("queries.views", level="INFO") as cm:
            self.view(request)

        receipt_lines = [line for line in cm.output if "Query received:" in line]
        self.assertEqual(len(receipt_lines), 1)
        # The "..." truncation marker is present.
        self.assertIn("...", receipt_lines[0])
        # The full 200-char question is NOT present.
        self.assertNotIn("x" * 200, receipt_lines[0])


class QueryAPIViewLoggingTests(SimpleTestCase):
    """Tests for the `queries.views` logger on QueryAPIView."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = QueryAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        self.user.pk = 1
        self.user.id = 1
        self.user.username = "alice"

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_logs_received_line_with_truncated_question(self, mock_retrieve, mock_build_prompt, mock_generate):
        """`Query received: "..."` line includes the truncated question and username."""
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None
        request = self.factory.post("/api/queries/", {"question": "What is the deductible?"})
        force_authenticate(request, user=self.user)

        with self.assertLogs("queries.views", level="INFO") as cm:
            self.view(request)

        receipt_lines = [line for line in cm.output if "Query received:" in line]
        self.assertEqual(len(receipt_lines), 1)
        self.assertIn("What is the deductible?", receipt_lines[0])
        self.assertIn("user=alice", receipt_lines[0])

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_logs_no_relevant_info_path(self, mock_retrieve, mock_build_prompt, mock_generate):
        """No-chunks path emits the "Returned 'no relevant information' response" line."""
        mock_retrieve.return_value = []
        mock_build_prompt.return_value = None
        request = self.factory.post("/api/queries/", {"question": "What is the deductible?"})
        force_authenticate(request, user=self.user)

        with self.assertLogs("queries.views", level="INFO") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        no_info_lines = [line for line in cm.output if "no relevant information" in line]
        self.assertEqual(len(no_info_lines), 1)
        mock_generate.assert_not_called()

    @mock.patch("queries.views.generate_response")
    @mock.patch("queries.views.build_prompt")
    @mock.patch("queries.views.retrieve_chunks")
    def test_query_logs_streaming_response_with_prompt_size(self, mock_retrieve, mock_build_prompt, mock_generate):
        """Streaming path emits a "Streamed answer" line with prompt size and citation count."""
        chunks = [
            {"text": "Coverage yes.", "page_number": 2, "document_name": "Policy.pdf", "similarity_score": 0.85},
        ]
        mock_retrieve.return_value = chunks
        mock_build_prompt.return_value = "prompt text"
        mock_generate.return_value = iter(["Yes"])
        request = self.factory.post("/api/queries/", {"question": "Is it covered?"})
        force_authenticate(request, user=self.user)

        with self.assertLogs("queries.views", level="INFO") as cm:
            response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stream_lines = [line for line in cm.output if "Streamed answer" in line]
        self.assertEqual(len(stream_lines), 1)
        self.assertIn("prompt=11 chars", stream_lines[0])
        self.assertIn("citations=1", stream_lines[0])
