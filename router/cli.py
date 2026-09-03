"""waterfall -- classify a prompt, route the routine part to the cheapest
capable model on OpenRouter (auto-falling back to the next-cheapest one if
it's down or rate-limited), and log what that kept off Claude's plate.

    python3 -m router.cli classify "explain this traceback: ..."
    python3 -m router.cli route "..." --dry-run
    python3 -m router.cli route "..."
    python3 -m router.cli run "fix the flaky auth test"
    python3 -m router.cli why
    python3 -m router.cli leaderboard --publish
    python3 -m router.cli bench --suite coding-smoketest --models grok-4.6,glm-5.3
    python3 -m router.cli stats
    python3 -m router.cli claude-usage --by-day
    python3 -m router.cli hook-log --verbose
    python3 -m router.cli usage-pace --used-pct 22
    python3 -m router.cli usage-pace --used-pct 84 --bucket codex=15:720:400 --bucket grok=60:720:200
    python3 -m router.cli claude-estimate
    python3 -m router.cli dashboard
    python3 -m router.cli dashboard --used-pct 24 --session-pct 13 --session-hours-remaining 3.45 --model-pct fable=3
    python3 -m router.cli desktop
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
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smart_router import SmartRouter, SMART_ROUTER_AVAILABLE, API_ROUTER_AVAILABLE
from tracker import SavingsTracker, estimate_cost_saved
import usage_pace
import dashboard
from classifier.types import SavingsEvent


def _parse_model_pct(raw: str) -> tuple[str, float]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"expected MODEL=PCT, got {raw!r}")
    model, _, pct = raw.partition("=")
    try:
        return model.strip(), float(pct)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{pct!r} isn't a number in {raw!r}")


def _parse_bucket(raw: str) -> tuple[str, float, float, float]:
    """LABEL=USED_PCT:WINDOW_HOURS:HOURS_REMAINING -- for a subscription with
    its own independent reset schedule (Codex, Grok, anything that isn't on
    Claude's own weekly clock). --model-pct assumes Claude's own weekly
    reset, which is wrong for a separately-billed product."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"expected LABEL=USED_PCT:WINDOW_HOURS:HOURS_REMAINING, got {raw!r}")
    label, _, rest = raw.partition("=")
    parts = rest.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"expected LABEL=USED_PCT:WINDOW_HOURS:HOURS_REMAINING, got {raw!r}"
        )
    try:
        used_pct, window_hours, hours_remaining = (float(p) for p in parts)
    except ValueError:
        raise argparse.ArgumentTypeError(f"non-numeric value in {raw!r}")
    return label.strip(), used_pct, window_hours, hours_remaining


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


def _add_coding_signal_args(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--repo-file-count", type=int, default=0,
                    help="files touched in the previous session, when known")
    sp.add_argument("--language", action="append", default=[],
                    help="repository language signal; repeat for multiple languages")
    sp.add_argument("--test-runner", action="store_true",
                    help="signal that the repository has an executable test runner")
    sp.add_argument("--previous-harden-failed", action="store_true",
                    help="the same task already failed the harden tier")


def cmd_classify(args: argparse.Namespace) -> int:
    from waterfall_policy import RepoSignals, RoutingPolicy

    prompt = _read_prompt(args)
    signals = RepoSignals(
        file_count=args.repo_file_count,
        languages=tuple(args.language or []),
        test_runner_present=args.test_runner,
        previous_harden_failed=args.previous_harden_failed,
    )
    decision = RoutingPolicy().classify(
        prompt, signals, tier=args.tier, effort=args.effort
    )
    print(json.dumps(decision.to_dict(), indent=2))
    return 0


def _repo_signals_from_args(args: argparse.Namespace, prompt: str = ""):
    from waterfall_policy import RepoSignals, same_task_failed_harden

    return RepoSignals(
        file_count=args.repo_file_count,
        languages=tuple(args.language or []),
        test_runner_present=args.test_runner,
        previous_harden_failed=(
            args.previous_harden_failed or bool(prompt and same_task_failed_harden(prompt))
        ),
    )


