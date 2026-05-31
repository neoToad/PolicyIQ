import time

import requests

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
OLLAMA_EMBED_MODEL = "nomic-embed-text"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Embed each chunk's text using the configured embedding model.

    Returns the chunks with an additional ``embedding`` key containing
    the normalized vector.
    """
    embedded_chunks = []
    for chunk in chunks:
        embedding = _embed_text(chunk["text"])
        embedded_chunks.append({**chunk, "embedding": embedding})
    return embedded_chunks


def embed_query(query: str) -> list[float]:
    """Embed a user query so it can be used for vector search."""
    return _embed_text(query)


def _embed_text(text: str) -> list[float]:
    """Call the Ollama embedding endpoint with retries and L2-normalize the result."""
    payload = {"model": OLLAMA_EMBED_MODEL, "prompt": text}
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(OLLAMA_EMBED_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            if not isinstance(embedding, list):
                raise ValueError("Ollama response missing 'embedding' list.")
            # nomic-embed-text via Ollama does not guarantee unit vectors.
            # Normalize so ChromaDB l2 distances map to cosine similarity.
            norm = sum(x * x for x in embedding) ** 0.5
            if norm == 0:
                raise ValueError("Ollama returned a zero-length embedding.")
            return [x / norm for x in embedding]
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        "Ollama embedding service is unreachable after 3 attempts at http://localhost:11434/api/embeddings."
    ) from last_error
