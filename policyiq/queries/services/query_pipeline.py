"""Cross-view pipeline: retrieve → prompt → stream.

Phase 3.1 collapses the body of :class:`queries.views.AskPageView` and
:class:`queries.views.QueryAPIView` into a single ``run_query`` function
that returns a :class:`QueryResult`. The two views become thin adapters
that translate the result into HTML or JSON.

The pipeline:

1. Calls :func:`queries.services.retriever.retrieve_chunks` with the
   ``top_k`` setting (unless overridden).
2. Calls :func:`queries.services.generator.build_prompt` to assemble
   the LLM prompt; ``build_prompt`` returns ``None`` if no chunk clears
   the threshold.
3. Calls :func:`queries.services.generator.generate_response` to stream
   the answer, wrapped in :func:`queries.services.generator.safe_stream`
   so mid-stream :class:`GenerationError` becomes a sentinel marker
   (audit H6) instead of a truncated response.

Audit H7: when the LLM backend is unreachable, ``run_query`` raises
:class:`policyiq.ollama.OllamaError` (or its :class:`EmbeddingError`
alias) so the view can return a 502 Bad Gateway. We do this by calling
``generate_response`` once eagerly — if it raises before yielding a
token, the exception propagates and the view handles it. If it raises
mid-stream, :func:`safe_stream` catches it and yields the sentinel.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from django.conf import settings

from queries.services.citations import build_citations
from queries.services.generator import build_prompt, generate_response, safe_stream
from queries.services.retriever import retrieve_chunks

QueryKind = Literal["answer", "no_information"]


@dataclass
class QueryResult:
    """The outcome of a single ``run_query`` call.

    Attributes:
        kind: ``"answer"`` if a streamed LLM answer is available, or
            ``"no_information"`` if the retrieved chunks were empty or
            below the similarity threshold.
        answer_stream: An iterator yielding the LLM's tokens, wrapped in
            :func:`safe_stream` so mid-stream errors become a sentinel
            marker. ``None`` when ``kind == "no_information"``.
        citations: Citation dicts built from the retrieved chunks; empty
            for the no-information case.
        duration_s: Wall-clock duration of the retrieve + prompt-build
            step in seconds. The streaming duration is captured by the
            generator itself, not by this pipeline.
    """

    kind: QueryKind
    answer_stream: Iterator[str] | None = None
    citations: list[dict] = field(default_factory=list)
    duration_s: float = 0.0


def run_query(
    question: str,
    document_id: str | None,
    *,
    top_k: int | None,
    threshold: float,
) -> QueryResult:
    """Run the retrieve → prompt → stream pipeline for a single question.

    Args:
        question: The user's query.
        document_id: Optional UUID restricting the search to a single
            document. ``None`` searches the whole library.
        top_k: Maximum number of chunks to retrieve. ``None`` falls back
            to ``settings.RETRIEVAL_TOP_K``.
        threshold: Minimum similarity score for a chunk to count as
            relevant. Forwarded to :func:`build_prompt`.

    Returns:
        A :class:`QueryResult` with ``kind`` of either ``"answer"``
        (with a streaming ``answer_stream` and citations) or
        ``"no_information"`` (no stream, empty citations).

    Raises:
        policyiq.ollama.OllamaError: If the LLM/embedding backend is
            unreachable or returns an error envelope (audit H7). The
            view layer maps this to a 502 Bad Gateway.
    """
    if top_k is None:
        top_k = settings.RETRIEVAL_TOP_K

    chunks = retrieve_chunks(question, document_id=document_id, top_k=top_k)
    prompt = build_prompt(question, chunks, similarity_threshold=threshold)

    if prompt is None:
        return QueryResult(kind="no_information")

    citations = build_citations(chunks)
    # Audit H7: pre-flight ``generate_response`` so a backend-down
    # failure surfaces BEFORE we hand a stream to the view. The function
    # is a generator, so calling ``next()`` here is what actually runs
    # the first HTTP request. Any OllamaError raised at this point
    # propagates to the view's 502 handler. Once we have a first token
    # the stream is handed to safe_stream for the mid-stream sentinel
    # behaviour (audit H6).
    gen = generate_response(prompt)
    try:
        first_token = next(gen)
    except StopIteration:
        first_token = ""
    return QueryResult(
        kind="answer",
        answer_stream=safe_stream(_chain_first_token(first_token, gen)),
        citations=citations,
    )


def _chain_first_token(first: str, rest: Iterator[str]) -> Iterator[str]:
    """Yield ``first`` then everything from ``rest``.

    Used to reassemble a generator after we pulled the first token for
    the pre-flight OllamaError check.
    """
    yield first
    yield from rest
