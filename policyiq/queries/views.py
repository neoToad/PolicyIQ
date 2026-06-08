import json
import logging
import time

from django.conf import settings
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views import View
from documents.exceptions import EmbeddingError
from documents.models import Document
from documents.services.indexer import get_collection
from policyiq.ollama import OllamaError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from queries.serializers import CitationSerializer, QueryRequestSerializer
from queries.services import health
from queries.services.query_pipeline import run_query
from queries.services.retriever import MAX_QUESTION_LOG_CHARS
from queries.throttles import QueryAnonRateThrottle, QueryUserRateThrottle
from queries.exceptions import GenerationError

logger = logging.getLogger("queries.views")

# Audit H7: any failure to reach the LLM/embedding backend is treated as
# a downstream-failure (502 Bad Gateway) — the client cannot reasonably
# retry, and a 200 with a partial stream would mislead the user.
_DOWNSTREAM_ERRORS = (OllamaError, EmbeddingError, GenerationError)


def _top_k() -> int:
    """Read RETRIEVAL_TOP_K from settings at request time.

    Reads on each call (not at import) so ``override_settings`` works in
    tests and live ops tuning is honored.
    """
    return settings.RETRIEVAL_TOP_K


def _log_query_receipt(question: str, username: str, top_k: int) -> None:
    """Emit the 'Query received' line with the truncated question.

    Centralized so the HTML and API views produce an identical log line
    and the truncation is consistent across both paths.
    """
    safe_q = question[:MAX_QUESTION_LOG_CHARS] + "..." if len(question) > MAX_QUESTION_LOG_CHARS else question
    logger.info('Query received: "%s" (user=%s, top_k=%d)', safe_q, username, top_k)


def _ollama_down_error(exc: Exception) -> str:
    """Build a human-readable error message for the 502 path.

    Audit H7: when the LLM backend is unreachable, the client must see
    a clear message, not a stack trace. We surface the original message
    because operators find it useful; production deployment is expected
    to scrub it if needed.
    """
    return f"Ollama is unreachable: {exc}"


class AskPageView(View):
    """Render the ask form and stream LLM answers via HTMX."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the ask page with the question form and document selector."""
        documents = Document.objects.order_by("-uploaded_at")
        return render(request, "queries/ask.html", {"documents": documents})

    def post(self, request: HttpRequest) -> HttpResponse:
        """Retrieve relevant chunks and stream an LLM-generated answer."""
        question = request.POST.get("question", "").strip()
        document_id = request.POST.get("document_id") or None

        if not question:
            return HttpResponse(
                "<p style='color: #b91c1c;'>Please enter a question.</p>",
                status=400,
            )

        username = getattr(getattr(request, "user", None), "username", "anonymous")
        top_k = _top_k()
        _log_query_receipt(question, username, top_k)

        t0 = time.monotonic()
        try:
            result = run_query(question, document_id, top_k=top_k, threshold=settings.SIMILARITY_THRESHOLD)
        except _DOWNSTREAM_ERRORS as exc:
            logger.error(_ollama_down_error(exc))
            return HttpResponse(
                f"<div class='card' style='color: #b91c1c;'><p>Ollama is unreachable: {exc}</p></div>",
                status=502,
            )

        if result.kind == "no_information":
            elapsed = time.monotonic() - t0
            logger.info("Returned 'no relevant information' response in %.2fs", elapsed)
            return HttpResponse("<p>No relevant information found in the uploaded documents.</p>")

        def stream():
            yield '<div class="card"><p style="white-space: pre-wrap;">'
            yield from result.answer_stream
            yield "</p></div>"

        response = StreamingHttpResponse(stream(), content_type="text/html")
        response["X-Citations"] = json.dumps(result.citations)
        logger.info(
            "Streamed answer (citations=%d) in %.2fs",
            len(result.citations),
            time.monotonic() - t0,
        )
        return response


class QueryAPIView(APIView):
    """Authenticated API endpoint for querying documents with RAG."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [QueryAnonRateThrottle, QueryUserRateThrottle]

    def post(self, request: Request) -> Response:
        """Validate request, retrieve chunks, and stream an LLM answer with citations."""
        request_serializer = QueryRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        question = request_serializer.validated_data["question"]
        document_id = request_serializer.validated_data.get("document_id")
        if document_id is not None:
            document_id = str(document_id)

        username = getattr(getattr(request, "user", None), "username", "anonymous")
        top_k = _top_k()
        _log_query_receipt(question, username, top_k)

        t0 = time.monotonic()
        try:
            result = run_query(question, document_id, top_k=top_k, threshold=settings.SIMILARITY_THRESHOLD)
        except _DOWNSTREAM_ERRORS as exc:
            logger.error(_ollama_down_error(exc))
            return Response(
                {"error": _ollama_down_error(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if result.kind == "no_information":
            elapsed = time.monotonic() - t0
            logger.info("Returned 'no relevant information' response in %.2fs", elapsed)
            return Response(
                {"answer": "No relevant information found in the uploaded documents."},
                status=status.HTTP_200_OK,
            )

        citation_serializer = CitationSerializer(data=result.citations, many=True)
        citation_serializer.is_valid(raise_exception=True)

        def stream():
            yield from result.answer_stream

        response = StreamingHttpResponse(stream(), content_type="text/plain")
        response["X-Citations"] = json.dumps(citation_serializer.data)
        logger.info(
            "Streamed answer (citations=%d) in %.2fs",
            len(result.citations),
            time.monotonic() - t0,
        )
        return response


class HealthCheckAPIView(APIView):
    """Unauthenticated, unthrottled endpoint for dependency health checks."""

    authentication_classes = []
    permission_classes = []
    # Explicit (rather than implicit) so monitors can poll freely without
    # consuming any user/anon throttle budget.
    throttle_classes: list = []

    def get(self, request: Request) -> Response:
        """Check PostgreSQL, ChromaDB, and Ollama connectivity."""
        results = {
            "postgresql": health.check_postgresql(),
            "chromadb": health.check_chromadb(get_collection),
            "ollama": health.check_ollama(),
        }
        all_healthy = all(dep["status"] == "up" for dep in results.values())
        status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(
            {"status": "healthy" if all_healthy else "unhealthy", "dependencies": results},
            status=status_code,
        )
