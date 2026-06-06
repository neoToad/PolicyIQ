"""Tests for the `stage_timer` context manager.

`stage_timer` is a tiny helper that records the wall-clock duration of a block
of code. It must record the duration on both success and failure paths, and
must never swallow exceptions raised inside the block.
"""

from unittest import mock

from django.test import SimpleTestCase

from queries.services.timing import stage_timer


class StageTimerTests(SimpleTestCase):
    def test_stage_timer_sets_elapsed_s_on_success(self):
        """After a successful block, `t["elapsed_s"]` is a positive float."""
        with stage_timer("noop") as t:
            # No work; duration should still be > 0 because monotonic has
            # nanosecond resolution and the context manager is called twice
            # (entry and exit).
            pass

        self.assertIn("elapsed_s", t)
        self.assertIsInstance(t["elapsed_s"], float)
        self.assertGreaterEqual(t["elapsed_s"], 0.0)

    def test_stage_timer_measures_nontrivial_work(self):
        """A real sleep should produce a duration close to the sleep length."""
        import time

        with stage_timer("sleep") as t:
            time.sleep(0.05)

        # Allow some scheduler slack on slow CI: 0.04s is a safe lower bound
        # for a 0.05s sleep.
        self.assertGreaterEqual(t["elapsed_s"], 0.04)

    def test_stage_timer_sets_elapsed_s_on_exception(self):
        """When the block raises, the duration is still recorded."""
        try:
            with stage_timer("boom") as t:
                raise RuntimeError("expected")
        except RuntimeError:
            pass

        # The dict was populated by the finally block in `stage_timer` before
        # the exception propagated out of the `with`.
        self.assertIn("elapsed_s", t)
        self.assertGreaterEqual(t["elapsed_s"], 0.0)

    def test_stage_timer_does_not_swallow_exceptions(self):
        """Exceptions raised inside the block must propagate to the caller."""
        with self.assertRaisesRegex(ValueError, "intentional"):
            with stage_timer("propagates"):
                raise ValueError("intentional failure")

    def test_stage_timer_uses_passed_in_logger(self):
        """If a logger is passed in, it is used (helper does not log itself,
        so this just verifies the API accepts the kwarg without error)."""
        custom_logger = mock.Mock()
        with stage_timer("custom", logger_=custom_logger):
            pass
        # stage_timer intentionally does NOT log — that would double-log with
        # the caller. So no calls expected on the custom logger either.
        custom_logger.info.assert_not_called()
        custom_logger.warning.assert_not_called()
        custom_logger.error.assert_not_called()
