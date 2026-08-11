"""waterfall -- classify a prompt, route the routine part to the cheapest
capable model on OpenRouter (auto-falling back to the next-cheapest one if
it's down or rate-limited), and log what that kept off Claude's plate.

    python3 -m router.cli classify "explain this traceback: ..."
    python3 -m router.cli route "..." --dry-run
    python3 -m router.cli route "..."
    python3 -m router.cli stats
    python3 -m router.cli claude-usage --by-day
    python3 -m router.cli hook-log --verbose
    python3 -m router.cli usage-pace --used-pct 22
    python3 -m router.cli dashboard
    python3 -m router.cli models

Or, if installed (`pip install -e .` from the repo root): `waterfall ...`.

classify/route --dry-run never touch the network and cost nothing --
they're the "clean desk" habits (classify before you send, split the
routine part off) turned into a command instead of something you have to
remember to do by hand. `route` without --dry-run logs every call to the
savings ledger (~/.claude/token_savings.jsonl) so `stats` can show what
actually got kept off Claude.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smart_router import SmartRouter, SMART_ROUTER_AVAILABLE, API_ROUTER_AVAILABLE
from tracker import SavingsTracker, estimate_cost_saved
import usage_pace
import dashboard
from classifier.types import SavingsEvent


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt:
        return args.prompt
    if args.file:
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("No prompt given -- pass it as an argument, --file <path>, or pipe it on stdin.")


def _add_prompt_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("prompt", nargs="?", help="the prompt (or use --file / pipe on stdin)")
    sp.add_argument("--file", help="read the prompt from a file instead of the argument")


def cmd_classify(args: argparse.Namespace) -> int:
    prompt = _read_prompt(args)
    router = SmartRouter()
    cls = router.classify(prompt)
    print(f"routing:      {cls.routing}")
    print(f"complexity:   {cls.complexity_score}")
    print(f"confidence:   {cls.confidence}")
    print(f"est free pct: {cls.estimated_free_pct:.0%}")
    print(f"task types:   {', '.join(cls.task_types) or '(none)'}")
    print(f"domains:      {', '.join(cls.domains) or '(none)'}")
    print(f"reasoning:    {cls.reasoning}")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    prompt = _read_prompt(args)
    router = SmartRouter()
    cls = router.classify(prompt)
    split = router.split(prompt, cls)

    import openrouter_api_client as orc
    inferred_tier = args.tier or orc.tier_for_complexity(cls.complexity_score)
    print(f"routing:  {cls.routing}  (complexity {cls.complexity_score}, "
          f"~{split.savings_pct:.0%} estimated off Claude's plate)")
    print(f"model tier: {inferred_tier}" + ("" if args.model or split.free_prompt else " (unused -- nothing routed off Claude)"))

    if args.dry_run or not split.free_prompt:
        if split.free_prompt:
            print("\n--- would send to free/cheap model ---")
            print(split.free_prompt)
        print("\n--- stays with Claude ---")
        print(split.claude_prompt or prompt)
        return 0

    if not API_ROUTER_AVAILABLE:
        print(
            "OpenRouter API client unavailable -- set OPENROUTER_API_KEY "
            "(or ~/.claude/openrouter_key.txt). Showing --dry-run output instead.",
            file=sys.stderr,
        )
        print("\n--- stays with Claude ---")
        print(split.claude_prompt or prompt)
        return 1

    result = router.route_with_api(prompt, system=args.system, model=args.model, tier=args.tier)

    if result.cache_hit:
        print("\nserved from cache -- identical routed text answered before, no new API call")
    print(f"\nmodel used:   {result.model_used or '(none -- routed fully to Claude)'}")
    print(f"model tier:   {result.model_tier or '(n/a)'}")
    print(f"cost (USD):   {result.cost_usd}")
    print(f"tokens:       {result.input_tokens} in / {result.output_tokens} out")
    print(f"elapsed:      {result.elapsed_sec}s")

    if result.free_response:
        print("\n--- free model output ---")
        print(result.free_response)

    print("\n--- hand this to Claude ---")
    print(result.final_claude_prompt or "(nothing left -- fully handled by the free model)")

    if not args.no_log:
        tracker = SavingsTracker()
        tokens_saved = split.free_token_estimate
        event = SavingsEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            original_tokens=split.free_token_estimate + split.claude_token_estimate,
            free_tokens_sent=split.free_token_estimate,
            claude_tokens_needed=split.claude_token_estimate,
            tokens_saved=tokens_saved,
            cost_saved_usd=estimate_cost_saved(tokens_saved, result.cost_usd),
            backend_used="cache" if result.cache_hit else "openrouter",
            model_used=result.model_used,
            routing_decision=cls.routing,
            task_types=cls.task_types,
            elapsed_sec=result.elapsed_sec,
            prompt_preview=prompt[:200],
            model_tier=result.model_tier,
        )
        tracker.record(event)

    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    tracker = SavingsTracker()
    since = None
    if args.since_days:
        since = datetime.now(timezone.utc) - timedelta(days=args.since_days)
    events = tracker.load_events(since=since)
    summary = tracker.summarize(events)

    if summary.total_prompts == 0:
        print('No routed prompts logged yet -- run `waterfall route "..."` (without --dry-run) to start the ledger.')
        return 0

    print(f"prompts routed:        {summary.total_prompts}")
    print(f"tokens kept off Claude: {summary.tokens_avoided:,}")
    print(f"est. cost saved:        ${summary.estimated_cost_saved}")
    print(f"avg free-model share:   {summary.avg_free_pct:.0%}")
    if summary.by_backend:
        print("by backend:             " + ", ".join(f"{k}={v}" for k, v in summary.by_backend.items()))
    if summary.by_task_type:
        print("by task type:           " + ", ".join(f"{k}={v}" for k, v in summary.by_task_type.items()))
    if summary.by_model_tier:
        print("by model tier:          " + ", ".join(f"{k}={v}" for k, v in summary.by_model_tier.items()))
    return 0


def cmd_claude_usage(args: argparse.Namespace) -> int:
    import claude_usage as cu

    since = None
    if args.since_days:
        since = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    turns = cu.load_usage_turns(project=args.project, since=since)
    if not turns:
        print("No Claude Code transcript data found for that filter.")
        return 0

    if args.by_day:
        for day, s in cu.group_by_day(turns).items():
            print(f"{day}  turns={s.turn_count:<5} sessions={s.session_count:<3} "
                  f"input(fresh+cached)={s.input_tokens + s.cache_creation_tokens:>9,}  "
                  f"reused={s.cache_read_tokens:>12,}  output={s.output_tokens:>8,}  "
                  f"reused%={s.reused_input_pct:.1%}  est.cost=${s.estimated_cost_usd}")
        return 0

    s = cu.summarize(turns)
    print(f"assistant turns:        {s.turn_count:,}")
    print(f"sessions:                {s.session_count}")
    print(f"fresh input tokens:      {s.input_tokens:,}")
    print(f"cache-write tokens:      {s.cache_creation_tokens:,}  (new context, cached for reuse)")
    print(f"cache-read tokens:       {s.cache_read_tokens:,}  (reused from a prior turn -- the compounding cost)")
    print(f"output tokens:           {s.output_tokens:,}")
    print(f"total input processed:   {s.total_input_seen:,}")
    print(f"reused-input share:      {s.reused_input_pct:.1%}")
    print(f"est. cost (this filter): ${s.estimated_cost_usd}")
    return 0


def cmd_hook_log(args: argparse.Namespace) -> int:
    import hook_log as hl

    since = None
    if args.since_days:
        since = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    entries = hl.load_entries(since=since)
    if args.project:
        entries = [e for e in entries if args.project.lower() in e.project.lower()]

    if not entries:
        print(
            "No hook activity logged for that filter -- either nothing fired, "
            "or the hooks aren't installed/reloaded in the relevant session yet."
        )
        return 0

    nudges = [e for e in entries if e.hook == "nudge"]
    denies = [e for e in entries if e.hook == "ringer"]
    print(f"nudges (UserPromptSubmit):  {len(nudges)}")
    print(f"denials (Ringer/PreToolUse): {len(denies)}")

    by_project: dict[str, int] = {}
    for e in entries:
        by_project[e.project] = by_project.get(e.project, 0) + 1
    print("by project: " + ", ".join(
        f"{p}={c}" for p, c in sorted(by_project.items(), key=lambda x: -x[1])
    ))

    if args.verbose:
        print()
        for e in entries[-args.limit:]:
            print(f"{e.timestamp}  [{e.hook:6}] {e.project:<24} {e.detail}")
    return 0


def cmd_usage_pace(args: argparse.Namespace) -> int:
    tz = timezone(timedelta(hours=args.utc_offset))
    now = datetime.now(tz)
    result = usage_pace.compute_pace(
        used_pct=args.used_pct,
        now=now,
        reset_weekday=usage_pace.WEEKDAYS[args.reset_day.lower()],
        reset_hour=args.reset_hour,
    )

    print(f"now:         {now.strftime('%Y-%m-%d %H:%M')} (UTC{args.utc_offset:+g})")
    print(f"last reset:  {result.last_reset.strftime('%Y-%m-%d %H:%M')} "
          f"({args.reset_day.title()} {args.reset_hour}:00)")
    print(f"next reset:  {result.next_reset.strftime('%Y-%m-%d %H:%M')}  "
          f"({result.hours_remaining:.1f}h remaining)")
    print(f"elapsed:     {result.hours_elapsed:.1f}h of {usage_pace.HOURS_PER_WEEK}h "
          f"({result.elapsed_pct:.1f}% of the week gone)")
    print(f"quota used:  {result.used_pct:.1f}%")
    print(f"delta:       {result.pace_delta:+.1f} points  -- {result.status}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    import hook_log as hl
    import claude_usage as cu

    since = datetime.now(timezone.utc) - timedelta(days=args.since_days) if args.since_days else None
    hook_entries = hl.load_entries(since=since)
    denial_tokens_list = [hl.denial_tokens(e) for e in hook_entries if e.hook == "ringer"]

    tracker = SavingsTracker()
    events = tracker.load_events(since=since)
    summary = tracker.summarize(events)
    openrouter_tokens = sum(e.tokens_saved for e in events if e.backend_used == "openrouter")
    cache_tokens = sum(e.tokens_saved for e in events if e.backend_used == "cache")

    usage_since_days = args.since_days or 8
    turns = cu.load_usage_turns(since=datetime.now(timezone.utc) - timedelta(days=usage_since_days))
    reuse_by_day = [
        (day, s.reused_input_pct * 100) for day, s in cu.group_by_day(turns).items()
    ]

    print(dashboard.render_full_dashboard(
        hook_by_day=hl.group_by_day(hook_entries),
        denial_tokens_list=denial_tokens_list,
        total_prompts=summary.total_prompts,
        tokens_avoided=summary.tokens_avoided,
        estimated_cost_saved=summary.estimated_cost_saved,
        reuse_by_day=reuse_by_day,
        model_by_day=cu.group_by_day_and_model(turns),
        top_opus_projects=cu.top_projects_by_model(turns, "opus"),
        openrouter_tokens_avoided=openrouter_tokens,
        cache_tokens_avoided=cache_tokens,
    ))
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    if not API_ROUTER_AVAILABLE:
        print("OpenRouter API client unavailable -- set OPENROUTER_API_KEY.", file=sys.stderr)
        return 1
    import openrouter_api_client as orc
    client = orc.OpenRouterClient()
    if args.tier:
        picks = client.pick_cheap_models_by_tier(args.tier, n=args.limit)
        print(f"tier: {args.tier}")
    else:
        picks = client.pick_cheap_models(n=args.limit)
    for i, m in enumerate(picks, 1):
        print(f"{i}. {m}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="waterfall", description="Cascade to the best model. Automatically.")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("classify", help="classify a prompt -- no network calls")
    _add_prompt_args(sp)
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("route", help="classify, split, and route via OpenRouter")
    _add_prompt_args(sp)
    sp.add_argument("--dry-run", action="store_true", help="classify/split only, never call the network")
    sp.add_argument("--model", help="pin a specific OpenRouter model id (skips auto tier+fallback)")
    sp.add_argument("--tier", choices=["small", "medium", "large"],
                     help="pin a model tier instead of deriving it from complexity (ignored if --model is set)")
    sp.add_argument("--system", help="system prompt for the free-model call")
    sp.add_argument("--no-log", action="store_true", help="don't append this call to the savings ledger")
    sp.set_defaults(func=cmd_route)

    sp = sub.add_parser("stats", help="show the savings ledger summary")
    sp.add_argument("--since-days", type=int, default=None, help="only include the last N days")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("claude-usage", help="real Claude Code token usage from local session transcripts")
    sp.add_argument("--project", help="filter to project dirs whose name contains this substring")
    sp.add_argument("--since-days", type=int, default=None, help="only include the last N days")
    sp.add_argument("--by-day", action="store_true", help="show a day-by-day trend instead of one summary")
    sp.set_defaults(func=cmd_claude_usage)

    sp = sub.add_parser("hook-log", help="show real nudge/deny events fired by the waterfall hooks")
    sp.add_argument("--project", help="filter to projects whose name contains this substring")
    sp.add_argument("--since-days", type=int, default=None, help="only include the last N days")
    sp.add_argument("--verbose", action="store_true", help="also list the individual events")
    sp.add_argument("--limit", type=int, default=20, help="how many recent events to show with --verbose")
    sp.set_defaults(func=cmd_hook_log)

    sp = sub.add_parser("usage-pace", help="check Claude plan weekly-quota pace against elapsed time")
    sp.add_argument("--used-pct", type=float, required=True,
                     help="your self-reported %% of weekly quota used, from Claude Code's own usage display")
    sp.add_argument("--reset-day", default="tuesday", choices=list(usage_pace.WEEKDAYS.keys()),
                     help="day of week the quota resets (default tuesday)")
    sp.add_argument("--reset-hour", type=int, default=17,
                     help="hour (0-23, local time) the quota resets (default 17 = 5pm)")
    sp.add_argument("--utc-offset", type=float, default=8.0,
                     help="your UTC offset in hours (default 8 = SGT)")
    sp.set_defaults(func=cmd_usage_pace)

    sp = sub.add_parser("dashboard", help="terminal ASCII dashboard of real hook/routing/usage data")
    sp.add_argument("--since-days", type=int, default=None,
                     help="restrict all sections to the last N days "
                          "(default: all-time for hooks/routing, last 8 days for the reuse trend)")
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("models", help="list the current cheapest capable OpenRouter models")
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--tier", choices=["small", "medium", "large"], help="preview a specific tier band instead of the flat cheapest list")
    sp.set_defaults(func=cmd_models)

    return p


def main(argv: list[str] | None = None) -> int:
    if not SMART_ROUTER_AVAILABLE:
        print("classifier not importable -- run from the router/ directory or `pip install -e .`.", file=sys.stderr)
        return 1
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
