import json
import time

import requests

OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
OLLAMA_GENERATE_MODEL = "llama3.2"
RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1


def generate_response(prompt: str):
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
        "Ollama generation service is unreachable after 3 attempts at "
        "http://localhost:11434/api/generate."
    ) from last_error


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
