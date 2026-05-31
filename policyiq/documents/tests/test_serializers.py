from unittest import mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from documents.serializers import DocumentSerializer, UploadResultSerializer


class DocumentSerializerTests(SimpleTestCase):
    def test_document_serializer_fields(self):
        """Output serialization includes the expected keys."""
        doc = mock.Mock()
        doc.id = uuid4()
        doc.name = "policy.pdf"
        doc.page_count = 10
        doc.chunk_count = 25
        doc.uploaded_at = "2026-01-01T12:00:00Z"
        doc.file = mock.Mock()
        doc.file.url = "/media/documents/policy.pdf"

        serializer = DocumentSerializer(doc)
        data = serializer.data
        self.assertEqual(data["name"], "policy.pdf")
        self.assertEqual(data["page_count"], 10)
        self.assertEqual(data["chunk_count"], 25)
        self.assertIn("id", data)
        self.assertIn("uploaded_at", data)

    def test_document_serializer_validates_with_file_upload(self):
        doc_id = uuid4()
        data = {
            "id": str(doc_id),
            "name": "policy.pdf",
            "file": SimpleUploadedFile("policy.pdf", b"%PDF-fake"),
            "page_count": 10,
            "chunk_count": 25,
            "uploaded_at": "2026-01-01T12:00:00Z",
        }
        serializer = DocumentSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["name"], "policy.pdf")


class UploadResultSerializerTests(SimpleTestCase):
    def test_success_result_serializes_correctly(self):
        data = {
            "success": True,
            "document_id": str(uuid4()),
            "name": "policy.pdf",
            "page_count": 10,
            "chunk_count": 25,
        }
        serializer = UploadResultSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["success"], True)
        self.assertEqual(serializer.validated_data["name"], "policy.pdf")

    def test_failure_result_serializes_without_document_fields(self):
        data = {
            "success": False,
            "name": "virus.exe",
            "error": "Invalid content type.",
            "reason": "validation",
        }
        serializer = UploadResultSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["success"], False)
        self.assertNotIn("document_id", serializer.validated_data)

    def test_failure_result_rejects_missing_success(self):
        data = {
            "name": "file.pdf",
            "error": "oops",
        }
        serializer = UploadResultSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("success", serializer.errors)
