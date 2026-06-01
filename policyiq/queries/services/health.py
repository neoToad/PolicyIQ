"""Health-check helpers for the application's external dependencies.

Each check returns a dict with a ``status`` key ("up" or "down") and an
optional ``error`` key describing the failure. Callers (e.g. the health
view) aggregate these to decide on an overall HTTP status.
"""

import logging

import requests
from django.conf import settings
from django.db import connection

logger = logging.getLogger("queries.health")


def check_postgresql() -> dict:
    """Verify the database connection with a lightweight ``SELECT 1``."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "up"}
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.warning("Health check: PostgreSQL unreachable: %s", exc)
        return {"status": "down", "error": str(exc)}


def check_chromadb(get_collection) -> dict:
    """Verify ChromaDB by calling ``get_collection`` (cached singleton)."""
    try:
        get_collection()
        return {"status": "up"}
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.warning("Health check: ChromaDB unreachable: %s", exc)
        return {"status": "down", "error": str(exc)}


def check_ollama(timeout: float = 2.0) -> dict:
    """Verify Ollama is reachable by calling ``GET /api/tags``."""
    ollama_url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        response = requests.get(ollama_url, timeout=timeout)
        response.raise_for_status()
        return {"status": "up"}
    except Exception as exc:  # pragma: no cover - exercised via tests
        logger.warning("Health check: Ollama unreachable: %s", exc)
        return {"status": "down", "error": str(exc)}
