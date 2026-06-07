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
        (with a streaming ``answer_stream`` and citations) or
        ``"no_information"`` (no stream, empty citations).
    """
    if top_k is None:
        top_k = settings.RETRIEVAL_TOP_K

    chunks = retrieve_chunks(question, document_id=document_id, top_k=top_k)
    prompt = build_prompt(question, chunks, similarity_threshold=threshold)

    if prompt is None:
        return QueryResult(kind="no_information")

    citations = build_citations(chunks)
    return QueryResult(
        kind="answer",
        answer_stream=safe_stream(generate_response(prompt)),
        citations=citations,
    )
