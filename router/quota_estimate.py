"""Cache and tiered-warning logic for the local-transcript-based Claude
quota estimate (claude_usage.estimate_pct_used).

Scanning transcripts is too slow to do on every hook invocation -- this
caches the last computed estimate and only recomputes when it's stale or
the weekly reset boundary has rolled over. It also tracks which warning
tier was last surfaced, so the nudge hook fires a warning once per tier
crossed (70/85/95%), not on every single prompt once you're over one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_CACHE_PATH = Path.home() / ".claude" / "waterfall_quota_estimate_cache.json"
# A full transcript scan (claude_usage.estimate_pct_used) takes real time --
# tens of seconds during an active session, since actively-touched files
# can't be mtime-skipped. 30 minutes keeps that cost rare rather than
# pretending it's free; a cache hit is instant either way.
REFRESH_INTERVAL = timedelta(minutes=30)
WARNING_TIERS = (70, 85, 95)


@dataclass
class CachedEstimate:
    estimated_pct: float
    computed_at: datetime
    reset_boundary: datetime
    last_warned_tier: int = 0


def _load(cache_path: Path) -> CachedEstimate | None:
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return CachedEstimate(
            estimated_pct=data["estimated_pct"],
            computed_at=datetime.fromisoformat(data["computed_at"]),
            reset_boundary=datetime.fromisoformat(data["reset_boundary"]),
            last_warned_tier=data.get("last_warned_tier", 0),
        )
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        return None


def _save(cache_path: Path, estimate: CachedEstimate) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "estimated_pct": estimate.estimated_pct,
            "computed_at": estimate.computed_at.isoformat(),
            "reset_boundary": estimate.reset_boundary.isoformat(),
            "last_warned_tier": estimate.last_warned_tier,
        }), encoding="utf-8")
    except OSError:
        pass  # best-effort cache -- a write failure never blocks the caller


def get_estimate(
    reset_boundary: datetime,
    now: datetime | None = None,
    cache_path: Path = DEFAULT_CACHE_PATH,
    compute_fn=None,
    force: bool = False,
) -> CachedEstimate:
    """Return a cached estimate if fresh and from the same reset window,
    else recompute via compute_fn(reset_boundary) and cache the result.
    A new reset_boundary (new week) always forces a fresh compute and
    resets last_warned_tier, since a new week means no tier has fired yet.
    force=True skips the freshness check entirely (an explicit on-demand
    refresh, e.g. `waterfall claude-estimate --force-refresh`)."""
    now = now or datetime.now(timezone.utc)
    cached = _load(cache_path)
    if (not force and cached is not None
            and cached.reset_boundary == reset_boundary
            and now - cached.computed_at < REFRESH_INTERVAL):
        return cached

    if compute_fn is None:
        import claude_usage as cu
        compute_fn = cu.estimate_pct_used

    fresh_pct = compute_fn(reset_boundary)
    carried_tier = cached.last_warned_tier if (cached and cached.reset_boundary == reset_boundary) else 0
    fresh = CachedEstimate(
        estimated_pct=fresh_pct, computed_at=now, reset_boundary=reset_boundary,
        last_warned_tier=carried_tier,
    )
    _save(cache_path, fresh)
    return fresh


def check_tier_crossing(estimate: CachedEstimate, cache_path: Path = DEFAULT_CACHE_PATH) -> int | None:
    """If estimate.estimated_pct has newly crossed into a warning tier
    above what was last warned about, return that tier and persist it so
    the same tier doesn't fire again. Else return None."""
    newly_crossed = [t for t in WARNING_TIERS if estimate.estimated_pct >= t and t > estimate.last_warned_tier]
    if not newly_crossed:
        return None
    tier = max(newly_crossed)
    estimate.last_warned_tier = tier
    _save(cache_path, estimate)
    return tier
