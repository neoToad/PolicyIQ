from pathlib import Path
from typing import BinaryIO

import fitz


def extract_pages(pdf_path: str) -> list[dict]:
    try:
        with fitz.open(pdf_path) as doc:
            return [
                {"page_number": page_number, "raw_text": page.get_text()}
                for page_number, page in enumerate(doc, start=1)
            ]
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"PDF file not found: {pdf_path}") from exc
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise ValueError(f"Invalid or corrupted PDF: {pdf_path}") from exc
