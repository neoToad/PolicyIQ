import functools
from pathlib import Path

import chromadb
from django.conf import settings


def _get_persist_dir() -> str:
    persist_dir = getattr(settings, "CHROMA_PERSIST_DIR", None)
    if not persist_dir:
        persist_dir = str(Path(settings.BASE_DIR) / "chroma")
    return persist_dir


@functools.lru_cache(maxsize=1)
def get_chroma_client() -> chromadb.PersistentClient:
    """Return a lazily-created singleton PersistentClient instance."""
    return chromadb.PersistentClient(path=_get_persist_dir())


def get_collection(collection_name: str = "policyiq"):
    return get_chroma_client().get_or_create_collection(name=collection_name)


def index_document(document_id: str, chunks: list[dict], document_name: str = "") -> int:
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
    return len(chunks)


def delete_document(document_id: str):
    collection = get_collection()
    collection.delete(where={"document_id": document_id})
