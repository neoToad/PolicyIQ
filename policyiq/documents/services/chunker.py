import logging
import time

import tiktoken
from django.conf import settings

logger = logging.getLogger("documents.chunker")


def chunk_pages(pages: list[dict], chunk_size: int | None = None, overlap: int | None = None) -> list[dict]:
    """Create sliding token chunks where each next chunk starts `overlap` tokens before the prior one ends.

    Args:
        pages: List of page dicts with ``page_number`` and ``cleaned_text``.
        chunk_size: Token count per chunk. Defaults to ``settings.CHUNK_SIZE``.
        overlap: Token count that adjacent chunks share. Defaults to
            ``settings.CHUNK_OVERLAP``.

    Returns:
        List of chunk dicts with ``text``, ``page_number``, and ``token_offset``.
    """
    if chunk_size is None:
        chunk_size = settings.CHUNK_SIZE
    if overlap is None:
        overlap = settings.CHUNK_OVERLAP

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    t0 = time.monotonic()
    encoding = tiktoken.get_encoding("cl100k_base")
    all_tokens = []
    token_page_numbers: list[int] = []

    for page in pages:
        page_number = page["page_number"]
        text = page.get("cleaned_text", "")
        page_tokens = encoding.encode(text)
        all_tokens.extend(page_tokens)
        token_page_numbers.extend([page_number] * len(page_tokens))

    if not all_tokens:
        logger.info("Created 0 chunks (no tokens) in %.2fs", time.monotonic() - t0)
        return []

    step = chunk_size - overlap
    chunks = []

    for start in range(0, len(all_tokens), step):
        end = min(start + chunk_size, len(all_tokens))
        chunk_tokens = all_tokens[start:end]
        chunks.append(
            {
                "text": encoding.decode(chunk_tokens),
                "page_number": token_page_numbers[start],
                "token_offset": start,
            }
        )
        if end == len(all_tokens):
            break

    elapsed = time.monotonic() - t0
    char_lens = [len(c["text"]) for c in chunks]
    avg_chars = sum(char_lens) // len(char_lens) if char_lens else 0
    min_chars = min(char_lens) if char_lens else 0
    max_chars = max(char_lens) if char_lens else 0
    logger.info(
        "Created %d chunks (avg %d chars, min %d, max %d) in %.2fs",
        len(chunks),
        avg_chars,
        min_chars,
        max_chars,
        elapsed,
    )

    return chunks
