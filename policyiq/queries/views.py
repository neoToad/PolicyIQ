import json

from django.http import StreamingHttpResponse
from django.shortcuts import render
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from queries.services.generator import build_prompt, generate_response
from queries.services.retriever import retrieve_chunks


class AskPageView(View):
    def get(self, request):
        return render(request, "queries/ask.html")


class QueryAPIView(APIView):
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
