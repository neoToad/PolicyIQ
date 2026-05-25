from unittest import mock

import fitz
from django.contrib import admin
from django.test import SimpleTestCase

from documents.models import Chunk, Document
from documents.services.extractor import clean_pages, extract_pages


class ExtractPagesTests(SimpleTestCase):
    @mock.patch("documents.services.extractor.fitz.open")
    def test_extract_pages_returns_raw_text_per_page(self, mock_open):
        mock_page_1 = mock.Mock()
        mock_page_1.get_text.return_value = "first page raw text"
        mock_page_2 = mock.Mock()
        mock_page_2.get_text.return_value = "second page raw text"

        mock_doc = mock.MagicMock()
        mock_doc.__iter__.return_value = iter([mock_page_1, mock_page_2])
        mock_open.return_value.__enter__.return_value = mock_doc

        result = extract_pages("fake.pdf")

        self.assertEqual(
            result,
            [
                {"page_number": 1, "raw_text": "first page raw text"},
                {"page_number": 2, "raw_text": "second page raw text"},
            ],
        )
        mock_open.assert_called_once_with("fake.pdf")

    @mock.patch("documents.services.extractor.fitz.open")
    def test_extract_pages_raises_file_not_found_for_missing_pdf(self, mock_open):
        mock_open.side_effect = FileNotFoundError

        with self.assertRaises(FileNotFoundError):
            extract_pages("missing.pdf")

    @mock.patch("documents.services.extractor.fitz.open")
    def test_extract_pages_raises_value_error_for_corrupted_pdf(self, mock_open):
        mock_open.side_effect = fitz.FileDataError("cannot open broken document")

        with self.assertRaises(ValueError):
            extract_pages("corrupted.pdf")


class CleanPagesTests(SimpleTestCase):
    def test_clean_pages_removes_repeated_headers_and_footers(self):
        pages = [
            {
                "page_number": 1,
                "raw_text": "Policy Manual\nUnique A\nConfidential Footer",
            },
            {
                "page_number": 2,
                "raw_text": "Policy Manual\nUnique B\nConfidential Footer",
            },
            {
                "page_number": 3,
                "raw_text": "Policy Manual\nUnique C\nConfidential Footer",
            },
        ]

        result = clean_pages(pages)

        self.assertEqual(result[0]["cleaned_text"], "Unique A")
        self.assertEqual(result[1]["cleaned_text"], "Unique B")
        self.assertEqual(result[2]["cleaned_text"], "Unique C")

    def test_clean_pages_removes_page_number_artifacts(self):
        pages = [
            {
                "page_number": 1,
                "raw_text": "Page 1 of 3\nCoverage details\n1",
            },
            {
                "page_number": 2,
                "raw_text": "Page 2 of 3\nMore policy text\n2",
            },
        ]

        result = clean_pages(pages)

        self.assertEqual(result[0]["cleaned_text"], "Coverage details")
        self.assertEqual(result[1]["cleaned_text"], "More policy text")

    def test_clean_pages_rejoins_mid_sentence_line_breaks(self):
        pages = [
            {
                "page_number": 1,
                "raw_text": "Coverage is provided when patient meets\nall clinical criteria.\nStandalone line.",
            }
        ]

        result = clean_pages(pages)

        self.assertEqual(
            result[0]["cleaned_text"],
            "Coverage is provided when patient meets all clinical criteria.\nStandalone line.",
        )

    def test_clean_pages_adds_cleaned_text_and_preserves_raw_text(self):
        pages = [{"page_number": 1, "raw_text": "  Policy text here  \n"}]

        result = clean_pages(pages)

        self.assertEqual(result[0]["raw_text"], "  Policy text here  \n")
        self.assertEqual(result[0]["cleaned_text"], "Policy text here")


class AdminRegistrationTests(SimpleTestCase):
    def test_document_models_are_registered_in_admin(self):
        import documents.admin  # noqa: F401

        self.assertIn(Document, admin.site._registry)
        self.assertIn(Chunk, admin.site._registry)
