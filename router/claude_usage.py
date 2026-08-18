"""Reads Claude Code's own session transcripts (~/.claude/projects/*/*.jsonl)
to compute REAL token usage -- not routed-away savings, not estimates, but
what Claude Code itself actually processed turn by turn. This is the ground
truth for "why tokens are spent" and for measuring whether the token-saving
habits in this project are actually working.

Every assistant turn's transcript entry carries the exact usage block the
API returned: input_tokens (genuinely new this turn), cache_creation_
input_tokens (new context written to the prompt cache, reusable next turn),
cache_read_input_tokens (context reused from a prior turn's cache write --
this is the "reused input" the token-saving transcript is about), and
output_tokens. Nothing here is estimated from prompt text; it's the
literal usage block Anthropic's API returned for that call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Rough public per-token pricing (USD), standard tier -- display estimates
# only, not billing-accurate. Matched by substring against the model name
# recorded in the transcript (e.g. "claude-sonnet-5").
MODEL_PRICING = {
    "opus": (15e-6, 75e-6),
    "sonnet": (3e-6, 15e-6),
    "haiku": (1e-6, 5e-6),
    "fable": (3e-6, 15e-6),  # no public pricing yet; sonnet-tier assumed
}
DEFAULT_PRICING = (3e-6, 15e-6)  # sonnet-tier fallback for unrecognized models

# Anthropic's published prompt-caching multipliers on the base input price.
CACHE_READ_DISCOUNT = 0.1        # cache reads cost ~10% of a fresh input token
CACHE_WRITE_1H_MULTIPLIER = 2.0  # 1-hour cache writes cost ~2x a fresh input token


def _pricing_for(model: str) -> tuple[float, float]:
    model_lower = model.lower()
    for key, prices in MODEL_PRICING.items():
        if key in model_lower:
            return prices
    return DEFAULT_PRICING


# Known tiers, checked in this order so "other" only catches genuinely
# unrecognized strings like "<synthetic>" (internal turns, not a real model).
MODEL_TIERS = ["opus", "sonnet", "haiku", "fable"]


def simplify_model(model: str) -> str:
    """Collapse a raw model string (e.g. "claude-sonnet-5",
    "claude-haiku-4-5-20251001", "claude-opus-4-8") down to its tier name,
    for grouping real usage by model family rather than exact version."""
    model_lower = model.lower()
    for tier in MODEL_TIERS:
        if tier in model_lower:
            return tier
    return "other"


@dataclass
class UsageTurn:
    """One assistant turn's real, API-reported token usage."""
    project: str
    session_id: str
    timestamp: str
    model: str
    input_tokens: int
    cache_creation_tokens: int
    cache_read_tokens: int
    output_tokens: int

    @property
    def total_input_seen(self) -> int:
        """Everything the model actually read this turn: fresh + newly
        cached + reused-from-cache."""
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def estimated_cost_usd(self) -> float:
        in_price, out_price = _pricing_for(self.model)
        cost = self.input_tokens * in_price
        cost += self.cache_creation_tokens * in_price * CACHE_WRITE_1H_MULTIPLIER
        cost += self.cache_read_tokens * in_price * CACHE_READ_DISCOUNT
        cost += self.output_tokens * out_price
        return cost


def _iter_transcript_files(project: Optional[str] = None) -> list[Path]:
    if not CLAUDE_PROJECTS_DIR.is_dir():
        return []
    dirs = [d for d in CLAUDE_PROJECTS_DIR.iterdir() if d.is_dir()]
    if project:
        dirs = [d for d in dirs if project.lower() in d.name.lower()]
    files: list[Path] = []
    for d in dirs:
        files.extend(d.glob("*.jsonl"))
    return files


def _parse_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_usage_turns(
    project: Optional[str] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    transcript_files: Optional[list[Path]] = None,
) -> list[UsageTurn]:
    """Parse every assistant turn's real usage across matching transcripts.

    `transcript_files` lets callers (tests) bypass disk discovery entirely.
    """
    turns: list[UsageTurn] = []
    files = transcript_files if transcript_files is not None else _iter_transcript_files(project)
    for path in files:
        project_name = path.parent.name
        if since is not None:
            # Transcripts are append-only -- a file's mtime is its last
            # write, so if that predates `since`, every line in it does
            # too. Skipping the read entirely (rather than reading and
            # filtering line by line) is what actually makes --since-days
            # fast: most of an active user's transcript directory is old,
            # inactive project files this avoids opening at all. Compared
            # in UTC regardless of `since`'s own tzinfo, since a file
            # mtime is an absolute point in time either way.
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                mtime = None
            since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
            if mtime is not None and mtime < since_utc:
                continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
                continue
            msg = d.get("message") or {}
            usage = msg.get("usage") or {}
            if not usage:
                continue
            ts_raw = d.get("timestamp")
            ts = _parse_timestamp(ts_raw)
            if since is not None and ts is not None and ts < since:
                continue
            if until is not None and ts is not None and ts > until:
                continue
            turns.append(UsageTurn(
                project=project_name,
                session_id=d.get("sessionId", ""),
                timestamp=ts_raw or "",
                model=msg.get("model", ""),
                input_tokens=usage.get("input_tokens", 0) or 0,
                cache_creation_tokens=usage.get("cache_creation_input_tokens", 0) or 0,
                cache_read_tokens=usage.get("cache_read_input_tokens", 0) or 0,
                output_tokens=usage.get("output_tokens", 0) or 0,
            ))
    return turns


