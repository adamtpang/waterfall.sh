"""Tests for install.py's hook-merging logic -- no git/pip/network calls.

clone_or_update() and install_dependencies() are real system operations
(git, pip) and aren't unit-tested here; this covers the part that's
actually risky to get wrong -- merging into a stranger's existing
~/.claude/settings.json without clobbering it.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import install  # noqa: E402


class HookEntryTests(unittest.TestCase):
    def test_entry_without_matcher(self) -> None:
        entry = install._hook_entry(Path("/repo/router/hooks/x.py"))
        self.assertNotIn("matcher", entry)
        self.assertIn("/repo/router/hooks/x.py", entry["hooks"][0]["command"])

    def test_entry_with_matcher(self) -> None:
        entry = install._hook_entry(Path("/repo/router/hooks/x.py"), matcher="Read|Bash")
        self.assertEqual(entry["matcher"], "Read|Bash")


class EntryAlreadyPresentTests(unittest.TestCase):
    def test_absent_in_empty_list(self) -> None:
        self.assertFalse(install._entry_already_present([], Path("/repo/x.py")))

    def test_detects_present_entry(self) -> None:
        existing = [install._hook_entry(Path("/repo/router/hooks/x.py"))]
        self.assertTrue(install._entry_already_present(existing, Path("/repo/router/hooks/x.py")))

    def test_absent_for_different_path(self) -> None:
        existing = [install._hook_entry(Path("/repo/router/hooks/x.py"))]
        self.assertFalse(install._entry_already_present(existing, Path("/repo/router/hooks/y.py")))


class WireHooksTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.settings_path = Path(self._tmp.name) / "settings.json"
        self.repo_dir = Path(self._tmp.name) / "repo"
        self._patch = mock.patch.object(install, "CLAUDE_SETTINGS", self.settings_path)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_creates_settings_file_when_missing(self) -> None:
        install.wire_hooks(self.repo_dir)
        self.assertTrue(self.settings_path.exists())
        data = json.loads(self.settings_path.read_text())
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)

    def test_preserves_existing_unrelated_keys(self) -> None:
        self.settings_path.write_text(json.dumps({
            "permissions": {"allow": ["Read"]},
            "theme": "dark",
        }))
        install.wire_hooks(self.repo_dir)
        data = json.loads(self.settings_path.read_text())
        self.assertEqual(data["permissions"], {"allow": ["Read"]})
        self.assertEqual(data["theme"], "dark")
        self.assertIn("UserPromptSubmit", data["hooks"])

    def test_preserves_existing_hook_entries_from_other_tools(self) -> None:
        self.settings_path.write_text(json.dumps({
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"type": "command", "command": "some-other-tool.sh"}]}
                ]
            }
        }))
        install.wire_hooks(self.repo_dir)
        data = json.loads(self.settings_path.read_text())
        commands = [h["command"] for entry in data["hooks"]["PreToolUse"] for h in entry["hooks"]]
        self.assertIn("some-other-tool.sh", commands)
        self.assertTrue(any("pre_tool_use.py" in c for c in commands))

    def test_idempotent_on_rerun(self) -> None:
        install.wire_hooks(self.repo_dir)
        install.wire_hooks(self.repo_dir)
        data = json.loads(self.settings_path.read_text())
        self.assertEqual(len(data["hooks"]["UserPromptSubmit"]), 1)
        self.assertEqual(len(data["hooks"]["PreToolUse"]), 1)

    def test_backs_up_existing_settings(self) -> None:
        self.settings_path.write_text(json.dumps({"theme": "dark"}))
        install.wire_hooks(self.repo_dir)
        backups = list(self.settings_path.parent.glob("settings.json.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), {"theme": "dark"})

    def test_no_backup_created_when_settings_did_not_exist(self) -> None:
        install.wire_hooks(self.repo_dir)
        backups = list(self.settings_path.parent.glob("settings.json.bak-*"))
        self.assertEqual(len(backups), 0)

    def test_invalid_existing_json_fails_loudly(self) -> None:
        self.settings_path.write_text("not json")
        with self.assertRaises(SystemExit):
            install.wire_hooks(self.repo_dir)


if __name__ == "__main__":
    unittest.main()
