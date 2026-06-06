"""Library-wide statistics used by the homepage and (potentially) other views."""

from typing import TypedDict

from django.db.models import Count, Sum

from documents.models import Document


class LastUpload(TypedDict):
    """Shape of the most recently uploaded document as returned to templates.

    Mirrors the `values("id", "name", "uploaded_at")` projection in
    `get_library_stats` — using a TypedDict so the view's call site gets
    IDE auto-completion and any refactor that drops a field is caught at
    type-check time.
    """

    id: object  # UUIDField primary key
    name: str
    uploaded_at: object  # DateTimeField (tz-aware)


class LibraryStats(TypedDict):
    """Shape of the dict returned by `get_library_stats`."""

    documents: int
    chunks: int
    pages: int
    last_upload: LastUpload | None


def get_library_stats() -> LibraryStats:
    """Return aggregate stats across all documents in the knowledge base.

    Performs two queries:
      1. An aggregate over `Document` for total count, total `chunk_count`,
         and total `page_count`.
      2. A `values()` lookup for the most recent document's `id`, `name`,
         and `uploaded_at` (used by the homepage's "Last upload: <name>,
         <time> ago" subtitle).

    Returns:
        A `LibraryStats` dict with:
          - documents (int): non-negative count of documents
          - chunks (int): total chunk_count across all documents
          - pages (int): total page_count across all documents
          - last_upload (LastUpload | None): most recently uploaded
            document, or None if the library is empty

        Empty-library callers get all-zero ints and `last_upload=None`.
    """
    aggregate = Document.objects.aggregate(
        documents=Count("id"),
        chunks=Sum("chunk_count"),
        pages=Sum("page_count"),
    )
    last = Document.objects.order_by("-uploaded_at").values("id", "name", "uploaded_at").first()
    return {
        "documents": aggregate["documents"] or 0,
        "chunks": aggregate["chunks"] or 0,
        "pages": aggregate["pages"] or 0,
        "last_upload": last,
    }
