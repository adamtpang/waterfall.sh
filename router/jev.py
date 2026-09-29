"""Jev second opinion for the prompt router.

The local keyword classifier stays the instant, offline first pass. When its
confidence is low (it usually is: it reports 0.3 whenever no keyword matches),
route_with_api() asks TypeSafe's Jev on OpenRouter for a calibrated verdict:
one call, two questions (free/split/claude choice, plus "needs outside
context"). Any failure, timeout, or low-confidence answer returns None or keeps
the local decision, so routing never breaks because Jev is unavailable.

Measured 2026-09-19 on 30 labeled prompts (scratchpad eval, not a benchmark):
local classifier 12/30, Jev alone 25/30, Jev plus the context override below
29/30. About 0.43s and $0.000018 per call. Threshold and cutoff were tuned on
that same small set, so treat them as a starting point.

Jev also picks the model tier (small/medium/large price band) for the text
that gets routed to a cheap model, replacing tier_for_complexity() when it is
confident. Measured 2026-09-19 on 30 labeled synthetic prompts:
tier_for_complexity 10/30 (it put 29 of 30 in "small"), Jev 29/30, about 0.37s
and 0.000018 USD per call.

Disable with WATERFALL_JEV=0.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Optional

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = "~typesafe/jev-latest"
KEY_FILE = Path.home() / ".claude" / "openrouter_key.txt"

# Ask Jev only when the local classifier is less sure than this.
LOCAL_CONFIDENT = 0.6
# Below this, Jev's own top probability is not trusted and the local call stands.
JEV_THRESHOLD = 0.5
# A "free" verdict on text that needs outside context can't be served by a
# cheap model reading only the prompt ("fix it", "do the same for the other one").
CONTEXT_CUTOFF = 0.5
# Tier picks below this confidence fall back to tier_for_complexity(). On the
# 30-prompt set the one wrong pick was 0.63 and the lowest right one 0.69.
TIER_THRESHOLD = 0.65
TIERS = ("small", "medium", "large")

TIER_QUESTIONS: dict[str, Any] = {
    "tier": {
        "type": "score",
        "instructions": ("This self-contained task will be sent to a cheap model. How capable "
                         "a model does it need to get it right on the first try?"),
        "criteria": [
            "small: trivial or mechanical; any tiny model gets it right (a lookup, a rename, a one-liner, a format conversion)",
            "medium: a short, ordinary piece of code or writing with a few details to get right (a typical function, a small script, a clear explanation)",
            "large: needs careful multi-step reasoning, tricky edge cases, or a nontrivial algorithm or design, even though it is self-contained",
        ],
    },
}

QUESTIONS: dict[str, Any] = {
    "route": {
        "type": "choice",
        "instructions": ("A developer is about to send this request to an expensive "
                         "frontier coding model. Who should handle it?"),
        "criteria": {
            "free": "Small, self-contained, mechanical. A cheap model can do all of it from the text alone.",
            "split": ("Contains a mechanical part a cheap model can do AND a hard part "
                      "needing deep reasoning or codebase knowledge."),
            "claude": "Needs deep reasoning, broad codebase context, or careful judgment throughout.",
        },
    },
    "needs_context": {
        "type": "noul",
        "instructions": ("Does answering this require seeing the repository, prior "
                         "conversation, or files that are not included in the text itself?"),
    },
}


@dataclass
class JevVerdict:
    routing: str
    confidence: float
    needs_context: float
    cost_usd: float = 0.0


def enabled() -> bool:
    return os.environ.get("WATERFALL_JEV", "1").strip() != "0"


def _load_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    try:
        return KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


@dataclass
class TierVerdict:
    tier: str
    confidence: float
    cost_usd: float = 0.0


def _call(state: str, questions: dict, timeout: float, key: Optional[str],
          urlopen: Callable[..., Any]) -> Optional[dict]:
    key = key or _load_key()
    if not key:
        return None
    req = urllib.request.Request(
        URL,
        data=json.dumps({"model": MODEL, "state": state, "questions": questions}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def ask_tier(text: str, timeout: float = 3.0, key: Optional[str] = None,
             urlopen: Callable[..., Any] = urllib.request.urlopen) -> Optional[TierVerdict]:
    """Which cheap-model tier the routed text needs. None on any failure."""
    try:
        data = _call(text, TIER_QUESTIONS, timeout, key, urlopen)
        if data is None:
            return None
        probs = data["answers"]["tier"]["probabilities"]
        best = max(probs, key=lambda k: probs[k])
        return TierVerdict(
            tier=TIERS[int(best)],
            confidence=float(probs[best]),
            cost_usd=float((data.get("usage") or {}).get("cost") or 0.0),
        )
    except Exception:  # noqa: BLE001
        return None


def pick_tier(verdict: Optional[TierVerdict], local_tier: str) -> tuple[str, str]:
    """(tier, source): Jev's tier when confident, else the local one."""
    if verdict is not None and verdict.confidence >= TIER_THRESHOLD:
        return verdict.tier, "jev"
    return local_tier, "local"


def ask(prompt: str, timeout: float = 3.0, key: Optional[str] = None,
        urlopen: Callable[..., Any] = urllib.request.urlopen) -> Optional[JevVerdict]:
    """One Jev call. Returns None on any failure; never raises."""
    try:
        data = _call(prompt, QUESTIONS, timeout, key, urlopen)
        if data is None:
            return None
        route = data["answers"]["route"]
        choice = route["choice"]
        if choice not in ("free", "split", "claude"):
            return None
        return JevVerdict(
            routing=choice,
            confidence=float(max(route.get("probabilities", {}).values(), default=0.0)),
            needs_context=float(data["answers"]["needs_context"]["noul"]),
            cost_usd=float((data.get("usage") or {}).get("cost") or 0.0),
        )
    except Exception:  # noqa: BLE001 - a second opinion must never break routing
        return None


def should_ask(cls: Any) -> bool:
    return cls.confidence < LOCAL_CONFIDENT


def refine(cls: Any, verdict: Optional[JevVerdict]) -> Any:
    """Return a TaskClassification adjusted by Jev, or `cls` unchanged."""
    if verdict is None:
        return cls
    routing, conf = verdict.routing, verdict.confidence
    if routing == "free" and verdict.needs_context >= CONTEXT_CUTOFF:
        routing, conf = "claude", verdict.needs_context
    if conf < JEV_THRESHOLD or routing == cls.routing:
        return cls
    est_free = {"free": 1.0, "claude": 0.0}.get(routing, cls.estimated_free_pct
                                                if cls.routing == "split" else 0.5)
    return replace(
        cls,
        routing=routing,
        estimated_free_pct=est_free,
        reasoning=f"{cls.reasoning} | jev: {routing} ({conf:.2f}, was {cls.routing})",
    )
