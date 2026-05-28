def build_prompt(question: str, chunks: list[dict], similarity_threshold: float = 0.5) -> str | None:
    if not chunks:
        return None
    if max(c["similarity_score"] for c in chunks) < similarity_threshold:
        return None

    lines = [
        "You are a helpful assistant that answers questions using only the provided context.",
        "Answer only from the provided context. Do not speculate or add information not present in the context.",
        "If the context does not contain enough information to answer the question, say so clearly.",
        "Cite the source document and page number for each piece of information you use.",
        "",
        "Context:",
    ]
    for chunk in chunks:
        doc_name = chunk.get("document_name", "Unknown")
        page = chunk.get("page_number", "?")
        text = chunk["text"]
        lines.append(f"[{doc_name} - page {page}]\n{text}")

    lines.extend(["", f"Question: {question}", ""])
    return "\n".join(lines)
