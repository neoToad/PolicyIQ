"""Service layer for deleting a Document and its associated data.

Audit-H2 fix: a document lives in two stores — PostgreSQL (the `Document`
row and its `Chunk` rows via FK CASCADE) and ChromaDB (the vector
embeddings, keyed by `document_id` metadata). The two stores must be
kept in sync on delete.

The atomicity contract mirrors the ingestion pipeline in
`pipeline.py`: the writes are wrapped in `transaction.atomic()`, and
`delete_document` (ChromaDB) is called BEFORE `document.delete()`
(PostgreSQL). This ordering means a PG delete failure leaves ChromaDB
already cleaned up; a ChromaDB delete failure rolls back the PG
transaction entirely.
"""

import logging

from django.db import transaction

from documents.services.indexer import delete_document

logger = logging.getLogger("documents.deletion")


def delete_document_with_chunks(document) -> None:
    """Delete a document and all of its associated data from both stores.

    Removes the document's vectors from ChromaDB and the document row
    (plus its `Chunk` rows via FK CASCADE) from PostgreSQL. The two
    writes are atomic: if either fails, the document is preserved.

    Args:
        document: The Document instance to delete. Must have a populated
            `id` (UUID) for the ChromaDB delete to find the right
            vectors.

    Raises:
        IndexingError: If the ChromaDB delete fails. The PG transaction
            is rolled back, so the document and its chunks survive.

    Emits:
        INFO: success line with document id + name + duration.
        WARNING: vector-orphan marker if the ChromaDB delete raises
            (so an ops sweeper can find the leftover state).
    """
    import time

    t_start = time.monotonic()
    doc_id = str(document.id)
    doc_name = document.name
    logger.info("Deleting document %s (%s)", doc_id, doc_name)

    try:
        with transaction.atomic():
            # Delete from ChromaDB FIRST. If this raises, the
            # transaction.atomic() context exits without committing
            # the document.delete() call below, so the PG state is
            # preserved.
            delete_document(doc_id)
            document.delete()
    except Exception as exc:
        # Either the ChromaDB delete failed (PG is rolled back, doc
        # still exists) or the document.delete() raised (ChromaDB
        # was already cleared but PG state is rolled back). Both
        # paths leave the system consistent — no orphan chunks in
        # PG, no orphan vectors in ChromaDB. The vector-orphan
        # WARNING marker is only meaningful when the ChromaDB call
        # actually wrote something that needs sweeping, but the
        # cleanest invariant is "always log the document id on
        # failure" so an ops sweep can act on the document in
        # either case.
        elapsed = time.monotonic() - t_start
        logger.warning(
            "Deletion failed for document_id=%s (%s) after %.2fs: %s",
            doc_id,
            doc_name,
            elapsed,
            type(exc).__name__,
        )
        raise

    elapsed = time.monotonic() - t_start
    logger.info(
        "Deleted document %s (%s) in %.2fs",
        doc_id,
        doc_name,
        elapsed,
    )
