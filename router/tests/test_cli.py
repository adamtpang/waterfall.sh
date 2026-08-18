"""Tests for cli.py's pure parsing helpers -- no network, no disk."""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli import _parse_bucket, _parse_model_pct, _build_usage_pace_buckets


def _ns(**kwargs) -> argparse.Namespace:
    base = dict(
        used_pct=None, utc_offset=8.0, reset_day="tuesday", reset_hour=16,
        session_pct=None, session_hours_remaining=None, session_window_hours=5.0,
        model_pct=[], bucket=[],
    )
    base.update(kwargs)
    return argparse.Namespace(**base)


class ParseModelPctTests(unittest.TestCase):
    def test_valid(self) -> None:
        self.assertEqual(_parse_model_pct("fable=3"), ("fable", 3.0))

    def test_missing_equals_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_model_pct("fable3")

    def test_non_numeric_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_model_pct("fable=abc")


class ParseBucketTests(unittest.TestCase):
    def test_valid(self) -> None:
        label, used_pct, window_hours, hours_remaining = _parse_bucket("codex=15:720:400")
        self.assertEqual(label, "codex")
        self.assertEqual(used_pct, 15.0)
        self.assertEqual(window_hours, 720.0)
        self.assertEqual(hours_remaining, 400.0)

    def test_missing_equals_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_bucket("codex15:720:400")

    def test_wrong_field_count_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_bucket("codex=15:720")

    def test_too_many_fields_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_bucket("codex=15:720:400:1")

    def test_non_numeric_field_raises(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            _parse_bucket("codex=abc:720:400")

    def test_label_is_stripped(self) -> None:
        label, *_ = _parse_bucket(" codex =15:720:400")
        self.assertEqual(label, "codex")


class BuildUsagePaceBucketsTests(unittest.TestCase):
    def test_no_flags_returns_empty(self) -> None:
        self.assertEqual(_build_usage_pace_buckets(_ns()), [])

    def test_bucket_added_without_used_pct(self) -> None:
        buckets = _build_usage_pace_buckets(_ns(bucket=[("codex", 15.0, 720.0, 400.0)]))
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0].label, "codex")
        self.assertEqual(buckets[0].used_pct, 15.0)
        self.assertEqual(buckets[0].window_hours, 720.0)

    def test_used_pct_and_bucket_together(self) -> None:
        buckets = _build_usage_pace_buckets(_ns(used_pct=50.0, bucket=[("grok", 60.0, 720.0, 200.0)]))
        labels = [b.label for b in buckets]
        self.assertIn("weekly (all models)", labels)
        self.assertIn("grok", labels)

    def test_multiple_buckets_independent_windows(self) -> None:
        buckets = _build_usage_pace_buckets(_ns(bucket=[
            ("codex", 15.0, 720.0, 400.0),
            ("grok", 60.0, 720.0, 200.0),
        ]))
        self.assertEqual(len(buckets), 2)
        by_label = {b.label: b for b in buckets}
        self.assertAlmostEqual(by_label["codex"].elapsed_pct, (720 - 400) / 720 * 100, places=1)
        self.assertAlmostEqual(by_label["grok"].elapsed_pct, (720 - 200) / 720 * 100, places=1)

    def test_session_pct_without_used_pct_warns_and_skips(self) -> None:
        buckets = _build_usage_pace_buckets(_ns(session_pct=10.0, session_hours_remaining=2.0))
        self.assertEqual(buckets, [])


if __name__ == "__main__":
    unittest.main()
