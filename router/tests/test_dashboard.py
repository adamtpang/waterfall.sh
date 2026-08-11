"""Tests for dashboard.py's pure rendering functions -- no disk/network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard import (
    bar_chart, render_full_dashboard, render_hook_activity, render_reuse_trend,
    render_ringer_summary, render_routing_summary,
    render_model_usage_by_day, render_top_model_projects,
)


class BarChartTests(unittest.TestCase):
    def test_empty_rows(self) -> None:
        self.assertEqual(bar_chart([]), "(no data)")

    def test_single_row_full_width_bar(self) -> None:
        out = bar_chart([("Aug 5", 10.0, "10")], width=40)
        self.assertIn("#" * 40, out)
        self.assertIn("10", out)

    def test_proportional_bar_lengths(self) -> None:
        out = bar_chart([("a", 10.0, "10"), ("b", 5.0, "5")], width=40)
        lines = out.splitlines()
        len_a = lines[0].count("#")
        len_b = lines[1].count("#")
        self.assertEqual(len_a, 40)
        self.assertEqual(len_b, 20)

    def test_zero_value_row_renders_empty_bar(self) -> None:
        out = bar_chart([("a", 5.0, "5"), ("b", 0.0, "0")])
        lines = out.splitlines()
        self.assertNotIn("#", lines[1])

    def test_all_zero_rows_does_not_divide_by_zero(self) -> None:
        out = bar_chart([("a", 0.0, "0"), ("b", 0.0, "0")])
        self.assertEqual(len(out.splitlines()), 2)


class RenderHookActivityTests(unittest.TestCase):
    def test_empty_by_day(self) -> None:
        out = render_hook_activity({})
        self.assertIn("no hook activity", out)

    def test_renders_both_nudge_and_ringer_sections(self) -> None:
        by_day = {"2026-08-05": {"nudge": 43, "ringer": 17}, "2026-08-06": {"nudge": 88, "ringer": 5}}
        out = render_hook_activity(by_day)
        self.assertIn("nudges by day", out)
        self.assertIn("denials by day", out)
        self.assertIn("43", out)
        self.assertIn("88", out)
        self.assertIn("17", out)
        self.assertIn("5", out)


class RenderRingerSummaryTests(unittest.TestCase):
    def test_empty_list(self) -> None:
        out = render_ringer_summary([])
        self.assertIn("denials:               0", out)
        self.assertIn("$0.0000", out)

    def test_sums_tokens_and_computes_cost(self) -> None:
        out = render_ringer_summary([100_000, 50_000])
        self.assertIn("denials:               2", out)
        self.assertIn("150,000", out)
        self.assertIn(f"${150_000 * 3e-6:,.4f}", out)


class RenderRoutingSummaryTests(unittest.TestCase):
    def test_basic_render(self) -> None:
        out = render_routing_summary(total_prompts=5, tokens_avoided=75, estimated_cost_saved=0.0002)
        self.assertIn("prompts routed:  5", out)
        self.assertIn("tokens avoided:  75", out)
        self.assertIn("$0.0002", out)


class RenderReuseTrendTests(unittest.TestCase):
    def test_empty(self) -> None:
        out = render_reuse_trend([])
        self.assertIn("no claude-usage data", out)

    def test_renders_percentages(self) -> None:
        out = render_reuse_trend([("2026-08-05", 86.7), ("2026-08-06", 95.4)])
        self.assertIn("86.7%", out)
        self.assertIn("95.4%", out)


class RenderModelUsageByDayTests(unittest.TestCase):
    def test_empty(self) -> None:
        out = render_model_usage_by_day({})
        self.assertIn("no claude-usage data", out)

    def test_renders_breakdown_per_day(self) -> None:
        out = render_model_usage_by_day({
            "2026-08-09": {"sonnet": 5891, "opus": 12, "haiku": 3},
            "2026-08-10": {"sonnet": 6203, "opus": 41},
        })
        self.assertIn("sonnet=5891", out)
        self.assertIn("opus=12", out)
        self.assertIn("haiku=3", out)
        self.assertIn("sonnet=6203", out)

    def test_zero_count_tiers_omitted(self) -> None:
        out = render_model_usage_by_day({"2026-08-09": {"sonnet": 10, "opus": 0}})
        self.assertNotIn("opus=0", out)

    def test_tier_order_is_opus_sonnet_haiku_fable_other(self) -> None:
        out = render_model_usage_by_day({"2026-08-09": {"haiku": 1, "opus": 1, "sonnet": 1}})
        line = out.splitlines()[-1]
        self.assertLess(line.index("opus"), line.index("sonnet"))
        self.assertLess(line.index("sonnet"), line.index("haiku"))


class RenderTopModelProjectsTests(unittest.TestCase):
    def test_empty(self) -> None:
        out = render_top_model_projects("opus", [])
        self.assertIn("top projects by opus usage", out)
        self.assertIn("none this range", out)

    def test_renders_ranked_projects(self) -> None:
        out = render_top_model_projects("opus", [("themain.quest", 191), ("summon.guide", 2)])
        self.assertIn("themain.quest", out)
        self.assertIn("191 opus turns", out)
        self.assertIn("summon.guide", out)


class RenderFullDashboardTests(unittest.TestCase):
    def test_combines_all_sections(self) -> None:
        out = render_full_dashboard(
            hook_by_day={"2026-08-05": {"nudge": 43, "ringer": 17}},
            denial_tokens_list=[25000, 25000],
            total_prompts=5,
            tokens_avoided=75,
            estimated_cost_saved=0.0002,
            reuse_by_day=[("2026-08-05", 86.7)],
        )
        self.assertIn("nudges by day", out)
        self.assertIn("Ringer prevention", out)
        self.assertIn("Routing savings", out)
        self.assertIn("reused-input", out)

    def test_model_sections_omitted_when_not_provided(self) -> None:
        out = render_full_dashboard(
            hook_by_day={}, denial_tokens_list=[], total_prompts=0,
            tokens_avoided=0, estimated_cost_saved=0.0, reuse_by_day=[],
        )
        self.assertNotIn("model usage by day", out)
        self.assertNotIn("top projects by", out)

    def test_model_sections_included_when_provided(self) -> None:
        out = render_full_dashboard(
            hook_by_day={}, denial_tokens_list=[], total_prompts=0,
            tokens_avoided=0, estimated_cost_saved=0.0, reuse_by_day=[],
            model_by_day={"2026-08-09": {"sonnet": 10}},
            top_opus_projects=[("themain.quest", 191)],
        )
        self.assertIn("model usage by day", out)
        self.assertIn("top projects by opus usage", out)
        self.assertIn("themain.quest", out)


if __name__ == "__main__":
    unittest.main()
