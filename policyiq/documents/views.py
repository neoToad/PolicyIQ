from pathlib import PurePath

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Chunk, Document
from documents.services.chunker import chunk_pages
from documents.services.embedder import embed_chunks
from documents.services.extractor import clean_pages, extract_pages
from documents.services.indexer import delete_document, index_document


def _save_upload_and_ingest(upload) -> Document:
    """Save the uploaded PDF via Django's storage and run the full ingestion pipeline.

    The file is saved to temporary storage first, the pipeline runs, and the
    Document record is only created after successful ingestion — preventing
    orphaned database records when extraction fails.
    """
    # Strip directory components to prevent path traversal.
    safe_name = PurePath(upload.name).name
    temp_path = default_storage.save(f"documents/_tmp_{safe_name}", ContentFile(b""))

    try:
        # Write uploaded content to the temp file.
        with default_storage.open(temp_path, "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)

        full_path = default_storage.path(temp_path)
        pages = extract_pages(full_path)
        cleaned_pages = clean_pages(pages)
        chunks = chunk_pages(cleaned_pages)
        embedded_chunks = embed_chunks(chunks)
    except Exception:
        # Clean up temp file on pipeline failure.
        if default_storage.exists(temp_path):
            default_storage.delete(temp_path)
        raise

    # Pipeline succeeded — create the Document record with the real file.
    document = Document.objects.create(
        name=safe_name,
        file=temp_path,
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
    return document


class UploadPageView(View):
    def get(self, request):
        return render(request, "documents/upload.html")

    def post(self, request):
        uploads = request.FILES.getlist("file")
        if not uploads:
            return render(
                request,
                "documents/_upload_result.html",
                {"error": "At least one PDF file is required."},
                status=400,
            )

        results = []
        for upload in uploads:
            try:
                document = _save_upload_and_ingest(upload)
                results.append({"success": True, "document": document})
            except Exception as exc:
                results.append({"success": False, "name": upload.name, "error": str(exc)})

        status_code = 201 if any(r["success"] for r in results) else 500
        return render(
            request,
            "documents/_upload_result.html",
            {"results": results},
            status=status_code,
        )


class HistoryPageView(View):
    def get(self, request):
        documents = Document.objects.order_by("-uploaded_at")
        return render(request, "documents/history.html", {"documents": documents})


class DocumentDeleteView(View):
    def delete(self, request, pk):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return HttpResponse(status=404)

        delete_document(str(document.id))
        document.delete()
        return HttpResponse(status=200)


@method_decorator(staff_member_required, name="dispatch")
class StaffDocumentListView(View):
    def get(self, request):
        documents = Document.objects.order_by("-uploaded_at")
        return render(request, "documents/admin.html", {"documents": documents})


@method_decorator(staff_member_required, name="dispatch")
class StaffDocumentDeleteView(View):
    def delete(self, request, pk):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return HttpResponse(status=404)

        delete_document(str(document.id))
        document.delete()
        return HttpResponse(status=200)


@method_decorator(staff_member_required, name="dispatch")
class StaffDocumentReindexView(View):
    def post(self, request, pk):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return HttpResponse(status=404)

        # Purge old chunks from PG and ChromaDB
        Chunk.objects.filter(document=document).delete()
        delete_document(str(document.id))

        # Re-run full pipeline from the stored file
        pages = extract_pages(document.file.path)
        cleaned_pages = clean_pages(pages)
        chunks = chunk_pages(cleaned_pages)
        embedded_chunks = embed_chunks(chunks)

        document.page_count = len(pages)
        document.chunk_count = len(embedded_chunks)
        document.save()

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
        return HttpResponse(status=200)


class DocumentUploadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uploads = request.FILES.getlist("file")
        if not uploads:
            return Response(
                {"error": {"message": "At least one PDF file is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        for upload in uploads:
            try:
                document = _save_upload_and_ingest(upload)
                results.append(
                    {
                        "success": True,
                        "document_id": str(document.id),
                        "name": document.name,
                        "page_count": document.page_count,
                        "chunk_count": document.chunk_count,
                    }
                )
            except Exception as exc:
                results.append({"success": False, "name": upload.name, "error": str(exc)})

        status_code = status.HTTP_201_CREATED if any(r["success"] for r in results) else status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"results": results}, status=status_code)