@dataclass
class UsageSummary:
    turn_count: int = 0
    session_count: int = 0
    input_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    @property
    def total_input_seen(self) -> int:
        return self.input_tokens + self.cache_creation_tokens + self.cache_read_tokens

    @property
    def reused_input_pct(self) -> float:
        """The transcript's core metric: what share of everything processed
        this turn was material the model had already seen before (cache
        reads) vs genuinely new. High = compounding-conversation cost."""
        total = self.total_input_seen
        return round(self.cache_read_tokens / total, 4) if total else 0.0


def summarize(turns: list[UsageTurn]) -> UsageSummary:
    s = UsageSummary()
    sessions = set()
    for t in turns:
        s.turn_count += 1
        sessions.add(t.session_id)
        s.input_tokens += t.input_tokens
        s.cache_creation_tokens += t.cache_creation_tokens
        s.cache_read_tokens += t.cache_read_tokens
        s.output_tokens += t.output_tokens
        s.estimated_cost_usd += t.estimated_cost_usd
    s.session_count = len(sessions)
    s.estimated_cost_usd = round(s.estimated_cost_usd, 4)
    return s


def group_by_day(turns: list[UsageTurn]) -> dict[str, UsageSummary]:
    """Bucket turns by the UTC calendar day of their timestamp (YYYY-MM-DD
    prefix of the ISO timestamp) -- the basis for a before/after trend."""
    by_day: dict[str, list[UsageTurn]] = {}
    for t in turns:
        if not t.timestamp:
            continue
        day = t.timestamp[:10]
        by_day.setdefault(day, []).append(t)
    return {day: summarize(day_turns) for day, day_turns in sorted(by_day.items())}


def group_by_day_and_model(turns: list[UsageTurn]) -> dict[str, dict[str, int]]:
    """Bucket turn counts by day, then by simplified model tier -- e.g.
    {"2026-08-10": {"sonnet": 6203, "opus": 41, "haiku": 8}}. Reveals model
    differentiation (or the lack of it) day by day, which raw volume alone
    doesn't show -- 6,000 Sonnet turns and 6,000 turns split across tiers
    look identical in every other metric here."""
    by_day: dict[str, dict[str, int]] = {}
    for t in turns:
        if not t.timestamp:
            continue
        day = t.timestamp[:10]
        tier = simplify_model(t.model)
        by_day.setdefault(day, {})
        by_day[day][tier] = by_day[day].get(tier, 0) + 1
    return dict(sorted(by_day.items()))


def top_projects_by_model(
    turns: list[UsageTurn], tier: str, limit: int = 5
) -> list[tuple[str, int]]:
    """Projects with the most turns on a given model tier, descending --
    e.g. tier="opus" surfaces which projects actually reach for heavier
    reasoning, as an organic signal rather than a guess."""
    counts: dict[str, int] = {}
    for t in turns:
        if simplify_model(t.model) == tier:
            counts[t.project] = counts.get(t.project, 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]


# Rough, single-data-point calibration (2026-08-15): 11,206,650,304 raw
# tokens processed (fresh input + cache writes + cache reads + output,
# across every project) corresponded to Adam's real self-reported 92%
# weekly Claude quota used, 96.9h into a 168h week. This is NOT Anthropic's
# real internal quota-weighting formula (unpublished, and almost certainly
# discounts cache reads the way API billing does) -- it's a rough linear
# proxy from local data alone. Good enough for "you're probably getting
# close" automatic warnings; not precise enough to trust over Claude
# Code's own self-reported %, which always wins when you have it.
EST_TOKENS_PER_PERCENT = 121_800_000


def estimate_pct_used(since: datetime) -> float:
    """Rough estimate of weekly quota %-used from real local token volume
    processed since `since` (pass the last weekly reset boundary). See
    EST_TOKENS_PER_PERCENT for the calibration and its caveat -- this is
    an approximation, surfaced as one, never a substitute for the real
    number when Claude Code's own display is checked."""
    turns = load_usage_turns(since=since)
    total = sum(t.total_input_seen for t in turns) + sum(t.output_tokens for t in turns)
    return round(total / EST_TOKENS_PER_PERCENT, 1)


def estimate_pct_used_rolling(since: datetime) -> float:
    """Same math as estimate_pct_used, for a rolling window (e.g. the
    5-hour session limit) instead of a fixed weekly reset -- pass
    `now - window_hours` as `since`. Rougher than the weekly estimate: the
    single calibration point behind EST_TOKENS_PER_PERCENT was measured
    against a full week's aggregate volume, not a 5-hour slice, and
    Claude's real session-limit weighting may not scale linearly the same
    way. Treat this as directional (is it climbing fast right now), not
    precise."""
    return estimate_pct_used(since)


def estimate_pct_used_by_tier(since: datetime, tier: str) -> float:
    """Same math, restricted to turns on one model tier (e.g. "fable") --
    for a per-model weekly bucket. Rougher still: EST_TOKENS_PER_PERCENT
    was calibrated against ALL-model aggregate volume, and a single tier's
    real per-token quota weighting could differ meaningfully from the
    blended average. Directional only, same as estimate_pct_used_rolling."""
    turns = [t for t in load_usage_turns(since=since) if simplify_model(t.model) == tier]
    total = sum(t.total_input_seen for t in turns) + sum(t.output_tokens for t in turns)
    return round(total / EST_TOKENS_PER_PERCENT, 1)
