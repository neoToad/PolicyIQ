import logging
import time
from pathlib import PurePath

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from documents.models import Chunk, Document
from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks
from documents.services.extractor import clean_pages, extract_pages
from documents.services.indexer import delete_document, index_document

logger = logging.getLogger("documents.pipeline")


def ingest_uploaded_pdf(upload: UploadedFile, *, username: str | None = None) -> Document:
    """Take an uploaded file and run the full ingestion pipeline end-to-end.

    **Audit M2 fix:** This is the canonical "user uploaded a PDF" entry
    point. The view layer used to do five things in one block — validate,
    save-to-temp, create-row, run-pipeline, cleanup-on-failure — tangled
    with the lower-level ``ingest_document`` call. This service owns the
    whole lifecycle so the view becomes a 5-line adapter and a future
    bulk-import management command can reuse the same path.

    The function:

    1. Strips directory components from the upload name (path-traversal
       protection) and logs the receipt.
    2. Writes the upload bytes to ``default_storage`` under a temp
       filename.
    3. Creates a ``Document`` row pointing at the temp file.
    4. Calls :func:`ingest_document` with the resolved filesystem path.
    5. On success, deletes the temp file. On failure, deletes the
       ``Document`` row and the temp file (no orphan rows or files).

    Args:
        upload: A Django ``UploadedFile`` (or any object with ``.name``,
            ``.chunks()``). Required.
        username: Optional username for the audit-trail log line.

    Returns:
        The newly-created :class:`documents.models.Document` row with
        ``page_count`` and ``chunk_count`` populated.

    Raises:
        Any exception from :func:`ingest_document` (extraction,
        chunking, embedding, indexing failures). The Document row and
        the temp file are cleaned up before the exception propagates.
    """
    safe_name = PurePath(upload.name).name
    size_mb = (upload.size or 0) / (1024 * 1024)
    logger.info(
        "Received upload %r (%.2f MB) from user=%s",
        safe_name,
        size_mb,
        username or "anonymous",
    )

    temp_path = default_storage.save(f"documents/_tmp_{safe_name}", ContentFile(b""))

    try:
        with default_storage.open(temp_path, "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)
    except Exception:
        if default_storage.exists(temp_path):
            default_storage.delete(temp_path)
        raise

    full_path = default_storage.path(temp_path)
    logger.info("Wrote %r to %s", safe_name, temp_path)

    document = Document.objects.create(
        name=safe_name,
        file=temp_path,
        page_count=0,
        chunk_count=0,
    )

    t0 = time.monotonic()  # TODO: shared stage timer
    try:
        ingest_document(document, file_path=full_path)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "Ingestion failed for %r after %.2fs: %s: %s",
            safe_name,
            elapsed,
            type(exc).__name__,
            exc,
        )
        document.delete()
        if default_storage.exists(temp_path):
            default_storage.delete(temp_path)
        raise
    elapsed = time.monotonic() - t0
    logger.info(
        "Dispatched ingestion for %r (document_id=%s) in %.2fs",
        safe_name,
        document.id,
        elapsed,
    )

    # Clean up the temp file — the pipeline wrote a real copy to disk
    # for ingestion but the canonical file lives at ``document.file``.
    if default_storage.exists(temp_path):
        default_storage.delete(temp_path)

    return document


def ingest_document(document, file_path: str | None = None) -> dict:
    """Run the full ingestion pipeline on a document's file.

    Extracts, cleans, chunks, embeds, and indexes the document. Updates the
    Document record with page_count and chunk_count, creates Chunk records,
    and indexes embeddings in ChromaDB.

    **Atomicity (audit H1):** The whole body runs inside
    ``transaction.atomic()``. Writes are ordered ``index_document``
    (ChromaDB) **before** ``Chunk.objects.bulk_create`` (PostgreSQL) so a
    PostgreSQL write failure can be compensated by deleting the just-written
    vectors. If ``bulk_create`` raises, the pipeline calls
    ``delete_document(document_id)`` to keep the two stores in sync.

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
        with transaction.atomic():
            t0 = time.monotonic()  # TODO: shared stage timer
            pages = extract_pages(path)
            extract_s = time.monotonic() - t0
            logger.info("Extracted %d pages from %s in %.2fs", len(pages), document.name, extract_s)

            t0 = time.monotonic()  # TODO: shared stage timer
            cleaned_pages = clean_pages(pages)
            chunks = chunk_pages(cleaned_pages)
            chunk_s = time.monotonic() - t0
            logger.info("Created %d chunks for %s in %.2fs", len(chunks), document.name, chunk_s)

            t0 = time.monotonic()  # TODO: shared stage timer
            embedded_chunks = embed_chunks(chunks)
            embed_s = time.monotonic() - t0
            logger.info("Embedded %d chunks for %s in %.2fs", len(embedded_chunks), document.name, embed_s)

            document.page_count = len(pages)
            document.chunk_count = len(embedded_chunks)
            document.save()

            # Index FIRST so a bulk_create failure can be compensated by
            # deleting the just-written vectors. If index_document raises
            # here, the transaction rolls back document.save() and no
            # Chunk rows have been written yet, so no PG compensation
            # is needed.
            t0 = time.monotonic()  # TODO: shared stage timer
            index_document(str(document.id), embedded_chunks, document_name=document.name)
            index_s = time.monotonic() - t0

            try:
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
            except Exception:
                # PostgreSQL write failed after ChromaDB write succeeded.
                # Compensate the vector store so we don't leave orphan
                # embeddings with no corresponding Chunk row. The outer
                # transaction.atomic() will roll back the failed PG write
                # (and the document.save() above) automatically.
                logger.warning(
                    "Bulk create of %d chunks failed for %s (document_id=%s); compensating vector store",
                    len(embedded_chunks),
                    document.name,
                    document.id,
                )
                try:
                    delete_document(str(document.id))
                except Exception as comp_exc:
                    # Surface a clear "vector orphan" warning so an ops
                    # sweeper job can find and clean up the leftover
                    # vectors. The PG transaction will still roll back.
                    logger.warning(
                        "Vector orphan: failed to compensate %d vectors for document_id=%s after PG write failure: %s",
                        len(embedded_chunks),
                        document.id,
                        type(comp_exc).__name__,
                    )
                raise

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
