"""Constants shared across the ``queries`` app.

Audit L8: ``MAX_QUESTION_LOG_CHARS`` was previously defined in
``retriever.py`` but used by ``views.py`` too. The cross-module import
on what was effectively a private constant was a smell. The constant
lives here now, and both ``retriever.py`` and ``views.py`` import it
from this single source of truth.
"""

# Don't dump full questions into INFO logs — they may contain PHI. Truncate
# at this many characters with a "..." suffix in the "Retrieving up to N
# chunks" and "Query received" receipt lines.
MAX_QUESTION_LOG_CHARS = 80

# Cap the "Chunks: [...]" log line at this many entries to keep log volume
# bounded when top_k is large. The summary line above still reports the
# total count; the cap only affects the per-chunk detail list.
MAX_CHUNKS_IN_LOG = 10
