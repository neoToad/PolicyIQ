import logging

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

    Args:
        document: The Document instance to ingest.
        file_path: Optional override path. Defaults to document.file.path.

    Returns:
        A dict with keys: pages, cleaned_pages, chunks, embedded_chunks.
    """
    path = file_path or document.file.path
    logger.info("Starting ingestion for document %s (%s)", document.id, document.name)

    pages = extract_pages(path)
    logger.info("Extracted %d pages from %s", len(pages), document.name)

    cleaned_pages = clean_pages(pages)
    chunks = chunk_pages(cleaned_pages)
    logger.info("Created %d chunks for %s", len(chunks), document.name)

    embedded_chunks = embed_chunks(chunks)

    document.page_count = len(pages)
    document.chunk_count = len(embedded_chunks)
    document.save()

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
    logger.info("Ingestion complete for %s (%d pages, %d chunks)", document.name, len(pages), len(embedded_chunks))

    return {
        "pages": pages,
        "cleaned_pages": cleaned_pages,
        "chunks": chunks,
        "embedded_chunks": embedded_chunks,
    }
