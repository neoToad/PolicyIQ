"""Tests for the per-file upload loop helper (Phase 3.4).

``UploadPageView`` and ``DocumentUploadAPIView`` used to duplicate the
per-file validation + ingestion + result-accumulation loop. The shared
helper ``_process_uploads`` collapses that loop into a single function
that returns ``(results, status_code)``. These tests pin the new
boundary.
"""

from unittest import mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from documents.tests._isolation import IsolatedMediaRootMixin
from documents.views._uploads import _process_uploads


def _pdf_upload(name: str = "policy.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"%PDF-1.4 fake content", content_type="application/pdf")


def _txt_upload(name: str = "notes.txt") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"not a pdf", content_type="text/plain")


class ProcessUploadsTests(IsolatedMediaRootMixin, TestCase):
    """Unit tests for the ``_process_uploads`` helper.

    The helper owns the per-file loop, the validation, the per-file
    error handling, and the success/validation-error/all-failure
    status-code logic. The two upload views call it and then format
    the response.

    The :class:`IsolatedMediaRootMixin` provides a unique per-test
    ``MEDIA_ROOT`` via :func:`tempfile.mkdtemp` so tests do not share
    ``tempfile.gettempdir()`` (audit L1).
    """

    def setUp(self):
        IsolatedMediaRootMixin.setUp(self)
        self.username = "alice"

    @mock.patch("documents.views._uploads.ingest_uploaded_pdf")
    def test_process_uploads_returns_success_dict_for_valid_pdf(self, mock_ingest):
        """A single valid PDF produces a result dict with success=True and a document_id."""
        doc = mock.Mock()
        doc.id = uuid4()
        doc.name = "policy.pdf"
        doc.page_count = 2
        doc.chunk_count = 5
        mock_ingest.return_value = doc

        results, status_code = _process_uploads([_pdf_upload()], username=self.username)

        self.assertEqual(status_code, 201)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0]["success"])
        self.assertEqual(results[0]["document_id"], doc.id)
        self.assertEqual(results[0]["name"], "policy.pdf")
        self.assertEqual(results[0]["page_count"], 2)
        self.assertEqual(results[0]["chunk_count"], 5)

    @mock.patch("documents.views._uploads.ingest_uploaded_pdf")
    def test_process_uploads_returns_validation_error_for_non_pdf(self, mock_ingest):
        """A non-PDF file produces a validation-error result and a 400 status."""
        results, status_code = _process_uploads([_txt_upload()], username=self.username)

        self.assertEqual(status_code, 400)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["success"])
        self.assertEqual(results[0]["reason"], "validation")
        self.assertIn("Invalid content type", results[0]["error"])
        mock_ingest.assert_not_called()

    @mock.patch("documents.views._uploads.ingest_uploaded_pdf")
    def test_process_uploads_returns_500_when_pipeline_fails(self, mock_ingest):
        """A valid PDF whose ingestion raises produces a 500 + failure result."""
        mock_ingest.side_effect = ValueError("Invalid or corrupted PDF")

        results, status_code = _process_uploads([_pdf_upload()], username=self.username)

        self.assertEqual(status_code, 500)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["success"])
        self.assertIn("Invalid or corrupted PDF", results[0]["error"])

    @mock.patch("documents.views._uploads.ingest_uploaded_pdf")
    def test_process_uploads_mixed_success_and_validation(self, mock_ingest):
        """Mixed success + validation → 201 (any success wins)."""
        doc = mock.Mock()
        doc.id = uuid4()
        doc.name = "policy.pdf"
        doc.page_count = 1
        doc.chunk_count = 1
        mock_ingest.return_value = doc

        results, status_code = _process_uploads(
            [_pdf_upload("good.pdf"), _txt_upload("bad.txt")],
            username=self.username,
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[1]["success"])
        self.assertEqual(results[1]["reason"], "validation")

    @mock.patch("documents.views._uploads.ingest_uploaded_pdf")
    def test_process_uploads_mixed_success_and_pipeline_failure(self, mock_ingest):
        """Mixed success + pipeline failure → 201 (any success wins)."""
        good_doc = mock.Mock()
        good_doc.id = uuid4()
        good_doc.name = "good.pdf"
        good_doc.page_count = 1
        good_doc.chunk_count = 1

        def _ingest_side_effect(upload, *, username=None):
            if "bad" in upload.name:
                raise ValueError("corrupt")
            return good_doc

        mock_ingest.side_effect = _ingest_side_effect

        results, status_code = _process_uploads(
            [_pdf_upload("good.pdf"), _pdf_upload("bad.pdf")],
            username=self.username,
        )

        self.assertEqual(status_code, 201)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["success"])
        self.assertFalse(results[1]["success"])
        self.assertIn("corrupt", results[1]["error"])

    @mock.patch("documents.views._uploads.ingest_uploaded_pdf")
    def test_process_uploads_passes_username_to_pipeline(self, mock_ingest):
        """The username argument is forwarded to ``ingest_uploaded_pdf`` so the
        audit-trail log line carries the right user."""
        doc = mock.Mock()
        doc.id = uuid4()
        doc.name = "policy.pdf"
        doc.page_count = 1
        doc.chunk_count = 1
        mock_ingest.return_value = doc

        _process_uploads([_pdf_upload()], username="bob")

        mock_ingest.assert_called_once()
        self.assertEqual(mock_ingest.call_args.kwargs["username"], "bob")
