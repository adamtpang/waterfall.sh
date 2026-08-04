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
from datetime import datetime
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
