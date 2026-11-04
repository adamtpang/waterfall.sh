"""Tests for waterfall tabs (no host launch, no network)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "router"))

import tabs  # noqa: E402
from cli import build_parser  # noqa: E402


class ResolveProjectTests(unittest.TestCase):
    def test_resolves_aether_child(self):
        root = Path(tempfile.mkdtemp())
        child = root / "waterfall.sh"
        child.mkdir()
        found = tabs.resolve_project("waterfall.sh", root)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "waterfall.sh")
        self.assertEqual(found.path, child.resolve())

    def test_missing_name_returns_none(self):
        root = Path(tempfile.mkdtemp())
        self.assertIsNone(tabs.resolve_project("nope", root))


class FleetTests(unittest.TestCase):
    def test_fleet_falls_back_to_aether_root(self):
        root = Path(tempfile.mkdtemp())
        with mock.patch.object(tabs, "load_json", return_value={}):
            fleet = tabs.list_fleet(root)
        self.assertEqual(len(fleet), 1)
        self.assertEqual(fleet[0].path, root.resolve())


class WtCommandTests(unittest.TestCase):
    def test_wt_mux_builds_semicolon_tabs(self):
        a = tabs.TabProject("one", Path(r"C:\tmp\one"))
        b = tabs.TabProject("two", Path(r"C:\tmp\two"))
        with mock.patch.object(tabs.shutil, "which", return_value=r"C:\bin\grok.exe"):
            cmd = tabs.build_wt_command([a, b], "grok", new_window=True)
        self.assertEqual(cmd[0], "wt")
        self.assertIn("-w", cmd)
        self.assertIn("new", cmd)
        self.assertEqual(cmd.count(";"), 1)
        self.assertEqual(cmd.count("nt"), 2)
        self.assertIn("--cwd", cmd)
        self.assertIn(r"C:\tmp\one", cmd)
        self.assertIn(r"C:\tmp\two", cmd)

    def test_unknown_agent_errors(self):
        proj = tabs.TabProject("one", Path(r"C:\tmp\one"))
        with self.assertRaises(ValueError):
            tabs.build_wt_command([proj], "not-an-agent", new_window=False)


class PinMergeTests(unittest.TestCase):
    def test_pin_merges_without_wiping_store(self):
        home = Path(tempfile.mkdtemp())
        proj = home / "cuties.app"
        proj.mkdir()
        store = home / "projects.json"
        store.write_text(
            json.dumps({"pinned": [str(home / "already")], "archived": ["keep-me"], "manual": []}),
            encoding="utf-8",
        )
        with mock.patch.object(tabs, "WATERFALL_HOME", home), mock.patch.object(
            tabs, "PROJECTS_FILE", store
        ):
            tabs.pin_project(str(proj))
            data = json.loads(store.read_text(encoding="utf-8"))
        self.assertIn("keep-me", data["archived"])
        self.assertTrue(any(Path(p).name == "cuties.app" for p in data["pinned"]))


class CliWireTests(unittest.TestCase):
    def test_tabs_is_a_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["tabs", "list", "--dry-run"])
        self.assertEqual(args.command, "tabs")
        self.assertEqual(args.tabs_command, "list")
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()
