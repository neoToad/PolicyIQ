"""Health-check helpers for the application's external dependencies.

Each check returns a dict with a ``status`` key ("up" or "down") and an
optional ``error`` key describing the failure. Callers (e.g. the health
view) aggregate these to decide on an overall HTTP status.

Phase 0.2e: ``check_ollama`` delegates to :func:`policyiq.ollama.ping`
so the retry/error-envelope logic stays in the shared client and the
health check just reports the boolean reachability.
"""

import logging

from django.db import connection

from policyiq import ollama

logger = logging.getLogger("queries.health")


def check_postgresql() -> dict:
    """Verify the database connection with a lightweight ``SELECT 1``."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "up"}
    except Exception as exc:
        logger.warning("Health check: PostgreSQL unreachable: %s", exc)
        return {"status": "down", "error": str(exc)}


def check_chromadb(get_collection) -> dict:
    """Verify ChromaDB by calling ``get_collection`` (cached singleton)."""
    try:
        get_collection()
        return {"status": "up"}
    except Exception as exc:
        logger.warning("Health check: ChromaDB unreachable: %s", exc)
        return {"status": "down", "error": str(exc)}


def check_ollama() -> dict:
    """Verify Ollama is reachable via ``GET /api/tags``.

    Delegates to :func:`policyiq.ollama.ping`, which owns the HTTP call
    and the broad-exception catch. The health view gets a single
    boolean; the only error message we surface is the generic
    "Ollama unreachable" because the client logs the actual cause.
    """
    if ollama.ping():
        return {"status": "up"}
    logger.warning("Health check: Ollama unreachable")
    return {"status": "down", "error": "Ollama unreachable"}
