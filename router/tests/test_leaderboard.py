"""Bang-for-buck aggregation and feed tests."""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import leaderboard


class ValueFormulaTests(unittest.TestCase):
    def test_formula_uses_one_cent_floor_and_normalizes_to_board_max(self) -> None:
        rows = leaderboard.apply_value_scores([
            {"model": "a", "quality": 80, "cost_per_solved": 0.0},
            {"model": "b", "quality": 100, "cost_per_solved": 1.0},
        ])
        by_model = {row["model"]: row for row in rows}
        self.assertEqual(100.0, by_model["a"]["value"])
        self.assertEqual(1.2, by_model["b"]["value"])
        self.assertEqual(8000.0, by_model["a"]["value_raw"])

    def test_seed_board_is_value_sorted(self) -> None:
        board = leaderboard.build_leaderboard(
            runs_dir=Path("this-directory-does-not-exist"),
            generated_at="2026-09-03T00:00:00+00:00",
        )
        values = [row["value"] for row in board["rows"]]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual("DeepSeek V4 Flash", board["rows"][0]["model"])
        self.assertEqual("snapshot-2026-09-03", board["rows"][0]["source"])
        self.assertEqual(list(range(1, 11)), [row["rank"] for row in board["rows"]])


class SnapshotTests(unittest.TestCase):
    def test_seed_is_dated_and_explicitly_not_waterfall_measurement(self) -> None:
        snapshot = leaderboard.load_snapshot()
        self.assertEqual("2026-09-03", snapshot["as_of"])
        self.assertEqual(10, len(snapshot["rows"]))
        self.assertIn("Priors", snapshot["disclaimer"])
        self.assertIn("Replace", snapshot["disclaimer"])

    def test_fable_is_visible_but_not_the_default_value_winner(self) -> None:
        board = leaderboard.build_leaderboard(runs_dir=Path("missing"))
        fable = [row for row in board["rows"] if row["model"] == "Claude Fable 5.1"]
        self.assertEqual(2, len(fable))
        self.assertGreaterEqual(max(row["quality"] for row in fable), 96)
        self.assertTrue(all(row["rank"] > 1 for row in fable))


class HarnessAggregationTests(unittest.TestCase):
    def test_harness_row_replaces_matching_prior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp)
            path = runs / "2026-09-04.jsonl"
            records = [
                {
                    "record_type": "bench_attempt", "timestamp": "2026-09-04T01:00:00Z",
                    "suite": "coding-smoketest", "task_id": "one", "category": "bugfix",
                    "model": "grok-4.6", "effort": "medium", "cost_usd": 0.10, "passed": True,
                },
                {
                    "record_type": "bench_attempt", "timestamp": "2026-09-04T02:00:00Z",
                    "suite": "coding-smoketest", "task_id": "two", "category": "feature",
                    "model": "grok-4.6", "effort": "medium", "cost_usd": 0.30, "passed": False,
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
            board = leaderboard.build_leaderboard(
                runs_dir=runs, generated_at="2026-09-04T03:00:00Z"
            )

        grok = next(row for row in board["rows"] if row["model"] == "Grok 4.6" and row["effort"] == "medium")
        self.assertEqual("harness", grok["source"])
        self.assertEqual(2, grok["n"])
        self.assertEqual(0.50, grok["solved_pct"])
        self.assertEqual(0.20, grok["cost_per_attempt"])
        self.assertEqual(0.10, grok["cost_per_solved"])
        self.assertEqual(50.0, grok["quality"])
        self.assertEqual(2.0, grok["price_in"])

    def test_category_quality_is_equal_weight_not_volume_weighted(self) -> None:
        records = [
            {"category": "bugfix", "passed": True},
            {"category": "bugfix", "passed": True},
            {"category": "bugfix", "passed": True},
            {"category": "review", "passed": False},
        ]
        self.assertEqual(50.0, leaderboard._quality_from_records(records))


class FeedTests(unittest.TestCase):
    def test_csv_contains_public_columns(self) -> None:
        board = leaderboard.build_leaderboard(
            runs_dir=Path("missing"), generated_at="2026-09-03T00:00:00Z"
        )
        rows = list(csv.DictReader(io.StringIO(leaderboard.leaderboard_csv(board))))
        self.assertEqual(10, len(rows))
        self.assertEqual(list(leaderboard.CSV_FIELDS), list(rows[0]))
        self.assertEqual("DeepSeek V4 Flash", rows[0]["model"])

    def test_publish_writes_json_and_csv(self) -> None:
        board = leaderboard.build_leaderboard(
            runs_dir=Path("missing"), generated_at="2026-09-03T00:00:00Z"
        )
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "api" / "leaderboard.json"
            csv_path = Path(tmp) / "api" / "leaderboard.csv"
            leaderboard.publish_leaderboard(board, json_path, csv_path)
            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            csv_text = csv_path.read_text(encoding="utf-8")
        self.assertEqual(10, len(parsed["rows"]))
        self.assertIn("cost_per_attempt", csv_text.splitlines()[0])


class PublicSurfaceTests(unittest.TestCase):
    def test_static_route_assets_and_discovery_links_exist(self) -> None:
        root = Path(__file__).resolve().parents[2]
        html = (root / "leaderboard.html").read_text(encoding="utf-8")
        index = (root / "index.html").read_text(encoding="utf-8")
        sitemap = (root / "sitemap.xml").read_text(encoding="utf-8")
        llms = (root / "llms.txt").read_text(encoding="utf-8")
        vercel = json.loads((root / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn('href="/leaderboard.css"', html)
        self.assertIn('src="/leaderboard.js"', html)
        self.assertIn('href="/leaderboard"', index)
        self.assertIn("https://waterfall.sh/leaderboard", sitemap)
        self.assertIn("api/leaderboard.json", llms)
        self.assertIn(
            {"source": "/badge/value.svg", "destination": "/api/badge"},
            vercel["rewrites"],
        )
        self.assertIn(
            {"source": "/api/leaderboard.json", "destination": "/api/leaderboard-feed?format=json"},
            vercel["rewrites"],
        )
        self.assertIn(
            {"source": "/api/leaderboard.csv", "destination": "/api/leaderboard-feed?format=csv"},
            vercel["rewrites"],
        )

    def test_public_leaderboard_assets_use_no_em_dashes_or_inline_code(self) -> None:
        root = Path(__file__).resolve().parents[2]
        for relative in (
            "leaderboard.html", "leaderboard.css", "leaderboard.js",
            "api/leaderboard.json", "api/leaderboard.csv", "api/badge.js",
            "api/leaderboard-feed.js",
        ):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertNotIn("—", text, relative)
        html = (root / "leaderboard.html").read_text(encoding="utf-8")
        self.assertNotIn("<style", html)
        self.assertIsNone(re.search(r"<script(?![^>]+\bsrc=)", html))

    def test_readme_routing_policy_is_exactly_15_lines(self) -> None:
        root = Path(__file__).resolve().parents[2]
        readme = (root / "README.md").read_text(encoding="utf-8")
        section = readme.split("## Routing policy", 1)[1].split("\n## ", 1)[0]
        numbered = re.findall(r"^\d+\. ", section, re.MULTILINE)
        self.assertEqual(15, len(numbered))


if __name__ == "__main__":
    unittest.main()
