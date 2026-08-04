"""Tests for tracker.py -- no network calls."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker import SavingsTracker, estimate_cost_saved
from classifier.types import SavingsEvent


def _event(timestamp: str, tokens_saved: int = 100, cost_saved: float = 0.001,
           backend: str = "openrouter", model: str = "cheap/model",
           task_types: list[str] | None = None, model_tier: str = "small") -> SavingsEvent:
    return SavingsEvent(
        timestamp=timestamp,
        original_tokens=300,
        free_tokens_sent=tokens_saved,
        claude_tokens_needed=300 - tokens_saved,
        tokens_saved=tokens_saved,
        cost_saved_usd=cost_saved,
        backend_used=backend,
        model_used=model,
        routing_decision="split",
        task_types=task_types or ["coding"],
        model_tier=model_tier,
    )


class SavingsTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self._tmp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _tracker(self) -> SavingsTracker:
        return SavingsTracker(ledger_path=self.ledger_path)

    def test_record_and_load_round_trip(self) -> None:
        tracker = self._tracker()
        now = datetime.now(timezone.utc).isoformat()
        tracker.record(_event(now, tokens_saved=100))
        tracker.record(_event(now, tokens_saved=200))

        events = tracker.load_events()
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].tokens_saved, 100)
        self.assertEqual(events[1].tokens_saved, 200)

    def test_load_events_empty_when_no_ledger(self) -> None:
        tracker = self._tracker()
        self.assertEqual(tracker.load_events(), [])

    def test_summarize_aggregates_totals(self) -> None:
        tracker = self._tracker()
        now = datetime.now(timezone.utc).isoformat()
        tracker.record(_event(now, tokens_saved=100, cost_saved=0.01, model_tier="small"))
        tracker.record(_event(now, tokens_saved=200, cost_saved=0.02, model_tier="large"))

        summary = tracker.summarize()
        self.assertEqual(summary.total_prompts, 2)
        self.assertEqual(summary.tokens_avoided, 300)
        self.assertAlmostEqual(summary.estimated_cost_saved, 0.03, places=4)
        self.assertEqual(summary.by_backend, {"openrouter": 2})
        self.assertEqual(summary.by_task_type, {"coding": 2})
        self.assertEqual(summary.by_model_tier, {"small": 1, "large": 1})

    def test_load_events_backward_compatible_without_model_tier(self) -> None:
        """Ledger lines written before model_tier existed must still parse."""
        tracker = self._tracker()
        legacy = _event(datetime.now(timezone.utc).isoformat())
        import json
        from dataclasses import asdict
        data = asdict(legacy)
        del data["model_tier"]
        with tracker.ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")

        events = tracker.load_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].model_tier, "")

    def test_summarize_empty_ledger_returns_zeroed_summary(self) -> None:
        tracker = self._tracker()
        summary = tracker.summarize()
        self.assertEqual(summary.total_prompts, 0)
        self.assertEqual(summary.tokens_avoided, 0)

    def test_load_events_filters_by_since(self) -> None:
        tracker = self._tracker()
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        recent = datetime.now(timezone.utc).isoformat()
        tracker.record(_event(old, tokens_saved=50))
        tracker.record(_event(recent, tokens_saved=75))

        since = datetime.now(timezone.utc) - timedelta(days=1)
        events = tracker.load_events(since=since)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].tokens_saved, 75)

    def test_load_events_skips_corrupt_lines(self) -> None:
        tracker = self._tracker()
        tracker.record(_event(datetime.now(timezone.utc).isoformat()))
        with tracker.ledger_path.open("a", encoding="utf-8") as f:
            f.write("not json\n")
            f.write("{}\n")  # valid json, missing required SavingsEvent fields

        events = tracker.load_events()
        self.assertEqual(len(events), 1)


class EstimateCostSavedTests(unittest.TestCase):
    def test_estimate_cost_saved_floors_at_zero(self) -> None:
        # openrouter cost exceeds the claude-equivalent estimate
        self.assertEqual(estimate_cost_saved(tokens_saved=1, openrouter_cost_usd=1.0), 0.0)

    def test_estimate_cost_saved_basic(self) -> None:
        result = estimate_cost_saved(tokens_saved=1000, openrouter_cost_usd=0.0001)
        # 1000 tokens * 3e-6 - 0.0001 == 0.0029
        self.assertAlmostEqual(result, 0.0029, places=6)


if __name__ == "__main__":
    unittest.main()
