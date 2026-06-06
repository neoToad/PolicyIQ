"""Tests for the `documents.pipeline` logger.

The pipeline orchestrates extract → clean → chunk → embed → index. These
tests verify that the pipeline emits a complete stage-level narrative on
both success and failure, with timing on each stage and the exception type
when a stage fails.
"""

from unittest import mock

from django.test import SimpleTestCase

from documents.exceptions import ChunkingError, ExtractionError, IndexingError
from documents.services.pipeline import ingest_document


def _make_document_mock(name: str = "policy.pdf") -> mock.Mock:
    """Build a Document mock that supports the attributes ingest_document reads."""
    doc = mock.Mock()
    doc.id = "doc-123"
    doc.name = name
    doc.page_count = 0
    doc.chunk_count = 0
    doc.file = mock.Mock()
    doc.file.path = "/tmp/policy.pdf"
    return doc


class PipelineLoggingTests(SimpleTestCase):
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
        mock_extract.return_value = [{"page_number": 1, "raw_text": "a"}]
        mock_clean.return_value = [{"page_number": 1, "cleaned_text": "a"}]
        mock_chunk.return_value = [{"text": "a", "page_number": 1, "token_offset": 0}]
        mock_embed.return_value = [{"text": "a", "page_number": 1, "token_offset": 0, "embedding": [0.1]}]
        mock_index.return_value = 1
        doc = _make_document_mock()

        with self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(doc)

        completion_lines = [line for line in cm.output if "Ingestion complete" in line]
        self.assertEqual(len(completion_lines), 1)
        # The "Ingestion complete" line includes a duration ("in T.TTs").
        self.assertIn("in ", completion_lines[0])

    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_failure_at_extractor_stage(self, mock_extract):
        """When extract_pages raises, the pipeline logs the failure with stage + type."""
        mock_extract.side_effect = ExtractionError("PDF corrupt")
        doc = _make_document_mock("broken.pdf")

        with self.assertRaises(ExtractionError):
            with self.assertLogs("documents.pipeline", level="INFO") as cm:
                ingest_document(doc)

        failure_lines = [line for line in cm.output if "Ingestion failed" in line and "stage=extract" in line]
        self.assertEqual(len(failure_lines), 1)
        self.assertIn("ExtractionError", failure_lines[0])
        self.assertIn("broken.pdf", failure_lines[0])

    @mock.patch("documents.services.pipeline.chunk_pages")
    @mock.patch("documents.services.pipeline.clean_pages")
    @mock.patch("documents.services.pipeline.extract_pages")
    def test_pipeline_logs_failure_at_chunker_stage(self, mock_extract, mock_clean, mock_chunk):
        """When chunk_pages raises, the pipeline logs the failure with stage=chunk + type."""
        mock_extract.return_value = [{"page_number": 1, "raw_text": "a"}]
        mock_clean.return_value = [{"page_number": 1, "cleaned_text": "a"}]
        mock_chunk.side_effect = ChunkingError("chunk failed")
        doc = _make_document_mock("broken.pdf")

        with self.assertRaises(ChunkingError):
            with self.assertLogs("documents.pipeline", level="INFO") as cm:
                ingest_document(doc)

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
        mock_extract.return_value = [{"page_number": 1, "raw_text": "a"}]
        mock_clean.return_value = [{"page_number": 1, "cleaned_text": "a"}]
        mock_chunk.return_value = [{"text": "a", "page_number": 1, "token_offset": 0}]
        mock_embed.return_value = [{"text": "a", "page_number": 1, "token_offset": 0, "embedding": [0.1]}]
        mock_index.side_effect = IndexingError("ChromaDB write failed")
        doc = _make_document_mock("broken.pdf")

        with self.assertRaises(IndexingError):
            with self.assertLogs("documents.pipeline", level="INFO") as cm:
                ingest_document(doc)

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
        mock_extract.return_value = [{"page_number": 1, "raw_text": "a"}]
        mock_clean.return_value = [{"page_number": 1, "cleaned_text": "a"}]
        mock_chunk.return_value = [{"text": "a", "page_number": 1, "token_offset": 0}]
        mock_embed.return_value = [{"text": "a", "page_number": 1, "token_offset": 0, "embedding": [0.1]}]
        mock_index.return_value = 1
        doc = _make_document_mock("policy.pdf")

        with self.assertLogs("documents.pipeline", level="INFO") as cm:
            ingest_document(doc)

        start_lines = [line for line in cm.output if "Starting ingestion" in line]
        self.assertEqual(len(start_lines), 1)
        self.assertIn("doc-123", start_lines[0])
        self.assertIn("policy.pdf", start_lines[0])
