"""Tests for hook_log.py -- no network calls."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hook_log import HookLogEntry, append_entry, load_entries, log_deny, log_nudge, project_label


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


if __name__ == "__main__":
    unittest.main()
