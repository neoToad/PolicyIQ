from django.urls import path

from documents.views import DocumentUploadAPIView

urlpatterns = [
    path("upload/", DocumentUploadAPIView.as_view(), name="document-upload"),
]
