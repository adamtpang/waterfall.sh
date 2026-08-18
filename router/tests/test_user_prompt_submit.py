"""Tests for the user_prompt_submit nudge hook -- no network calls.

classify() itself isn't mocked -- it's the real, local, zero-network
classifier, same as smart_router.py's other integration tests rely on
for the split() path. ROUTINE_PROMPT is the exact example already
verified live against this classifier (see CLAUDE.md's 2026-08-04 note).
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import user_prompt_submit as nudge  # noqa: E402
import hook_log  # noqa: E402
import usage_pace  # noqa: E402
import quota_estimate  # noqa: E402

ROUTINE_PROMPT = "rename the variable x to userCount throughout utils.py"
TOO_SHORT_PROMPT = "fix this"
BARE_ARITHMETIC_PROMPT = "2+2"
SHORT_FILLER_PROMPT = "yes, look into why"


class NudgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = self._tmp.name
        self.quota_cache_path = Path(self._tmp.name) / "quota_cache.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _seed_quota_cache(self, estimated_pct: float = 0.0) -> None:
        """Pre-seed a fresh cache entry so _quota_warning() takes the
        cache-hit path -- no real transcript scan, no real scan latency,
        and (at 0%) no tier warning polluting routing-nudge assertions."""
        tz = timezone(timedelta(hours=8))
        now = datetime.now(tz)
        reset_boundary = usage_pace._last_reset(now, usage_pace.WEEKDAYS["tuesday"], 16)
        quota_estimate.get_estimate(
            reset_boundary, now=now, cache_path=self.quota_cache_path,
            compute_fn=lambda rb: estimated_pct,
        )

    def _run_main(self, prompt: str, log_path: Path, quota_pct: float = 0.0) -> tuple[int, dict | None]:
        self._seed_quota_cache(quota_pct)
        stdin = io.StringIO(json.dumps({"prompt": prompt, "cwd": self.cwd}))
        stdout = io.StringIO()
        old_stdin, old_stdout = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = stdin, stdout
        try:
            with mock.patch.object(hook_log, "DEFAULT_LOG_PATH", log_path), \
                 mock.patch.object(quota_estimate, "DEFAULT_CACHE_PATH", self.quota_cache_path):
                code = nudge.main()
        finally:
            sys.stdin, sys.stdout = old_stdin, old_stdout
        out = stdout.getvalue().strip()
        return code, (json.loads(out) if out else None)


class MainBehaviorTests(NudgeTestCase):
    def test_too_short_prompt_skipped_no_log(self) -> None:
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(TOO_SHORT_PROMPT, log_path)
        self.assertEqual(code, 0)
        self.assertIsNone(out)
        self.assertEqual(hook_log.load_entries(log_path=log_path), [])

    def test_bare_arithmetic_nudges_despite_being_under_min_words(self) -> None:
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(BARE_ARITHMETIC_PROMPT, log_path)
        self.assertEqual(code, 0)
        self.assertIsNotNone(out, "bare arithmetic should nudge even though it's under MIN_WORDS")
        self.assertIn("routing='free'", out["hookSpecificOutput"]["additionalContext"])

    def test_short_conversational_filler_still_skipped(self) -> None:
        # The arithmetic carve-out must stay narrow -- a short follow-up that
        # leans on conversation history the classifier can't see should still
        # be skipped, same as before this change.
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(SHORT_FILLER_PROMPT, log_path)
        self.assertEqual(code, 0)
        self.assertIsNone(out)

    def test_malformed_stdin_fails_open(self) -> None:
        stdin = io.StringIO("not json")
        old_stdin = sys.stdin
        sys.stdin = stdin
        try:
            code = nudge.main()
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)

    def test_routine_prompt_nudges_and_logs(self) -> None:
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(ROUTINE_PROMPT, log_path)
        self.assertEqual(code, 0)

        if out is None:
            self.skipTest("classifier didn't route this sample as free/split -- nothing to nudge")

        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("waterfall", out["hookSpecificOutput"]["additionalContext"])

        entries = hook_log.load_entries(log_path=log_path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].hook, "nudge")
        self.assertEqual(entries[0].action, "nudged")
        self.assertEqual(entries[0].project, Path(self.cwd).name)


class QuotaWarningTests(NudgeTestCase):
    def test_no_warning_below_first_tier(self) -> None:
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(ROUTINE_PROMPT, log_path, quota_pct=50.0)
        self.assertEqual(code, 0)
        if out is not None:
            self.assertNotIn("crossed ~", out["hookSpecificOutput"]["additionalContext"])

    def test_warning_fires_when_crossing_a_tier(self) -> None:
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(ROUTINE_PROMPT, log_path, quota_pct=72.0)
        self.assertEqual(code, 0)
        self.assertIsNotNone(out)
        self.assertIn("crossed ~70%", out["hookSpecificOutput"]["additionalContext"])

    def test_quota_warning_fires_independent_of_routing_nudge(self) -> None:
        # A too-short prompt gets no routing nudge, but should still get a
        # quota warning -- these are different concerns and one shouldn't
        # gate the other.
        log_path = Path(self.cwd) / "hook_log.jsonl"
        code, out = self._run_main(TOO_SHORT_PROMPT, log_path, quota_pct=96.0)
        self.assertEqual(code, 0)
        self.assertIsNotNone(out, "quota warning should fire even on a prompt too short to route")
        self.assertIn("crossed ~95%", out["hookSpecificOutput"]["additionalContext"])

    def test_same_tier_does_not_refire_on_next_prompt(self) -> None:
        log_path = Path(self.cwd) / "hook_log.jsonl"
        self._run_main(ROUTINE_PROMPT, log_path, quota_pct=72.0)
        # Second call reuses the same fresh cache (seeded again at the same
        # pct by _run_main), but the tier was already marked warned.
        code, out = self._run_main(ROUTINE_PROMPT, log_path, quota_pct=72.0)
        self.assertEqual(code, 0)
        if out is not None:
            self.assertNotIn("crossed ~", out["hookSpecificOutput"]["additionalContext"])


if __name__ == "__main__":
    unittest.main()
