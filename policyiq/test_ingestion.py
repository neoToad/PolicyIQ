from pathlib import Path
from statistics import mean

from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks
from documents.services.extractor import clean_pages, extract_pages

# Configure this before running.
PDF_PATH = Path(r"C:\Users\colin\PycharmProjects\PolicyIQ\2601.00008v1.pdf")
EXPECTED_EMBEDDING_DIM = 768
CHUNK_PREVIEW_CHARS = 200


def summarize_step(step_name: str, pages: list[dict], chunks: list[dict]) -> None:
    page_count = len(pages)
    chunk_count = len(chunks)
    avg_chunk_len = mean(len(chunk.get("text", "")) for chunk in chunks) if chunks else 0.0
    first_chunk_preview = (
        chunks[0].get("text", "")[:CHUNK_PREVIEW_CHARS].replace("\n", " ")
        if chunks
        else "N/A"
    )

    print(f"\n[{step_name}]")
    print(f"page_count={page_count}")
    print(f"chunk_count={chunk_count}")
    print(f"average_chunk_length={avg_chunk_len:.2f}")
    print(f"first_chunk_preview={first_chunk_preview}")


def validate_embeddings(chunks: list[dict], expected_dim: int) -> None:
    if not chunks:
        raise RuntimeError("No chunks to validate embeddings.")

    bad_indexes: list[int] = []
    for idx, chunk in enumerate(chunks):
        embedding = chunk.get("embedding")
        if embedding is None:
            bad_indexes.append(idx)
            continue
        if not isinstance(embedding, list) or len(embedding) != expected_dim:
            bad_indexes.append(idx)

    if bad_indexes:
        sample = ", ".join(str(i) for i in bad_indexes[:10])
        raise RuntimeError(
            f"Embedding validation failed for {len(bad_indexes)} chunk(s). "
            f"Example chunk indexes: {sample}"
        )

    print(
        f"\n[embedding_validation]\n"
        f"all_embeddings_non_null=True\n"
        f"expected_dimension={expected_dim}\n"
        f"validated_chunks={len(chunks)}"
    )


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found at: {PDF_PATH}")

    print(f"Running ingestion pipeline for: {PDF_PATH}")

    pages = extract_pages(str(PDF_PATH))
    summarize_step("extract_pages", pages, [])

    cleaned_pages = clean_pages(pages)
    summarize_step("clean_pages", cleaned_pages, [])

    chunks = chunk_pages(cleaned_pages)
    summarize_step("chunk_pages", cleaned_pages, chunks)

    embedded_chunks = embed_chunks(chunks)
    summarize_step("embed_chunks", cleaned_pages, embedded_chunks)

    validate_embeddings(embedded_chunks, EXPECTED_EMBEDDING_DIM)

    print("\nPipeline validation complete.")


if __name__ == "__main__":
    main()
