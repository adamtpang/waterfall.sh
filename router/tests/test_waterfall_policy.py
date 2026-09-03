"""Routing policy and verify-then-escalate tests, with no network calls."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from waterfall_policy import (
    PromotionSignal,
    RepoSignals,
    RoutingPolicy,
    RunAttempt,
    RunTrace,
    format_why,
    load_trace,
    parse_reviewer_verdict,
    save_trace,
    same_task_failed_harden,
    task_hash,
)
from waterfall_run import execute_waterfall


class FakeGenerator:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)
        self.calls = []

    def generate(self, prompt: str, model: str, effort: str, system: str):
        self.calls.append({"prompt": prompt, "model": model, "effort": effort, "system": system})
        return SimpleNamespace(text=next(self.outputs), cost_usd=0.10)


class ClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = RoutingPolicy()

    def test_classifier_json_schema_is_exact(self) -> None:
        result = self.policy.classify(
            "implement a local parser feature",
            RepoSignals(file_count=2, languages=("python",), test_runner_present=True),
        ).to_dict()
        self.assertEqual(
            {
                "tier", "effort", "reason", "failure_cost", "frontend",
                "long_horizon", "suggested_models",
            },
            set(result),
        )
        json.dumps(result)

    def test_default_path_never_starts_on_fable(self) -> None:
        decision = self.policy.classify("implement a local parser feature")
        self.assertEqual("implement", decision.tier)
        self.assertNotIn("claude-fable-5.1", decision.suggested_models)
        self.assertFalse(self.policy.default_path_starts_on_fable())

    def test_trivial_task_starts_on_draft(self) -> None:
        decision = self.policy.classify("write a commit message")
        self.assertEqual("draft", decision.tier)
        self.assertEqual("low", decision.effort)

    def test_frontend_prefers_kimi_at_implement(self) -> None:
        decision = self.policy.classify("build a responsive frontend component")
        self.assertEqual("implement", decision.tier)
        self.assertEqual("kimi-k3", decision.suggested_models[0])

    def test_build_word_does_not_trigger_ui_substring(self) -> None:
        decision = self.policy.classify("build a backend parser")
        self.assertFalse(decision.frontend)
        self.assertEqual("grok-4.6", decision.suggested_models[0])

    def test_repo_span_starts_on_harden(self) -> None:
        decision = self.policy.classify("add a feature", RepoSignals(file_count=6))
        self.assertEqual("harden", decision.tier)

    def test_explicit_cant_be_wrong_can_start_escalate(self) -> None:
        decision = self.policy.classify("This authentication fix can't be wrong")
        self.assertEqual("escalate", decision.tier)
        self.assertEqual(("claude-fable-5.1",), decision.suggested_models)

    def test_invalid_effort_for_tier_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.policy.classify("rename this", tier="draft", effort="max")


class PromotionRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = RoutingPolicy()

    def test_allowed_failure_signals_promote(self) -> None:
        for kind in ("tests_failed", "author_stuck", "author_refused", "empty_patch", "diff_empty", "diff_reverts_repo", "user_escalate"):
            with self.subTest(kind=kind):
                self.assertTrue(self.policy.promotion_decision(
                    PromotionSignal(kind), promotions_so_far=0
                )[0])

    def test_style_and_verbosity_do_not_promote(self) -> None:
        for kind in ("verbosity", "style_nit", "could_be_more_elegant", "missing_comments", "author_requests_smarter_model"):
            with self.subTest(kind=kind):
                self.assertFalse(self.policy.promotion_decision(
                    PromotionSignal(kind), promotions_so_far=0
                )[0])

    def test_reviewer_reject_requires_concrete_defect(self) -> None:
        self.assertFalse(self.policy.promotion_decision(
            PromotionSignal("reviewer_reject"), promotions_so_far=0
        )[0])
        self.assertTrue(self.policy.promotion_decision(
            PromotionSignal("reviewer_reject", blocking_defects=("breaks empty input",)),
            promotions_so_far=0,
        )[0])

    def test_default_promotion_cap_is_two(self) -> None:
        self.assertFalse(self.policy.promotion_decision(
            PromotionSignal("tests_failed"), promotions_so_far=2
        )[0])
        self.assertTrue(self.policy.promotion_decision(
            PromotionSignal("tests_failed"), promotions_so_far=2, no_cap=True
        )[0])

    def test_author_never_reviews_own_patch(self) -> None:
        reviewer_tier, reviewer, _ = self.policy.reviewer_for("implement", "grok-4.6")
        self.assertEqual("harden", reviewer_tier)
        self.assertNotEqual("grok-4.6", reviewer)


class RunnerTests(unittest.TestCase):
    def test_pass_stops_without_fable(self) -> None:
        fake = FakeGenerator(["implemented patch", "PASS\nESCALATE: no"])
        result = execute_waterfall("implement a local parser feature", generator=fake)
        self.assertTrue(result.passed)
        self.assertEqual(0, len(result.trace.promotions))
        self.assertEqual("claude-fable-5.1", result.trace.skipped[0])
        self.assertNotEqual(fake.calls[0]["model"], fake.calls[1]["model"])

    def test_concrete_reject_promotes_to_harden(self) -> None:
        fake = FakeGenerator([
            "first patch",
            "REJECT\n- breaks empty input\nESCALATE: yes",
            "fixed patch",
            "PASS\nESCALATE: no",
        ])
        result = execute_waterfall("implement a local parser feature", generator=fake)
        self.assertTrue(result.passed)
        self.assertEqual([{"from": "implement", "to": "harden", "reason": "reviewer found a blocking defect"}], result.trace.promotions)
        author_tiers = [attempt.tier for attempt in result.trace.attempts if attempt.role == "author"]
        self.assertEqual(["implement", "harden"], author_tiers)

    def test_repeated_rejects_stop_at_two_promotions(self) -> None:
        fake = FakeGenerator([
            "draft 1", "REJECT\n- defect 1\nESCALATE: yes",
            "draft 2", "REJECT\n- defect 2\nESCALATE: yes",
            "draft 3", "REJECT\n- defect 3\nESCALATE: yes",
        ])
        result = execute_waterfall("write a one-file lint fix", generator=fake)
        self.assertFalse(result.passed)
        self.assertEqual(2, len(result.trace.promotions))
        self.assertFalse(any("fable" in call["model"] for call in fake.calls))

    def test_style_only_reject_does_not_promote(self) -> None:
        fake = FakeGenerator(["good patch", "REJECT\n- could be more elegant\nESCALATE: no"])
        result = execute_waterfall("implement a local parser feature", generator=fake)
        self.assertFalse(result.passed)
        self.assertEqual([], result.trace.promotions)
        self.assertEqual(2, len(fake.calls))

    def test_empty_reviewer_output_does_not_promote(self) -> None:
        fake = FakeGenerator(["good patch", ""])
        result = execute_waterfall("implement a local parser feature", generator=fake)
        self.assertFalse(result.passed)
        self.assertEqual([], result.trace.promotions)

    def test_explicit_ceiling_uses_fable_max(self) -> None:
        fake = FakeGenerator(["ceiling patch", "PASS\nESCALATE: no"])
        result = execute_waterfall(
            "fix this", generator=fake, tier="ceiling", effort="max"
        )
        self.assertTrue(result.passed)
        self.assertIn("fable", fake.calls[0]["model"])
        self.assertEqual("max", fake.calls[0]["effort"])

    def test_two_failed_escalate_attempts_reach_ceiling(self) -> None:
        fake = FakeGenerator([
            "fable high patch", "REJECT\n- defect one\nESCALATE: yes",
            "fable xhigh patch", "REJECT\n- defect two\nESCALATE: yes",
            "fable max patch", "PASS\nESCALATE: no",
        ])
        result = execute_waterfall("fix this", generator=fake, tier="escalate")
        self.assertTrue(result.passed)
        author_attempts = [attempt for attempt in result.trace.attempts if attempt.role == "author"]
        self.assertEqual(["high", "xhigh", "max"], [attempt.effort for attempt in author_attempts])
        self.assertEqual(
            [("escalate", "escalate"), ("escalate", "ceiling")],
            [(item["from"], item["to"]) for item in result.trace.promotions],
        )


class TraceTests(unittest.TestCase):
    def test_trace_round_trip_and_why(self) -> None:
        trace = RunTrace(
            task_preview="fix it",
            classified={"tier": "implement", "reason": "local feature"},
            skipped=["claude-fable-5.1"],
            total_cost_usd=0.53,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last.json"
            save_trace(trace, path)
            loaded = load_trace(path)
        rendered = format_why(loaded)
        self.assertIn("classified: local feature -> implement", rendered)
        self.assertIn("skipped: claude-fable-5.1", rendered)
        self.assertIn("total: $0.53", rendered)

    def test_reviewer_protocol_excludes_escalate_line_from_defects(self) -> None:
        verdict, defects = parse_reviewer_verdict(
            "REJECT\n- breaks empty input\nESCALATE: yes"
        )
        self.assertEqual("REJECT", verdict)
        self.assertEqual(["breaks empty input"], defects)

    def test_same_task_harden_failure_is_detected_from_trace(self) -> None:
        task = "finish the parser"
        trace = RunTrace(
            task_preview=task,
            task_hash=task_hash(task),
            classified={"tier": "harden", "reason": "repo-spanning work"},
            attempts=[RunAttempt(
                role="reviewer", tier="harden", model="claude-sonnet-5",
                effort="high", status="reject",
            )],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "last.json"
            save_trace(trace, path)
            self.assertTrue(same_task_failed_harden(task, path))
            self.assertFalse(same_task_failed_harden("another task", path))


if __name__ == "__main__":
    unittest.main()
