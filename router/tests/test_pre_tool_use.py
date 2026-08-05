"""Tests for the pre_tool_use "Ringer" hook -- no network calls."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))

import pre_tool_use as ringer  # noqa: E402

CAP = 100  # tiny cap for tests: 100 tokens == 400 bytes


class RingerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cwd = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _write(self, name: str, num_bytes: int) -> str:
        path = Path(self.cwd) / name
        path.write_bytes(b"x" * num_bytes)
        return str(path)


class EstimateTokensTests(RingerTestCase):
    def test_estimate_tokens_basic(self) -> None:
        self.assertEqual(ringer.estimate_tokens(400), 100)

    def test_estimate_tokens_floors_at_zero(self) -> None:
        self.assertEqual(ringer.estimate_tokens(0), 0)


class CheckReadTests(RingerTestCase):
    def test_small_file_allowed(self) -> None:
        path = self._write("small.txt", 100)
        reason = ringer.check_read({"file_path": path}, self.cwd, cap_tokens=CAP)
        self.assertIsNone(reason)

    def test_large_file_denied(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_read({"file_path": path}, self.cwd, cap_tokens=CAP)
        self.assertIsNotNone(reason)
        self.assertIn(path, reason)
        self.assertIn("250", reason)  # 1000 bytes / 4 == 250 estimated tokens

    def test_large_file_with_limit_allowed(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_read(
            {"file_path": path, "limit": 50}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNone(reason)

    def test_large_file_with_offset_allowed(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_read(
            {"file_path": path, "offset": 10}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNone(reason)

    def test_missing_file_path_allowed(self) -> None:
        self.assertIsNone(ringer.check_read({}, self.cwd, cap_tokens=CAP))

    def test_nonexistent_file_allowed(self) -> None:
        missing = str(Path(self.cwd) / "does-not-exist.txt")
        reason = ringer.check_read({"file_path": missing}, self.cwd, cap_tokens=CAP)
        self.assertIsNone(reason)

    def test_relative_path_resolved_against_cwd(self) -> None:
        self._write("big.txt", 1000)
        reason = ringer.check_read({"file_path": "big.txt"}, self.cwd, cap_tokens=CAP)
        self.assertIsNotNone(reason)


class CheckBashTests(RingerTestCase):
    def test_bare_cat_of_large_file_denied(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_bash({"command": f"cat {path}"}, self.cwd, cap_tokens=CAP)
        self.assertIsNotNone(reason)

    def test_bare_cat_of_small_file_allowed(self) -> None:
        path = self._write("small.txt", 100)
        reason = ringer.check_bash({"command": f"cat {path}"}, self.cwd, cap_tokens=CAP)
        self.assertIsNone(reason)

    def test_piped_cat_allowed(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_bash(
            {"command": f"cat {path} | head -5"}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNone(reason)

    def test_redirected_cat_allowed(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_bash(
            {"command": f"cat {path} > out.txt"}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNone(reason)

    def test_unrelated_command_allowed(self) -> None:
        reason = ringer.check_bash({"command": "git status"}, self.cwd, cap_tokens=CAP)
        self.assertIsNone(reason)

    def test_quoted_path_matched(self) -> None:
        path = self._write("big file.txt", 1000)
        reason = ringer.check_bash(
            {"command": f'cat "{path}"'}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNotNone(reason)


class CheckPowershellTests(RingerTestCase):
    def test_get_content_of_large_file_denied(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_powershell(
            {"command": f"Get-Content {path}"}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNotNone(reason)

    def test_type_of_large_file_denied(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_powershell(
            {"command": f"type {path}"}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNotNone(reason)

    def test_piped_get_content_allowed(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.check_powershell(
            {"command": f"Get-Content {path} | Select-Object -First 5"},
            self.cwd,
            cap_tokens=CAP,
        )
        self.assertIsNone(reason)


class EvaluateDispatchTests(RingerTestCase):
    def test_dispatches_read(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.evaluate("Read", {"file_path": path}, self.cwd, cap_tokens=CAP)
        self.assertIsNotNone(reason)

    def test_dispatches_bash(self) -> None:
        path = self._write("big.txt", 1000)
        reason = ringer.evaluate(
            "Bash", {"command": f"cat {path}"}, self.cwd, cap_tokens=CAP
        )
        self.assertIsNotNone(reason)

    def test_unhandled_tool_allowed(self) -> None:
        reason = ringer.evaluate("Grep", {"pattern": "foo"}, self.cwd, cap_tokens=CAP)
        self.assertIsNone(reason)


class MainStdinTests(RingerTestCase):
    def _run_main(self, payload: dict) -> tuple[int, dict | None]:
        stdin = io.StringIO(json.dumps(payload))
        stdout = io.StringIO()
        old_stdin, old_stdout = sys.stdin, sys.stdout
        sys.stdin, sys.stdout = stdin, stdout
        try:
            code = ringer.main()
        finally:
            sys.stdin, sys.stdout = old_stdin, old_stdout
        out = stdout.getvalue().strip()
        return code, (json.loads(out) if out else None)

    def test_main_allows_small_read(self) -> None:
        path = self._write("small.txt", 100)
        code, out = self._run_main(
            {"tool_name": "Read", "tool_input": {"file_path": path}, "cwd": self.cwd}
        )
        self.assertEqual(code, 0)
        self.assertIsNone(out)

    def test_main_denies_large_read(self) -> None:
        path = self._write("big.txt", 100_000)  # well over the real default cap
        code, out = self._run_main(
            {"tool_name": "Read", "tool_input": {"file_path": path}, "cwd": self.cwd}
        )
        self.assertEqual(code, 0)
        self.assertIsNotNone(out)
        self.assertEqual(
            out["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("Ringer", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_main_malformed_stdin_fails_open(self) -> None:
        stdin = io.StringIO("not json")
        old_stdin = sys.stdin
        sys.stdin = stdin
        try:
            code = ringer.main()
        finally:
            sys.stdin = old_stdin
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
