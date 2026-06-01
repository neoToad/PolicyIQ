import logging
import time

import requests

from documents.exceptions import EmbeddingError

logger = logging.getLogger("documents.embedder")

OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
OLLAMA_EMBED_MODEL = "nomic-embed-text"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1
DEFAULT_BATCH_SIZE = 32


def embed_chunks(chunks: list[dict], batch_size: int = DEFAULT_BATCH_SIZE) -> list[dict]:
    """Embed each chunk's text using the configured embedding model.

    Chunks are sent to Ollama in batches via the ``/api/embed`` endpoint,
    which accepts a list of inputs and returns a list of embeddings. This
    collapses N sequential HTTP calls into ``ceil(N / batch_size)`` calls,
    which is meaningfully faster for large documents.

    If a batch request fails, the function falls back to per-chunk sequential
    calls (one ``/api/embed`` request per chunk) so a partial outage of
    the batch endpoint does not block ingestion entirely.

    Returns the chunks with an additional ``embedding`` key containing
    the normalized vector.
    """
    if not chunks:
        return []

    embedded_chunks: list[dict] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c["text"] for c in batch]
        try:
            vectors = _embed_batch_with_retry(texts)
        except EmbeddingError as exc:
            logger.warning("Batch embedding failed (%s); falling back to per-chunk sequential calls.", exc)
            vectors = [_embed_single_with_retry(text) for text in texts]
        for chunk, vector in zip(batch, vectors, strict=True):
            embedded_chunks.append({**chunk, "embedding": vector})
    return embedded_chunks


def embed_query(query: str) -> list[float]:
    """Embed a user query so it can be used for vector search."""
    return _embed_single_with_retry(query)


def _embed_batch_with_retry(texts: list[str]) -> list[list[float]]:
    """Send a batch of texts to ``/api/embed`` with retry/backoff.

    Raises ``EmbeddingError`` if all retries fail.
    """
    payload = {"model": OLLAMA_EMBED_MODEL, "input": texts}
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                raise ValueError(
                    f"Ollama /api/embed returned malformed 'embeddings' "
                    f"(expected list of {len(texts)} vectors, got {type(embeddings).__name__})."
                )
            return [_normalize(vec) for vec in embeddings]
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning("Batch embedding attempt %d/%d failed: %s", attempt, RETRY_ATTEMPTS, exc)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error(
        "Ollama batch embedding service unreachable after %d attempts: %s",
        RETRY_ATTEMPTS,
        last_error,
    )
    raise EmbeddingError(
        f"Ollama batch embedding service is unreachable after {RETRY_ATTEMPTS} attempts at {OLLAMA_EMBED_URL}."
    ) from last_error


def _embed_single_with_retry(text: str) -> list[float]:
    """Send a single text to ``/api/embed`` (as a one-element list) with retry/backoff.

    Used for the single-query path (``embed_query``) and as the sequential
    fallback when ``_embed_batch_with_retry`` exhausts its retries.
    """
    payload = {"model": OLLAMA_EMBED_MODEL, "input": text}
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or not embeddings:
                raise ValueError("Ollama response missing 'embeddings' list.")
            return _normalize(embeddings[0])
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logger.warning("Embedding attempt %d/%d failed: %s", attempt, RETRY_ATTEMPTS, exc)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    logger.error("Ollama embedding service unreachable after %d attempts: %s", RETRY_ATTEMPTS, last_error)
    raise EmbeddingError(
        f"Ollama embedding service is unreachable after {RETRY_ATTEMPTS} attempts at {OLLAMA_EMBED_URL}."
    ) from last_error


def _normalize(embedding: list[float]) -> list[float]:
    """L2-normalize a single embedding vector.

    nomic-embed-text via Ollama does not guarantee unit vectors, so we
    normalize here so ChromaDB's L2 distances map cleanly to cosine similarity.
    Raises ``ValueError`` for a zero-length vector.
    """
    norm = sum(x * x for x in embedding) ** 0.5
    if norm == 0:
        raise ValueError("Ollama returned a zero-length embedding.")
    return [x / norm for x in embedding]
