"""Claude plan weekly-quota pace check -- is self-reported %-used tracking
ahead of, on, or behind a flat linear share of the week elapsed since the
last reset.

This does NOT compute %-used itself -- Claude Max/Pro plan quota weighs
cached/reused tokens far lighter than fresh ones (the whole point of
prompt caching), and neither the exact weighting formula nor the plan's
ceiling is available from local transcripts. The %-used number has to
come from Claude Code's own usage display; this module only answers
"given that number, and how much of the week has passed, am I pacing
comfortably toward the next reset."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

HOURS_PER_WEEK = 24 * 7

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

# Within this many percentage points of the elapsed-time share counts as
# "on pace" rather than meaningfully ahead or behind.
STATUS_MARGIN = 5.0


@dataclass
class PaceResult:
    used_pct: float
    elapsed_pct: float
    pace_delta: float   # used_pct - elapsed_pct; positive = burning faster than time is passing
    status: str
    last_reset: datetime
    next_reset: datetime
    hours_elapsed: float
    hours_remaining: float


@dataclass
class BucketResult:
    """One quota clock -- Claude Code's own usage panel shows several of
    these at once (a 5-hour rolling limit, a weekly all-models limit, and
    weekly per-model limits), each on its own window length and its own
    reset. PaceResult above is the single-weekly-bucket case; this is the
    general one any window length reduces to."""
    label: str
    used_pct: float
    elapsed_pct: float
    pace_delta: float
    status: str
    window_hours: float
    hours_remaining: float


def _pace_status(used_pct: float, elapsed_pct: float, window_word: str) -> tuple[float, str]:
    delta = round(used_pct - elapsed_pct, 1)
    if delta > STATUS_MARGIN:
        status = f"burning faster than the {window_word} is passing -- risk of running out before reset"
    elif delta < -STATUS_MARGIN:
        status = f"comfortable cushion -- using less than the {window_word}'s pace"
    else:
        status = f"tracking the {window_word} evenly"
    return delta, status


def _last_reset(now: datetime, reset_weekday: int, reset_hour: int) -> datetime:
    """Most recent reset boundary at or before `now`."""
    candidate = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    days_back = (candidate.weekday() - reset_weekday) % 7
    candidate -= timedelta(days=days_back)
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def compute_pace(
    used_pct: float,
    now: datetime,
    reset_weekday: int = WEEKDAYS["tuesday"],
    reset_hour: int = 17,
) -> PaceResult:
    last_reset = _last_reset(now, reset_weekday, reset_hour)
    next_reset = last_reset + timedelta(days=7)

    hours_elapsed = (now - last_reset).total_seconds() / 3600
    hours_remaining = (next_reset - now).total_seconds() / 3600
    elapsed_pct = round(hours_elapsed / HOURS_PER_WEEK * 100, 1)
    delta, status = _pace_status(used_pct, elapsed_pct, "week")

    return PaceResult(
        used_pct=used_pct,
        elapsed_pct=elapsed_pct,
        pace_delta=delta,
        status=status,
        last_reset=last_reset,
        next_reset=next_reset,
        hours_elapsed=round(hours_elapsed, 1),
        hours_remaining=round(hours_remaining, 1),
    )


def compute_bucket_pace(label: str, used_pct: float, window_hours: float, hours_remaining: float) -> BucketResult:
    """Same pace math as compute_pace(), generalized to any window length
    and driven by a countdown (what Claude Code's panel actually shows,
    e.g. "resets in 3h 27m") rather than a weekday+hour reset schedule."""
    hours_remaining = max(0.0, hours_remaining)
    hours_elapsed = max(0.0, window_hours - hours_remaining)
    elapsed_pct = round(hours_elapsed / window_hours * 100, 1) if window_hours else 0.0
    delta, status = _pace_status(used_pct, elapsed_pct, "window")
    return BucketResult(
        label=label, used_pct=used_pct, elapsed_pct=elapsed_pct, pace_delta=delta,
        status=status, window_hours=window_hours, hours_remaining=round(hours_remaining, 2),
    )


def guidance(buckets: list[BucketResult]) -> str:
    """Which bucket is actually the binding constraint right now (tightest
    relative to its own elapsed time, not just the lowest raw %-used --
    3% used with only 3% of the window elapsed is just as tight as 50%
    used with 50% elapsed), and what that means for pushing harder on one
    model vs easing off. All buckets must stay under 100%, so the tightest
    one governs even if others have plenty of room."""
    if not buckets:
        return "no usage buckets given"

    tightest = max(buckets, key=lambda b: b.pace_delta)
    lines = [
        f"binding constraint: {tightest.label} ({tightest.pace_delta:+.1f} points vs its own elapsed time)"
    ]
    if tightest.pace_delta > STATUS_MARGIN:
        lines.append(f"ease off {tightest.label} specifically -- it's the one actually at risk of running out early")
    else:
        lines.append("nothing is currently tight -- every bucket has room relative to its own clock")

    roomiest = min(buckets, key=lambda b: b.pace_delta)
    if roomiest.label != tightest.label and roomiest.pace_delta < -STATUS_MARGIN:
        lines.append(f"most headroom: {roomiest.label} ({roomiest.pace_delta:+.1f} points) -- safe to lean on this one harder")

    return "\n".join(lines)
