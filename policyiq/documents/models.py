import uuid
from pathlib import PurePath

from django.db import models


def _document_upload_path(instance, filename):
    """Generate a safe upload path, stripping directory components to prevent traversal."""
    safe_name = PurePath(filename).name
    return f"documents/{safe_name}"


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to=_document_upload_path)
    page_count = models.IntegerField()
    chunk_count = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class Chunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    page_number = models.IntegerField()
    token_offset = models.IntegerField()
    text = models.TextField()

    def __str__(self) -> str:
        return f"{self.document.name} p{self.page_number} @ {self.token_offset}"