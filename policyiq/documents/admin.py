from django.contrib import admin

from .models import Chunk, Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "page_count", "chunk_count", "uploaded_at")
    search_fields = ("name", "file_path")


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number", "token_offset")
    search_fields = ("document__name", "text")
    list_select_related = ("document",)
