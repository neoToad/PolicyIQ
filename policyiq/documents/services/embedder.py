"""Embedding service: turn text into normalized vectors via Ollama.

Phase 0.2c: this module no longer talks to ``requests`` directly — it
delegates to :mod:`policyiq.ollama` which owns the retry loop, HTTP
error wrapping, and 200-but-error envelope detection. The only thing
left here is shape normalization, batching, and the ``embed_chunks`` /
``embed_query`` public entry points.
"""

from __future__ import annotations

import logging

from django.conf import settings

from documents.exceptions import EmbeddingError
from policyiq import ollama

logger = logging.getLogger("documents.embedder")


def embed_chunks(chunks: list[dict], batch_size: int | None = None) -> list[dict]:
    """Embed each chunk's text using the configured embedding model.

    Chunks are sent to Ollama in batches via ``embed_texts``, which uses
    the ``/api/embed`` endpoint and accepts a list of inputs. This collapses
    N sequential HTTP calls into ``ceil(N / batch_size)`` calls, which is
    meaningfully faster for large documents.

    If a batch call fails (the underlying :class:`policyiq.ollama.OllamaError`
    bubbles up after the client's retries are exhausted), the function falls
    back to per-chunk sequential calls (one ``/api/embed`` request per chunk)
    so a partial outage of the batch endpoint does not block ingestion entirely.

    Returns the chunks with an additional ``embedding`` key containing
    the normalized vector.
    """
    if not chunks:
        return []

    if batch_size is None:
        batch_size = settings.EMBEDDING_BATCH_SIZE

    embedded_chunks: list[dict] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c["text"] for c in batch]
        try:
            vectors = ollama.embed_texts(settings.OLLAMA_EMBED_MODEL, texts)
        except ollama.OllamaError as exc:
            logger.warning("Batch embedding failed (%s); falling back to per-chunk sequential calls.", exc)
            try:
                vectors = [ollama.embed_query(settings.OLLAMA_EMBED_MODEL, text) for text in texts]
            except ollama.OllamaError as fallback_exc:
                logger.error("Ollama embedding service unreachable: %s", fallback_exc)
                raise EmbeddingError(f"Ollama embedding service is unreachable: {fallback_exc}") from fallback_exc
        for chunk, vector in zip(batch, vectors, strict=True):
            embedded_chunks.append({**chunk, "embedding": _normalize(vector)})
    return embedded_chunks


def embed_query(query: str) -> list[float]:
    """Embed a user query so it can be used for vector search.

    Returns the L2-normalized embedding vector.
    """
    try:
        vector = ollama.embed_query(settings.OLLAMA_EMBED_MODEL, query)
    except ollama.OllamaError as exc:
        raise EmbeddingError(f"Ollama embedding service is unreachable: {exc}") from exc
    return _normalize(vector)


def _normalize(embedding: list[float]) -> list[float]:
    """L2-normalize a single embedding vector.

    nomic-embed-text via Ollama does not guarantee unit vectors, so we
    normalize here so ChromaDB's L2 distances map cleanly to cosine similarity.
    Raises :class:`ValueError` for a zero-length vector.
    """
    norm = sum(x * x for x in embedding) ** 0.5
    if norm == 0:
        raise ValueError("Ollama returned a zero-length embedding.")
    return [x / norm for x in embedding]
