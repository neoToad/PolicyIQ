from rest_framework import serializers

from documents.models import Chunk, Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ["id", "name", "file", "page_count", "chunk_count", "uploaded_at"]


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "document", "page_number", "token_offset", "text"]


class UploadResultSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    document_id = serializers.UUIDField(required=False)
    name = serializers.CharField(required=False)
    page_count = serializers.IntegerField(required=False)
    chunk_count = serializers.IntegerField(required=False)
    error = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True)
