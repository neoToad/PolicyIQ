import re
from collections import Counter

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


PAGE_ARTIFACT_PATTERN = re.compile(r"^page\s+\d+\s+of\s+\d+$", re.IGNORECASE)


def clean_pages(pages: list[dict]) -> list[dict]:
    line_counts: Counter[str] = Counter()
    page_lines: list[list[str]] = []

    for page in pages:
        lines = page.get("raw_text", "").splitlines()
        page_lines.append(lines)
        line_counts.update(line.strip() for line in lines if line.strip())

    cleaned_pages: list[dict] = []
    repeated_lines = {line for line, count in line_counts.items() if count >= 3}

    for page, lines in zip(pages, page_lines):
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
