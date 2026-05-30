import tempfile
from unittest import mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from documents.models import Chunk, Document
from documents.views import (
    DocumentUploadAPIView,
    StaffDocumentDeleteView,
    StaffDocumentListView,
    StaffDocumentReindexView,
)


class DocumentUploadAPITests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = DocumentUploadAPIView.as_view()

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.Chunk.objects.bulk_create")
    @mock.patch("documents.views.Document.objects.create")
    @mock.patch("documents.views.index_document")
    @mock.patch("documents.views.embed_chunks")
    @mock.patch("documents.views.chunk_pages")
    @mock.patch("documents.views.clean_pages")
    @mock.patch("documents.views.extract_pages")
    def test_upload_pdf_runs_pipeline_and_returns_expected_payload(
        self,
        mock_extract_pages,
        mock_clean_pages,
        mock_chunk_pages,
        mock_embed_chunks,
        mock_index_document,
        mock_create_document,
        mock_bulk_create_chunks,
    ):
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
        fake_document = Document(
            id=uuid4(),
            name="policy.pdf",
            file_path="C:\\fake\\policy.pdf",
            page_count=2,
            chunk_count=2,
        )
        mock_create_document.return_value = fake_document

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
        mock_index_document.assert_called_once_with(str(fake_document.id), embedded_chunks)
        mock_bulk_create_chunks.assert_called_once()

        created_chunks = mock_bulk_create_chunks.call_args.args[0]
        self.assertEqual(len(created_chunks), 2)
        self.assertEqual(created_chunks[0].document, fake_document)
        self.assertEqual(created_chunks[0].page_number, 1)
        self.assertEqual(created_chunks[0].token_offset, 0)
        self.assertEqual(created_chunks[0].text, "chunk one")
        self.assertEqual(created_chunks[1].page_number, 2)
        self.assertEqual(created_chunks[1].token_offset, 500)
        self.assertEqual(created_chunks[1].text, "chunk two")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.views.extract_pages")
    def test_upload_returns_structured_error_on_pipeline_failure(self, mock_extract_pages):
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

        response = self.view(request)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        result = response.data["results"][0]
        self.assertEqual(result["success"], False)
        self.assertEqual(result["name"], "broken.pdf")
        self.assertIn("Invalid or corrupted PDF", result["error"])


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
        doc1 = Document(id=uuid4(), name="a.pdf", file_path="/a.pdf", page_count=1, chunk_count=2)
        doc2 = Document(id=uuid4(), name="b.pdf", file_path="/b.pdf", page_count=3, chunk_count=4)
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
        doc.file_path = "/gone.pdf"
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
        doc = Document(
            id=doc_id,
            name="reindex.pdf",
            file_path="C:\\fake\\reindex.pdf",
            page_count=2,
            chunk_count=2,
        )
        doc.save = mock.Mock()
        mock_get_document.return_value = doc
        mock_chunk_filter.return_value = mock.Mock(delete=mock.Mock())

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
