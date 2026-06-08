"""Per-file upload loop helper (Phase 3.4, audit L11).

``UploadPageView`` and ``DocumentUploadAPIView`` used to duplicate the
per-file validation + ingestion + result-accumulation loop. This
helper collapses that loop into a single function that returns
``(results, status_code)``. The two views call it and then format the
response (HTML template or JSON).

The status-code logic preserved here is the original (per audit M14):

- All files succeed (or any success) → ``201``
- All files fail validation → ``400``
- All files fail at the pipeline → ``500``
- Mixed success + validation → ``201`` (any success wins)
- Mixed success + pipeline failure → ``201`` (any success wins)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from documents.services.pipeline import ingest_uploaded_pdf

# Status code constants mirror the existing view behavior so callers
# don't have to know DRF's HTTP_201_CREATED numeric value.
STATUS_CREATED = 201
STATUS_BAD_REQUEST = 400
STATUS_INTERNAL_ERROR = 500


def _validate_pdf(upload: UploadedFile) -> str | None:
    """Validate that an uploaded file is a PDF within the size cap.

    Returns an error message string on failure, ``None`` on success.
    Moved from the view module so the per-file loop can own it.

    The size check uses ``settings.PDF_MAX_BYTES`` (default 50 MiB, audit
    M3) so a malicious or accidentally-large upload is rejected at the
    boundary before any disk write or extractor call happens.
    """
    content_type = getattr(upload, "content_type", "")
    if content_type != "application/pdf":
        return f"Invalid content type: {content_type or 'unknown'}. Only application/pdf is allowed."

    size = getattr(upload, "size", 0) or 0
    if size > settings.PDF_MAX_BYTES:
        max_mb = settings.PDF_MAX_BYTES / (1024 * 1024)
        actual_mb = size / (1024 * 1024)
        return f"File too large: {actual_mb:.1f} MB exceeds the {max_mb:.0f} MB limit. Please upload a smaller PDF."

    header = upload.read(5)
    upload.seek(0)
    if header != b"%PDF-":
        return "File does not appear to be a valid PDF (magic bytes mismatch)."

    return None


def _process_uploads(
    uploads: Iterable[UploadedFile],
    *,
    username: str,
) -> tuple[list[dict[str, Any]], int]:
    """Validate and ingest a batch of uploads, returning (results, status).

    Args:
        uploads: An iterable of :class:`UploadedFile` instances (the
            ``request.FILES.getlist("file")`` output). The iterator is
            consumed once.
        username: The username to pass to ``ingest_uploaded_pdf`` for
            the audit-trail log line.

    Returns:
        A tuple of ``(results, status_code)`` where ``results`` is a
        list of dicts ready to feed the ``UploadResultSerializer``
        (one per file, in input order) and ``status_code`` is the HTTP
        status to return.
    """
    results: list[dict[str, Any]] = []
    for upload in uploads:
        validation_error = _validate_pdf(upload)
        if validation_error:
            results.append(
                {
                    "success": False,
                    "name": upload.name,
                    "error": validation_error,
                    "reason": "validation",
                }
            )
            continue

        try:
            document = ingest_uploaded_pdf(upload, username=username)
        except Exception as exc:
            results.append({"success": False, "name": upload.name, "error": str(exc)})
            continue

        results.append(
            {
                "success": True,
                "document_id": document.id,
                "name": document.name,
                "page_count": document.page_count,
                "chunk_count": document.chunk_count,
            }
        )

    has_success = any(r["success"] for r in results)
    has_validation_error = any(r.get("reason") == "validation" for r in results)
    if has_success:
        status_code = STATUS_CREATED
    elif has_validation_error:
        status_code = STATUS_BAD_REQUEST
    else:
        status_code = STATUS_INTERNAL_ERROR
    return results, status_code
