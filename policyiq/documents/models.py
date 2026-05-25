import uuid

from django.db import models


class Document(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=1024)
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
