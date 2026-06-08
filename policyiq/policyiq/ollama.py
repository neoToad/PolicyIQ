"""Shared HTTP client for the local Ollama server.

Phase 0.2 consolidates the duplicated ``requests.post`` + retry/backoff
pattern that lived in ``embedder._embed_batch_with_retry`` /
``embedder._embed_single_with_retry`` and ``generator._ollama_token_stream``
(audit H4). Every Ollama-bound service should funnel through this
module so the retry policy, error-envelope detection, and health probe
behave identically.

Public API
----------
- :class:`OllamaError` — base exception (also aliased as ``EmbeddingError`` /
  ``GenerationError`` for backward compatibility with the call sites that
  used those names).
- :func:`post_json` — POST a JSON payload with shared retry, return parsed
  JSON or raise :class:`OllamaError`.
- :func:`post_stream` — streaming variant for ``/api/generate`` that yields
  decoded JSON lines.
- :func:`embed_texts` / :func:`embed_query` — thin wrappers over
  ``post_json("/api/embed", ...)``.
- :func:`generate` — picks ``post_stream`` (stream=True) or
  ``post_json("/api/generate", ...)`` (stream=False).
- :func:`ping` — ``GET /api/tags`` health probe (audit L20).
- :func:`is_error_envelope` — detects ``{"error": "..."}`` 200 responses
  (audit M8).
- :func:`validate_embedding_vector` — input-shape guard (audit M8).

The retry count and delay come from ``settings.EMBEDDING_RETRY_ATTEMPTS``
and ``settings.EMBEDDING_RETRY_DELAY`` (renamed historically because
the same knobs were first added for embeddings; they apply to every
Ollama call now).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import requests
from django.conf import settings

from policyiq.llm_config import (
    get_ollama_embed_url,
    get_ollama_generate_url,
    get_ollama_tags_url,
)

logger = logging.getLogger("policyiq.ollama")


class OllamaError(Exception):
    """Base exception for any Ollama client failure (transport, HTTP, envelope).

    ``EmbeddingError`` and ``GenerationError`` are kept as aliases so the
    existing exception imports in the call sites continue to work.
    """


# Back-compat aliases for the exception names the call sites already use.
EmbeddingError = OllamaError
GenerationError = OllamaError


# ---------------------------------------------------------------------------
# Error-shape helpers
# ---------------------------------------------------------------------------


def is_error_envelope(data: dict) -> bool:
    """Return True if the response body is Ollama's 200-but-error shape.

    Ollama returns HTTP 200 with ``{"error": "..."}`` for problems like a
    missing model name; the caller must detect this and treat it as a
    failure (audit M8).
    """
    return isinstance(data, dict) and bool(data.get("error"))


def validate_embedding_vector(vec: Any) -> list[float]:
    """Validate and return an embedding vector as a list of floats.

    Raises :class:`OllamaError` (or the underlying ``TypeError`` /
    ``ValueError``) when ``vec`` is not a non-empty iterable of numbers.
    Strings, ``None``, and other shapes are rejected.
    """
    if not isinstance(vec, list):
        raise OllamaError(f"Embedding vector must be a list, got {type(vec).__name__}.")
    if not vec:
        raise OllamaError("Embedding vector is empty.")
    try:
        return [float(x) for x in vec]
    except (TypeError, ValueError) as exc:
        raise OllamaError(f"Embedding vector contains non-numeric elements: {exc}") from exc


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def _retry_settings() -> tuple[int, float]:
    """Read (max_attempts, delay_seconds) from settings at call time."""
    return settings.EMBEDDING_RETRY_ATTEMPTS, settings.EMBEDDING_RETRY_DELAY


def post_json(path: str, payload: dict, *, timeout: float) -> dict:
    """POST a JSON payload to Ollama and return the parsed response.

    Retries on any :class:`requests.RequestException` (connection errors,
    timeouts, chunked-encoding errors) up to ``EMBEDDING_RETRY_ATTEMPTS``
    times with ``EMBEDDING_RETRY_DELAY`` seconds between attempts. Raises
    :class:`OllamaError` for transport failure, HTTP error status, or
    an ``{"error": "..."}`` envelope (audit H4, M8, M10).
    """
    max_attempts, delay = _retry_settings()
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(path, json=payload, timeout=timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Ollama POST %s attempt %d/%d failed: %s", path, attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(delay)
            continue

        try:
            data = response.json()
        except ValueError as exc:
            last_exc = exc
            logger.warning("Ollama POST %s returned non-JSON body: %s", path, exc)
            if attempt < max_attempts:
                time.sleep(delay)
            continue

        if is_error_envelope(data):
            # 200 + error envelope is non-retryable — Ollama told us the
            # request is malformed (e.g. unknown model). Don't burn retries.
            raise OllamaError(f"Ollama POST {path} returned error envelope: {data['error']}")

        return data

    # All retries exhausted.
    logger.error(
        "Ollama POST %s unreachable after %d attempts: %s",
        path,
        max_attempts,
        last_exc,
    )
    raise OllamaError(f"Ollama POST {path} unreachable after {max_attempts} attempts: {last_exc}") from last_exc


def post_stream(path: str, payload: dict, *, timeout: float) -> Iterator[dict]:
    """POST a JSON payload to Ollama and yield decoded JSON lines.

    Used for ``/api/generate`` with ``stream: true`` in the payload. Each
    non-blank line is parsed as JSON and yielded. A mid-stream disconnect
    (``ChunkedEncodingError``) surfaces as :class:`OllamaError` (audit H7,
    M10). An ``{"error": "..."}`` envelope line raises :class:`OllamaError`.
    """
    try:
        response = requests.post(path, json=payload, stream=True, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Ollama POST {path} could not be opened: {exc}") from exc

    try:
        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError as exc:
                raise OllamaError(f"Ollama stream returned non-JSON line: {exc}") from exc
            if is_error_envelope(data):
                raise OllamaError(f"Ollama stream returned error envelope: {data['error']}")
            yield data
    except requests.exceptions.ChunkedEncodingError as exc:
        raise OllamaError(f"Ollama stream disconnected mid-response: {exc}") from exc


# ---------------------------------------------------------------------------
# Thin wrappers
# ---------------------------------------------------------------------------


def embed_texts(model: str, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via ``POST /api/embed``.

    Returns a list of validated float vectors, one per input text, in the
    same order. Raises :class:`OllamaError` on any failure.
    """
    url = get_ollama_embed_url()
    payload = {"model": model, "input": texts}
    data = post_json(url, payload, timeout=settings.EMBEDDING_BATCH_TIMEOUT)
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise OllamaError(
            f"Ollama /api/embed returned malformed 'embeddings' "
            f"(expected list of {len(texts)} vectors, got {type(embeddings).__name__})."
        )
    return [validate_embedding_vector(vec) for vec in embeddings]


