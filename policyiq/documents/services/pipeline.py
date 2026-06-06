import logging
import time

from documents.models import Chunk
from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks
from documents.services.extractor import clean_pages, extract_pages
from documents.services.indexer import index_document

logger = logging.getLogger("documents.pipeline")


def ingest_document(document, file_path: str | None = None) -> dict:
    """Run the full ingestion pipeline on a document's file.

    Extracts, cleans, chunks, embeds, and indexes the document. Updates the
    Document record with page_count and chunk_count, creates Chunk records,
    and indexes embeddings in ChromaDB.

    Emits INFO log lines for: ingest start, each stage, ingest failure
    (with stage name + exception type), and ingest completion. Failures
    are re-raised to the caller (the view layer handles user-facing error
    presentation).

    Args:
        document: The Document instance to ingest.
        file_path: Optional override path. Defaults to document.file.path.

    Returns:
        A dict with keys: pages, cleaned_pages, chunks, embedded_chunks.
    """
    path = file_path or document.file.path
    t_start = time.monotonic()
    logger.info("Starting ingestion for document %s (%s)", document.id, document.name)

    try:
        t0 = time.monotonic()
        pages = extract_pages(path)
        extract_s = time.monotonic() - t0
        logger.info("Extracted %d pages from %s in %.2fs", len(pages), document.name, extract_s)

        t0 = time.monotonic()
        cleaned_pages = clean_pages(pages)
        chunks = chunk_pages(cleaned_pages)
        chunk_s = time.monotonic() - t0
        logger.info("Created %d chunks for %s in %.2fs", len(chunks), document.name, chunk_s)

        t0 = time.monotonic()
        embedded_chunks = embed_chunks(chunks)
        embed_s = time.monotonic() - t0
        logger.info("Embedded %d chunks for %s in %.2fs", len(embedded_chunks), document.name, embed_s)

        document.page_count = len(pages)
        document.chunk_count = len(embedded_chunks)
        document.save()

        t0 = time.monotonic()
        Chunk.objects.bulk_create(
            [
                Chunk(
                    document=document,
                    page_number=chunk["page_number"],
                    token_offset=chunk["token_offset"],
                    text=chunk["text"],
                )
                for chunk in embedded_chunks
            ]
        )
        index_document(str(document.id), embedded_chunks, document_name=document.name)
        index_s = time.monotonic() - t0
        logger.info(
            "Indexed %d chunks in collection for %s in %.2fs",
            len(embedded_chunks),
            document.name,
            index_s,
        )

        total_s = time.monotonic() - t_start
        logger.info(
            "Ingestion complete for %s (%d pages, %d chunks) in %.2fs",
            document.name,
            len(pages),
            len(embedded_chunks),
            total_s,
        )

        return {
            "pages": pages,
            "cleaned_pages": cleaned_pages,
            "chunks": chunks,
            "embedded_chunks": embedded_chunks,
        }
    except Exception as exc:
        # Identify the stage from the exception's class. The pipeline catches
        # all exceptions and re-raises; the class name maps cleanly to the
        # stage that produced it for known DocumentError subtypes.
        elapsed = time.monotonic() - t_start
        stage = _STAGE_BY_EXCEPTION_NAME.get(type(exc).__name__, "unknown")
        logger.info(
            "Ingestion failed for %s at stage=%s after %.2fs: %s",
            document.name,
            stage,
            elapsed,
            type(exc).__name__,
        )
        raise


_STAGE_BY_EXCEPTION_NAME: dict[str, str] = {
    "ExtractionError": "extract",
    "ChunkingError": "chunk",
    "EmbeddingError": "embed",
    "IndexingError": "index",
}
