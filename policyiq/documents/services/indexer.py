import functools
import logging
import time
from pathlib import Path

import chromadb
from django.conf import settings

logger = logging.getLogger("documents.indexer")


def _get_persist_dir() -> str:
    persist_dir = getattr(settings, "CHROMA_PERSIST_DIR", None)
    if not persist_dir:
        persist_dir = str(Path(settings.BASE_DIR) / "chroma")
    return persist_dir


@functools.lru_cache(maxsize=4)
def get_chroma_client(path: str | None = None) -> chromadb.PersistentClient:
    """Return a lazily-created singleton PersistentClient instance.

    The path is part of the cache key (audit L5) so an
    ``override_settings(CHROMA_PERSIST_DIR=...)`` test sees a new
    client rather than the singleton from a previous call. Callers
    that don't pass ``path`` get the default
    ``settings.CHROMA_PERSIST_DIR`` (or ``<BASE_DIR>/chroma`` if
    unset).
    """
    return chromadb.PersistentClient(path=path or _get_persist_dir())


def get_collection(collection_name: str = "policyiq") -> chromadb.Collection:
    """Get or create a ChromaDB collection by name."""
    return get_chroma_client().get_or_create_collection(name=collection_name)


def index_document(document_id: str, chunks: list[dict], document_name: str = "") -> int:
    """Index chunk embeddings and metadata into ChromaDB.

    Args:
        document_id: UUID of the document being indexed.
        chunks: List of chunks with ``embedding``, ``text``, ``page_number``, and ``token_offset``.
        document_name: Human-readable name stored in metadata for retrieval.

    Returns:
        The number of chunks indexed.
    """
    t0 = time.monotonic()  # TODO: shared stage timer
    try:
        collection = get_collection()
        ids = [f"{document_id}:{chunk['token_offset']}" for chunk in chunks]
        embeddings = [chunk["embedding"] for chunk in chunks]
        documents = [chunk["text"] for chunk in chunks]
        metadatas = [
            {
                "document_id": document_id,
                "document_name": document_name,
                "page_number": chunk["page_number"],
                "token_offset": chunk["token_offset"],
            }
            for chunk in chunks
        ]

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "Failed to index %d vectors for document_id=%s after %.2fs: %s",
            len(chunks),
            document_id,
            elapsed,
            type(exc).__name__,
        )
        raise
    elapsed = time.monotonic() - t0
    logger.info(
        "Indexed %d vectors in collection for document_id=%s in %.2fs",
        len(chunks),
        document_id,
        elapsed,
    )
    return len(chunks)


def delete_document(document_id: str) -> None:
    """Delete all chunks belonging to a document from ChromaDB."""
    collection = get_collection()
    collection.delete(where={"document_id": document_id})
