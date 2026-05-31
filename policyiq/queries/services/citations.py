def build_citations(chunks: list[dict]) -> list[dict]:
    """Build citation dicts from retrieved chunks.

    Each citation includes the document name, page number, similarity score,
    and a text preview capped at 150 characters.
    """
    return [
        {
            "document_name": chunk.get("document_name", "Unknown"),
            "page_number": chunk.get("page_number"),
            "similarity_score": chunk["similarity_score"],
            "text_preview": chunk["text"][:150],
        }
        for chunk in chunks
    ]
