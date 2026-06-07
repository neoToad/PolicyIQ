"""Documents views package (Phase 3.4).

The package now splits the per-file upload loop out into
``documents.views._uploads._process_uploads`` so ``UploadPageView`` and
``DocumentUploadAPIView`` are thin adapters. The split keeps the
previously-monolithic ``views.py`` file readable.
"""

from documents.views._uploads import _process_uploads
from documents.views.upload import (
    DocumentUploadAPIView,
    HistoryPageView,
    HomePageView,
    StaffDocumentDeleteView,
    StaffDocumentListView,
    StaffDocumentReindexView,
    UploadPageView,
)

__all__ = [
    "DocumentUploadAPIView",
    "HistoryPageView",
    "HomePageView",
    "StaffDocumentDeleteView",
    "StaffDocumentListView",
    "StaffDocumentReindexView",
    "UploadPageView",
    "_process_uploads",
]
