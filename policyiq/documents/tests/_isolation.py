"""Test isolation helpers for the documents app (audit L1).

The Django storage layer is a process-singleton bound to ``settings.MEDIA_ROOT``.
Tests that need a writable media root were previously using
``@override_settings(MEDIA_ROOT=tempfile.gettempdir())`` — every test in
the suite shared the same temp directory, so parallel runs (or even a
sequential run that left files behind) could collide.

The :class:`IsolatedMediaRootMixin` provides a per-test temp directory
via :func:`tempfile.mkdtemp` in ``setUp`` and tears it down in
``tearDown``. Each test gets its own directory; no cross-test state can
leak.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import override_settings


class IsolatedMediaRootMixin:
    """Mixin that gives each test its own ``MEDIA_ROOT`` directory.

    The base ``setUp``/``tearDown`` create and clean up
    ``tempfile.mkdtemp()`` so tests cannot collide on the shared
    ``tempfile.gettempdir()`` root. The Django storage layer sees the
    override for the duration of the test.

    Usage::

        class MyTest(IsolatedMediaRootMixin, TestCase):
            def test_x(self):
                # self._media_root is a unique temp dir for this test
                ...
    """

    _media_root: str | None = None

    def setUp(self) -> None:  # noqa: D401 — unittest-style hook
        super().setUp()
        self._media_root = tempfile.mkdtemp(prefix="policyiq-test-media-")
        self._media_root_override = override_settings(MEDIA_ROOT=Path(self._media_root))
        self._media_root_override.enable()

    def tearDown(self) -> None:  # noqa: D401 — unittest-style hook
        try:
            self._media_root_override.disable()
        finally:
            if self._media_root and Path(self._media_root).exists():
                shutil.rmtree(self._media_root, ignore_errors=True)
            super().tearDown()
