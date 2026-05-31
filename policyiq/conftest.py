"""Shared pytest fixtures for the PolicyIQ test suite.

These fixtures coexist with Django's unittest-based tests. They are discovered
automatically by pytest and can be used in any ``test_*.py`` file.
"""

from datetime import UTC
from unittest import mock
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Return a DRF APIClient for making authenticated/unauthenticated requests."""
    return APIClient()


@pytest.fixture
def authenticated_user():
    """Return a mock user that passes DRF ``IsAuthenticated`` checks."""
    user = mock.Mock()
    user.is_authenticated = True
    user.is_staff = False
    user.pk = uuid4()
    return user


@pytest.fixture
def staff_user():
    """Return a mock user that passes ``staff_member_required`` checks."""
    user = mock.Mock()
    user.is_authenticated = True
    user.is_staff = True
    user.pk = uuid4()
    return user


@pytest.fixture
def pdf_file():
    """Return a valid PDF SimpleUploadedFile for use in upload tests."""
    return SimpleUploadedFile(
        "policy.pdf",
        b"%PDF-1.4 fake content",
        content_type="application/pdf",
    )


@pytest.fixture
def mock_document():
    """Return a mock Document instance with common attributes pre-set."""
    from datetime import datetime

    doc = mock.Mock()
    doc.id = uuid4()
    doc.name = "mock_policy.pdf"
    doc.page_count = 2
    doc.chunk_count = 2
    doc.uploaded_at = datetime(2026, 1, 1, tzinfo=UTC)
    return doc
