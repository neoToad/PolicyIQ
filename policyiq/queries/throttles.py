"""Custom DRF throttle classes for the queries app.

The implementations live in :mod:`policyiq.throttles` (audit L17). This
module re-exports the query-scope throttles so existing imports
(``from queries.throttles import QueryAnonRateThrottle``) keep working.
Per-view throttle scoping means each endpoint has its own counter, so
query traffic doesn't starve upload traffic and vice versa.
"""

from policyiq.throttles import (
    DynamicRateMixin,
    QueryAnonRateThrottle,
    QueryUserRateThrottle,
)

__all__ = [
    "DynamicRateMixin",
    "QueryAnonRateThrottle",
    "QueryUserRateThrottle",
]
