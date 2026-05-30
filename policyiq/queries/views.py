import json

from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Document
from queries.services.generator import build_prompt, generate_response
from queries.services.retriever import retrieve_chunks


class AskPageView(View):
    def get(self, request):
        documents = Document.objects.order_by("-uploaded_at")
        return render(request, "queries/ask.html", {"documents": documents})

    def post(self, request):
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
            return HttpResponse(
                "<p>No relevant information found in the uploaded documents.</p>"
            )

        citations = [
            {
                "document_name": c.get("document_name", "Unknown"),
                "page_number": c.get("page_number"),
                "similarity_score": c["similarity_score"],
                "text_preview": c["text"][:150],
            }
            for c in chunks
        ]

        def stream():
            yield '<div class="card"><p style="white-space: pre-wrap;">'
            for token in generate_response(prompt):
                yield token
            yield "</p></div>"

        response = StreamingHttpResponse(stream(), content_type="text/html")
        response["X-Citations"] = json.dumps(citations)
        return response


class QueryAPIView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        question = request.data.get("question", "").strip()
        document_id = request.data.get("document_id") or None

        if not question:
            return Response(
                {"error": {"message": "Question is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        chunks = retrieve_chunks(question, document_id=document_id, top_k=5)
        prompt = build_prompt(question, chunks, similarity_threshold=0.5)

        if prompt is None:
            return Response(
                {"answer": "No relevant information found in the uploaded documents."},
                status=status.HTTP_200_OK,
            )

        citations = [
            {
                "document_name": c.get("document_name", "Unknown"),
                "page_number": c.get("page_number"),
                "similarity_score": c["similarity_score"],
                "text_preview": c["text"][:150],
            }
            for c in chunks
        ]

        def stream():
            for token in generate_response(prompt):
                yield token

        response = StreamingHttpResponse(stream(), content_type="text/plain")
        response["X-Citations"] = json.dumps(citations)
        return response
