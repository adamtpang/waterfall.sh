"""UserPromptSubmit hook -- classifies the incoming prompt (local, zero
network, ~instant) and, when it looks routine enough that part of it could
be handed to a cheaper model, surfaces a one-line nudge as additional
context. This is the Level 3-ish piece from the token-saving pass: instead
of relying on Claude to remember to self-invoke the `waterfall` skill, this
runs automatically before the prompt is even processed.

Contract: must NEVER block a prompt and must NEVER raise. Any failure here
(classifier not importable, malformed stdin, whatever) just means no nudge
-- the session continues completely normally. This only reads stdin and
prints to stdout; it makes no network calls and sends nothing anywhere.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MIN_WORDS = 6  # skip trivial prompts -- not worth classifying, and noisy.
# Was 12 until 2026-08-04 live testing showed real routine asks ("rename the
# variable x to userCount throughout utils.py", 8 words) getting skipped.


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = payload.get("user_prompt") or payload.get("prompt") or ""
    if len(prompt.split()) < MIN_WORDS:
        return 0

    try:
        from smart_router import SmartRouter
        router = SmartRouter()
        cls = router.classify(prompt)
    except Exception:
        return 0

    if cls.routing == "claude":
        return 0  # genuinely needs Claude -- no nudge

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

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
