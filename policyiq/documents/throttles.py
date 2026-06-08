"""Custom DRF throttle classes for the documents app.

The implementations live in :mod:`policyiq.throttles` (audit L17). This
module re-exports the upload-scope throttles so existing imports
(``from documents.throttles import UploadAnonRateThrottle``) keep
working. Per-view throttle scoping means each endpoint has its own
counter, so upload traffic doesn't starve query traffic and vice versa.
"""

from policyiq.throttles import (
    DynamicRateMixin,
    UploadAnonRateThrottle,
    UploadUserRateThrottle,
)

__all__ = [
    "DynamicRateMixin",
    "UploadAnonRateThrottle",
    "UploadUserRateThrottle",
]
