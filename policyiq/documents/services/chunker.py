import tiktoken


def chunk_pages(pages: list[dict], chunk_size: int = 500, overlap: int = 50) -> list[dict]:
    """Create sliding token chunks where each next chunk starts `overlap` tokens before the prior one ends."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

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

    return chunks
