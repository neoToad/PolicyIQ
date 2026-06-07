import tempfile
from datetime import UTC
from unittest import mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from documents.views import (
    DocumentUploadAPIView,
    StaffDocumentDeleteView,
    StaffDocumentListView,
    StaffDocumentReindexView,
    UploadPageView,
)


class DocumentUploadAPITests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = DocumentUploadAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        self.user.is_staff = False
        # Set pk/id explicitly so the UserRateThrottle cache key uses the integer
        # value (avoiding Django's CacheKeyWarning about Mock objects in keys).
        self.user.pk = 1
        self.user.id = 1

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_upload_pdf_runs_pipeline_and_returns_expected_payload(self, mock_storage, mock_ingest):
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest_side_effect(document, file_path=None):
            document.page_count = 2
            document.chunk_count = 2
            return {}

        mock_ingest.side_effect = _ingest_side_effect

        upload = SimpleUploadedFile(
            "policy.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        result = response.data["results"][0]
        self.assertEqual(result["name"], "policy.pdf")
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["chunk_count"], 2)
        mock_ingest.assert_called_once()

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_upload_returns_structured_error_on_pipeline_failure(self, mock_storage, mock_ingest):
        mock_storage.save.return_value = "documents/_tmp_broken.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_broken.pdf"
        mock_ingest.side_effect = ValueError("Invalid or corrupted PDF")

        upload = SimpleUploadedFile(
            "broken.pdf",
            b"%PDF-broken",
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        result = response.data["results"][0]
        self.assertEqual(result["success"], False)
        self.assertEqual(result["name"], "broken.pdf")
        self.assertIn("Invalid or corrupted PDF", result["error"])
        # Verify temp file was cleaned up on failure.
        mock_storage.delete.assert_called_once()

    def test_upload_rejects_non_pdf_content_type(self):
        upload = SimpleUploadedFile(
            "not_a_pdf.txt",
            b"This is a text file",
            content_type="text/plain",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        result = response.data["results"][0]
        self.assertEqual(result["success"], False)
        self.assertEqual(result["name"], "not_a_pdf.txt")
        self.assertIn("content type", result["error"].lower())

    def test_upload_rejects_invalid_magic_bytes(self):
        upload = SimpleUploadedFile(
            "fake.pdf",
            b"NOTPDF fake content",
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        result = response.data["results"][0]
        self.assertEqual(result["success"], False)
        self.assertEqual(result["name"], "fake.pdf")
        self.assertIn("magic bytes", result["error"].lower())


class UploadPageViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.view = UploadPageView.as_view()

    def test_upload_rejects_non_pdf_content_type(self):
        upload = SimpleUploadedFile(
            "not_a_pdf.txt",
            b"This is a text file",
            content_type="text/plain",
        )
        request = self.factory.post("/upload/", {"file": upload})

        response = self.view(request)

        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertIn("content type", content.lower())
        self.assertIn("not_a_pdf.txt", content)

    def test_upload_rejects_invalid_magic_bytes(self):
        upload = SimpleUploadedFile(
            "fake.pdf",
            b"NOTPDF fake content",
            content_type="application/pdf",
        )
        request = self.factory.post("/upload/", {"file": upload})

        response = self.view(request)

        self.assertEqual(response.status_code, 400)
        content = response.content.decode()
        self.assertIn("magic bytes", content.lower())
        self.assertIn("fake.pdf", content)


class StaffDocumentListViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StaffDocumentListView.as_view()

    def _staff_user(self):
        user = mock.Mock()
        user.is_authenticated = True
        user.is_staff = True
        return user

    def _non_staff_user(self):
        user = mock.Mock()
        user.is_authenticated = True
        user.is_staff = False
        return user

    @mock.patch("documents.views.Document.objects.order_by")
    def test_staff_user_sees_document_list(self, mock_order_by):
        from datetime import datetime

        dt = datetime(2026, 1, 1, tzinfo=UTC)
        doc1 = mock.Mock(id=uuid4(), name="a.pdf", page_count=1, chunk_count=2, uploaded_at=dt)
        doc2 = mock.Mock(id=uuid4(), name="b.pdf", page_count=3, chunk_count=4, uploaded_at=dt)
        mock_order_by.return_value = [doc1, doc2]

        request = self.factory.get("/admin/documents/")
        request.user = self._staff_user()
        response = self.view(request)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("a.pdf", content)
        self.assertIn("b.pdf", content)

    def test_non_staff_user_is_redirected_to_login(self):
        request = self.factory.get("/admin/documents/")
        request.user = self._non_staff_user()
        response = self.view(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_anonymous_user_is_redirected_to_login(self):
        request = self.factory.get("/admin/documents/")
        user = mock.Mock()
        user.is_authenticated = False
        user.is_staff = False
        request.user = user
        response = self.view(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


class StaffDocumentDeleteViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StaffDocumentDeleteView.as_view()

    def _staff_user(self):
        user = mock.Mock()
        user.is_authenticated = True
        user.is_staff = True
        return user

    @mock.patch("documents.views.delete_document_with_chunks")
    @mock.patch("documents.views.Document.objects.get")
    def test_staff_delete_delegates_to_deletion_service(self, mock_get, mock_delete_service):
        """The view now delegates to the shared `delete_document_with_chunks` service.

        The view's only job is the 404 check; the atomic delete logic
        lives in the service layer (audit H2, Phase 2.1).
        """
        doc_id = uuid4()
        doc = mock.Mock()
        doc.id = doc_id
        doc.name = "gone.pdf"
        mock_get.return_value = doc

        request = self.factory.delete("/admin/documents/" + str(doc_id) + "/delete/")
        request.user = self._staff_user()
        response = self.view(request, pk=str(doc_id))

        self.assertEqual(response.status_code, 200)
        mock_delete_service.assert_called_once_with(doc)


class StaffDocumentReindexViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StaffDocumentReindexView.as_view()

    def _staff_user(self):
        user = mock.Mock()
        user.is_authenticated = True
        user.is_staff = True
        return user

    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.delete_document")
    @mock.patch("documents.views.Chunk.objects.filter")
    @mock.patch("documents.views.Document.objects.get")
    def test_staff_reindex_delegates_to_ingest_document(
        self,
        mock_get_document,
        mock_chunk_filter,
        mock_delete_document,
        mock_ingest,
    ):
        doc_id = uuid4()
        doc = mock.Mock()
        doc.id = doc_id
        doc.name = "reindex.pdf"
        mock_get_document.return_value = doc
        mock_chunk_filter.return_value = mock.Mock(delete=mock.Mock())

        request = self.factory.post("/admin/documents/" + str(doc_id) + "/reindex/")
        request.user = self._staff_user()
        response = self.view(request, pk=str(doc_id))

        self.assertEqual(response.status_code, 200)
        mock_chunk_filter.return_value.delete.assert_called_once()
        mock_delete_document.assert_called_once_with(str(doc_id))
        mock_ingest.assert_called_once_with(doc)


class CORSTests(SimpleTestCase):
    def test_api_preflight_includes_cors_headers(self):
        """An OPTIONS preflight request from an allowed origin must return CORS headers."""
        from django.test import Client

        client = Client()
        response = client.options(
            "/api/documents/upload/",
            HTTP_ORIGIN="http://localhost:3000",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Access-Control-Allow-Origin", response)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:3000")

    def test_api_get_includes_cors_headers(self):
        """A GET request from an allowed origin must include the CORS header."""
        from django.test import Client

        client = Client()
        response = client.get(
            "/api/documents/upload/",
            HTTP_ORIGIN="http://localhost:3000",
        )
        self.assertIn("Access-Control-Allow-Origin", response)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:3000")


class CSRFTests(SimpleTestCase):
    def test_upload_page_rejects_post_without_csrf_token(self):
        """Django's CsrfViewMiddleware must block POSTs missing the CSRF token."""
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post("/upload/")
        self.assertEqual(response.status_code, 403)

    @mock.patch("rest_framework.authentication.TokenAuthentication.authenticate")
    def test_api_upload_with_token_auth_bypasses_csrf(self, mock_auth):
        """DRF TokenAuthentication must not require a CSRF token."""
        from django.test import Client

        mock_user = mock.Mock()
        mock_user.is_authenticated = True
        mock_user.pk = 1
        mock_user.id = 1
        mock_auth.return_value = (mock_user, None)

        client = Client(enforce_csrf_checks=True)
        response = client.post(
            "/api/documents/upload/",
            HTTP_AUTHORIZATION="Token faketoken",
        )
        # Token auth bypasses CSRF → we get 400 (missing file), not 403 (CSRF failure).
        self.assertEqual(response.status_code, 400)
        mock_auth.assert_called_once()


class UploadThrottleTests(TestCase):
    """Verify per-view throttling on the upload endpoint."""

    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # ensure no throttle state from previous tests
        self.factory = APIRequestFactory()
        self.view = DocumentUploadAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        self.user.pk = 1
        self.user.id = 1

    def _make_upload_request(self):
        upload = SimpleUploadedFile(
            "policy.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        return self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "rest_framework.authentication.SessionAuthentication",
                "rest_framework.authentication.TokenAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_THROTTLE_RATES": {
                "query_anon": "30/hour",
                "query_user": "120/hour",
                "upload_anon": "2/minute",
                "upload_user": "2/minute",
            },
        }
    )
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_authenticated_user_is_throttled_after_limit(self, mock_storage, mock_ingest):
        """Authenticated users exceeding upload_user rate get 429."""
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest_side_effect(document, file_path=None):
            document.page_count = 1
            document.chunk_count = 1
            return {}

        mock_ingest.side_effect = _ingest_side_effect

        for _ in range(2):
            request = self._make_upload_request()
            force_authenticate(request, user=self.user)
            response = self.view(request)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Third request should be throttled.
        request = self._make_upload_request()
        force_authenticate(request, user=self.user)
        response = self.view(request)
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(
        REST_FRAMEWORK={
            "DEFAULT_AUTHENTICATION_CLASSES": [
                "rest_framework.authentication.SessionAuthentication",
                "rest_framework.authentication.TokenAuthentication",
            ],
            "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
            "DEFAULT_THROTTLE_RATES": {
                "query_anon": "30/hour",
                "query_user": "120/hour",
                "upload_anon": "1/minute",
                "upload_user": "2/minute",
            },
        }
    )
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_anonymous_requests_are_throttled_via_upload_anon_scope(self, mock_storage, mock_ingest):
        """Anonymous users (no auth) are throttled by the upload_anon scope."""
        from rest_framework.permissions import AllowAny

        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest_side_effect(document, file_path=None):
            document.page_count = 1
            document.chunk_count = 1
            return {}

        mock_ingest.side_effect = _ingest_side_effect

        # Patch permission_classes away so the throttle chain can run end-to-end
        # (otherwise auth would short-circuit with 401/403 before the throttle fires).
        with mock.patch.object(DocumentUploadAPIView, "permission_classes", [AllowAny]):
            # First request consumes the single allowed hit.
            request = self._make_upload_request()
            response = self.view(request)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

            # Second request should be throttled (anonymous scope was exhausted).
            request = self._make_upload_request()
            response = self.view(request)
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_view_exposes_throttle_classes(self):
        """DocumentUploadAPIView must declare the upload throttles for protection."""
        from documents.throttles import UploadAnonRateThrottle, UploadUserRateThrottle

        self.assertIn(UploadAnonRateThrottle, DocumentUploadAPIView.throttle_classes)
        self.assertIn(UploadUserRateThrottle, DocumentUploadAPIView.throttle_classes)


class DocumentUploadLoggingTests(TestCase):
    """Tests for the `documents.views` logger on the upload path."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = DocumentUploadAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        self.user.is_staff = False
        self.user.username = "alice"
        self.user.pk = 1
        self.user.id = 1

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_upload_logs_received_line(self, mock_storage, mock_ingest):
        """The 'Received upload X (Y MB) from user=Z' line fires at view entry."""
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest_side_effect(document, file_path=None):
            document.page_count = 2
            document.chunk_count = 2
            return {}

        mock_ingest.side_effect = _ingest_side_effect

        upload = SimpleUploadedFile(
            "policy.pdf",
            b"%PDF-1.4 " + b"x" * (1024 * 1024),  # ~1 MB
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        with self.assertLogs("documents.views", level="INFO") as cm:
            self.view(request)

        received_lines = [line for line in cm.output if "Received upload" in line]
        self.assertEqual(len(received_lines), 1)
        self.assertIn("policy.pdf", received_lines[0])
        self.assertIn("MB", received_lines[0])
        self.assertIn("user=alice", received_lines[0])

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_upload_logs_validated_and_written_lines(self, mock_storage, mock_ingest):
        """The 'Validated PDF magic bytes' and 'Wrote X to Y' lines both fire."""
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest_side_effect(document, file_path=None):
            document.page_count = 1
            document.chunk_count = 1
            return {}

        mock_ingest.side_effect = _ingest_side_effect

        upload = SimpleUploadedFile(
            "policy.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        with self.assertLogs("documents.views", level="INFO") as cm:
            self.view(request)

        validated_lines = [line for line in cm.output if "Validated PDF" in line]
        written_lines = [line for line in cm.output if "Wrote" in line and "policy.pdf" in line]
        self.assertEqual(len(validated_lines), 1)
        self.assertEqual(len(written_lines), 1)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_upload_logs_dispatched_line_on_success(self, mock_storage, mock_ingest):
        """The 'Dispatched ingestion' line fires on success with a duration."""
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest_side_effect(document, file_path=None):
            document.page_count = 1
            document.chunk_count = 1
            return {}

        mock_ingest.side_effect = _ingest_side_effect

        upload = SimpleUploadedFile(
            "policy.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        with self.assertLogs("documents.views", level="INFO") as cm:
            self.view(request)

        dispatched_lines = [line for line in cm.output if "Dispatched ingestion" in line]
        self.assertEqual(len(dispatched_lines), 1)
        self.assertIn("policy.pdf", dispatched_lines[0])
        self.assertIn("document_id=", dispatched_lines[0])
        # Duration "in T.TTs" suffix.
        self.assertIn("in ", dispatched_lines[0])

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.ingest_document")
    @mock.patch("documents.views.default_storage")
    def test_upload_logs_error_with_exception_type_on_failure(self, mock_storage, mock_ingest):
        """When ingest_document raises, the view logs an ERROR line with the exception type."""
        from documents.exceptions import ExtractionError

        mock_storage.save.return_value = "documents/_tmp_broken.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_broken.pdf"
        mock_ingest.side_effect = ExtractionError("PDF corrupt")

        upload = SimpleUploadedFile(
            "broken.pdf",
            b"%PDF-broken",
            content_type="application/pdf",
        )
        request = self.factory.post(
            "/api/documents/upload/",
            {"file": upload},
            format="multipart",
        )
        force_authenticate(request, user=self.user)

        with self.assertLogs("documents.views", level="ERROR") as cm:
            self.view(request)

        error_lines = [line for line in cm.output if "Ingestion failed" in line and "broken.pdf" in line]
        self.assertEqual(len(error_lines), 1)
        self.assertIn("ExtractionError", error_lines[0])
        # The error line includes a duration.
        self.assertIn("after ", error_lines[0])


class HomePageViewTests(TestCase):
    """Tests for the public homepage (`GET /`)."""

    @mock.patch("documents.views.get_library_stats")
    def test_get_renders_home_template(self, mock_get_stats):
        """GET / returns 200, uses home.html, and contains the hero H1 text."""
        mock_get_stats.return_value = {
            "documents": 0,
            "chunks": 0,
            "pages": 0,
            "last_upload": None,
        }

        from django.test import Client

        response = Client().get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.templates[0].name, "home.html")
        # Hero tagline (per the spec).
        self.assertContains(response, "Ask plain-language questions about payer policy PDFs.")

    @mock.patch("documents.views.get_library_stats")
    def test_get_calls_stats_service(self, mock_get_stats):
        """The view must call get_library_stats() exactly once per request."""
        mock_get_stats.return_value = {
            "documents": 0,
            "chunks": 0,
            "pages": 0,
            "last_upload": None,
        }

        from django.test import Client

        Client().get("/")

        mock_get_stats.assert_called_once_with()

    @mock.patch("documents.views.get_library_stats")
    def test_get_passes_stats_to_template(self, mock_get_stats):
        """The view passes the stats dict to the template so numbers render."""
        mock_get_stats.return_value = {
            "documents": 3,
            "chunks": 42,
            "pages": 17,
            "last_upload": None,
        }

        from django.test import Client

        response = Client().get("/")

        self.assertContains(response, "3")  # documents count
        self.assertContains(response, "42")  # chunks count
        self.assertContains(response, "17")  # pages count
        self.assertIn("stats", response.context)
