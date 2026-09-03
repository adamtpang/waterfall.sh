"""Executable smoke-harness tests, using tiny fixtures and fake models."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bench


CLAMP_PATCH = """```diff
diff --git a/math_utils.py b/math_utils.py
--- a/math_utils.py
+++ b/math_utils.py
@@ -1,2 +1,3 @@
 def clamp(value, low, high):
+    low, high = sorted((low, high))
     return min(high, max(low, value))
```
"""


class FakeGenerator:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = iter(outputs)
        self.calls = []

    def generate(self, prompt: str, model: str, effort: str, system: str):
        self.calls.append((prompt, model, effort, system))
        return SimpleNamespace(
            text=next(self.outputs), input_tokens=100, output_tokens=40,
            cache_read_tokens=20, cost_usd=0.05,
        )


class SuiteTests(unittest.TestCase):
    def test_coding_smoketest_has_the_required_15_task_mix(self) -> None:
        suite = bench.load_suite("coding-smoketest")
        counts = {}
        for task in suite["tasks"]:
            counts[task["category"]] = counts.get(task["category"], 0) + 1
        self.assertEqual(15, len(suite["tasks"]))
        self.assertEqual(bench.EXPECTED_CATEGORY_COUNTS, counts)

    def test_suite_paths_cannot_escape_fixture(self) -> None:
        with self.assertRaises(ValueError):
            bench._safe_relative("../outside.py")
        with self.assertRaises(ValueError):
            bench._safe_relative("C:/outside.py")


class PatchVerificationTests(unittest.TestCase):
    def test_extract_and_execute_real_fixture_tests(self) -> None:
        task = bench.load_suite("coding-smoketest")["tasks"][0]
        patch = bench.extract_diff(CLAMP_PATCH)
        passed, reason = bench.verify_patch(task, patch)
        self.assertTrue(passed, reason)
        self.assertEqual("tests passed", reason)

    def test_editing_tests_is_rejected_before_apply(self) -> None:
        task = bench.load_suite("coding-smoketest")["tasks"][0]
        patch = "diff --git a/test_math_utils.py b/test_math_utils.py\n--- a/test_math_utils.py\n+++ b/test_math_utils.py\n@@ -1 +1 @@\n-import unittest\n+import unittest\n"
        passed, reason = bench.verify_patch(task, patch)
        self.assertFalse(passed)
        self.assertIn("outside the allowed list", reason)


class AttemptTests(unittest.TestCase):
    def test_patch_attempt_runs_tests_and_independent_review(self) -> None:
        task = bench.load_suite("coding-smoketest")["tasks"][0]
        fake = FakeGenerator([CLAMP_PATCH, "PASS\nESCALATE: no"])
        attempt = bench.run_attempt("coding-smoketest", task, "deepseek-v4-flash", generator=fake)
        self.assertTrue(attempt.passed, attempt.failure_reason)
        self.assertEqual("grok-4.6", attempt.reviewer_model)
        self.assertNotEqual(fake.calls[0][1], fake.calls[1][1])
        self.assertEqual(200, attempt.input_tokens)
        self.assertEqual(80, attempt.output_tokens)
        self.assertEqual(40, attempt.cache_reads)
        self.assertEqual(0.10, attempt.cost_usd)

    def test_review_only_task_uses_expected_verdict_gate(self) -> None:
        task = bench.load_suite("coding-smoketest")["tasks"][10]
        fake = FakeGenerator(["REJECT\n- SQL injection permits arbitrary queries\nESCALATE: yes"])
        attempt = bench.run_attempt("coding-smoketest", task, "grok-4.6", generator=fake)
        self.assertTrue(attempt.passed, attempt.failure_reason)
        self.assertEqual("REJECT", attempt.reviewer_verdict)
        self.assertEqual("expected-review-verdict", attempt.verification)

    def test_run_suite_appends_leaderboard_ready_jsonl(self) -> None:
        suite = bench.load_suite("coding-smoketest")
        fake = FakeGenerator([CLAMP_PATCH, "PASS\nESCALATE: no"])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "2026-09-03.jsonl"
            attempts = bench.run_suite(
                suite, ["deepseek-v4-flash"], output_path=output,
                limit=1, generator=fake,
            )
            record = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(1, len(attempts))
        required = {
            "model", "effort", "input_tokens", "output_tokens", "cache_reads",
            "cost_at_list_cache_usd", "wall_time", "passed", "escalate_count",
            "reviewer_verdict",
        }
        self.assertFalse(required - set(record))


if __name__ == "__main__":
    unittest.main()
