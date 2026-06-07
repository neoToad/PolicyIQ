from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from documents.views import (
    HistoryPageView,
    HomePageView,
    StaffDocumentDeleteView,
    StaffDocumentListView,
    StaffDocumentReindexView,
    UploadPageView,
)
from queries.views import AskPageView, HealthCheckAPIView

urlpatterns = [
    path("", HomePageView.as_view(), name="home"),
    path("admin/documents/", StaffDocumentListView.as_view(), name="staff-documents"),
    path("admin/documents/<uuid:pk>/delete/", StaffDocumentDeleteView.as_view(), name="staff-document-delete"),
    path("admin/documents/<uuid:pk>/reindex/", StaffDocumentReindexView.as_view(), name="document-reindex"),
    path("admin/", admin.site.urls),
    path("api/documents/", include("documents.urls")),
    path("api/queries/", include("queries.urls")),
    path("api/health/", HealthCheckAPIView.as_view(), name="health-check"),
    path("upload/", UploadPageView.as_view(), name="upload-page"),
    path("history/", HistoryPageView.as_view(), name="history-page"),
    path("ask/", AskPageView.as_view(), name="ask-page"),
]

# Serve media files in development only.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
