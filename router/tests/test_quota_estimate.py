"""Tests for quota_estimate.py -- no real transcript scans, no network.

Every test injects compute_fn and a temp cache path so nothing here ever
touches real ~/.claude data or takes real scan time.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quota_estimate import CachedEstimate, get_estimate, check_tier_crossing, WARNING_TIERS

SGT = timezone(timedelta(hours=8))
RESET = datetime(2026, 8, 18, 16, 0, tzinfo=SGT)


class GetEstimateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "cache.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_cache_miss_calls_compute_fn(self) -> None:
        calls = []

        def compute(reset_boundary):
            calls.append(reset_boundary)
            return 42.0

        est = get_estimate(RESET, now=RESET + timedelta(minutes=1), cache_path=self.cache_path, compute_fn=compute)
        self.assertEqual(est.estimated_pct, 42.0)
        self.assertEqual(calls, [RESET])

    def test_fresh_cache_hit_skips_compute_fn(self) -> None:
        def compute(reset_boundary):
            raise AssertionError("should not be called on a fresh cache hit")

        now = RESET + timedelta(hours=1)
        get_estimate(RESET, now=now, cache_path=self.cache_path, compute_fn=lambda rb: 10.0)
        est = get_estimate(RESET, now=now + timedelta(minutes=5), cache_path=self.cache_path, compute_fn=compute)
        self.assertEqual(est.estimated_pct, 10.0)

    def test_stale_cache_recomputes(self) -> None:
        now = RESET + timedelta(hours=1)
        get_estimate(RESET, now=now, cache_path=self.cache_path, compute_fn=lambda rb: 10.0)
        later = now + timedelta(minutes=31)  # past REFRESH_INTERVAL
        est = get_estimate(RESET, now=later, cache_path=self.cache_path, compute_fn=lambda rb: 20.0)
        self.assertEqual(est.estimated_pct, 20.0)

    def test_new_reset_boundary_forces_recompute_and_resets_tier(self) -> None:
        now = RESET + timedelta(hours=1)
        get_estimate(RESET, now=now, cache_path=self.cache_path, compute_fn=lambda rb: 90.0)
        est = get_estimate(RESET, now=now + timedelta(minutes=5), cache_path=self.cache_path, compute_fn=lambda rb: 90.0)
        check_tier_crossing(est, cache_path=self.cache_path)  # marks tier 85 warned

        next_week = RESET + timedelta(days=7)
        fresh = get_estimate(next_week, now=next_week + timedelta(hours=1),
                              cache_path=self.cache_path, compute_fn=lambda rb: 5.0)
        self.assertEqual(fresh.last_warned_tier, 0)
        self.assertEqual(fresh.estimated_pct, 5.0)


class CheckTierCrossingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "cache.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_tier_crossed_returns_none(self) -> None:
        est = CachedEstimate(estimated_pct=50.0, computed_at=RESET, reset_boundary=RESET)
        self.assertIsNone(check_tier_crossing(est, cache_path=self.cache_path))

    def test_crossing_70_returns_70(self) -> None:
        est = CachedEstimate(estimated_pct=72.0, computed_at=RESET, reset_boundary=RESET)
        self.assertEqual(check_tier_crossing(est, cache_path=self.cache_path), 70)

    def test_jumping_straight_to_95_returns_95_not_70(self) -> None:
        est = CachedEstimate(estimated_pct=97.0, computed_at=RESET, reset_boundary=RESET)
        self.assertEqual(check_tier_crossing(est, cache_path=self.cache_path), 95)

    def test_same_tier_does_not_refire(self) -> None:
        est = CachedEstimate(estimated_pct=72.0, computed_at=RESET, reset_boundary=RESET, last_warned_tier=70)
        self.assertIsNone(check_tier_crossing(est, cache_path=self.cache_path))

    def test_crossing_a_higher_tier_fires_again(self) -> None:
        est = CachedEstimate(estimated_pct=86.0, computed_at=RESET, reset_boundary=RESET, last_warned_tier=70)
        self.assertEqual(check_tier_crossing(est, cache_path=self.cache_path), 85)

    def test_persists_the_new_tier(self) -> None:
        est = CachedEstimate(estimated_pct=72.0, computed_at=RESET, reset_boundary=RESET)
        check_tier_crossing(est, cache_path=self.cache_path)
        self.assertEqual(est.last_warned_tier, 70)


if __name__ == "__main__":
    unittest.main()
