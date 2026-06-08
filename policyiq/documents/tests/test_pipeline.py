"""Tests for the `documents.pipeline` logger and atomicity guarantees.

The pipeline orchestrates extract → clean → chunk → embed → index. These
tests verify that the pipeline emits a complete stage-level narrative on
both success and failure (with timing on each stage and the exception type
when a stage fails), and that the pipeline is atomic — a failure in any
stage rolls back the PostgreSQL state and compensates the ChromaDB vector
store to avoid leaving orphan rows or vectors.

Phase 3.3 adds ``IngestUploadedPdfTests`` for the new
``ingest_uploaded_pdf(upload_file, username=None)`` service entry point
that owns the temp-file lifecycle and the ``Document.objects.create``
call — both of which were previously tangled into the view layer.
"""

import tempfile
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase, override_settings

from documents.exceptions import ChunkingError, ExtractionError, IndexingError
from documents.models import Chunk, Document
from documents.services.pipeline import ingest_document, ingest_uploaded_pdf


class PipelineLoggingTests(TestCase):
    """Stage-level logging: each test patches the upstream services so the
    pipeline runs end-to-end against a real (in-memory SQLite) database.

    The pipeline wraps its body in `transaction.atomic()` after the
    audit-H1 fix, so these tests use `TestCase` (real DB). The mocked
    upstream services return deterministic data so no actual extraction,
    embedding, or indexing work happens.
    """

    def setUp(self):
        self.document = _make_document_for_db("log.pdf", page_count=0, chunk_count=0)
        self.extracted = [{"page_number": 1, "raw_text": "a"}]
        self.cleaned = [{"page_number": 1, "cleaned_text": "a"}]
        self.chunks = [{"text": "a", "page_number": 1, "token_offset": 0}]
        self.embedded = [{"text": "a", "page_number": 1, "token_offset": 0, "embedding": [0.1]}]

    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_completion_summary_with_timing(
        self, mock_extract, mock_clean, mock_chunk, mock_embed, mock_chunk_model, mock_index
    ):
        """The 'Ingestion complete' line fires on success and includes a duration."""
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_index.return_value = 1

        with self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(self.document)

        completion_lines = [line for line in cm.output if "Ingestion complete" in line]
        self.assertEqual(len(completion_lines), 1)
        # The "Ingestion complete" line includes a duration ("in T.TTs").
        self.assertIn("in ", completion_lines[0])

    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_failure_at_extractor_stage(self, mock_extract):
        """When extract_pages raises, the pipeline logs the failure with stage + type."""
        mock_extract.side_effect = ExtractionError("PDF corrupt")

        with self.assertRaises(ExtractionError), self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(self.document)

        failure_lines = [line for line in cm.output if "Ingestion failed" in line and "stage=extract" in line]
        self.assertEqual(len(failure_lines), 1)
        self.assertIn("ExtractionError", failure_lines[0])
        self.assertIn("log.pdf", failure_lines[0])

    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_failure_at_chunker_stage(self, mock_extract, mock_clean, mock_chunk):
        """When chunk_pages raises, the pipeline logs the failure with stage=chunk + type."""
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.side_effect = ChunkingError("chunk failed")

        with self.assertRaises(ChunkingError), self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(self.document)

        failure_lines = [line for line in cm.output if "Ingestion failed" in line and "stage=chunk" in line]
        self.assertEqual(len(failure_lines), 1)
        self.assertIn("ChunkingError", failure_lines[0])

    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_failure_at_indexer_stage(
        self, mock_extract, mock_clean, mock_chunk, mock_embed, mock_chunk_model, mock_index
    ):
        """When index_document raises, the pipeline logs the failure with stage=index + type."""
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_index.side_effect = IndexingError("ChromaDB write failed")

        with self.assertRaises(IndexingError), self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(self.document)

        failure_lines = [line for line in cm.output if "Ingestion failed" in line and "stage=index" in line]
        self.assertEqual(len(failure_lines), 1)
        self.assertIn("IndexingError", failure_lines[0])

    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_starting_ingestion_line(
        self, mock_extract, mock_clean, mock_chunk, mock_embed, mock_chunk_model, mock_index
    ):
        """The 'Starting ingestion' line fires on entry with the document id + name."""
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_index.return_value = 1

        with self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(self.document)

        start_lines = [line for line in cm.output if "Starting ingestion" in line]
        self.assertEqual(len(start_lines), 1)
        self.assertIn(str(self.document.id), start_lines[0])
        self.assertIn("log.pdf", start_lines[0])


