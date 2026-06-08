import logging
import time

from django.conf import settings
from documents.services.embedder import embed_query
from documents.services.indexer import get_collection

from queries.constants import MAX_CHUNKS_IN_LOG, MAX_QUESTION_LOG_CHARS

logger = logging.getLogger("queries.retriever")


def _truncate_for_log(text: str, max_chars: int = MAX_QUESTION_LOG_CHARS) -> str:
    """Truncate a string with a '...' suffix when it exceeds ``max_chars``."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def retrieve_chunks(query: str, document_id: str | None = None, top_k: int | None = None) -> list[dict]:
    """Retrieve the most semantically similar chunks for a query.

    Embeds the query, queries ChromaDB, and converts squared L2 distances
    into cosine similarity scores. Emits INFO log lines on entry, embed,
    retrieve, and exit so operators can answer "did the LLM see the right
    chunks?" without re-running the request.

    Args:
        query: The user's question.
        document_id: Optional UUID to restrict search to a single document.
        top_k: Maximum number of chunks to return. Defaults to
            ``settings.RETRIEVAL_TOP_K`` when None.

    Returns:
        Chunks sorted by descending similarity score.
    """
    if top_k is None:
        top_k = settings.RETRIEVAL_TOP_K

    safe_q = _truncate_for_log(query)
    logger.info(
        "Retrieving up to %d chunks for question=%r document_id=%s",
        top_k,
        safe_q,
        document_id or "<all>",
    )

    t0 = time.monotonic()  # TODO: shared stage timer
    query_embedding = embed_query(query)
    embed_s = time.monotonic() - t0
    logger.info("Embedded query (%d chars) in %.2fs", len(query), embed_s)

    t0 = time.monotonic()  # TODO: shared stage timer
    collection = get_collection()
    where_filter = {"document_id": document_id} if document_id else None
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter,
    )
    retrieve_s = time.monotonic() - t0

    chunks = []
    ids = results.get("ids", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i in range(len(ids)):
        # ChromaDB default l2 space returns squared L2 distance.
        # nomic-embed-text produces unit vectors, so:
        #   cosine_similarity = 1 - (squared_l2_distance / 2)
        raw_distance = distances[i]
        similarity = max(0.0, round(1 - raw_distance / 2, 4))
        chunks.append(
            {
                "text": documents[i],
                "page_number": metadatas[i].get("page_number"),
                "document_id": metadatas[i].get("document_id"),
                "document_name": metadatas[i].get("document_name", "Unknown"),
                "similarity_score": similarity,
            }
        )

    chunks.sort(key=lambda c: c["similarity_score"], reverse=True)

    if chunks:
        scores = [c["similarity_score"] for c in chunks]
        # The diagnostic "Chunks: [...]" line lists docname, page, and score
        # for each chunk — the operator's answer to "did the LLM see the
        # right chunks?". Capped at MAX_CHUNKS_IN_LOG to bound log volume.
        listed = chunks[:MAX_CHUNKS_IN_LOG]
        chunk_summary = ", ".join(
            f"{c['document_name']} p.{c['page_number']} ({c['similarity_score']:.3f})" for c in listed
        )
        if len(chunks) > MAX_CHUNKS_IN_LOG:
            chunk_summary += f" +{len(chunks) - MAX_CHUNKS_IN_LOG} more"
        logger.info("Chunks: [%s]", chunk_summary)
        logger.info(
            "Retrieved %d chunks from %d documents (top=%.3f, range %.3f-%.3f) in %.2fs",
            len(chunks),
            len({c["document_id"] for c in chunks}),
            max(scores),
            min(scores),
            max(scores),
            retrieve_s,
        )
    else:
        logger.info("Retrieved 0 chunks in %.2fs", retrieve_s)

    return chunks
