from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.views import View
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Chunk, Document
from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks
from documents.services.extractor import clean_pages, extract_pages
from documents.services.indexer import index_document


class UploadPageView(View):
    def get(self, request):
        return render(request, "documents/upload.html")


class HistoryPageView(View):
    def get(self, request):
        return render(request, "documents/history.html")


class DocumentUploadAPIView(APIView):
    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"error": {"message": "A PDF file is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            media_root = Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR / "media"))
            documents_dir = media_root / "documents"
            documents_dir.mkdir(parents=True, exist_ok=True)
            file_path = documents_dir / upload.name

            with file_path.open("wb+") as destination:
                for chunk in upload.chunks():
                    destination.write(chunk)

            pages = extract_pages(str(file_path))
            cleaned_pages = clean_pages(pages)
            chunks = chunk_pages(cleaned_pages)
            embedded_chunks = embed_chunks(chunks)

            document = Document.objects.create(
                name=upload.name,
                file_path=str(file_path),
                page_count=len(pages),
                chunk_count=len(embedded_chunks),
            )
            Chunk.objects.bulk_create(
                [
                    Chunk(
                        document=document,
                        page_number=chunk["page_number"],
                        token_offset=chunk["token_offset"],
                        text=chunk["text"],
                    )
                    for chunk in embedded_chunks
                ]
            )
            index_document(str(document.id), embedded_chunks)

            return Response(
                {
                    "document_id": str(document.id),
                    "name": document.name,
                    "page_count": document.page_count,
                    "chunk_count": document.chunk_count,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            return Response(
                {
                    "error": {
                        "message": "Document ingestion failed.",
                        "detail": str(exc),
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
