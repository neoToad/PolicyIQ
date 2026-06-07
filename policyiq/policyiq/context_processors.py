"""Template context processors injected into every Django template render.

The threshold values exposed here mirror the server-side gates in
``build_prompt`` (``SIMILARITY_THRESHOLD``) and the citations panel colour
band boundary (``SIMILARITY_BAR_HIGH``). Keeping them as injected
context — rather than literals in the template — means a single env-var
change retunes both the prompt gate and the UI bar in lockstep (audit L13).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest


def similarity_thresholds(request: HttpRequest | None) -> dict[str, Any]:
    """Inject the two similarity threshold settings into the template context.

    Args:
        request: Django request object (unused, but required by the
            ``context_processors`` protocol).

    Returns:
        Dict with ``SIMILARITY_THRESHOLD`` and ``SIMILARITY_BAR_HIGH`` keys
        read from Django settings at render time.
    """
    return {
        "SIMILARITY_THRESHOLD": settings.SIMILARITY_THRESHOLD,
        "SIMILARITY_BAR_HIGH": settings.SIMILARITY_BAR_HIGH,
    }
