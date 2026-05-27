import tempfile
from unittest import mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory

from documents.models import Document
from documents.views import DocumentUploadAPIView


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
        self.assertEqual(response.data["document_id"], str(fake_document.id))
        self.assertEqual(response.data["name"], "policy.pdf")
        self.assertEqual(response.data["page_count"], 2)
        self.assertEqual(response.data["chunk_count"], 2)
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
        self.assertEqual(response.data["error"]["message"], "Document ingestion failed.")
        self.assertIn("Invalid or corrupted PDF", response.data["error"]["detail"])
