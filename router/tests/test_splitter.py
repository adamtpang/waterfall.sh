"""Regression tests for splitting a mixed prompt (2026-11-07 bug report from
themain.quest): `route` labelled "split" but sent the whole prompt to both sides,
because a one-sentence "do X, then explain Y" never got divided."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from classifier import PromptClassifier, TaskSplitter
from openrouter_api_client import GenerateResult

EASY = "Write a Python function that reverses a string"
HARD = "explain the tradeoffs of a lock-free queue design for our distributed scheduler"
MIXED = f"{EASY}, then {HARD}"


class MixedPromptSplitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = PromptClassifier()
        self.splitter = TaskSplitter(self.classifier)

    def test_mixed_prompt_is_classified_split(self):
        self.assertEqual(self.classifier.classify(MIXED).routing, "split")

    def test_only_the_easy_part_goes_to_the_cheap_model(self):
        result = self.splitter.split(MIXED, self.classifier.classify(MIXED))
        self.assertEqual(result.free_prompt, EASY)
        self.assertNotIn("lock-free", result.free_prompt)

    def test_only_the_hard_part_stays_with_claude(self):
        result = self.splitter.split(MIXED, self.classifier.classify(MIXED))
        self.assertIn(HARD, result.claude_prompt)
        self.assertNotIn("reverses a string", result.claude_prompt)
        self.assertIn("{free_model_results}", result.claude_prompt)

    def test_savings_count_task_text_not_the_results_header(self):
        result = self.splitter.split(MIXED, self.classifier.classify(MIXED))
        self.assertGreater(result.savings_pct, 0.2)
        self.assertLess(result.savings_pct, 1.0)

    def test_clause_joiners_split(self):
        for joiner in (", then ", "; then ", " and then ", "; "):
            parts = TaskSplitter._split_sentences(f"{EASY}{joiner}{HARD}")
            self.assertEqual(parts, [EASY, HARD], joiner)

    def test_hard_prompt_with_a_routine_clause_still_splits(self):
        # No cheap-work keyword in the first clause: it used to route all of it to Claude.
        prompt = ("Write a JavaScript function that checks if a number is prime, then explain the "
                  "tradeoffs of sharding our Postgres database for distributed multi-tenant scalability")
        cls = self.classifier.classify(prompt)
        self.assertEqual(cls.routing, "split")
        result = self.splitter.split(prompt, cls)
        self.assertIn("prime", result.free_prompt)
        self.assertNotIn("sharding", result.free_prompt)
        self.assertIn("sharding", result.claude_prompt)

    def test_hard_prompt_without_a_routine_clause_stays_claude(self):
        prompt = "Refactor our auth middleware across 6 files to fix an intermittent race condition in session refresh."
        self.assertEqual(self.classifier.classify(prompt).routing, "claude")

    def test_and_inside_a_word_is_not_a_joiner(self):
        self.assertEqual(TaskSplitter._split_sentences("Rebrand then ship"), ["Rebrand then ship"])

    def test_code_blocks_are_not_split_on_joiners(self):
        prompt = "Fix this:\n```\na = 1; then_b = 2\n```"
        joined = " ".join(TaskSplitter._split_sentences(prompt))
        self.assertIn("a = 1; then_b = 2", joined)


class DryRunOutputTests(unittest.TestCase):
    def _dry_run(self, prompt: str) -> str:
        import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["route", "--dry-run", "--no-log", prompt])
        return out.getvalue()

    def test_dry_run_shows_each_part_on_its_own_side(self):
        out = self._dry_run(MIXED)
        free_side = out.split("--- would send to free/cheap model ---")[1].split("--- stays with Claude ---")[0]
        claude_side = out.split("--- stays with Claude ---")[1]
        self.assertIn("reverses a string", free_side)
        self.assertNotIn("lock-free", free_side)
        self.assertIn("lock-free", claude_side)
        self.assertNotIn("reverses a string", claude_side)
        self.assertIn("model tier: small", out)

    def test_fully_routed_prompt_does_not_repeat_it_under_claude(self):
        out = self._dry_run("Write a Python function that reverses a string")
        claude_side = out.split("--- stays with Claude ---")[1]
        self.assertNotIn("reverses a string", claude_side)


class RouteWithApiTierTests(unittest.TestCase):
    def test_tier_and_effort_follow_the_routed_text(self):
        import os
        os.environ["WATERFALL_JEV"] = "0"
        from smart_router import SmartRouter
        gen = GenerateResult(text="def rev(s): return s[::-1]", model="m", input_tokens=1,
                             output_tokens=1, cost_usd=0.0, elapsed_sec=0.0)
        router = SmartRouter(cache=None, use_jev=False)
        router._cache = None
        with mock.patch("openrouter_api_client.OpenRouterClient") as client:
            client.return_value.generate_with_usage.return_value = gen
            res = router.route_with_api(MIXED)
        kwargs = client.return_value.generate_with_usage.call_args.kwargs
        self.assertEqual(client.return_value.generate_with_usage.call_args.args[0], EASY)
        self.assertEqual(kwargs["tier"], "small")
        self.assertEqual(kwargs["output_effort"], "low")
        self.assertIn(HARD, res.final_claude_prompt)
        self.assertIn("def rev(s)", res.final_claude_prompt)
        self.assertNotIn("reverses a string", res.final_claude_prompt.split("Please handle the remaining work:")[1])


if __name__ == "__main__":
    unittest.main()


class RouteSavingsTests(unittest.TestCase):
    def test_savings_count_the_prompt_read_and_the_answer_written(self):
        from tracker import estimate_route_savings
        s = estimate_route_savings("a" * 400, "b" * 400, 0.0)
        # 100 tokens in at $3/M + 100 tokens out at $15/M
        self.assertAlmostEqual(s["claude_equivalent_usd"], 0.0018)
        self.assertAlmostEqual(s["saved_usd"], 0.0018)
        self.assertEqual(s["saved_per_1000_usd"], 1.8)
        self.assertEqual(s["tokens_off_claude"], 200)

    def test_savings_subtract_what_the_cheap_model_cost_and_never_go_negative(self):
        from tracker import estimate_route_savings
        self.assertAlmostEqual(estimate_route_savings("a" * 400, "b" * 400, 0.0008)["saved_usd"], 0.001)
        self.assertEqual(estimate_route_savings("a" * 4, "", 5.0)["saved_usd"], 0.0)
