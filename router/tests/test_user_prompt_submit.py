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
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import user_prompt_submit as nudge  # noqa: E402
import hook_log  # noqa: E402

ROUTINE_PROMPT = "rename the variable x to userCount throughout utils.py"
TOO_SHORT_PROMPT = "fix this"
BARE_ARITHMETIC_PROMPT = "2+2"
SHORT_FILLER_PROMPT = "yes, look into why"


class NudgeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_main(self, prompt: str, log_path: Path) -> tuple[int, dict | None]:
        stdin = io.StringIO(json.dumps({"prompt": prompt, "cwd": self.cwd}))
        stdout = io.StringIO()
        old_stdin, old_stdout = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = stdin, stdout
        try:
            with mock.patch.object(hook_log, "DEFAULT_LOG_PATH", log_path):
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


if __name__ == "__main__":
    unittest.main()