def cmd_run(args: argparse.Namespace) -> int:
    from waterfall_policy import RoutingPolicy, RunTrace, format_why, save_trace

    prompt = _read_prompt(args)
    policy = RoutingPolicy()
    signals = _repo_signals_from_args(args, prompt)
    decision = policy.classify(prompt, signals, tier=args.tier, effort=args.effort)

    if args.dry_run:
        from waterfall_policy import task_hash
        trace = RunTrace(
            task_preview=prompt[:200], classified=decision.to_dict(), task_hash=task_hash(prompt)
        )
        if not (set(decision.suggested_models) & policy.fable_models()):
            trace.skipped.append("claude-fable-5.1")
        save_trace(trace)
        print(json.dumps(decision.to_dict(), indent=2))
        print("\ndry run: no model contacted")
        return 0

    try:
        from waterfall_run import execute_waterfall
        result = execute_waterfall(
            prompt,
            policy=policy,
            signals=signals,
            tier=args.tier,
            effort=args.effort,
            no_cap=args.no_cap,
        )
    except Exception as exc:
        print(f"waterfall run failed: {exc}", file=sys.stderr)
        return 1

    save_trace(result.trace)
    print(format_why(result.trace))
    if result.output:
        print("\n--- author output ---")
        print(result.output)
    return 0 if result.passed else 2


def cmd_why(_args: argparse.Namespace) -> int:
    from waterfall_policy import format_why, load_trace

    try:
        trace = load_trace()
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(format_why(trace))
    return 0


def cmd_leaderboard(args: argparse.Namespace) -> int:
    import leaderboard
    import leaderboard_coverage

    board = leaderboard.build_leaderboard(
        catalog_models=leaderboard_coverage.load_catalog_models(),
    )
    cov = board.get("coverage") or {}
    print(f"coverage: {cov.get('count', 0)} borrowed rows from {cov.get('catalog_models_seen', 0)} catalog models")
    if args.publish:
        json_path, csv_path = leaderboard.publish_leaderboard(board)
        print(f"published: {json_path}")
        print(f"published: {csv_path}")
    print(leaderboard.format_table(board))
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    import bench

    models = [model.strip() for model in args.models.split(",") if model.strip()]
    if not models:
        print("--models needs at least one comma-separated model alias", file=sys.stderr)
        return 2
    try:
        suite = bench.load_suite(args.suite)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"could not load benchmark suite: {exc}", file=sys.stderr)
        return 2

    tasks = suite["tasks"][:args.limit] if args.limit else suite["tasks"]
    if args.dry_run:
        print(f"suite: {suite['id']} ({len(tasks)} of {len(suite['tasks'])} tasks)")
        print("models: " + ", ".join(models))
        for task in tasks:
            print(f"  {task['id']:<30} {task['category']}")
        print("dry run: no model contacted and no JSONL written")
        return 0

    output_path = Path(args.output) if args.output else None

    def progress(attempt) -> None:
        result = "pass" if attempt.passed else "fail"
        print(
            f"{attempt.model:<22} {attempt.task_id:<30} {result:<4} "
            f"${attempt.cost_usd:.4f} {attempt.wall_time:.1f}s"
        )

    try:
        attempts = bench.run_suite(
            suite,
            models,
            effort=args.effort,
            output_path=output_path,
            limit=args.limit,
            progress=progress,
        )
    except Exception as exc:
        print(f"benchmark stopped: {exc}", file=sys.stderr)
        return 1
    passed = sum(attempt.passed for attempt in attempts)
    spent = sum(attempt.cost_usd for attempt in attempts)
    print(f"\n{passed}/{len(attempts)} passed · ${spent:.4f} total")
    print(f"records: {output_path or bench.DEFAULT_RUNS_DIR / (datetime.now(timezone.utc).date().isoformat() + '.jsonl')}")
    print("rebuild feeds: waterfall leaderboard --publish")
    return 0


