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
    delta = round(used_pct - elapsed_pct, 1)

    if delta > STATUS_MARGIN:
        status = "burning faster than the week is passing -- risk of running out before reset"
    elif delta < -STATUS_MARGIN:
        status = "comfortable cushion -- using less than the week's pace"
    else:
        status = "tracking the week evenly"

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
