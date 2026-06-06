"""Custom DRF throttle classes for the documents app.

These throttles scope per-view so each endpoint has its own counter (so
upload traffic doesn't starve query traffic, and vice versa).

They override ``get_rate()`` to look up rates from ``api_settings`` at call
time rather than relying on the ``THROTTLE_RATES`` class attribute, which
DRF freezes at class-definition time. The dynamic lookup means changes via
``override_settings(REST_FRAMEWORK=...)`` take effect immediately.
"""

from rest_framework.settings import api_settings
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class _DynamicRateMixin:
    """Look up throttle rates from ``api_settings`` on every request.

    DRF's ``SimpleRateThrottle`` captures rates into a class attribute at
    class-definition time, so ``override_settings(REST_FRAMEWORK=...)`` does
    not propagate to the throttle. This mixin re-fetches the rate from
    ``api_settings.DEFAULT_THROTTLE_RATES`` on every instantiation so live
    overrides work correctly.
    """

    def get_rate(self) -> str | None:
        """Return the rate string for this throttle's scope, or None if unset."""
        if not getattr(self, "scope", None):
            return None
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError:
            return None


class UploadAnonRateThrottle(_DynamicRateMixin, AnonRateThrottle):
    """Throttle anonymous users on the upload endpoint.

    Uses the ``upload_anon`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['upload_anon']``.
    """

    scope = "upload_anon"


class UploadUserRateThrottle(_DynamicRateMixin, UserRateThrottle):
    """Throttle authenticated users on the upload endpoint.

    Uses the ``upload_user`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['upload_user']``.
    """

    scope = "upload_user"
