from unittest import mock

import fitz
from django.test import SimpleTestCase

from documents.services.extractor import extract_pages


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