def _print_model_queue(result) -> None:
    """Show the cascade's ranked candidates and what happened to each.

    "Cheapest capable model" is a decision waterfall makes on your behalf
    every call, and it used to be invisible: you saw the winner with no way to
    tell whether it was first pick or the third one after two failures.
    Models listed below the last attempt were never contacted.
    """
    queue = list(getattr(result, "queue", []) or [])
    attempts = list(getattr(result, "attempts", []) or [])

    if getattr(result, "cache_hit", False):
        print("\nmodel queue:  skipped, served from cache, no model contacted")
        return
    if not queue:
        return

    outcome = {a.get("model"): a for a in attempts}
    print(f"\nmodel queue:  {len(queue)} candidate(s), cheapest first")
    for i, name in enumerate(queue, 1):
        got = outcome.get(name)
        if got is None:
            print(f"  {i}. {name}  [not needed]")
        elif got.get("status") == "ok":
            print(f"  {i}. {name}  [answered in {got.get('elapsed_sec', 0)}s]")
        else:
            reason = (got.get("reason") or "failed").splitlines()[0]
            if len(reason) > 96:
                reason = reason[:93] + "..."
            print(f"  {i}. {name}  [failed: {reason}]")


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

    _print_model_queue(result)

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


def _build_usage_pace_buckets(args: argparse.Namespace) -> list[usage_pace.BucketResult]:
    """Shared by `usage-pace` and `dashboard` -- same flags build the same
    bucket list, so the two commands' guidance never disagrees.

    --used-pct/--session-pct/--model-pct all describe Claude's own account
    (weekly reset, or Claude's per-model buckets which share that reset).
    --bucket is for a DIFFERENT subscription entirely (Codex, Grok, anything
    billed and reset on its own schedule) -- those are added regardless of
    whether --used-pct was given, since they don't depend on Claude's clock
    at all."""
    buckets: list[usage_pace.BucketResult] = []

    if args.used_pct is not None:
        tz = timezone(timedelta(hours=args.utc_offset))
        now = datetime.now(tz)
        result = usage_pace.compute_pace(
            used_pct=args.used_pct,
            now=now,
            reset_weekday=usage_pace.WEEKDAYS[args.reset_day.lower()],
            reset_hour=args.reset_hour,
        )
        buckets.append(usage_pace.BucketResult(
            label="weekly (all models)", used_pct=result.used_pct, elapsed_pct=result.elapsed_pct,
            pace_delta=result.pace_delta, status=result.status,
            window_hours=usage_pace.HOURS_PER_WEEK, hours_remaining=result.hours_remaining,
        ))

        if args.session_pct is not None:
            if args.session_hours_remaining is None:
                print("--session-pct needs --session-hours-remaining too, skipping the session bucket", file=sys.stderr)
            else:
                buckets.append(usage_pace.compute_bucket_pace(
                    "5-hour session", args.session_pct, args.session_window_hours, args.session_hours_remaining,
                ))

        for model, pct in args.model_pct or []:
            buckets.append(usage_pace.compute_bucket_pace(
                f"weekly ({model})", pct, usage_pace.HOURS_PER_WEEK, result.hours_remaining,
            ))
    elif args.session_pct is not None or args.model_pct:
        print("--session-pct/--model-pct describe Claude's own account and need --used-pct too, skipping", file=sys.stderr)

    for label, used_pct, window_hours, hours_remaining in getattr(args, "bucket", None) or []:
        buckets.append(usage_pace.compute_bucket_pace(label, used_pct, window_hours, hours_remaining))

    return buckets


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

    buckets = _build_usage_pace_buckets(args)
    for b in buckets[1:]:
        print(f"\n{b.label}")
        print(f"  window:      {b.window_hours:g}h, {b.hours_remaining:.2f}h remaining "
              f"({b.elapsed_pct:.1f}% of the window gone)")
        print(f"  used:        {b.used_pct:.1f}%")
        print(f"  delta:       {b.pace_delta:+.1f} points  -- {b.status}")

    if len(buckets) > 1:
        print(f"\n{usage_pace.guidance(buckets)}")
    return 0