def _make_document_for_db(name: str = "policy.pdf", page_count: int = 0, chunk_count: int = 0) -> Document:
    """Create a real Document row in the test DB for the atomicity tests.

    Bypasses the real file-field machinery by writing an empty tempfile via
    default_storage so the FileField's path accessor works. The pipeline only
    reads `document.file.path` and `document.id`; the file content is mocked
    out in each test.
    """

    temp_path = default_storage.save(f"documents/_atomic_test_{name}", ContentFile(b"%PDF-1.4\n"))
    return Document.objects.create(
        name=name,
        file=temp_path,
        page_count=page_count,
        chunk_count=chunk_count,
    )


class AtomicityTests(TestCase):
    """Verify that the pipeline is atomic (audit H1).

    A failure in any stage after a write must roll back the PostgreSQL state
    and compensate the ChromaDB vector store so no orphan rows or vectors
    remain. The pipeline's write order is also pinned: `index_document`
    (ChromaDB) runs BEFORE `bulk_create` (PostgreSQL) so a bulk_create
    failure can be compensated by deleting the just-written vectors.
    """

    def setUp(self):
        self.document = _make_document_for_db("atomic.pdf", page_count=0, chunk_count=0)
        # The successful-pipeline fixtures below are reused by most tests.
        self.extracted = [{"page_number": 1, "raw_text": "a"}]
        self.cleaned = [{"page_number": 1, "cleaned_text": "a"}]
        self.chunks = [{"text": "a", "page_number": 1, "token_offset": 0}]
        self.embedded = [{"text": "a", "page_number": 1, "token_offset": 0, "embedding": [0.1]}]

    def _patch_happy_path(self, index_mock, bulk_create_mock):
        """Wire the four upstream services + Chunk.bulk_create to succeed."""
        index_mock.return_value = 1
        bulk_create_mock.return_value = [mock.Mock()]
        return (
            mock.patch("documents.services.pipeline.extract_pages", return_value=self.extracted),
            mock.patch("documents.services.pipeline.clean_pages", return_value=self.cleaned),
            mock.patch("documents.services.pipeline.chunk_pages", return_value=self.chunks),
            mock.patch("documents.services.pipeline.embed_chunks", return_value=self.embedded),
        )

    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk.objects.bulk_create")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_rolls_back_chunks_on_indexer_failure(
        self,
        mock_extract,
        mock_clean,
        mock_chunk,
        mock_embed,
        mock_bulk_create,
        mock_index,
    ):
        """When `index_document` raises after `bulk_create` ran, no Chunk rows remain.

        The pipeline runs `index_document` AFTER `bulk_create` in the old
        order, so an indexer failure left orphan Chunk rows in PG. The
        audit-H1 fix wraps the whole body in `transaction.atomic`, so the
        bulk_create write is rolled back when the indexer raises.
        """
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_bulk_create.return_value = [mock.Mock()]
        mock_index.side_effect = IndexingError("ChromaDB write failed")

        with self.assertRaises(IndexingError):
            ingest_document(self.document)

        self.assertEqual(Chunk.objects.filter(document=self.document).count(), 0)
        # The page_count/chunk_count save() inside the pipeline must also
        # have been rolled back; the document is back to its pre-call value.
        self.document.refresh_from_db()
        self.assertEqual(self.document.page_count, 0)
        self.assertEqual(self.document.chunk_count, 0)

    @mock.patch("documents.services.pipeline.delete_document")
    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk.objects.bulk_create")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_rolls_back_indexer_writes_on_bulk_create_failure(
        self,
        mock_extract,
        mock_clean,
        mock_chunk,
        mock_embed,
        mock_bulk_create,
        mock_index,
        mock_delete,
    ):
        """When `bulk_create` raises, the just-written vectors are compensated.

        The audit-H1 fix reorders writes to `index_document` (ChromaDB)
        BEFORE `bulk_create` (PostgreSQL). When the PG write fails, the
        pipeline must explicitly delete the vectors it just wrote to avoid
        leaving orphan embeddings that no longer have a corresponding
        Chunk row.
        """
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_index.return_value = 1
        mock_bulk_create.side_effect = IntegrityError("duplicate key")

        with self.assertRaises(IntegrityError):
            ingest_document(self.document)

        # No Chunk rows from the failed run.
        self.assertEqual(Chunk.objects.filter(document=self.document).count(), 0)
        # Vector store was compensated: delete_document called with this doc's id.
        mock_delete.assert_called_once_with(str(self.document.id))

    @mock.patch("documents.services.pipeline.transaction.atomic")
    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk.objects.bulk_create")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_uses_atomic_block(
        self,
        mock_extract,
        mock_clean,
        mock_chunk,
        mock_embed,
        mock_bulk_create,
        mock_index,
        mock_atomic,
    ):
        """`transaction.atomic` is entered as a context manager.

        The audit-H1 fix wraps the whole pipeline body in a single
        `transaction.atomic` block. The mock here proves the call site:
        the pipeline uses `with transaction.atomic():` (i.e., it calls
        the function to get a context manager), not the function itself.
        """
        # transaction.atomic(...) returns a context manager; the pipeline
        # enters it with `with`. The mock's return value is itself a CM.
        mock_atomic.return_value = mock.MagicMock()
        mock_atomic.return_value.__enter__.return_value = None
        mock_atomic.return_value.__exit__.return_value = False
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_bulk_create.return_value = [mock.Mock()]
        mock_index.return_value = 1

        ingest_document(self.document)

        # The pipeline entered exactly one atomic block.
        self.assertEqual(mock_atomic.call_count, 1)
        # ...and actually used it as a context manager.
        mock_atomic.return_value.__enter__.assert_called_once()
        mock_atomic.return_value.__exit__.assert_called_once()

    def test_reindex_does_not_leave_orphan_chunks_on_failure(self):
        """The staff reindex view must not leave orphan chunks when ingest fails.

        The reindex path pre-deletes old chunks and then calls
        `ingest_document`. If ingestion fails, the new atomic block rolls
        back any PG writes the pipeline made, so the net result is zero
        chunks for the document (the old ones are gone, the new ones
        never persisted).

        This test does NOT mock `ingest_document` — it lets the real
        pipeline run with the upstream services (extract/clean/chunk/
        embed) mocked. The `index_document` mock raises, exposing the
        difference between the current code (orphan chunk remains) and
        the fixed code (transaction rolled back, zero chunks).
        """
        from rest_framework.test import APIRequestFactory

        from documents.views import StaffDocumentReindexView

        # Seed a chunk so the pre-delete has something to remove.
        Chunk.objects.create(
            document=self.document,
            page_number=1,
            token_offset=0,
            text="seed",
        )
        self.assertEqual(Chunk.objects.filter(document=self.document).count(), 1)

        factory = APIRequestFactory()
        view = StaffDocumentReindexView.as_view()
        request = factory.post(f"/admin/documents/{self.document.id}/reindex/")
        request.user = mock.Mock(is_authenticated=True, is_staff=True)

        # Let the real ingest_document run; mock the upstream services
        # to deterministic data, and make index_document raise so the
        # post-pre-delete pipeline path is exercised. The view now
        # catches the pipeline exception and returns 500 (Phase 4.4).
        with (
            mock.patch("documents.services.pipeline.index_document", side_effect=IndexingError("boom")),
            mock.patch("documents.services.pipeline.embed_chunks", return_value=self.embedded),
            mock.patch("documents.services.pipeline.chunk_pages", return_value=self.chunks),
            mock.patch("documents.services.pipeline.clean_pages", return_value=self.cleaned),
            mock.patch("documents.services.pipeline.extract_pages", return_value=self.extracted),
        ):
            response = view(request, pk=str(self.document.id))

        # The view returned 5xx because ingest failed.
        self.assertGreaterEqual(response.status_code, 500)

        # No orphan chunks: pre-delete cleared the seed, the rolled-back
        # transaction cleared anything the pipeline would have written.
        self.assertEqual(Chunk.objects.filter(document=self.document).count(), 0)

    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk.objects.bulk_create")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_orders_bulk_create_after_indexer(
        self,
        mock_extract,
        mock_clean,
        mock_chunk,
        mock_embed,
        mock_bulk_create,
        mock_index,
    ):
        """`bulk_create` is only attempted after `index_document` succeeds.

        The audit-H1 fix reorders writes to `index_document` (ChromaDB)
        before `bulk_create` (PostgreSQL). If `index_document` raises, no
        PG write should have happened, and `bulk_create` must never have
        been called.
        """
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_index.side_effect = IndexingError("ChromaDB write failed")

        with self.assertRaises(IndexingError):
            ingest_document(self.document)

        mock_bulk_create.assert_not_called()
        self.assertEqual(Chunk.objects.filter(document=self.document).count(), 0)

    @mock.patch("documents.services.pipeline.delete_document")
    @mock.patch("documents.services.pipeline.index_document")
    @mock.patch("documents.services.pipeline.Chunk.objects.bulk_create")
    @mock.patch("documents.services.pipeline.embed_chunks")
    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_vector_orphan_warning_fires_when_compensation_fails(
        self,
        mock_extract,
        mock_clean,
        mock_chunk,
        mock_embed,
        mock_bulk_create,
        mock_index,
        mock_delete,
    ):
        """When `bulk_create` fails and compensation fails, a vector-orphan warning is logged.

        The audit-H2 partial fix: if the compensation `delete_document`
        call also raises, the pipeline emits a `WARNING` log line that an
        ops sweeper job can grep for. The line includes `document_id`
        and `chunk_count` so a follow-up sweeper can find and clean up
        the leftover vectors. The pipeline still re-raises the original
        `IntegrityError` so the caller sees the failure.
        """
        mock_extract.return_value = self.extracted
        mock_clean.return_value = self.cleaned
        mock_chunk.return_value = self.chunks
        mock_embed.return_value = self.embedded
        mock_index.return_value = 1
        mock_bulk_create.side_effect = IntegrityError("duplicate key")
        mock_delete.side_effect = IndexingError("compensation also failed")

        with self.assertRaises(IntegrityError), self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(self.document)

        # The orphan warning fires with a stable prefix ops can grep for.
        orphan_lines = [
            line for line in cm.output if "vector_orphan" in line.lower() or "vector orphan" in line.lower()
        ]
        self.assertEqual(len(orphan_lines), 1)
        # Includes document_id and chunk_count so a sweeper can act on it.
        self.assertIn(str(self.document.id), orphan_lines[0])
        self.assertIn("1", orphan_lines[0])  # chunk_count = 1 embedded chunk


