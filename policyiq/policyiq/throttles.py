"""Project-level DRF throttle classes (audit L17).

Consolidates the ``_DynamicRateMixin`` and the four per-scope throttle
subclasses that used to live in :mod:`documents.throttles` and
:mod:`queries.throttles`. ``_DynamicRateMixin`` re-fetches the rate from
``api_settings.DEFAULT_THROTTLE_RATES`` on every request, so live
``override_settings`` calls take effect (the default DRF
``SimpleRateThrottle`` freezes the rate at class-definition time).

App-level ``throttles.py`` modules re-export the classes they need so
existing import paths (``documents.throttles.UploadAnonRateThrottle``
etc.) keep working.
"""

from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class DynamicRateMixin:
    """Look up throttle rates from ``api_settings`` on every request.

    DRF's ``SimpleRateThrottle`` captures rates into a class attribute at
    class-definition time, so ``override_settings(REST_FRAMEWORK=...)`` does
    not propagate to the throttle. This mixin re-fetches the rate from
    ``api_settings.DEFAULT_THROTTLE_RATES`` on every instantiation so live
    overrides work correctly.

    Public (no leading underscore) because app-level throttle classes
    inherit from it across module boundaries.
    """

    def get_rate(self) -> str | None:
        """Return the rate string for this throttle's scope, or None if unset."""
        if not getattr(self, "scope", None):
            return None
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError:
            return None


class UploadAnonRateThrottle(DynamicRateMixin, AnonRateThrottle):
    """Throttle anonymous users on the upload endpoint.

    Uses the ``upload_anon`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['upload_anon']``.
    """

    scope = "upload_anon"


class UploadUserRateThrottle(DynamicRateMixin, UserRateThrottle):
    """Throttle authenticated users on the upload endpoint.

    Uses the ``upload_user`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['upload_user']``.
    """

    scope = "upload_user"


class QueryAnonRateThrottle(DynamicRateMixin, AnonRateThrottle):
    """Throttle anonymous users on the query endpoint.

    Uses the ``query_anon`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['query_anon']``.
    """

    scope = "query_anon"


class QueryUserRateThrottle(DynamicRateMixin, UserRateThrottle):
    """Throttle authenticated users on the query endpoint.

    Uses the ``query_user`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['query_user']``.
    """

    scope = "query_user"
