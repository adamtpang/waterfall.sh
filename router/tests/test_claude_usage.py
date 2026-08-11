"""Tests for claude_usage.py -- uses synthetic JSONL fixtures, never reads
real transcripts (that's private user session data)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claude_usage import (
    load_usage_turns, summarize, group_by_day, _pricing_for,
    simplify_model, group_by_day_and_model, top_projects_by_model,
)


def _assistant_line(session_id, timestamp, model, input_tokens=0,
                     cache_creation=0, cache_read=0, output_tokens=0):
    return json.dumps({
        "type": "assistant",
        "sessionId": session_id,
        "timestamp": timestamp,
        "message": {
            "model": model,
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tokens,
            },
        },
    })


def _other_line(kind="user"):
    return json.dumps({"type": kind})


class ClaudeUsageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_transcript(self, project_dir: str, filename: str, lines: list[str]) -> Path:
        d = self.root / project_dir
        d.mkdir(parents=True, exist_ok=True)
        path = d / filename
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_load_usage_turns_parses_assistant_entries_only(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _other_line("user"),
            _assistant_line("s1", "2026-08-04T10:00:00+00:00", "claude-sonnet-5",
                             input_tokens=10, cache_creation=100, cache_read=500, output_tokens=50),
            _other_line("attachment"),
        ])
        turns = load_usage_turns(transcript_files=[path])
        self.assertEqual(len(turns), 1)
        t = turns[0]
        self.assertEqual(t.project, "proj-a")
        self.assertEqual(t.total_input_seen, 10 + 100 + 500)

    def test_load_usage_turns_skips_assistant_without_usage(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            json.dumps({"type": "assistant", "sessionId": "s1", "timestamp": "2026-08-04T10:00:00+00:00",
                        "message": {"model": "claude-sonnet-5"}}),  # no usage field
        ])
        turns = load_usage_turns(transcript_files=[path])
        self.assertEqual(turns, [])

    def test_load_usage_turns_skips_malformed_lines(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            "not json at all",
            _assistant_line("s1", "2026-08-04T10:00:00+00:00", "claude-sonnet-5", output_tokens=5),
        ])
        turns = load_usage_turns(transcript_files=[path])
        self.assertEqual(len(turns), 1)

    def test_since_until_filter_by_timestamp(self) -> None:
        from datetime import datetime, timezone
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-01T10:00:00+00:00", "claude-sonnet-5", input_tokens=1),
            _assistant_line("s1", "2026-08-05T10:00:00+00:00", "claude-sonnet-5", input_tokens=2),
        ])
        since = datetime(2026, 8, 3, tzinfo=timezone.utc)
        turns = load_usage_turns(transcript_files=[path], since=since)
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].input_tokens, 2)

    def test_summarize_aggregates_and_computes_reused_pct(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-04T10:00:00+00:00", "claude-sonnet-5",
                             input_tokens=10, cache_creation=90, cache_read=900, output_tokens=20),
            _assistant_line("s1", "2026-08-04T10:05:00+00:00", "claude-sonnet-5",
                             input_tokens=0, cache_creation=0, cache_read=100, output_tokens=5),
        ])
        turns = load_usage_turns(transcript_files=[path])
        s = summarize(turns)
        self.assertEqual(s.turn_count, 2)
        self.assertEqual(s.session_count, 1)
        self.assertEqual(s.cache_read_tokens, 1000)
        self.assertEqual(s.total_input_seen, 10 + 90 + 900 + 0 + 0 + 100)
        self.assertGreater(s.reused_input_pct, 0.9)  # dominated by cache reads

    def test_summarize_empty_is_zeroed(self) -> None:
        s = summarize([])
        self.assertEqual(s.turn_count, 0)
        self.assertEqual(s.reused_input_pct, 0.0)

    def test_group_by_day_buckets_by_date_prefix(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-04T10:00:00+00:00", "claude-sonnet-5", input_tokens=1),
            _assistant_line("s1", "2026-08-04T22:00:00+00:00", "claude-sonnet-5", input_tokens=2),
            _assistant_line("s2", "2026-08-05T09:00:00+00:00", "claude-sonnet-5", input_tokens=3),
        ])
        turns = load_usage_turns(transcript_files=[path])
        by_day = group_by_day(turns)
        self.assertEqual(set(by_day.keys()), {"2026-08-04", "2026-08-05"})
        self.assertEqual(by_day["2026-08-04"].turn_count, 2)
        self.assertEqual(by_day["2026-08-05"].turn_count, 1)

    def test_pricing_matches_by_model_substring(self) -> None:
        in_p, out_p = _pricing_for("claude-opus-4-8")
        self.assertEqual((in_p, out_p), (15e-6, 75e-6))
        in_p, out_p = _pricing_for("claude-haiku-4-5")
        self.assertEqual((in_p, out_p), (1e-6, 5e-6))

    def test_pricing_falls_back_for_unknown_model(self) -> None:
        in_p, out_p = _pricing_for("some-future-model-x")
        self.assertEqual((in_p, out_p), (3e-6, 15e-6))

    def test_estimated_cost_accounts_for_cache_discount_and_premium(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-04T10:00:00+00:00", "claude-sonnet-5",
                             input_tokens=1000, cache_creation=1000, cache_read=1000, output_tokens=1000),
        ])
        turns = load_usage_turns(transcript_files=[path])
        t = turns[0]
        # sonnet pricing: in=3e-6, out=15e-6
        expected = (1000 * 3e-6) + (1000 * 3e-6 * 2.0) + (1000 * 3e-6 * 0.1) + (1000 * 15e-6)
        self.assertAlmostEqual(t.estimated_cost_usd, expected, places=8)

    def test_multiple_projects_and_sessions_all_included_without_filter(self) -> None:
        p1 = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-04T10:00:00+00:00", "claude-sonnet-5", input_tokens=1),
        ])
        p2 = self._write_transcript("proj-b", "s2.jsonl", [
            _assistant_line("s2", "2026-08-04T10:00:00+00:00", "claude-sonnet-5", input_tokens=2),
        ])
        turns = load_usage_turns(transcript_files=[p1, p2])
        self.assertEqual({t.project for t in turns}, {"proj-a", "proj-b"})


class SimplifyModelTests(unittest.TestCase):
    def test_recognizes_each_tier(self) -> None:
        self.assertEqual(simplify_model("claude-sonnet-5"), "sonnet")
        self.assertEqual(simplify_model("claude-opus-5"), "opus")
        self.assertEqual(simplify_model("claude-opus-4-8"), "opus")
        self.assertEqual(simplify_model("claude-haiku-4-5-20251001"), "haiku")
        self.assertEqual(simplify_model("claude-fable-5"), "fable")

    def test_unrecognized_model_is_other(self) -> None:
        self.assertEqual(simplify_model("<synthetic>"), "other")
        self.assertEqual(simplify_model(""), "other")


class _TranscriptFixtureMixin:
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write_transcript(self, project_dir: str, filename: str, lines: list[str]) -> Path:
        d = self.root / project_dir
        d.mkdir(parents=True, exist_ok=True)
        path = d / filename
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


class GroupByDayAndModelTests(_TranscriptFixtureMixin, unittest.TestCase):
    def test_buckets_by_day_and_tier(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-09T10:00:00+00:00", "claude-sonnet-5"),
            _assistant_line("s1", "2026-08-09T11:00:00+00:00", "claude-sonnet-5"),
            _assistant_line("s1", "2026-08-09T12:00:00+00:00", "claude-opus-5"),
            _assistant_line("s1", "2026-08-10T10:00:00+00:00", "claude-haiku-4-5-20251001"),
        ])
        turns = load_usage_turns(transcript_files=[path])
        by_day = group_by_day_and_model(turns)
        self.assertEqual(by_day["2026-08-09"], {"sonnet": 2, "opus": 1})
        self.assertEqual(by_day["2026-08-10"], {"haiku": 1})

    def test_sorted_chronologically(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-10T10:00:00+00:00", "claude-sonnet-5"),
            _assistant_line("s1", "2026-08-05T10:00:00+00:00", "claude-sonnet-5"),
        ])
        turns = load_usage_turns(transcript_files=[path])
        by_day = group_by_day_and_model(turns)
        self.assertEqual(list(by_day.keys()), ["2026-08-05", "2026-08-10"])

    def test_empty_input(self) -> None:
        self.assertEqual(group_by_day_and_model([]), {})


class TopProjectsByModelTests(_TranscriptFixtureMixin, unittest.TestCase):
    def test_ranks_projects_by_tier_descending(self) -> None:
        p1 = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-09T10:00:00+00:00", "claude-opus-5"),
            _assistant_line("s1", "2026-08-09T11:00:00+00:00", "claude-opus-5"),
        ])
        p2 = self._write_transcript("proj-b", "s2.jsonl", [
            _assistant_line("s2", "2026-08-09T10:00:00+00:00", "claude-opus-5"),
        ])
        p3 = self._write_transcript("proj-c", "s3.jsonl", [
            _assistant_line("s3", "2026-08-09T10:00:00+00:00", "claude-sonnet-5"),
        ])
        turns = load_usage_turns(transcript_files=[p1, p2, p3])
        top = top_projects_by_model(turns, "opus")
        self.assertEqual(top, [("proj-a", 2), ("proj-b", 1)])

    def test_respects_limit(self) -> None:
        paths = [
            self._write_transcript(f"proj-{i}", f"s{i}.jsonl", [
                _assistant_line(f"s{i}", "2026-08-09T10:00:00+00:00", "claude-opus-5"),
            ])
            for i in range(5)
        ]
        turns = load_usage_turns(transcript_files=paths)
        top = top_projects_by_model(turns, "opus", limit=2)
        self.assertEqual(len(top), 2)

    def test_empty_when_tier_never_used(self) -> None:
        path = self._write_transcript("proj-a", "s1.jsonl", [
            _assistant_line("s1", "2026-08-09T10:00:00+00:00", "claude-sonnet-5"),
        ])
        turns = load_usage_turns(transcript_files=[path])
        self.assertEqual(top_projects_by_model(turns, "opus"), [])


if __name__ == "__main__":
    unittest.main()
