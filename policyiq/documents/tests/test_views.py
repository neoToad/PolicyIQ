import tempfile
from unittest import mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from documents.models import Chunk, Document
from documents.views import (
    DocumentUploadAPIView,
    StaffDocumentDeleteView,
    StaffDocumentListView,
    StaffDocumentReindexView,
    UploadPageView,
)


class DocumentUploadAPITests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = DocumentUploadAPIView.as_view()
        self.user = mock.Mock()
        self.user.is_authenticated = True
        self.user.is_staff = False

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.Chunk.objects.bulk_create")
    @mock.patch("documents.views.Document.objects.create")
    @mock.patch("documents.views.index_document")
    @mock.patch("documents.views.embed_chunks")
    @mock.patch("documents.views.chunk_pages")
    @mock.patch("documents.views.clean_pages")
    @mock.patch("documents.views.extract_pages")
    @mock.patch("documents.views.default_storage")
    def test_upload_pdf_runs_pipeline_and_returns_expected_payload(
        self,
        mock_storage,
        mock_extract_pages,
        mock_clean_pages,
        mock_chunk_pages,
        mock_embed_chunks,
        mock_index_document,
        mock_create_document,
        mock_bulk_create_chunks,
    ):
        # Set up storage mocks
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"
        fake_document = Document(
            id=uuid4(),
            name="policy.pdf",
            page_count=2,
            chunk_count=2,
        )
        mock_create_document.return_value = fake_document

        mock_extract_pages.return_value = [
            {"page_number": 1, "raw_text": "raw one"},
            {"page_number": 2, "raw_text": "raw two"},
        ]
        mock_clean_pages.return_value = [
            {"page_number": 1, "raw_text": "raw one", "cleaned_text": "clean one"},
            {"page_number": 2, "raw_text": "raw two", "cleaned_text": "clean two"},
        ]
        mock_chunk_pages.return_value = [
            {"text": "chunk one", "page_number": 1, "token_offset": 0},
            {"text": "chunk two", "page_number": 2, "token_offset": 500},
        ]
        embedded_chunks = [
            {
                "text": "chunk one",
                "page_number": 1,
                "token_offset": 0,
                "embedding": [0.1, 0.2],
            },
            {
                "text": "chunk two",
                "page_number": 2,
                "token_offset": 500,
                "embedding": [0.3, 0.4],
            },
        ]
        mock_embed_chunks.return_value = embedded_chunks
        mock_index_document.return_value = 2

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
        self.assertEqual(result["document_id"], str(fake_document.id))
        self.assertEqual(result["name"], "policy.pdf")
        self.assertEqual(result["page_count"], 2)
        self.assertEqual(result["chunk_count"], 2)
        mock_clean_pages.assert_called_once_with(mock_extract_pages.return_value)
        mock_chunk_pages.assert_called_once_with(mock_clean_pages.return_value)
        mock_embed_chunks.assert_called_once_with(mock_chunk_pages.return_value)
        mock_index_document.assert_called_once()

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.default_storage")
    @mock.patch("documents.views.extract_pages")
    def test_upload_returns_structured_error_on_pipeline_failure(self, mock_extract_pages, mock_storage):
        mock_storage.save.return_value = "documents/_tmp_broken.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_broken.pdf"
        mock_extract_pages.side_effect = ValueError("Invalid or corrupted PDF")

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
        from datetime import datetime, timezone
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
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

    @mock.patch("documents.views.delete_document")
    @mock.patch("documents.views.Document.objects.get")
    def test_staff_delete_removes_document_and_chromadb_chunks(
        self, mock_get, mock_delete_document
    ):
        doc_id = uuid4()
        doc = mock.Mock()
        doc.id = doc_id
        doc.name = "gone.pdf"
        mock_get.return_value = doc

        request = self.factory.delete("/admin/documents/" + str(doc_id) + "/delete/")
        request.user = self._staff_user()
        response = self.view(request, pk=str(doc_id))

        self.assertEqual(response.status_code, 200)
        mock_delete_document.assert_called_once_with(str(doc_id))
        doc.delete.assert_called_once()


class StaffDocumentReindexViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = StaffDocumentReindexView.as_view()

    def _staff_user(self):
        user = mock.Mock()
        user.is_authenticated = True
        user.is_staff = True
        return user

    @mock.patch("documents.views.index_document")
    @mock.patch("documents.views.embed_chunks")
    @mock.patch("documents.views.chunk_pages")
    @mock.patch("documents.views.clean_pages")
    @mock.patch("documents.views.extract_pages")
    @mock.patch("documents.views.Chunk.objects.bulk_create")
    @mock.patch("documents.views.Chunk.objects.filter")
    @mock.patch("documents.views.Document.objects.get")
    def test_staff_reindex_rebuilds_chunks_and_index(
        self,
        mock_get_document,
        mock_chunk_filter,
        mock_bulk_create,
        mock_extract_pages,
        mock_clean_pages,
        mock_chunk_pages,
        mock_embed_chunks,
        mock_index_document,
    ):
        doc_id = uuid4()
        doc = Document(id=doc_id, name="reindex.pdf", page_count=2, chunk_count=2)
        doc.file = mock.Mock()
        doc.file.path = "/fake/reindex.pdf"
        doc.save = mock.Mock()
        mock_get_document.return_value = doc
        mock_chunk_filter.return_value = mock.Mock(delete=mock.Mock())
        # Use side_effect to accept Chunk() calls without DB validation.
        mock_bulk_create.return_value = []

        mock_extract_pages.return_value = [
            {"page_number": 1, "raw_text": "raw one"},
            {"page_number": 2, "raw_text": "raw two"},
        ]
        mock_clean_pages.return_value = [
            {"page_number": 1, "raw_text": "raw one", "cleaned_text": "clean one"},
            {"page_number": 2, "raw_text": "raw two", "cleaned_text": "clean two"},
        ]
        mock_chunk_pages.return_value = [
            {"text": "chunk one", "page_number": 1, "token_offset": 0},
            {"text": "chunk two", "page_number": 2, "token_offset": 500},
            {"text": "chunk three", "page_number": 2, "token_offset": 950},
        ]
        embedded = [
            {"text": "chunk one", "page_number": 1, "token_offset": 0, "embedding": [0.1]},
            {"text": "chunk two", "page_number": 2, "token_offset": 500, "embedding": [0.2]},
            {"text": "chunk three", "page_number": 2, "token_offset": 950, "embedding": [0.3]},
        ]
        mock_embed_chunks.return_value = embedded
        mock_index_document.return_value = 3

        request = self.factory.post("/admin/documents/" + str(doc_id) + "/reindex/")
        request.user = self._staff_user()
        response = self.view(request, pk=str(doc_id))

        self.assertEqual(response.status_code, 200)
        mock_chunk_filter.return_value.delete.assert_called_once()
        mock_bulk_create.assert_called_once()
        mock_index_document.assert_called_once_with(str(doc_id), embedded)
        self.assertEqual(doc.chunk_count, 3)
        self.assertEqual(doc.page_count, 2)