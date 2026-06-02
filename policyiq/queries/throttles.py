"""Custom DRF throttle classes for the queries app.

These throttles scope per-view so each endpoint has its own counter (so
upload traffic doesn't starve query traffic, and vice versa).
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class QueryAnonRateThrottle(AnonRateThrottle):
    """Throttle anonymous users on the query endpoint.

    Uses the ``query_anon`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['query_anon']``.
    """

    scope = "query_anon"


class QueryUserRateThrottle(UserRateThrottle):
    """Throttle authenticated users on the query endpoint.

    Uses the ``query_user`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['query_user']``.
    """

    scope = "query_user"
