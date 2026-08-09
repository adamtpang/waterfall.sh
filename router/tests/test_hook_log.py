"""Tests for hook_log.py -- no network calls."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hook_log import HookLogEntry, append_entry, denial_tokens, group_by_day, load_entries, log_deny, log_nudge, project_label


class ProjectLabelTests(unittest.TestCase):
    def test_basename_of_cwd(self) -> None:
        self.assertEqual(project_label("C:/Users/adamp/Aether/waterfall.sh"), "waterfall.sh")

    def test_empty_cwd_is_unknown(self) -> None:
        self.assertEqual(project_label(""), "(unknown)")


class HookLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmp.name) / "hook_log.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_load_entries_empty_when_no_file(self) -> None:
        self.assertEqual(load_entries(log_path=self.log_path), [])

    def test_append_then_load_round_trip(self) -> None:
        append_entry(HookLogEntry(
            timestamp="2026-08-05T12:00:00+00:00", hook="ringer",
            project="waterfall.sh", action="denied", detail="Read: too big",
        ), log_path=self.log_path)

        entries = load_entries(log_path=self.log_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].hook, "ringer")
        self.assertEqual(entries[0].project, "waterfall.sh")
        self.assertEqual(entries[0].action, "denied")

    def test_log_nudge_writes_a_nudge_entry(self) -> None:
        log_nudge("C:/Users/adamp/Aether/some-project", "routing=free tier=small", log_path=self.log_path)
        entries = load_entries(log_path=self.log_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].hook, "nudge")
        self.assertEqual(entries[0].project, "some-project")
        self.assertEqual(entries[0].action, "nudged")

    def test_log_deny_writes_a_ringer_entry(self) -> None:
        log_deny("C:/Users/adamp/Aether/some-project", "Bash: cat too big", log_path=self.log_path)
        entries = load_entries(log_path=self.log_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].hook, "ringer")
        self.assertEqual(entries[0].action, "denied")

    def test_multiple_entries_preserve_order(self) -> None:
        log_nudge("proj-a", "first", log_path=self.log_path)
        log_deny("proj-b", "second", log_path=self.log_path)
        entries = load_entries(log_path=self.log_path)
        self.assertEqual([e.detail for e in entries], ["first", "second"])

    def test_since_filter_excludes_older_entries(self) -> None:
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        recent = datetime.now(timezone.utc).isoformat()
        append_entry(HookLogEntry(old, "nudge", "p", "nudged", "old"), log_path=self.log_path)
        append_entry(HookLogEntry(recent, "nudge", "p", "nudged", "recent"), log_path=self.log_path)

        since = datetime.now(timezone.utc) - timedelta(days=1)
        entries = load_entries(log_path=self.log_path, since=since)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].detail, "recent")

    def test_corrupt_lines_are_skipped(self) -> None:
        log_nudge("p", "ok", log_path=self.log_path)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write("not json\n")
            f.write("{}\n")  # valid json, missing required fields

        entries = load_entries(log_path=self.log_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].detail, "ok")


class DenialTokensTests(unittest.TestCase):
    def test_parses_comma_formatted_token_count(self) -> None:
        entry = HookLogEntry("t", "ringer", "p", "denied", "waterfall Ringer: x is ~25,000 tokens (100,000 bytes), over the cap.")
        self.assertEqual(denial_tokens(entry), 25000)

    def test_unparseable_detail_returns_zero(self) -> None:
        entry = HookLogEntry("t", "nudge", "p", "nudged", "routing=free tier=small complexity=0.3")
        self.assertEqual(denial_tokens(entry), 0)


class GroupByDayTests(unittest.TestCase):
    def test_buckets_by_day_and_hook_type(self) -> None:
        entries = [
            HookLogEntry("2026-08-05T01:00:00+00:00", "nudge", "p", "nudged", "d"),
            HookLogEntry("2026-08-05T02:00:00+00:00", "ringer", "p", "denied", "d"),
            HookLogEntry("2026-08-05T03:00:00+00:00", "nudge", "p", "nudged", "d"),
            HookLogEntry("2026-08-06T01:00:00+00:00", "ringer", "p", "denied", "d"),
        ]
        by_day = group_by_day(entries)
        self.assertEqual(by_day["2026-08-05"], {"nudge": 2, "ringer": 1})
        self.assertEqual(by_day["2026-08-06"], {"nudge": 0, "ringer": 1})

    def test_sorted_chronologically(self) -> None:
        entries = [
            HookLogEntry("2026-08-07T00:00:00+00:00", "nudge", "p", "nudged", "d"),
            HookLogEntry("2026-08-05T00:00:00+00:00", "nudge", "p", "nudged", "d"),
        ]
        by_day = group_by_day(entries)
        self.assertEqual(list(by_day.keys()), ["2026-08-05", "2026-08-07"])

    def test_empty_input(self) -> None:
        self.assertEqual(group_by_day([]), {})

    def test_skips_entries_without_timestamp(self) -> None:
        entries = [HookLogEntry("", "nudge", "p", "nudged", "d")]
        self.assertEqual(group_by_day(entries), {})


if __name__ == "__main__":
    unittest.main()
