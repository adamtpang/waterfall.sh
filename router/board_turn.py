"""One classify (+ optional cheap route) for the board Send path."""

from __future__ import annotations

import json
import sys
from typing import Any

from smart_router import API_ROUTER_AVAILABLE, SMART_ROUTER_AVAILABLE, SmartRouter


def run_turn(prompt: str, route: bool = True) -> dict[str, Any]:
    out: dict[str, Any] = {
        "routing": "claude",
        "complexity": 1.0,
        "reasoning": "",
        "handled": False,
        "cheap_text": None,
        "grok_prompt": prompt,
        "model": None,
        "cost_usd": 0.0,
        "tokens_saved": 0,
        "error": None,
    }
    if not prompt.strip():
        return out
    if not SMART_ROUTER_AVAILABLE:
        out["error"] = "classifier unavailable"
        return out

    router = SmartRouter()
    cls = router.classify(prompt)
    split = router.split(prompt, cls)
    out["routing"] = cls.routing
    out["complexity"] = cls.complexity_score
    out["reasoning"] = cls.reasoning
    out["tokens_saved"] = int(getattr(split, "free_token_estimate", 0) or 0)

    if cls.routing == "claude" and not split.free_prompt:
        return out

    if not route or not API_ROUTER_AVAILABLE:
        if split.free_prompt and split.claude_prompt:
            out["grok_prompt"] = split.claude_prompt
        return out

    try:
        result = router.route_with_api(prompt)
    except Exception as exc:
        out["error"] = str(exc)
        return out

    out["model"] = result.model_used or None
    out["cheap_text"] = result.free_response or None
    out["cost_usd"] = float(result.cost_usd or 0)
    if result.final_claude_prompt:
        out["grok_prompt"] = result.final_claude_prompt
        out["handled"] = False
        if cls.routing == "free":
            out["routing"] = "split"
    else:
        out["handled"] = bool(result.free_response)
        out["grok_prompt"] = ""
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    route = "--no-route" not in argv
    prompt = sys.stdin.read()
    if not prompt.strip():
        for a in argv:
            if not a.startswith("-"):
                prompt = a
                break
    print(json.dumps(run_turn(prompt, route=route)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
