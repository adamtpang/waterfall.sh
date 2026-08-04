"""Savings tracker -- append-only JSONL ledger of routing events + summary.

Mirrors the ~/.claude/token_savings.jsonl pattern from the Claude-Token-Saver
fork this project grew out of: one JSON object per line, append-only, so
concurrent CLI invocations never corrupt each other's writes.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from .classifier.types import SavingsEvent, SavingsSummary
except ImportError:
    from classifier.types import SavingsEvent, SavingsSummary

DEFAULT_LEDGER_PATH = Path.home() / ".claude" / "token_savings.jsonl"

# Rough blended Claude pricing (USD/token), used only to estimate what
# tokens routed away from Claude would otherwise have cost. This is a
# display estimate for the ledger, not billing-accurate -- update if
# pricing changes materially.
CLAUDE_INPUT_PRICE_PER_TOKEN = 3e-6
CLAUDE_OUTPUT_PRICE_PER_TOKEN = 15e-6


def estimate_cost_saved(tokens_saved: int, openrouter_cost_usd: float) -> float:
    """What those tokens would've cost on Claude, minus what was actually
    paid to OpenRouter to handle them instead. Floored at 0."""
    claude_equivalent = tokens_saved * CLAUDE_INPUT_PRICE_PER_TOKEN
    return round(max(0.0, claude_equivalent - openrouter_cost_usd), 6)


class SavingsTracker:
    """Read/write the append-only JSONL savings ledger."""

    def __init__(self, ledger_path: Optional[Path] = None) -> None:
        self.ledger_path = Path(ledger_path) if ledger_path else DEFAULT_LEDGER_PATH
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: SavingsEvent) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event)) + "\n")

    def load_events(self, since: Optional[datetime] = None) -> list[SavingsEvent]:
        if not self.ledger_path.is_file():
            return []

        events: list[SavingsEvent] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                event = SavingsEvent(**data)
            except (json.JSONDecodeError, TypeError):
                continue  # skip corrupt/partial lines rather than fail the whole read
            if since is not None:
                try:
                    ts = datetime.fromisoformat(event.timestamp)
                except ValueError:
                    ts = None
                if ts is not None and ts < since:
                    continue
            events.append(event)
        return events

    def summarize(self, events: Optional[list[SavingsEvent]] = None) -> SavingsSummary:
        events = events if events is not None else self.load_events()
        summary = SavingsSummary()
        if not events:
            return summary

        summary.total_prompts = len(events)
        free_pcts: list[float] = []
        for e in events:
            summary.tokens_sent_to_free += e.free_tokens_sent
            summary.tokens_sent_to_claude += e.claude_tokens_needed
            summary.tokens_avoided += e.tokens_saved
            summary.estimated_cost_saved += e.cost_saved_usd
            summary.by_backend[e.backend_used] = summary.by_backend.get(e.backend_used, 0) + 1
            if e.model_tier:
                summary.by_model_tier[e.model_tier] = summary.by_model_tier.get(e.model_tier, 0) + 1
            for t in e.task_types:
                summary.by_task_type[t] = summary.by_task_type.get(t, 0) + 1
            total = e.free_tokens_sent + e.claude_tokens_needed
            if total > 0:
                free_pcts.append(e.free_tokens_sent / total)

        summary.avg_free_pct = round(sum(free_pcts) / len(free_pcts), 3) if free_pcts else 0.0
        summary.estimated_cost_saved = round(summary.estimated_cost_saved, 4)
        return summary