def cmd_claude_estimate(args: argparse.Namespace) -> int:
    import quota_estimate

    tz = timezone(timedelta(hours=args.utc_offset))
    now = datetime.now(tz)
    reset_boundary = usage_pace._last_reset(now, usage_pace.WEEKDAYS[args.reset_day.lower()], args.reset_hour)

    print("Rough local-only estimate -- NOT Claude Code's own number. Check the real")
    print("usage panel for the precise figure; this is a fallback for when you haven't.")
    print()
    estimate = quota_estimate.get_estimate(
        reset_boundary, now=now, cache_path=quota_estimate.DEFAULT_CACHE_PATH,
        force=args.force_refresh,
    )
    age_min = (now - estimate.computed_at).total_seconds() / 60
    print(f"estimated %-used: {estimate.estimated_pct:.1f}%")
    print(f"as of:            {estimate.computed_at.strftime('%Y-%m-%d %H:%M')} ({age_min:.0f} min ago)")
    print(f"reset boundary:   {reset_boundary.strftime('%Y-%m-%d %H:%M')} ({args.reset_day.title()} {args.reset_hour}:00)")
    if estimate.last_warned_tier:
        print(f"last tier warned: {estimate.last_warned_tier}%")
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
        usage_pace_buckets=_build_usage_pace_buckets(args),
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


def cmd_pick(args: argparse.Namespace) -> int:
    """Sidebar-style Aether project picker."""
    import picker
    import projects as projmod

    if args.project:
        catalog = {p.name.lower(): p for p in projmod.list_projects()}
        hit = catalog.get(args.project.lower())
        if not hit:
            found = __import__("tabs").resolve_project(args.project)
            if not found:
                print(f"not a project: {args.project}", file=sys.stderr)
                return 1
            hit = projmod.Project(found.name, str(found.path), found.pinned, "resolved")
        return picker.act_on(hit, args.action, args.agent or __import__("tabs").default_agent())
    return picker.run_picker(action=args.action, agent=args.agent)


def cmd_license(args: argparse.Namespace) -> int:
    import license as licmod

    action = args.license_command or "status"
    if action == "paid":
        st = licmod.mark_paid()
        print(f"licensed  {st['kind']}  {st['path']}")
        print("next: waterfall remote open")
        return 0
    if action == "founder":
        st = licmod.mark_founder()
        print(f"licensed  {st['kind']}  {st['path']}")
        return 0
    st = licmod.status()
    print(f"ok:    {st['ok']}")
    print(f"kind:  {st['kind']}")
    print(f"path:  {st['path']}")
    if not st["ok"]:
        print("after Stripe: waterfall license paid")
        print("buy: https://buy.stripe.com/4gM14n0wy7cFbIAecVaMU1J")
        return 1
    return 0


def cmd_remote(args: argparse.Namespace) -> int:
    """waterfall board (ACP host). Source lives under grok-remote/."""
    repo_root = Path(__file__).resolve().parent.parent
    gr = repo_root / "grok-remote" / "bin" / "gr"
    if not gr.is_file():
        print("waterfall board missing -- grok-remote/bin/gr not found", file=sys.stderr)
        return 1
    env = os.environ.copy()
    env["GR_HOME"] = str(repo_root / "grok-remote")
    grok_exe = Path.home() / ".grok" / "bin" / "grok.EXE"
    if grok_exe.is_file():
        env["GROK_BIN"] = str(grok_exe)
    cmd = ["node", "--import", "tsx", str(gr), *list(args.remote_args or [])]
    try:
        rc = subprocess.call(cmd, env=env, cwd=str(repo_root / "grok-remote"))
    except OSError as exc:
        print(f"failed to launch waterfall board: {exc}", file=sys.stderr)
        return 1
    extra = list(args.remote_args or [])
    if rc == 0 and (not extra or extra[0] in {"open", ""}):
        try:
            import pin_app
            pin_app.pin()
        except Exception:
            pass
    return rc


