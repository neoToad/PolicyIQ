"""Custom DRF throttle classes for the documents app.

These throttles scope per-view so each endpoint has its own counter (so
upload traffic doesn't starve query traffic, and vice versa).
"""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class UploadAnonRateThrottle(AnonRateThrottle):
    """Throttle anonymous users on the upload endpoint.

    Uses the ``upload_anon`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['upload_anon']``.
    """

    scope = "upload_anon"


class UploadUserRateThrottle(UserRateThrottle):
    """Throttle authenticated users on the upload endpoint.

    Uses the ``upload_user`` scope so the rate is looked up from
    ``settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['upload_user']``.
    """

    scope = "upload_user"
