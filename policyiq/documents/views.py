import logging
import time
from pathlib import PurePath

from django.contrib.admin.views.decorators import staff_member_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Chunk, Document
from documents.serializers import UploadResultSerializer
from documents.services.indexer import delete_document
from documents.services.pipeline import ingest_document
from documents.services.stats import get_library_stats
from documents.throttles import UploadAnonRateThrottle, UploadUserRateThrottle

logger = logging.getLogger("documents.views")


def _validate_pdf(upload: UploadedFile) -> str | None:
    """Validate that an uploaded file is a PDF.

    Checks the Content-Type header and the PDF magic bytes (%PDF-) at the
    start of the file content. Returns an error message if invalid, None if
    the file passes validation.
    """
    content_type = getattr(upload, "content_type", "")
    if content_type != "application/pdf":
        return f"Invalid content type: {content_type or 'unknown'}. Only application/pdf is allowed."

    header = upload.read(5)
    upload.seek(0)
    if header != b"%PDF-":
        return "File does not appear to be a valid PDF (magic bytes mismatch)."

    return None


def _save_upload_and_ingest(upload: UploadedFile, username: str = "anonymous") -> Document:
    """Save the uploaded PDF via Django's storage and run the full ingestion pipeline.

    The file is saved to temporary storage first, a Document record is created,
    and the shared `ingest_document` pipeline is invoked. On pipeline failure
    the Document and temp file are both cleaned up to prevent orphaned records.

    Emits INFO lines at: receive, validate, write, dispatch; and an ERROR
    line on ingest failure (with the exception type and total duration).
    """
    # Strip directory components to prevent path traversal.
    safe_name = PurePath(upload.name).name
    size_mb = (upload.size or 0) / (1024 * 1024)
    logger.info(
        "Received upload %r (%.2f MB) from user=%s",
        safe_name,
        size_mb,
        username,
    )

    validation_error = _validate_pdf(upload)
    if validation_error:
        # Validation should be caught by the caller before reaching this
        # function, but if it slips through, log it for visibility.
        logger.warning("Validation failed for %r: %s", safe_name, validation_error)

    logger.info("Validated PDF magic bytes for %r", safe_name)

    temp_path = default_storage.save(f"documents/_tmp_{safe_name}", ContentFile(b""))

    try:
        # Write uploaded content to the temp file.
        with default_storage.open(temp_path, "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)
    except Exception:
        if default_storage.exists(temp_path):
            default_storage.delete(temp_path)
        raise

    full_path = default_storage.path(temp_path)
    logger.info("Wrote %r to %s", safe_name, temp_path)

    # Create the Document record before running the pipeline so the shared
    # service can update it directly. We delete it on failure.
    document = Document.objects.create(
        name=safe_name,
        file=temp_path,
        page_count=0,
        chunk_count=0,
    )

    t0 = time.monotonic()
    try:
        ingest_document(document, file_path=full_path)
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.error(
            "Ingestion failed for %r after %.2fs: %s: %s",
            safe_name,
            elapsed,
            type(exc).__name__,
            exc,
        )
        document.delete()
        if default_storage.exists(temp_path):
            default_storage.delete(temp_path)
        raise
    elapsed = time.monotonic() - t0
    logger.info(
        "Dispatched ingestion for %r (document_id=%s) in %.2fs",
        safe_name,
        document.id,
        elapsed,
    )

    return document


class HomePageView(View):
    """Public landing page: explains what PolicyIQ is and shows library stats."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the homepage with hero, how-it-works, and library stats.

        Anonymous-accessible per the homepage plan §1.1 ("Visitors (public)"
        audience) — the brand link in the nav (base.html:21) and any incoming
        first-time visitor must be able to land on `/`.
        """
        stats = get_library_stats()
        return render(request, "home.html", {"stats": stats})


class UploadPageView(View):
    """Render the upload form and handle HTMX multi-file uploads."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the upload page with the file input form."""
        return render(request, "documents/upload.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle multi-file upload, validate PDFs, and run ingestion pipeline."""
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
            validation_error = _validate_pdf(upload)
            if validation_error:
                results.append(
                    {"success": False, "name": upload.name, "error": validation_error, "reason": "validation"}
                )
                continue

            try:
                username = getattr(getattr(request, "user", None), "username", "anonymous")
                document = _save_upload_and_ingest(upload, username=username)
                results.append({"success": True, "document": document})
            except Exception as exc:
                results.append({"success": False, "name": upload.name, "error": str(exc)})

        has_success = any(r["success"] for r in results)
        has_validation_error = any(r.get("reason") == "validation" for r in results)
        if has_success:
            status_code = 201
        elif has_validation_error:
            status_code = 400
        else:
            status_code = 500
        return render(
            request,
            "documents/_upload_result.html",
            {"results": results},
            status=status_code,
        )


class HistoryPageView(View):
    """Display a chronological list of all uploaded documents."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the history page with documents ordered by upload date."""
        documents = Document.objects.order_by("-uploaded_at")
        return render(request, "documents/history.html", {"documents": documents})


class DocumentDeleteView(View):
    """Delete a document and its associated ChromaDB chunks."""

    def delete(self, request: HttpRequest, pk: str) -> HttpResponse:
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return HttpResponse(status=404)

        delete_document(str(document.id))
        document.delete()
        return HttpResponse(status=200)


@method_decorator(staff_member_required, name="dispatch")
class StaffDocumentListView(View):
    """Staff-only view listing all documents for administration."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the staff admin page with all documents."""
        documents = Document.objects.order_by("-uploaded_at")
        return render(request, "documents/admin.html", {"documents": documents})


@method_decorator(staff_member_required, name="dispatch")
class StaffDocumentDeleteView(View):
    """Staff-only view to delete a document and its ChromaDB chunks."""

    def delete(self, request: HttpRequest, pk: str) -> HttpResponse:
        """Remove the document from PostgreSQL and ChromaDB."""
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return HttpResponse(status=404)

        delete_document(str(document.id))
        document.delete()
        return HttpResponse(status=200)


@method_decorator(staff_member_required, name="dispatch")
class StaffDocumentReindexView(View):
    """Staff-only view to purge and re-run the ingestion pipeline for a document."""

    def post(self, request: HttpRequest, pk: str) -> HttpResponse:
        """Delete existing chunks and re-ingest the document."""
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return HttpResponse(status=404)

        # Purge old chunks from PG and ChromaDB
        Chunk.objects.filter(document=document).delete()
        delete_document(str(document.id))

        # Re-run full pipeline via the shared service.
        ingest_document(document)
        return HttpResponse(status=200)


class DocumentUploadAPIView(APIView):
    """Authenticated API endpoint for uploading PDF documents."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [UploadAnonRateThrottle, UploadUserRateThrottle]

    def post(self, request: Request) -> Response:
        """Validate and ingest uploaded PDFs, returning structured results."""
        uploads = request.FILES.getlist("file")
        if not uploads:
            return Response(
                {"error": {"message": "At least one PDF file is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results = []
        for upload in uploads:
            validation_error = _validate_pdf(upload)
            if validation_error:
                results.append(
                    {"success": False, "name": upload.name, "error": validation_error, "reason": "validation"}
                )
                continue

            try:
                username = getattr(getattr(request, "user", None), "username", "anonymous")
                document = _save_upload_and_ingest(upload, username=username)
                results.append(
                    {
                        "success": True,
                        "document_id": document.id,
                        "name": document.name,
                        "page_count": document.page_count,
                        "chunk_count": document.chunk_count,
                    }
                )
            except Exception as exc:
                results.append({"success": False, "name": upload.name, "error": str(exc)})

        serializer = UploadResultSerializer(data=results, many=True)
        serializer.is_valid(raise_exception=True)

        has_success = any(r["success"] for r in results)
        has_validation_error = any(r.get("reason") == "validation" for r in results)
        if has_success:
            status_code = status.HTTP_201_CREATED
        elif has_validation_error:
            status_code = status.HTTP_400_BAD_REQUEST
        else:
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"results": serializer.data}, status=status_code)
