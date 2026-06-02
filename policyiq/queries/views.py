import json

from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views import View
from documents.models import Document
from documents.services.indexer import get_collection
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from queries.serializers import CitationSerializer, QueryRequestSerializer
from queries.services import health
from queries.services.citations import build_citations
from queries.services.generator import build_prompt, generate_response
from queries.services.retriever import retrieve_chunks
from queries.throttles import QueryAnonRateThrottle, QueryUserRateThrottle


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

        chunks = retrieve_chunks(question, document_id=document_id, top_k=5)
        prompt = build_prompt(question, chunks, similarity_threshold=0.5)

        if prompt is None:
            return HttpResponse("<p>No relevant information found in the uploaded documents.</p>")

        citations = build_citations(chunks)

        def stream():
            yield '<div class="card"><p style="white-space: pre-wrap;">'
            yield from generate_response(prompt)
            yield "</p></div>"

        response = StreamingHttpResponse(stream(), content_type="text/html")
        response["X-Citations"] = json.dumps(citations)
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

        chunks = retrieve_chunks(question, document_id=document_id, top_k=5)
        prompt = build_prompt(question, chunks, similarity_threshold=0.5)

        if prompt is None:
            return Response(
                {"answer": "No relevant information found in the uploaded documents."},
                status=status.HTTP_200_OK,
            )

        citations = build_citations(chunks)
        citation_serializer = CitationSerializer(data=citations, many=True)
        citation_serializer.is_valid(raise_exception=True)

        def stream():
            yield from generate_response(prompt)

        response = StreamingHttpResponse(stream(), content_type="text/plain")
        response["X-Citations"] = json.dumps(citation_serializer.data)
        return response


class HealthCheckAPIView(APIView):
    """Unauthenticated endpoint for dependency health checks."""

    authentication_classes = []
    permission_classes = []

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
