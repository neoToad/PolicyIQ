"""Document views: thin adapters over the service layer.

Phase 3.4 collapsed the per-file upload loop into
:func:`documents.views._uploads._process_uploads`. The two upload views
(``UploadPageView`` and ``DocumentUploadAPIView``) now each call the
helper and format the response.
"""

import logging
import time

from django.contrib.admin.views.decorators import staff_member_required
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
from documents.services.deletion import delete_document_with_chunks
from documents.services.indexer import delete_document
from documents.services.pipeline import ingest_document
from documents.services.stats import get_library_stats
from documents.throttles import UploadAnonRateThrottle, UploadUserRateThrottle
from documents.views._uploads import _process_uploads

logger = logging.getLogger("documents.views")


class HomePageView(View):
    """Public landing page: explains what PolicyIQ is and shows library stats."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the homepage with hero, how-it-works, and library stats."""
        stats = get_library_stats()
        return render(request, "home.html", {"stats": stats})


class UploadPageView(View):
    """Render the upload form and handle HTMX multi-file uploads."""

    def get(self, request: HttpRequest) -> HttpResponse:
        """Render the upload page with the file input form."""
        return render(request, "documents/upload.html")

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle multi-file upload via the shared ``_process_uploads`` helper."""
        uploads = request.FILES.getlist("file")
        if not uploads:
            return render(
                request,
                "documents/_upload_result.html",
                {"error": "At least one PDF file is required."},
                status=400,
            )

        username = getattr(getattr(request, "user", None), "username", "anonymous")
        # Audit L6: view logs the receipt line; the per-stage lines
        # (Wrote / Dispatched / per-failure) live in the pipeline service.
        logger.info("Upload request received: %d file(s) (user=%s)", len(uploads), username)
        t0 = time.monotonic()
        results, status_code = _process_uploads(uploads, username=username)
        logger.info(
            "Upload request complete: %d file(s), status=%d in %.2fs",
            len(uploads),
            status_code,
            time.monotonic() - t0,
        )
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

        delete_document_with_chunks(document)
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

        # Purge old chunks from PG and ChromaDB before re-ingesting.
        # Audit M4: this pre-delete is intentional, not redundant with the
        # atomic writes inside ``ingest_document``. It guarantees a clean
        # slate (no leftover embeddings/chunks) before the new run, so a
        # partial reindex failure leaves the document in a known-empty
        # state rather than half-old/half-new.
        Chunk.objects.filter(document=document).delete()
        delete_document(str(document.id))

        # Re-run full pipeline via the shared service. Audit M9: if the
        # new ingest raises (e.g., ExtractionError on a corrupt PDF), we
        # log at ERROR level and return 500 so the operator sees the
        # failure in the admin UI instead of a silent 200.
        try:
            ingest_document(document)
        except Exception as exc:
            logger.error(
                "Reindex failed for document_id=%s: %s",
                pk,
                exc,
                exc_info=True,
            )
            return HttpResponse(
                f"Reindex failed: {exc}",
                status=500,
            )
        return HttpResponse(status=200)


class DocumentUploadAPIView(APIView):
    """Authenticated API endpoint for uploading PDF documents."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [UploadAnonRateThrottle, UploadUserRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle multi-file upload via the shared ``_process_uploads`` helper."""
        uploads = request.FILES.getlist("file")
        if not uploads:
            return Response(
                {"error": {"message": "At least one PDF file is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = getattr(getattr(request, "user", None), "username", "anonymous")
        # Audit L6: view logs the receipt line; the per-stage lines
        # (Wrote / Dispatched / per-failure) live in the pipeline service.
        logger.info("Upload request received: %d file(s) (user=%s)", len(uploads), username)
        t0 = time.monotonic()
        results, status_code = _process_uploads(uploads, username=username)
        logger.info(
            "Upload request complete: %d file(s), status=%d in %.2fs",
            len(uploads),
            status_code,
            time.monotonic() - t0,
        )

        serializer = UploadResultSerializer(data=results, many=True)
        serializer.is_valid(raise_exception=True)

        # Map the helper's plain int status to the DRF constants.
        if status_code == 201:
            drf_status = status.HTTP_201_CREATED
        elif status_code == 400:
            drf_status = status.HTTP_400_BAD_REQUEST
        else:
            drf_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        return Response({"results": serializer.data}, status=drf_status)
