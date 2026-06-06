"""Tiny timing helper used by view-layer and service code.

The helper exists purely to make timing uniform across the codebase. It does
NOT emit a log line of its own — service code reads ``t["elapsed_s"]`` from
the yielded dict and includes the duration in its own human-readable info
line. Avoiding a second "X done in T.TTs" line from the helper prevents
double-logging.
"""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("queries.timing")


@contextmanager
def stage_timer(stage: str, logger_: logging.Logger | None = None) -> Iterator[dict]:
    """Record a stage's wall-clock duration on context exit (success or failure).

    Args:
        stage: A short human-readable name for the stage. Reserved for future
            log lines and for stack traces; the helper itself does not log.
        logger_: Optional logger. Reserved for future use; the helper
            intentionally does not log so the caller's own info line is the
            single source of truth.

    Yields:
        A dict that the caller can read after the block. The dict always
        contains an ``elapsed_s`` key with a non-negative float (seconds).
        Exceptions raised inside the block propagate to the caller; the
        duration is still recorded before propagation.
    """
    t0 = time.monotonic()
    out: dict = {"elapsed_s": 0.0}
    try:
        yield out
    finally:
        out["elapsed_s"] = time.monotonic() - t0
