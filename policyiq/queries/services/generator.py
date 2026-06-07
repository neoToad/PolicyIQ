import json
import logging
import time
from collections.abc import Iterator

import requests
from django.conf import settings
from policyiq.llm_config import get_ollama_generate_url

from queries.exceptions import GenerationError

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

logger = logging.getLogger("queries.generator")


def _generate_ollama(prompt: str) -> Iterator[str]:
    url = get_ollama_generate_url()
    timeout = settings.GENERATION_TIMEOUT
    max_attempts = settings.EMBEDDING_RETRY_ATTEMPTS
    delay = settings.EMBEDDING_RETRY_DELAY
    payload = {"model": settings.OLLAMA_GENERATE_MODEL, "prompt": prompt, "stream": True}
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, json=payload, stream=True, timeout=timeout)
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                token = data.get("response", "")
                if token:
                    yield token
            return
        except (requests.RequestException, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning("Generation attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(delay)

    logger.error("Ollama generation service unreachable after %d attempts: %s", max_attempts, last_error)
    raise GenerationError(
        f"Ollama generation service is unreachable after {max_attempts} attempts at {url}."
    ) from last_error


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
        gen = _generate_ollama(prompt)
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
