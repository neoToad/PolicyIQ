"""PDF text extraction and per-page cleanup.

Phase 0.3 owns the fitz-boundary; Phase 5.11 (audit M13) ensures the
extractor raises :class:`documents.exceptions.ExtractionError` instead
of leaking fitz's :class:`FileNotFoundError` / :class:`ValueError` /
``fitz.FileDataError`` shapes into the pipeline so the ``isinstance``
ladder in ``ingest_document`` can map the stage cleanly.
"""

import logging
import re
import time
from collections import Counter

import fitz

from documents.exceptions import ExtractionError

logger = logging.getLogger("documents.extractor")


def extract_pages(pdf_path: str) -> list[dict]:
    """Extract raw text from each page of a PDF.

    Args:
        pdf_path: Absolute path to the PDF file.

    Returns:
        A list of dicts with keys ``page_number`` and ``raw_text``.

    Raises:
        ExtractionError: If the file is missing, unreadable, or not a
            valid PDF. The original fitz/builtin exception is chained
            via ``from`` for diagnostics.
    """
    t0 = time.monotonic()  # TODO: shared stage timer
    try:
        # TODO: stream get_text() for very large PDFs. (audit L15) The
        # list-comprehension reads every page into memory at once; for
        # very large PDFs (e.g. 5k+ pages) this can OOM the worker.
        # Switch to a generator + per-page flush once we know the
        # real-world upper bound on upload size.
        with fitz.open(pdf_path) as doc:
            pages = [
                {"page_number": page_number, "raw_text": page.get_text()}
                for page_number, page in enumerate(doc, start=1)
            ]
    except FileNotFoundError as exc:
        elapsed = time.monotonic() - t0
        logger.error("Failed to extract pages from %s after %.2fs: FileNotFoundError", pdf_path, elapsed)
        raise ExtractionError(f"PDF file not found: {pdf_path}") from exc
    except (fitz.FileDataError, fitz.EmptyFileError, ValueError) as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "Failed to extract pages from %s after %.2fs: %s",
            pdf_path,
            elapsed,
            type(exc).__name__,
        )
        raise ExtractionError(f"Invalid or corrupted PDF: {pdf_path}") from exc
    elapsed = time.monotonic() - t0
    logger.info("Extracted %d pages from %s in %.2fs", len(pages), pdf_path, elapsed)
    return pages


PAGE_ARTIFACT_PATTERN = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)


def clean_pages(pages: list[dict]) -> list[dict]:
    """Remove headers, footers, page artifacts, and rejoin broken lines.

    The first pass builds a frequency counter for each line across all
    pages; the second pass filters out lines that appear on 3+ pages
    (assumed headers/footers) and rejoins mid-sentence line breaks.
    """
    # TODO: fuse with single-pass counter. (audit L16) The current two-pass
    # shape (count, then filter) reads every page twice. For small docs
    # this is fine; for very large libraries it's a measurable hotspot.
    # Combine the counter update with the filter step once we have a
    # representative doc-size distribution.
    line_counts: Counter[str] = Counter()
    page_lines: list[list[str]] = []

    for page in pages:
        lines = page.get("raw_text", "").splitlines()
        page_lines.append(lines)
        line_counts.update(line.strip() for line in lines if line.strip())

    cleaned_pages: list[dict] = []
    repeated_lines = {line for line, count in line_counts.items() if count >= 3}

    for page, lines in zip(pages, page_lines, strict=False):
        filtered = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in repeated_lines:
                continue
            if stripped.isdigit() or PAGE_ARTIFACT_PATTERN.match(stripped):
                continue
            filtered.append(stripped)

        rejoined = _rejoin_mid_sentence_lines(filtered)
        cleaned_text = "\n".join(rejoined).strip()
        cleaned_pages.append({**page, "cleaned_text": cleaned_text})

    return cleaned_pages


def _rejoin_mid_sentence_lines(lines: list[str]) -> list[str]:
    if not lines:
        return []

    result = [lines[0]]
    punctuation = {".", "!", "?", ":", ";"}

    for current in lines[1:]:
        previous = result[-1]
        if previous and previous[-1] not in punctuation and current[:1].islower():
            result[-1] = f"{previous} {current}"
        else:
            result.append(current)

    return result
