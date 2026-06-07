"""Helpers for deriving Ollama endpoint URLs from the configured base URL.

Centralizing URL construction here means a future move from the default
``http://localhost:11434`` to a remote Ollama host only needs a single
``OLLAMA_BASE_URL`` env-var change — every consumer (embedder, generator,
health check) reads from this module.

The settings module is the source of truth for ``OLLAMA_BASE_URL``; this
module is a thin layer over it.
"""

from __future__ import annotations

from django.conf import settings


def _base_url() -> str:
    """Return the configured OLLAMA_BASE_URL with any trailing slash stripped."""
    return settings.OLLAMA_BASE_URL.rstrip("/")


def get_ollama_embed_url() -> str:
    """URL for the ``/api/embed`` endpoint (batch + single-shot embedding)."""
    return f"{_base_url()}/api/embed"


def get_ollama_generate_url() -> str:
    """URL for the ``/api/generate`` endpoint (streaming LLM tokens)."""
    return f"{_base_url()}/api/generate"


def get_ollama_tags_url() -> str:
    """URL for the ``/api/tags`` endpoint (model listing / health check)."""
    return f"{_base_url()}/api/tags"
