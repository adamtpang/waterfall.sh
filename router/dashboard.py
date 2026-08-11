"""Terminal ASCII dashboard -- `waterfall dashboard`. Renders real
hook-log, savings-ledger, and claude-usage data as bar charts directly
in the terminal. No browser, no server, works over SSH -- easy for a
beta tester to run and paste/screenshot back when reporting results.

Pure rendering functions here take already-loaded data (HookLogEntry
lists, SavingsSummary, claude_usage DaySummary dicts) so they're
testable without touching disk; cli.py's cmd_dashboard wires the real
loads to these.
"""

from __future__ import annotations

BAR_CHAR = "#"
MAX_BAR_WIDTH = 40


def bar_chart(rows: list[tuple[str, float, str]], width: int = MAX_BAR_WIDTH, label_width: int = 14) -> str:
    """rows: (label, numeric value the bar length is scaled to, display string
    printed after the bar). Empty bars (all-zero data) still render, just
    with zero-length bars, so callers don't need a special case."""
    if not rows:
        return "(no data)"
    max_value = max(v for _, v, _ in rows) or 1
    lines = []
    for label, value, display in rows:
        bar_len = round((value / max_value) * width) if max_value else 0
        bar = BAR_CHAR * bar_len
        lines.append(f"{label:<{label_width}} {bar} {display}")
    return "\n".join(lines)


def render_hook_activity(by_day: dict[str, dict[str, int]]) -> str:
    """by_day: hook_log.group_by_day()'s output -- {day: {"nudge": n, "ringer": n}}."""
    if not by_day:
        return "nudges/denials by day\n(no hook activity logged yet)"

    nudge_rows = [(day, float(counts.get("nudge", 0)), str(counts.get("nudge", 0)))
                  for day, counts in by_day.items()]
    ringer_rows = [(day, float(counts.get("ringer", 0)), str(counts.get("ringer", 0)))
                   for day, counts in by_day.items()]

    return (
        "nudges by day (UserPromptSubmit)\n" + bar_chart(nudge_rows) + "\n\n"
        "denials by day (Ringer)\n" + bar_chart(ringer_rows)
    )


def render_ringer_summary(denial_tokens_list: list[int]) -> str:
    """denial_tokens_list: one estimated-token-count int per real Ringer denial."""
    count = len(denial_tokens_list)
    total_tokens = sum(denial_tokens_list)
    cost_equivalent = total_tokens * 3e-6  # same CLAUDE_INPUT_PRICE_PER_TOKEN as tracker.py

    return (
        "Ringer prevention\n"
        f"  denials:               {count:,}\n"
        f"  tokens never read in:  {total_tokens:,}\n"
        f"  Claude-price equivalent: ${cost_equivalent:,.4f}"
    )


def render_routing_summary(
    total_prompts: int, tokens_avoided: int, estimated_cost_saved: float
) -> str:
    return (
        "Routing savings (waterfall route)\n"
        f"  prompts routed:  {total_prompts:,}\n"
        f"  tokens avoided:  {tokens_avoided:,}\n"
        f"  est. cost saved: ${estimated_cost_saved:,.4f}"
    )


MODEL_TIER_ORDER = ["opus", "sonnet", "haiku", "fable", "other"]


def render_model_usage_by_day(by_day_model: dict[str, dict[str, int]]) -> str:
    """by_day_model: claude_usage.group_by_day_and_model()'s output --
    {day: {"sonnet": n, "opus": n, ...}}. The bar reflects total turn volume
    that day; the trailing counts show whether that volume is actually
    split across model tiers or all landing on one, which raw volume alone
    can't reveal. Zero-count tiers are omitted per day to stay readable."""
    if not by_day_model:
        return "model usage by day\n(no claude-usage data for this range)"

    rows = []
    for day, counts in by_day_model.items():
        total = sum(counts.values())
        breakdown = " ".join(
            f"{tier}={counts[tier]}" for tier in MODEL_TIER_ORDER if counts.get(tier)
        )
        rows.append((day, float(total), breakdown))
    return "model usage by day\n" + bar_chart(rows)


def render_top_model_projects(tier: str, rows: list[tuple[str, int]]) -> str:
    """rows: claude_usage.top_projects_by_model()'s output for one tier."""
    header = f"top projects by {tier} usage"
    if not rows:
        return f"{header}\n(none this range)"
    lines = [f"{project:<20} {count:,} {tier} turns" for project, count in rows]
    return header + "\n" + "\n".join(lines)


def render_reuse_trend(by_day_pct: list[tuple[str, float]]) -> str:
    """by_day_pct: [(day, reused_input_pct_0_to_100), ...] chronological."""
    if not by_day_pct:
        return "reused-input % by day\n(no claude-usage data for this range)"
    rows = [(day, pct, f"{pct:.1f}%") for day, pct in by_day_pct]
    return "reused-input % by day (Claude Code, all projects)\n" + bar_chart(rows)


def render_full_dashboard(
    hook_by_day: dict[str, dict[str, int]],
    denial_tokens_list: list[int],
    total_prompts: int,
    tokens_avoided: int,
    estimated_cost_saved: float,
    reuse_by_day: list[tuple[str, float]],
    model_by_day: dict[str, dict[str, int]] | None = None,
    top_opus_projects: list[tuple[str, int]] | None = None,
) -> str:
    sections = [
        render_hook_activity(hook_by_day),
        render_ringer_summary(denial_tokens_list),
        render_routing_summary(total_prompts, tokens_avoided, estimated_cost_saved),
        render_reuse_trend(reuse_by_day),
    ]
    if model_by_day is not None:
        sections.append(render_model_usage_by_day(model_by_day))
    if top_opus_projects is not None:
        sections.append(render_top_model_projects("opus", top_opus_projects))
    return "\n\n".join(sections)