def embed_query(model: str, text: str) -> list[float]:
    """Embed a single query string via ``POST /api/embed``."""
    url = get_ollama_embed_url()
    payload = {"model": model, "input": text}
    data = post_json(url, payload, timeout=settings.EMBEDDING_QUERY_TIMEOUT)
    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        raise OllamaError("Ollama /api/embed response missing 'embeddings' list.")
    return validate_embedding_vector(embeddings[0])


def generate(model: str, prompt: str, *, stream: bool) -> Iterator[str] | str:
    """Generate an LLM response, choosing streaming or non-streaming mode.

    When ``stream=True`` returns an iterator that yields response tokens
    (the ``response`` field of each streamed JSON object). When
    ``stream=False`` returns the complete response as a single string.
    """
    url = get_ollama_generate_url()
    payload = {"model": model, "prompt": prompt, "stream": stream}
    if stream:
        return (chunk.get("response", "") for chunk in post_stream(url, payload, timeout=settings.GENERATION_TIMEOUT))
    data = post_json(url, payload, timeout=settings.GENERATION_TIMEOUT)
    return data.get("response", "")


def ping() -> bool:
    """Return True if ``GET /api/tags`` returns HTTP 200, False otherwise.

    Used by the health check to report Ollama reachability (audit L20).
    Catches the broadest set of failure modes (transport + HTTP) so a
    a single boolean answer can be returned without leaking exceptions
    to the health endpoint.
    """
    url = get_ollama_tags_url()
    try:
        response = requests.get(url, timeout=2.0)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - exercised via health check tests
        logger.warning("Ollama ping failed: %s", exc)
        return False
    return True