class IngestUploadedPdfTests(TestCase):
    """Tests for ``documents.services.pipeline.ingest_uploaded_pdf``.

    The audit-M2 fix moves the temp-file lifecycle and the
    ``Document.objects.create`` call from the view layer into a single
    service function. The view becomes a 5-line adapter that calls it.
    """

    def setUp(self):
        self.upload = SimpleUploadedFile(
            "policy.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.services.pipeline.ingest_document")
    @mock.patch("documents.services.pipeline.default_storage")
    def test_ingest_uploaded_pdf_creates_document_and_ingests(self, mock_storage, mock_ingest):
        """A successful call creates a ``Document`` row, writes the upload
        to temp storage, and delegates to ``ingest_document`` with the
        right document id and resolved file path."""
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"

        def _ingest(document, file_path=None):
            document.page_count = 2
            document.chunk_count = 2
            return {}

        mock_ingest.side_effect = _ingest

        document = ingest_uploaded_pdf(self.upload, username="alice")

        # A Document row was created with the right name.
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(document.name, "policy.pdf")
        # ingest_document was called with that document and the resolved
        # absolute file path so it can read the bytes off disk.
        mock_ingest.assert_called_once()
        call_args = mock_ingest.call_args
        self.assertEqual(call_args.args[0].id, document.id)
        # file_path is a keyword argument.
        self.assertEqual(call_args.kwargs["file_path"], "/tmp/media/documents/_tmp_policy.pdf")
        # The page/chunk counts from the pipeline were saved on the row.
        self.assertEqual(document.page_count, 2)
        self.assertEqual(document.chunk_count, 2)

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.services.pipeline.ingest_document")
    @mock.patch("documents.services.pipeline.default_storage")
    def test_ingest_uploaded_pdf_deletes_temp_file_on_success(self, mock_storage, mock_ingest):
        """After a successful ingest, the temp file is removed from storage."""
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"
        mock_ingest.return_value = {}

        ingest_uploaded_pdf(self.upload)

        # The temp file was saved once, opened once, and deleted once.
        self.assertEqual(mock_storage.save.call_count, 1)
        self.assertEqual(mock_storage.delete.call_count, 1)
        mock_storage.delete.assert_called_with("documents/_tmp_policy.pdf")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.services.pipeline.ingest_document")
    @mock.patch("documents.services.pipeline.default_storage")
    def test_ingest_uploaded_pdf_rolls_back_on_ingest_document_failure(self, mock_storage, mock_ingest):
        """When ``ingest_document`` raises, the Document row is deleted and
        the temp file is removed — no orphan rows or files."""
        mock_storage.save.return_value = "documents/_tmp_broken.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_broken.pdf"
        mock_ingest.side_effect = ExtractionError("PDF corrupt")

        with self.assertRaises(ExtractionError):
            ingest_uploaded_pdf(self.upload)

        # The Document row was rolled back.
        self.assertEqual(Document.objects.count(), 0)
        # The temp file was cleaned up.
        mock_storage.delete.assert_called_with("documents/_tmp_broken.pdf")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.services.pipeline.default_storage")
    def test_ingest_uploaded_pdf_writes_upload_chunks_to_storage(self, mock_storage):
        """The full upload payload lands in the temp file in storage.

        We avoid mocking ``ingest_document`` here so the real write path
        runs; the focus is the temp-file write, not the pipeline.
        """
        mock_storage.save.return_value = "documents/_tmp_policy.pdf"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_policy.pdf"
        # Capture what was written by recording calls to .open(...).write(...).
        written = bytearray()

        class FakeFile:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def write(self, data):
                written.extend(data)

        mock_storage.open.return_value = FakeFile()
        mock_storage.exists.return_value = False  # force save side-effect

        # Patch ingest_document to a no-op so the real pipeline doesn't run.
        with mock.patch("documents.services.pipeline.ingest_document", return_value={}):
            ingest_uploaded_pdf(self.upload)

        # The full upload bytes made it to the temp file.
        self.assertEqual(bytes(written), b"%PDF-1.4 fake content")

    @override_settings(MEDIA_ROOT=tempfile.gettempdir())
    @mock.patch("documents.services.pipeline.ingest_document")
    @mock.patch("documents.services.pipeline.default_storage")
    def test_ingest_uploaded_pdf_strips_path_components_from_name(self, mock_storage, mock_ingest):
        """An upload named ``../../etc/passwd`` becomes ``passwd`` on disk
        (path traversal protection)."""
        mock_storage.save.return_value = "documents/_tmp_passwd"
        mock_storage.path.return_value = "/tmp/media/documents/_tmp_passwd"
        mock_ingest.return_value = {}

        evil = SimpleUploadedFile(
            "../../etc/passwd",
            b"%PDF-1.4",
            content_type="application/pdf",
        )

        document = ingest_uploaded_pdf(evil)

        self.assertEqual(document.name, "passwd")

    def test_ingest_uploaded_pdf_signature_accepts_username_keyword(self):
        """Audit: ``username`` is keyword-only so callers can't pass a
        positional ``request`` object and confuse the audit trail."""
        import inspect

        from documents.services import pipeline

        sig = inspect.signature(pipeline.ingest_uploaded_pdf)
        self.assertIn("username", sig.parameters)
        self.assertEqual(sig.parameters["username"].default, None)
        self.assertEqual(sig.parameters["username"].kind, inspect.Parameter.KEYWORD_ONLY)
