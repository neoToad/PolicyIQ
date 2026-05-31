"""End-to-end integration tests that exercise real external services.

These tests require a running Ollama instance at localhost:11434 with the
``nomic-embed-text`` and ``llama3.2`` models pulled. They are tagged with
``integration`` so they are skipped during fast unit-test runs.

Run only integration tests::

    python manage.py test --tag integration

Exclude integration tests (default fast run)::

    python manage.py test --exclude-tag integration

The manual smoke-test scripts ``test_ingestion.py`` and ``test_query.py`` differ
from these tests in that:

- Smoke scripts are standalone CLI utilities with hard-coded configuration.
- Integration tests use Django ``TestCase``, temporary databases, and
  automatic cleanup, making them repeatable in CI.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz  # PyMuPDF
import requests
from django.conf import settings
from django.core.files import File
from django.test import TestCase, override_settings, tag

from documents.models import Document
from documents.services.indexer import delete_document
from documents.services.pipeline import ingest_document
from queries.services.retriever import retrieve_chunks


def _ollama_available() -> bool:
    """Return True if Ollama responds on the expected local endpoint."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except (requests.RequestException, OSError):
        return False


@tag("integration")
@unittest.skipUnless(_ollama_available(), "Ollama not available at localhost:11434")
@override_settings(
    MEDIA_ROOT=Path(tempfile.gettempdir()) / "policyiq_test_media",
    CHROMA_PERSIST_DIR=Path(tempfile.gettempdir()) / "policyiq_test_chroma",
)
@mock.patch.dict(os.environ, {"LLM_BACKEND": "ollama"})
class IngestionQueryRoundTripTests(TestCase):
    """Verify the full pipeline from PDF ingestion to RAG query retrieval."""

    def setUp(self):
        self.media_path = Path(settings.MEDIA_ROOT)
        self.media_path.mkdir(parents=True, exist_ok=True)
        self.chroma_path = Path(settings.CHROMA_PERSIST_DIR)
        self.chroma_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        for document in Document.objects.all():
            delete_document(str(document.id))
            document.delete()
        shutil.rmtree(self.media_path, ignore_errors=True)
        shutil.rmtree(self.chroma_path, ignore_errors=True)

    def _create_test_pdf(self, text: str, filename: str = "test_policy.pdf") -> Path:
        """Generate a minimal single-page PDF with the given text."""
        pdf_path = self.media_path / filename
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), text)
        doc.save(str(pdf_path))
        doc.close()
        return pdf_path

    def test_ingest_and_retrieve_round_trip(self):
        """Ingest a PDF and retrieve relevant chunks via vector search."""
        pdf_path = self._create_test_pdf(
            "Insurance coverage includes dental and vision benefits for all employees."
        )

        with open(pdf_path, "rb") as f:
            document = Document.objects.create(
                name="test_policy.pdf",
                file=File(f, name="test_policy.pdf"),
                page_count=0,
                chunk_count=0,
            )

        ingest_document(document)

        document.refresh_from_db()
        self.assertGreater(document.page_count, 0)
        self.assertGreater(document.chunk_count, 0)

        chunks = retrieve_chunks(
            "What benefits are included in insurance coverage?",
            document_id=str(document.id),
            top_k=5,
        )

        self.assertGreater(len(chunks), 0)
        combined_text = " ".join(chunk["text"].lower() for chunk in chunks)
        self.assertIn("dental", combined_text)
        self.assertIn("vision", combined_text)
