"""Unit tests for documents.services.stats."""

from datetime import UTC, datetime
from unittest import mock
from uuid import uuid4

from documents.services.stats import get_library_stats


class GetLibraryStatsTests(mock.TestCase):
    """Unit tests for `get_library_stats()` — fully mocked, no DB."""

    def test_get_library_stats_empty_db_returns_zeros(self):
        """An empty library returns all-zero counters and `last_upload=None`."""
        # Sum() returns None (not 0) on an empty table; the service must coerce.
        fake_aggregate = {
            "documents": 0,
            "chunks": None,
            "pages": None,
        }
        with (
            mock.patch("documents.services.stats.Document.objects") as mock_objects,
        ):
            mock_objects.aggregate.return_value = fake_aggregate
            mock_objects.order_by.return_value.values.return_value.first.return_value = None
            stats = get_library_stats()

        self.assertEqual(stats["documents"], 0)
        self.assertEqual(stats["chunks"], 0)
        self.assertEqual(stats["pages"], 0)
        self.assertIsNone(stats["last_upload"])

    def test_get_library_stats_passes_through_counts(self):
        """Aggregate counts flow through unchanged (no clamping, no recompute)."""
        fake_aggregate = {
            "documents": 7,
            "chunks": 1234,
            "pages": 567,
        }
        with mock.patch("documents.services.stats.Document.objects") as mock_objects:
            mock_objects.aggregate.return_value = fake_aggregate
            mock_objects.order_by.return_value.values.return_value.first.return_value = None
            stats = get_library_stats()

        self.assertEqual(stats["documents"], 7)
        self.assertEqual(stats["chunks"], 1234)
        self.assertEqual(stats["pages"], 567)

    def test_get_library_stats_returns_last_upload_dict(self):
        """The most recently uploaded document is returned as a dict with id/name/uploaded_at."""
        doc_id = uuid4()
        uploaded_at = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
        last_upload = {"id": doc_id, "name": "Aetna-2026-Policy.pdf", "uploaded_at": uploaded_at}
        fake_aggregate = {"documents": 1, "chunks": 5, "pages": 10}
        with mock.patch("documents.services.stats.Document.objects") as mock_objects:
            mock_objects.aggregate.return_value = fake_aggregate
            mock_objects.order_by.return_value.values.return_value.first.return_value = last_upload
            stats = get_library_stats()

        self.assertEqual(stats["last_upload"], last_upload)
        self.assertEqual(stats["last_upload"]["name"], "Aetna-2026-Policy.pdf")

    def test_get_library_stats_last_upload_none_when_empty(self):
        """Empty library: explicit assertion that last_upload is None (overlaps #1, called out separately)."""
        fake_aggregate = {"documents": 0, "chunks": None, "pages": None}
        with mock.patch("documents.services.stats.Document.objects") as mock_objects:
            mock_objects.aggregate.return_value = fake_aggregate
            mock_objects.order_by.return_value.values.return_value.first.return_value = None
            stats = get_library_stats()

        self.assertIsNone(stats["last_upload"])
        self.assertEqual(stats["documents"], 0)
