"""Tests for usage_pace.py -- no network calls, no dependence on real time."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from usage_pace import WEEKDAYS, compute_pace, _last_reset

SGT = timezone(timedelta(hours=8))
TUESDAY = WEEKDAYS["tuesday"]


class LastResetTests(unittest.TestCase):
    def test_friday_after_tuesday_reset(self) -> None:
        # Fri 2026-08-07 09:06 SGT -> last reset Tue 2026-08-04 17:00
        now = datetime(2026, 8, 7, 9, 6, tzinfo=SGT)
        reset = _last_reset(now, TUESDAY, 17)
        self.assertEqual(reset, datetime(2026, 8, 4, 17, 0, tzinfo=SGT))

    def test_exactly_at_reset_moment(self) -> None:
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT)
        reset = _last_reset(now, TUESDAY, 17)
        self.assertEqual(reset, now)

    def test_just_before_reset_hour_on_reset_day_rolls_back_a_week(self) -> None:
        # Tue 2026-08-04 16:59 -- reset hasn't fired yet today, so it's last week's
        now = datetime(2026, 8, 4, 16, 59, tzinfo=SGT)
        reset = _last_reset(now, TUESDAY, 17)
        self.assertEqual(reset, datetime(2026, 7, 28, 17, 0, tzinfo=SGT))

    def test_just_after_reset_hour_on_reset_day(self) -> None:
        now = datetime(2026, 8, 4, 17, 1, tzinfo=SGT)
        reset = _last_reset(now, TUESDAY, 17)
        self.assertEqual(reset, datetime(2026, 8, 4, 17, 0, tzinfo=SGT))


class ComputePaceTests(unittest.TestCase):
    def test_elapsed_pct_at_reset_moment_is_zero(self) -> None:
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT)
        result = compute_pace(used_pct=0.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertEqual(result.elapsed_pct, 0.0)

    def test_elapsed_pct_halfway_through_week(self) -> None:
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT) + timedelta(hours=84)
        result = compute_pace(used_pct=50.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertAlmostEqual(result.elapsed_pct, 50.0, places=1)

    def test_friday_scenario_matches_manual_calc(self) -> None:
        # Fri 2026-08-07 09:06 SGT, reset Tue 17:00 -> 64.1h elapsed / 168h = 38.2%
        now = datetime(2026, 8, 7, 9, 6, tzinfo=SGT)
        result = compute_pace(used_pct=22.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertAlmostEqual(result.elapsed_pct, 38.2, delta=0.2)
        self.assertLess(result.pace_delta, 0)  # 22% used < ~38% elapsed -- comfortable

    def test_comfortable_cushion_status(self) -> None:
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT) + timedelta(hours=84)  # 50% elapsed
        result = compute_pace(used_pct=20.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertIn("comfortable cushion", result.status)
        self.assertEqual(result.pace_delta, -30.0)

    def test_burning_too_fast_status(self) -> None:
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT) + timedelta(hours=84)  # 50% elapsed
        result = compute_pace(used_pct=90.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertIn("burning faster", result.status)
        self.assertEqual(result.pace_delta, 40.0)

    def test_on_pace_status_within_margin(self) -> None:
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT) + timedelta(hours=84)  # 50% elapsed
        result = compute_pace(used_pct=52.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertEqual(result.status, "tracking the week evenly")

    def test_on_pace_boundary_is_inclusive(self) -> None:
        # delta exactly at the +/-5 margin should count as "on pace", not over/under
        now = datetime(2026, 8, 4, 17, 0, tzinfo=SGT) + timedelta(hours=84)  # 50% elapsed
        result = compute_pace(used_pct=55.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertEqual(result.status, "tracking the week evenly")

    def test_next_reset_is_seven_days_after_last(self) -> None:
        now = datetime(2026, 8, 7, 9, 6, tzinfo=SGT)
        result = compute_pace(used_pct=22.0, now=now, reset_weekday=TUESDAY, reset_hour=17)
        self.assertEqual(result.next_reset - result.last_reset, timedelta(days=7))

    def test_different_reset_day_and_hour(self) -> None:
        # Reset Sunday 9am; now is Wednesday noon
        now = datetime(2026, 8, 5, 12, 0, tzinfo=SGT)  # Wednesday
        result = compute_pace(
            used_pct=10.0, now=now, reset_weekday=WEEKDAYS["sunday"], reset_hour=9
        )
        # Last Sunday before Wed 2026-08-05 is 2026-08-02
        self.assertEqual(result.last_reset, datetime(2026, 8, 2, 9, 0, tzinfo=SGT))


if __name__ == "__main__":
    unittest.main()
