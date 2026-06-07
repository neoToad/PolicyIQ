"""Prompt building + backend dispatch for LLM text generation.

Phase 0.2d: the Ollama HTTP/retry/envelope work lives in
:mod:`policyiq.ollama`; this module just selects a backend, delegates
to ``ollama.generate`` (or the Anthropic SDK), and reports token /
timing metrics. The same retry policy is now shared with the embedder
and the health probe.
"""

import logging
import time
from collections.abc import Iterator

from django.conf import settings

from policyiq import ollama
from queries.exceptions import GenerationError, QueryError

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

logger = logging.getLogger("queries.generator")


def safe_stream(iterator):
    """Wrap a token iterator so mid-stream :class:`GenerationError` is surfaced.

    **Audit H6 fix:** if the underlying generator raises after some tokens
    have already been yielded, Django's ``StreamingHttpResponse`` would
    truncate the response silently and HTMX would display a partial
    answer with no error indicator. This wrapper catches
    :class:`GenerationError` (and any :class:`QueryError` subclass), logs
    the failure, and yields a structured sentinel marker
    (``<!-- error: <message> -->``) so the client can render a
    user-visible "stream interrupted" indicator.

    Other exception types propagate unchanged — only LLM-stream failures
    are caught; an unexpected ``ValueError`` from the inner generator
    still bubbles up to surface the bug.

    Args:
        iterator: A generator that yields string tokens.

    Yields:
        Each token from ``iterator`` unchanged, followed by at most one
        ``<!-- error: ... -->`` sentinel on a caught
        :class:`GenerationError`.
    """
    try:
        yield from iterator
    except QueryError as exc:
        logger.error("safe_stream caught %s mid-stream: %s", type(exc).__name__, exc)
        yield f"<!-- error: {exc} -->"


def _generate_anthropic(prompt: str) -> Iterator[str]:
    if anthropic is None:
        raise GenerationError("Anthropic SDK is not installed. Install it with: pip install anthropic")
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
    if not api_key:
        raise GenerationError("ANTHROPIC_API_KEY is not configured. Set it in your environment or Django settings.")

    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=settings.ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    text = event.delta.text
                    if text:
                        yield text
    except Exception as exc:
        raise GenerationError(
            "Anthropic generation service failed. Check your API key and network connection."
        ) from exc


def generate_response(prompt: str) -> Iterator[str]:
    """Stream LLM tokens for the given prompt using the configured backend.

    Emits INFO log lines for: backend selection (with model + prompt size),
    time-to-first-token (the latency signal that matters for streaming UX),
    and total tokens + duration on completion.

    Yields:
        Individual text tokens from the LLM response stream.

    Raises:
        ValueError: If ``LLM_BACKEND`` is not ``ollama`` or ``anthropic``.
        GenerationError: If the chosen backend is unreachable or misconfigured.
    """
    backend = getattr(settings, "LLM_BACKEND", "ollama")
    model_name = settings.OLLAMA_GENERATE_MODEL if backend == "ollama" else settings.ANTHROPIC_MODEL
    logger.info(
        "Streaming from %s (model=%s, prompt=%d chars)",
        backend,
        model_name,
        len(prompt),
    )

    if backend == "ollama":
        gen = _ollama_token_stream(prompt)
    elif backend == "anthropic":
        gen = _generate_anthropic(prompt)
    else:
        raise ValueError(f"Unsupported LLM_BACKEND: {backend}")

    t_start = time.monotonic()
    t_first_token: float | None = None
    token_count = 0
    for token in gen:
        if t_first_token is None:
            t_first_token = time.monotonic() - t_start
            logger.info("First token in %.2fs", t_first_token)
        token_count += 1
        yield token

    logger.info(
        "Generated %d tokens in %.2fs (first-token=%.2fs, backend=%s)",
        token_count,
        time.monotonic() - t_start,
        t_first_token if t_first_token is not None else 0.0,
        backend,
    )


def _ollama_token_stream(prompt: str) -> Iterator[str]:
    """Yield tokens from the shared ollama client's stream.

    The client already pulls the ``response`` field out of each streamed
    JSON line and yields plain strings, so this is a thin pass-through
    that just maps :class:`OllamaError` to :class:`GenerationError` so
    the view layer's error path stays uniform.
    """
    try:
        yield from ollama.generate(settings.OLLAMA_GENERATE_MODEL, prompt, stream=True)
    except ollama.OllamaError as exc:
        raise GenerationError(f"Ollama generation service is unreachable: {exc}") from exc


def build_prompt(question: str, chunks: list[dict], similarity_threshold: float | None = None) -> str | None:
    """Assemble a RAG prompt from retrieved chunks.

    Returns ``None`` when no chunk meets the similarity threshold, signalling
    the view layer to return a "no relevant information" response.

    Args:
        question: The user's query.
        chunks: Retrieved chunks with ``text``, ``page_number``, ``document_name``,
            and ``similarity_score``.
        similarity_threshold: Minimum score required for any chunk to form a prompt.
            Defaults to ``settings.SIMILARITY_THRESHOLD`` when None.

    Returns:
        A formatted prompt string, or ``None`` if relevance is too low.
    """
    if similarity_threshold is None:
        similarity_threshold = settings.SIMILARITY_THRESHOLD

    if not chunks:
        return None
    if max(c["similarity_score"] for c in chunks) < similarity_threshold:
        return None

    lines = [
        "You are a helpful assistant that answers questions using only the provided context.",
        "Answer only from the provided context. Do not speculate or add information not present in the context.",
        "If the context does not contain enough information to answer the question, say so clearly.",
        "Cite the source document and page number for each piece of information you use.",
        "",
        "Context:",
    ]
    for chunk in chunks:
        doc_name = chunk.get("document_name", "Unknown")
        page = chunk.get("page_number", "?")
        text = chunk["text"]
        lines.append(f"[{doc_name} - page {page}]\n{text}")

    lines.extend(["", f"Question: {question}", ""])
    return "\n".join(lines)
