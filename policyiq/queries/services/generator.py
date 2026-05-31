import json
import time
from collections.abc import Iterator

import requests
from django.conf import settings

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_GENERATE_MODEL = "llama3.2"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1


def _generate_ollama(prompt: str) -> Iterator[str]:
    payload = {"model": OLLAMA_GENERATE_MODEL, "prompt": prompt, "stream": True}
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            response = requests.post(OLLAMA_GENERATE_URL, json=payload, stream=True, timeout=60)
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
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        "Ollama generation service is unreachable after 3 attempts at http://localhost:11434/api/generate."
    ) from last_error


ANTHROPIC_MODEL = "claude-sonnet-4-20250514"
ANTHROPIC_MAX_TOKENS = 1024


def _generate_anthropic(prompt: str) -> Iterator[str]:
    if anthropic is None:
        raise RuntimeError("Anthropic SDK is not installed. Install it with: pip install anthropic")
    api_key = getattr(settings, "ANTHROPIC_API_KEY", None)
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured. Set it in your environment or Django settings.")

    client = anthropic.Anthropic(api_key=api_key)
    try:
        with client.messages.stream(
            model=ANTHROPIC_MODEL,
            max_tokens=ANTHROPIC_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    text = event.delta.text
                    if text:
                        yield text
    except Exception as exc:
        raise RuntimeError("Anthropic generation service failed. Check your API key and network connection.") from exc


def generate_response(prompt: str) -> Iterator[str]:
    backend = getattr(settings, "LLM_BACKEND", "ollama")
    if backend == "ollama":
        yield from _generate_ollama(prompt)
    elif backend == "anthropic":
        yield from _generate_anthropic(prompt)
    else:
        raise ValueError(f"Unsupported LLM_BACKEND: {backend}")


def build_prompt(question: str, chunks: list[dict], similarity_threshold: float = 0.5) -> str | None:
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