def cmd_tabs(args: argparse.Namespace) -> int:
    """Flip between project CLIs using the host terminal's real tabs."""
    import tabs as tabmod

    action = args.tabs_command or "list"
    if action == "pin":
        try:
            proj = tabmod.pin_project(args.project)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"pinned {proj.name}  {proj.path}")
        return 0

    if action == "list":
        host = tabmod.pick_host(args.host)
        print(f"host:   {host.id if host else '(none on PATH -- install Windows Terminal)'}")
        print(f"agent:  {args.agent or tabmod.default_agent()}")
        print("fleet:")
        for proj in tabmod.list_fleet():
            mark = "*" if proj.pinned else " "
            print(f"  {mark} {proj.name:<28} {proj.path}")
        print()
        print("open one:   waterfall tabs open <name>")
        print("open all:   waterfall tabs mux")
        print("flip tabs:  Ctrl+Tab in Windows Terminal")
        return 0

    try:
        agent = args.agent or tabmod.default_agent()
        if action == "open":
            found = tabmod.resolve_project(args.project)
            if not found:
                print(f"not a project folder: {args.project}", file=sys.stderr)
                return 1
            fleet = [found]
            new_window = False
        else:
            names = list(args.project or [])
            if names:
                fleet = []
                for name in names:
                    found = tabmod.resolve_project(name)
                    if not found:
                        print(f"not a project folder: {name}", file=sys.stderr)
                        return 1
                    fleet.append(found)
            else:
                fleet = tabmod.list_fleet()
            new_window = not args.current_window

        host = tabmod.pick_host(args.host)
        if not host:
            print("no tab host on PATH (need wt, wezterm, tmux, or zellij)", file=sys.stderr)
            return 1
        if host.id == "wt":
            return tabmod.launch(tabmod.build_wt_command(fleet, agent, new_window=new_window), dry_run=args.dry_run)
        if host.id == "wezterm":
            code = 0
            for cmd in tabmod.build_wezterm_commands(fleet, agent):
                code = tabmod.launch(cmd, dry_run=args.dry_run) or code
            return code
        print(f"{host.id} is detected but only wt/wezterm are wired. Use --host wt.", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_desktop(args: argparse.Namespace) -> int:
    """Open the waterfall desktop command center (local GUI)."""
    repo_root = Path(__file__).resolve().parent.parent
    desktop_dir = repo_root / "desktop"
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if not (desktop_dir / "server.py").is_file():
        print("desktop/server.py missing -- is this a full waterfall checkout?", file=sys.stderr)
        return 1
    from desktop.server import main as desktop_main

    argv = ["--host", args.host, "--port", str(args.port)]
    if args.no_open:
        argv.append("--no-open")
    if args.native:
        argv.append("--native")
    return desktop_main(argv)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="waterfall",
        description="Cascade to the best model. Bare `waterfall` opens the local board.",
    )
    sub = p.add_subparsers(dest="command", required=False)

    sp = sub.add_parser("classify", help="classify a coding task to the cheapest likely tier")
    _add_prompt_args(sp)
    _add_coding_signal_args(sp)
    sp.add_argument("--tier", choices=["draft", "implement", "harden", "escalate", "ceiling"])
    sp.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    sp.set_defaults(func=cmd_classify)

    sp = sub.add_parser("run", help="author, independently review, and promote only on blocking failure")
    _add_prompt_args(sp)
    _add_coding_signal_args(sp)
    sp.add_argument("--tier", choices=["draft", "implement", "harden", "escalate", "ceiling"],
                    help="pin the starting coding tier")
    sp.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                    help="pin effort within the starting tier's allowed range")
    sp.add_argument("--no-cap", action="store_true", help="allow more than two promotions")
    sp.add_argument("--dry-run", action="store_true", help="classify and save the trace without model calls")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("why", help="explain the last run's route, attempts, cost, and promotions")
    sp.set_defaults(func=cmd_why)

    sp = sub.add_parser("leaderboard", help="print the bang-for-buck leaderboard")
    sp.add_argument("--publish", action="store_true", help="rebuild the public JSON and CSV feeds")
    sp.set_defaults(func=cmd_leaderboard)

    sp = sub.add_parser("bench", help="run the small coding harness and append task-level JSONL")
    sp.add_argument("--suite", default="coding-smoketest", help="suite id under data/suites")
    sp.add_argument("--models", required=True, help="comma-separated routing model aliases")
    sp.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                    help="override effort when the selected model's tier allows it")
    sp.add_argument("--output", help="append JSONL to this path instead of data/runs/YYYY-MM-DD.jsonl")
    sp.add_argument("--limit", type=int, help="run only the first N tasks per model")
    sp.add_argument("--dry-run", action="store_true", help="show the matrix without model calls or writes")
    sp.set_defaults(func=cmd_bench)

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
    sp.add_argument("--reset-hour", type=int, default=16,
                     help="hour (0-23, local time) the quota resets (default 16 = 4pm)")
    sp.add_argument("--utc-offset", type=float, default=8.0,
                     help="your UTC offset in hours (default 8 = SGT)")
    sp.add_argument("--session-pct", type=float, default=None,
                     help="%% used on the 5-hour rolling session limit, if your plan has one")
    sp.add_argument("--session-hours-remaining", type=float, default=None,
                     help="hours remaining on that session limit, e.g. 3.45 for \"3h 27m\"")
    sp.add_argument("--session-window-hours", type=float, default=5.0,
                     help="length of the session window in hours (default 5)")
    sp.add_argument("--model-pct", action="append", type=_parse_model_pct, default=[], metavar="MODEL=PCT",
                     help="a per-model weekly %% used, e.g. --model-pct fable=3 -- repeatable for several models")
    sp.add_argument("--bucket", action="append", type=_parse_bucket, default=[],
                     metavar="LABEL=USED_PCT:WINDOW_HOURS:HOURS_REMAINING",
                     help="a different subscription with its OWN reset schedule (Codex, Grok, anything not "
                          "on Claude's clock), e.g. --bucket codex=15:720:400 for 15%% used, 30-day window, "
                          "400h remaining -- repeatable")
    sp.set_defaults(func=cmd_usage_pace)

    sp = sub.add_parser("claude-estimate",
                         help="rough local-only estimate of Claude weekly-quota %%-used, no manual input needed")
    sp.add_argument("--reset-day", default="tuesday", choices=list(usage_pace.WEEKDAYS.keys()),
                     help="day of week the quota resets (default tuesday)")
    sp.add_argument("--reset-hour", type=int, default=16,
                     help="hour (0-23, local time) the quota resets (default 16 = 4pm)")
    sp.add_argument("--utc-offset", type=float, default=8.0,
                     help="your UTC offset in hours (default 8 = SGT)")
    sp.add_argument("--force-refresh", action="store_true",
                     help="skip the cache and rescan local transcripts now (can take real time -- "
                          "tens of seconds during an active session)")
    sp.set_defaults(func=cmd_claude_estimate)

    sp = sub.add_parser("dashboard", help="terminal ASCII dashboard of real hook/routing/usage data")
    sp.add_argument("--since-days", type=int, default=None,
                     help="restrict all sections to the last N days "
                          "(default: all-time for hooks/routing, last 8 days for the reuse trend)")
    sp.add_argument("--used-pct", type=float, default=None,
                     help="your self-reported %% of weekly quota used, from Claude Code's own usage "
                          "display -- adds the usage-pace guidance section (omit to skip it)")
    sp.add_argument("--reset-day", default="tuesday", choices=list(usage_pace.WEEKDAYS.keys()),
                     help="day of week the quota resets (default tuesday)")
    sp.add_argument("--reset-hour", type=int, default=16,
                     help="hour (0-23, local time) the quota resets (default 16 = 4pm)")
    sp.add_argument("--utc-offset", type=float, default=8.0,
                     help="your UTC offset in hours (default 8 = SGT)")
    sp.add_argument("--session-pct", type=float, default=None,
                     help="%% used on the 5-hour rolling session limit, if your plan has one")
    sp.add_argument("--session-hours-remaining", type=float, default=None,
                     help="hours remaining on that session limit, e.g. 3.45 for \"3h 27m\"")
    sp.add_argument("--session-window-hours", type=float, default=5.0,
                     help="length of the session window in hours (default 5)")
    sp.add_argument("--model-pct", action="append", type=_parse_model_pct, default=[], metavar="MODEL=PCT",
                     help="a per-model weekly %% used, e.g. --model-pct fable=3 -- repeatable for several models")
    sp.add_argument("--bucket", action="append", type=_parse_bucket, default=[],
                     metavar="LABEL=USED_PCT:WINDOW_HOURS:HOURS_REMAINING",
                     help="a different subscription with its OWN reset schedule (Codex, Grok, anything not "
                          "on Claude's clock), e.g. --bucket codex=15:720:400 -- repeatable")
    sp.set_defaults(func=cmd_dashboard)

    sp = sub.add_parser("models", help="list the current cheapest capable OpenRouter models")
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--tier", choices=["small", "medium", "large"], help="preview a specific tier band instead of the flat cheapest list")
    sp.set_defaults(func=cmd_models)

    sp = sub.add_parser(
        "tabs",
        help="flip between Aether projects as real terminal tabs (wt / wezterm)",
    )
    tabs_sub = sp.add_subparsers(dest="tabs_command", required=False)
    tabs_flags = argparse.ArgumentParser(add_help=False)
    tabs_flags.add_argument("--agent", choices=["grok", "claude", "codex", "opencode"], default=None)
    tabs_flags.add_argument("--host", choices=["wt", "wezterm", "tmux", "zellij"], default=None)
    tabs_flags.add_argument("--dry-run", action="store_true", help="print the host command, do not launch")
    tabs_sub.add_parser("list", parents=[tabs_flags], help="show fleet + detected tab host")
    op = tabs_sub.add_parser("open", parents=[tabs_flags], help="open one project in a new tab")
    op.add_argument("project", help="folder name under Aether, or an absolute path")
    mx = tabs_sub.add_parser("mux", parents=[tabs_flags], help="open the pinned fleet as tabs in one window")
    mx.add_argument("project", nargs="*", help="optional project names; default is pinned fleet")
    mx.add_argument(
        "--current-window",
        action="store_true",
        help="add tabs to the current Windows Terminal window instead of a new one",
    )
    pn = tabs_sub.add_parser("pin", parents=[tabs_flags], help="pin a project into ~/.waterfall/projects.json")
    pn.add_argument("project", help="folder name under Aether, or an absolute path")
    # Bare `waterfall tabs` == list
    sp.set_defaults(func=cmd_tabs, agent=None, host=None, dry_run=False, project=None, current_window=False)

    sp = sub.add_parser("pick", help="sidebar project picker (Aether folders)")
    sp.add_argument("project", nargs="?", help="skip the picker and act on this name")
    sp.add_argument(
        "--action",
        choices=["remote", "tab", "both"],
        default="remote",
        help="remote = waterfall board agent in that cwd (default); tab = Windows Terminal; both = both",
    )
    sp.add_argument("--agent", choices=["grok", "claude", "codex", "opencode"], default=None)
    sp.set_defaults(func=cmd_pick)

    sp = sub.add_parser("license", help="show or mark the local $30 founding license")
    lic_sub = sp.add_subparsers(dest="license_command", required=False)
    lic_sub.add_parser("status", help="print license state")
    lic_sub.add_parser("paid", help="mark paid after the Stripe checkout")
    lic_sub.add_parser("founder", help="mark this machine as the founder copy")
    sp.set_defaults(func=cmd_license)

    sp = sub.add_parser(
        "remote",
        help="waterfall.sh board (multi-agent, local Windows)",
    )
    sp.add_argument("remote_args", nargs=argparse.REMAINDER, help="passed to gr (open, status, start, ...)")
    sp.set_defaults(func=cmd_remote)

    sp = sub.add_parser(
        "desktop",
        help="open the local desktop GUI (dashboard + cascade + agent launcher)",
    )
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-open", action="store_true", help="bind the server only, don't open a browser")
    sp.add_argument(
        "--native",
        action="store_true",
        help="use a pywebview native window if installed (pip install pywebview)",
    )
    sp.set_defaults(func=cmd_desktop)

    return p


def open_board() -> int:
    """Start the local board, pin a Desktop shortcut, open an app window."""
    class _Args:
        remote_args = ["open", "--local"]
    rc = cmd_remote(_Args())  # type: ignore[arg-type]
    try:
        import pin_app
        info = pin_app.pin()
        opened = pin_app.open_app_window()
        print(f"board  http://127.0.0.1:7910")
        if info.get("written"):
            print("pinned " + info["written"][0])
        if opened:
            print("window Helium --app (or default browser)")
    except Exception as exc:
        print(f"pin/open skipped: {exc}", file=sys.stderr)
    return rc


def main(argv: list[str] | None = None) -> int:
    if not SMART_ROUTER_AVAILABLE:
        print("classifier not importable -- run from the router/ directory or `pip install -e .`.", file=sys.stderr)
        return 1
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        return open_board()
    parser = build_parser()
    args = parser.parse_args(raw)
    if args.command is None:
        return open_board()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
