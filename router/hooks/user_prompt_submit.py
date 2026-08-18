"""UserPromptSubmit hook -- two independent checks on every prompt:

1. Routing nudge (_routing_nudge): classifies the prompt (local, zero
   network, ~instant), and when it looks routine enough that part of it
   could be handed to a cheaper model, surfaces a one-line nudge. The
   Level 3-ish piece from the token-saving pass: instead of relying on
   Claude to remember to self-invoke the `waterfall` skill, this runs
   automatically before the prompt is even processed.

2. Quota warning (_quota_warning): a rough, local-only estimate of Claude
   weekly-quota pressure (see quota_estimate.py), warned once per tier
   crossed (70/85/95%) rather than on every prompt. Independent of (1) --
   quota safety and task routing are different concerns, so this runs
   even on short prompts or prompts that genuinely need Claude.

Contract: must NEVER block a prompt and must NEVER raise. Any failure in
either check (classifier not importable, malformed stdin, transcript scan
error, whatever) just means that check is silently skipped -- the session
continues completely normally. This only reads stdin and prints to stdout;
it makes no network calls and sends nothing anywhere.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_WORDS = 6  # skip trivial prompts -- not worth classifying, and noisy.
# Was 12 until 2026-08-04 live testing showed real routine asks ("rename the
# variable x to userCount throughout utils.py", 8 words) getting skipped.

_ARITHMETIC_RE = re.compile(r"^[\d\s.]+(?:[-+*/^%][\d\s.]+)+$")
# Bare arithmetic ("2+2") is short enough to fail MIN_WORDS but, unlike a
# short conversational follow-up ("yes, look into why"), it's fully
# self-contained -- answering it needs no conversation history, so it's
# always safe to nudge on. MIN_WORDS exists specifically to filter the
# former; without this carve-out it silently swallows the latter too,
# which is how "2+2" and "yes, look into why" ended up treated the same
# (both short) even though only one is actually unroutable.


def _routing_nudge(prompt: str, cwd: str) -> str | None:
    """The original routing nudge -- unchanged in spirit, just extracted so
    it can run independently of the quota-warning check below."""
    stripped = prompt.strip()
    if len(prompt.split()) < MIN_WORDS and not _ARITHMETIC_RE.match(stripped):
        return None

    try:
        from smart_router import SmartRouter
        router = SmartRouter()
        cls = router.classify(prompt)
    except Exception:
        return None

    if cls.routing == "claude":
        return None  # genuinely needs Claude -- no nudge

    try:
        import openrouter_api_client as orc
        tier = orc.tier_for_complexity(cls.complexity_score)
    except Exception:
        tier = "?"

    context = (
        f"[waterfall] This prompt classified as routing='{cls.routing}', "
        f"tier='{tier}' (complexity {cls.complexity_score}, "
        f"~{cls.estimated_free_pct:.0%} looks routine). If part of this is "
        f"mechanical/boilerplate, consider using the waterfall skill to "
        f"route that part to a cheaper model instead of generating it "
        f"inline."
    )

    try:
        from hook_log import log_nudge
        log_nudge(cwd, f"routing={cls.routing} tier={tier} complexity={cls.complexity_score}")
    except Exception:
        pass  # logging is a side effect -- never let it block the nudge itself

    return context


def _quota_warning() -> str | None:
    """Independent of routing: a rough, local-only estimate of Claude
    weekly-quota pressure, warned once per tier crossed (70/85/95%), not on
    every prompt. Runs regardless of what the routing nudge decided --
    quota safety and task routing are different concerns. Any failure here
    (cache unreadable, transcript scan errors, whatever) means no warning,
    same fail-open contract as the rest of this hook."""
    try:
        from datetime import datetime, timedelta, timezone
        import usage_pace
        import quota_estimate

        tz = timezone(timedelta(hours=8))  # SGT, this project's default
        now = datetime.now(tz)
        reset_boundary = usage_pace._last_reset(now, usage_pace.WEEKDAYS["tuesday"], 16)

        # cache_path passed explicitly (not relying on get_estimate's/
        # check_tier_crossing's own default parameter) so tests can mock
        # quota_estimate.DEFAULT_CACHE_PATH and actually have it take
        # effect -- a bound default parameter is fixed at def time and
        # won't see a module-attribute patch applied after import.
        estimate = quota_estimate.get_estimate(
            reset_boundary, now=now, cache_path=quota_estimate.DEFAULT_CACHE_PATH,
        )
        tier = quota_estimate.check_tier_crossing(estimate, cache_path=quota_estimate.DEFAULT_CACHE_PATH)
        if tier is None:
            return None

        return (
            f"[waterfall] Rough local estimate: you've likely crossed ~{tier}% of this "
            f"week's Claude quota (estimated {estimate.estimated_pct:.0f}% from local token "
            f"volume, not Claude Code's own number -- check the real usage panel and run "
            f"`waterfall usage-pace` for the precise figure)."
        )
    except Exception:
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = payload.get("user_prompt") or payload.get("prompt") or ""
    cwd = payload.get("cwd", "")

    routing_context = _routing_nudge(prompt, cwd)
    quota_context = _quota_warning()

    parts = [c for c in (routing_context, quota_context) if c]
    if not parts:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(parts),
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
