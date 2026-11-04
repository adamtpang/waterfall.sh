"""Tests for Aether project catalog and pick CLI wiring."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "router"))

import projects  # noqa: E402
from cli import build_parser  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_lists_marker_dirs_and_skips_junk(self):
        root = Path(tempfile.mkdtemp())
        good = root / "lightmark.app"
        good.mkdir()
        (good / "GROK_CONTINUE_FROM_CLAUDE.md").write_text("# hi\n", encoding="utf-8")
        via_claude = root / "quantus.com"
        via_claude.mkdir()
        (via_claude / "CLAUDE.md").write_text("# q\n", encoding="utf-8")
        junk = root / "check-quantus"
        junk.mkdir()
        (junk / "GROK_CONTINUE_FROM_CLAUDE.md").write_text("# no\n", encoding="utf-8")
        hidden = root / ".git"
        hidden.mkdir()
        with mock.patch.object(projects.tabs, "list_fleet", return_value=[]):
            found = projects.list_projects(root)
        names = {p.name for p in found}
        self.assertIn("lightmark.app", names)
        self.assertIn("quantus.com", names)
        self.assertNotIn("check-quantus", names)
        self.assertNotIn(".git", names)


class BareLaunchTests(unittest.TestCase):
    def test_empty_argv_opens_board(self):
        import cli
        with mock.patch.object(cli, "open_board", return_value=0) as opened:
            self.assertEqual(cli.main([]), 0)
            opened.assert_called_once()


class BoardTurnTests(unittest.TestCase):
    def test_empty_prompt_is_not_handled(self):
        from board_turn import run_turn
        out = run_turn("")
        self.assertFalse(out["handled"])
        self.assertEqual(out["routing"], "claude")

    def test_classify_returns_routing(self):
        from board_turn import run_turn
        out = run_turn("rename this variable from foo to bar", route=False)
        self.assertIn(out["routing"], {"free", "split", "claude"})
        self.assertFalse(out["handled"])


class CliPickTests(unittest.TestCase):
    def test_pick_is_wired(self):
        parser = build_parser()
        args = parser.parse_args(["pick", "lightmark.app", "--action", "tab"])
        self.assertEqual(args.command, "pick")
        self.assertEqual(args.action, "tab")
        self.assertEqual(args.project, "lightmark.app")


if __name__ == "__main__":
    unittest.main()
