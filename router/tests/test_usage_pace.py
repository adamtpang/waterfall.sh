"""Tests for usage_pace.py -- no network calls, no dependence on real time."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from usage_pace import WEEKDAYS, compute_pace, compute_bucket_pace, guidance, _last_reset, BucketResult

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


class ComputeBucketPaceTests(unittest.TestCase):
    def test_matches_manual_calc_for_five_hour_session(self) -> None:
        # 13% used, 5h window, 3h27m (3.45h) remaining -> 1.55h elapsed -> 31.0% elapsed
        b = compute_bucket_pace("session", used_pct=13.0, window_hours=5.0, hours_remaining=3.45)
        self.assertAlmostEqual(b.elapsed_pct, 31.0, delta=0.1)
        self.assertLess(b.pace_delta, 0)  # 13% used < 31% elapsed -- comfortable

    def test_zero_remaining_is_fully_elapsed(self) -> None:
        b = compute_bucket_pace("session", used_pct=50.0, window_hours=5.0, hours_remaining=0.0)
        self.assertEqual(b.elapsed_pct, 100.0)

    def test_negative_remaining_clamped_to_zero(self) -> None:
        b = compute_bucket_pace("session", used_pct=50.0, window_hours=5.0, hours_remaining=-1.0)
        self.assertEqual(b.hours_remaining, 0.0)
        self.assertEqual(b.elapsed_pct, 100.0)

    def test_status_reflects_window_language(self) -> None:
        b = compute_bucket_pace("session", used_pct=90.0, window_hours=5.0, hours_remaining=2.5)
        self.assertIn("burning faster than the window", b.status)

    def test_label_is_preserved(self) -> None:
        b = compute_bucket_pace("weekly (fable)", used_pct=3.0, window_hours=168.0, hours_remaining=100.0)
        self.assertEqual(b.label, "weekly (fable)")


class GuidanceTests(unittest.TestCase):
    def test_empty_list(self) -> None:
        self.assertIn("no usage buckets", guidance([]))

    def test_identifies_tightest_bucket_as_binding_constraint(self) -> None:
        tight = BucketResult("tight-one", used_pct=90, elapsed_pct=50, pace_delta=40.0,
                              status="burning faster than the window is passing", window_hours=5, hours_remaining=2.5)
        loose = BucketResult("loose-one", used_pct=5, elapsed_pct=50, pace_delta=-45.0,
                              status="comfortable cushion", window_hours=168, hours_remaining=80)
        out = guidance([tight, loose])
        self.assertIn("tight-one", out.split("\n")[0])

    def test_recommends_easing_off_the_tightest_when_over_margin(self) -> None:
        tight = BucketResult("tight-one", used_pct=90, elapsed_pct=50, pace_delta=40.0,
                              status="burning faster", window_hours=5, hours_remaining=2.5)
        out = guidance([tight])
        self.assertIn("ease off tight-one", out)

    def test_names_the_roomiest_bucket_when_comfortable(self) -> None:
        tight = BucketResult("even-one", used_pct=50, elapsed_pct=50, pace_delta=0.0,
                              status="tracking evenly", window_hours=5, hours_remaining=2.5)
        roomy = BucketResult("roomy-one", used_pct=3, elapsed_pct=50, pace_delta=-47.0,
                              status="comfortable cushion", window_hours=168, hours_remaining=80)
        out = guidance([tight, roomy])
        self.assertIn("most headroom: roomy-one", out)

    def test_no_headroom_callout_when_nothing_is_comfortable(self) -> None:
        b1 = BucketResult("a", used_pct=50, elapsed_pct=50, pace_delta=0.0, status="tracking evenly",
                           window_hours=5, hours_remaining=2.5)
        b2 = BucketResult("b", used_pct=52, elapsed_pct=50, pace_delta=2.0, status="tracking evenly",
                           window_hours=168, hours_remaining=80)
        out = guidance([b1, b2])
        self.assertNotIn("most headroom", out)


if __name__ == "__main__":
    unittest.main()
