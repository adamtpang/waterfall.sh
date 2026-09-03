"""Coverage rows: borrowed catalog scores must extend the board without
contaminating it."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import leaderboard
import leaderboard_coverage as cov


def _model(mid, *, prompt="0.000001", completion="0.000004", ctx=128000, aa=None, elo=None,
           efforts=None, modality="text->text", name=None):
    m = {
        "id": mid, "name": name or mid, "context_length": ctx,
        "architecture": {"modality": modality},
        "pricing": {"prompt": prompt, "completion": completion},
        "benchmarks": {},
        "reasoning": {"supported_efforts": efforts or []},
    }
    if aa is not None:
        m["benchmarks"]["artificial_analysis"] = aa
    if elo is not None:
        m["benchmarks"]["design_arena"] = [{"arena": "agents", "category": "webapps", "elo": elo}]
    return m


class CoverageRowTests(unittest.TestCase):
    def test_prefers_coding_index_then_intelligence_then_rescaled_elo(self) -> None:
        rows = cov.coverage_rows([
            _model("a/coding", aa={"coding_index": 70.0, "intelligence_index": 50.0}),
            _model("b/intel", aa={"intelligence_index": 60.0}),
            _model("c/elo-hi", elo=1300),
            _model("d/elo-lo", elo=1100),
        ])
        by = {r["model"]: r for r in rows}
        self.assertEqual((70.0, "aa:coding_index"), (by["a/coding"]["quality_borrowed"], by["a/coding"]["quality_source"]))
        self.assertEqual((60.0, "aa:intelligence_index"), (by["b/intel"]["quality_borrowed"], by["b/intel"]["quality_source"]))
        self.assertEqual("design_arena:elo_rescaled", by["c/elo-hi"]["quality_source"])
        self.assertEqual(100.0, by["c/elo-hi"]["quality_borrowed"])
        self.assertEqual(0.0, by["d/elo-lo"]["quality_borrowed"])

    def test_rows_never_carry_measured_only_fields(self) -> None:
        rows = cov.coverage_rows([_model("a/x", aa={"coding_index": 55})])
        self.assertEqual(1, len(rows))
        for forbidden in ("quality", "value", "value_raw", "cost_per_solved", "solved_pct", "rank"):
            self.assertNotIn(forbidden, rows[0], forbidden)
        self.assertEqual("catalog", rows[0]["source"])
        self.assertFalse(rows[0]["measured"])

    def test_excludes_measured_models_even_when_ids_differ_by_punctuation(self) -> None:
        rows = cov.coverage_rows(
            [_model("anthropic/claude-fable-5.1", aa={"coding_index": 90}),
             _model("other/model", aa={"coding_index": 40})],
            exclude_ids=["anthropic/claude-fable-5-1"],
        )
        self.assertEqual(["other/model"], [r["model"] for r in rows])

    def test_skips_unpriced_sentinel_small_context_and_non_text(self) -> None:
        rows = cov.coverage_rows([
            _model("skip/sentinel", prompt="-1", aa={"coding_index": 90}),
            _model("skip/unpriced", prompt=None, aa={"coding_index": 90}),
            _model("skip/tiny", ctx=2048, aa={"coding_index": 90}),
            _model("skip/image", modality="text->image", aa={"coding_index": 90}),
            # real leak from the live catalog: emits text AND images
            _model("skip/image-and-text", modality="text+image->text+image", aa={"coding_index": 90}),
            _model("skip/noscore"),
            _model("keep/me", aa={"coding_index": 10}),
            _model("keep/multimodal-in", modality="text+image->text", aa={"coding_index": 9}),
        ])
        self.assertEqual(["keep/me", "keep/multimodal-in"], [r["model"] for r in rows])

    def test_batch_variant_collapses_into_base_row(self) -> None:
        rows = cov.coverage_rows([
            _model("google/gemini-x", prompt="0.00000075", completion="0.00000375", aa={"coding_index": 76}),
            _model("google/gemini-x:batch", prompt="0.000000375", completion="0.000001875", aa={"coding_index": 76}),
            _model("other/solo", aa={"coding_index": 10}),
        ])
        self.assertEqual(["google/gemini-x", "other/solo"], [r["model"] for r in rows])
        gem = rows[0]
        self.assertEqual((0.75, 3.75), (gem["price_in"], gem["price_out"]), "base price stays the headline")
        self.assertEqual(1, len(gem["variants"]))
        self.assertEqual("batch", gem["variants"][0]["suffix"])
        self.assertEqual((0.375, 1.875), (gem["variants"][0]["price_in"], gem["variants"][0]["price_out"]))
        self.assertEqual([], rows[1]["variants"], "every row carries a variants list")

    def test_batch_without_a_base_row_stands_alone(self) -> None:
        rows = cov.coverage_rows([_model("lonely/model:batch", aa={"coding_index": 50})])
        self.assertEqual(["lonely/model:batch"], [r["model"] for r in rows])
        self.assertEqual([], rows[0]["variants"])

    def test_free_variant_collapses_and_flags_the_base_row(self) -> None:
        # folded like :batch, but the free signal must survive on the base row
        rows = cov.coverage_rows([
            _model("z-ai/glm-x", aa={"coding_index": 68}),
            _model("z-ai/glm-x:free", prompt="0", completion="0", aa={"coding_index": 68}),
            _model("paid/only", aa={"coding_index": 20}),
        ])
        self.assertEqual(["z-ai/glm-x", "paid/only"], [r["model"] for r in rows])
        glm, paid = rows
        self.assertFalse(glm["free"], "headline price stays the paid base price")
        self.assertTrue(glm["has_free_variant"])
        self.assertEqual([("free", True)], [(v["suffix"], v["free"]) for v in glm["variants"]])
        self.assertFalse(paid["has_free_variant"])

    def test_free_only_model_with_no_paid_base_stands_alone_and_is_free(self) -> None:
        rows = cov.coverage_rows([_model("lab/model:free", prompt="0", completion="0", aa={"coding_index": 40})])
        self.assertEqual(["lab/model:free"], [r["model"] for r in rows])
        self.assertTrue(rows[0]["free"])
        self.assertTrue(rows[0]["has_free_variant"])

    def test_free_tier_count_in_metadata(self) -> None:
        board = leaderboard.build_leaderboard(
            runs_dir=Path("this-directory-does-not-exist"),
            catalog_models=[
                _model("a/x", aa={"coding_index": 50}),
                _model("a/x:free", prompt="0", completion="0", aa={"coding_index": 50}),
                _model("b/y:free", prompt="0", completion="0", aa={"coding_index": 30}),
                _model("c/z", aa={"coding_index": 10}),
            ],
        )
        cov_meta = board["coverage"]
        self.assertEqual(3, cov_meta["count"])
        self.assertEqual(1, cov_meta["variants_folded"])
        self.assertEqual(2, cov_meta["free_tier_count"])

    def test_excludes_pricing_variants_of_measured_models(self) -> None:
        # :batch and :free are the same weights at a different price. The board
        # measured the base model, so its variants are not "unmeasured".
        rows = cov.coverage_rows(
            [_model("anthropic/claude-opus-5:batch", aa={"coding_index": 80}),
             _model("minimax/minimax-m3:free", aa={"coding_index": 60}),
             _model("z-ai/glm-5.2:free", aa={"coding_index": 68})],   # 5.2 is not 5.3; stays
            exclude_ids=["anthropic/claude-opus-5", "minimax/minimax-m3", "z-ai/glm-5.3"],
        )
        self.assertEqual(["z-ai/glm-5.2:free"], [r["model"] for r in rows])

    def test_prices_are_per_million_and_free_is_flagged(self) -> None:
        rows = cov.coverage_rows([
            _model("x/free", prompt="0", completion="0", aa={"coding_index": 30}),
            _model("x/paid", prompt="0.000002", completion="0.00001", aa={"coding_index": 30}),
        ])
        by = {r["model"]: r for r in rows}
        self.assertTrue(by["x/free"]["free"])
        self.assertEqual((2.0, 10.0), (by["x/paid"]["price_in"], by["x/paid"]["price_out"]))
        self.assertEqual(4.0, by["x/paid"]["price_blended"])   # (3*2 + 1*10) / 4

    def test_sorted_by_borrowed_quality_then_price(self) -> None:
        rows = cov.coverage_rows([
            _model("a/cheap-good", prompt="0.000001", aa={"coding_index": 80}),
            _model("b/pricey-good", prompt="0.00001", aa={"coding_index": 80}),
            _model("c/best", aa={"coding_index": 95}),
        ])
        self.assertEqual(["c/best", "a/cheap-good", "b/pricey-good"], [r["model"] for r in rows])


class BuildIntegrationTests(unittest.TestCase):
    def test_board_without_catalog_has_empty_coverage_and_untouched_rows(self) -> None:
        board = leaderboard.build_leaderboard(
            runs_dir=Path("this-directory-does-not-exist"),
            generated_at="2026-09-03T00:00:00+00:00",
        )
        self.assertEqual(10, len(board["rows"]))
        self.assertIn("coverage", board)
        self.assertEqual(0, board["coverage"]["count"])
        self.assertEqual([], board["coverage"]["rows"])

    def test_board_with_catalog_excludes_the_measured_ten(self) -> None:
        catalog = [
            _model("deepseek/deepseek-v4-flash", aa={"coding_index": 65}),   # measured, must be excluded
            _model("x-ai/grok-4.6", aa={"coding_index": 80}),                 # measured, must be excluded
            _model("qwen/qwen-9000", aa={"coding_index": 50}),                # not measured, must appear
        ]
        board = leaderboard.build_leaderboard(
            runs_dir=Path("this-directory-does-not-exist"),
            generated_at="2026-09-03T00:00:00+00:00",
            catalog_models=catalog,
        )
        self.assertEqual(10, len(board["rows"]), "coverage must never change the measured rows")
        self.assertEqual(["qwen/qwen-9000"], [r["model"] for r in board["coverage"]["rows"]])
        self.assertEqual(3, board["coverage"]["catalog_models_seen"])
        self.assertEqual({"aa:coding_index": 1}, board["coverage"]["by_source"])

    def test_csv_feed_ignores_coverage(self) -> None:
        board = leaderboard.build_leaderboard(
            runs_dir=Path("this-directory-does-not-exist"),
            catalog_models=[_model("qwen/qwen-9000", aa={"coding_index": 50})],
        )
        text = leaderboard.leaderboard_csv(board)
        self.assertNotIn("qwen/qwen-9000", text)
        self.assertEqual(11, len(text.strip().splitlines()))   # header + 10 measured rows

    def test_load_catalog_models_never_raises_without_key_or_cache(self) -> None:
        # Simulate a machine with no OpenRouter key (the client raises on
        # construction) and no on-disk cache. Must degrade to [], not raise,
        # so `waterfall leaderboard --publish` still works there.
        import openrouter_api_client

        def no_key(*_a, **_k):
            raise openrouter_api_client.OpenRouterError("no key")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(openrouter_api_client, "OpenRouterClient", no_key):
            missing = Path(tmp) / "nope.json"
            self.assertEqual([], cov.load_catalog_models(cache_path=missing))

    def test_load_catalog_models_falls_back_to_cache_when_client_fails(self) -> None:
        import openrouter_api_client

        def no_key(*_a, **_k):
            raise openrouter_api_client.OpenRouterError("no key")

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(openrouter_api_client, "OpenRouterClient", no_key):
            cache = Path(tmp) / "cache.json"
            cache.write_text(json.dumps({"models": [{"id": "x/y"}]}), encoding="utf-8")
            self.assertEqual([{"id": "x/y"}], cov.load_catalog_models(cache_path=cache))


if __name__ == "__main__":
    unittest.main()
