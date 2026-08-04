"""Smart Router — classifies prompts and chains free models into Claude.

Uses the bundled classifier (pure stdlib, no deps) and orchestrates
the split: easy parts → Gemini/free via CDP, hard parts → Claude via CDP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

SMART_ROUTER_AVAILABLE = False
_import_error = ""

try:
    # Works when smart_router is imported as part of a package (e.g.
    # `from mypkg import smart_router`).
    from .classifier import PromptClassifier, TaskSplitter, TaskClassification, RoutingResult
    SMART_ROUTER_AVAILABLE = True
except ImportError:
    try:
        # Works when smart_router.py is imported bare, e.g.
        # `from smart_router import SmartRouter` with the repo root on
        # sys.path -- the pattern used everywhere else in this repo
        # (openrouter_api_client, ai_profiles, universal_client, ...).
        # `.classifier` above requires a parent package context that
        # doesn't exist in that case, so fall back to an absolute import.
        from classifier import PromptClassifier, TaskSplitter, TaskClassification, RoutingResult
        SMART_ROUTER_AVAILABLE = True
    except ImportError as e:
        _import_error = str(e)
        logger.warning("Smart Router unavailable: %s", e)

# API-mode routing: talks to OpenRouter's real HTTP API directly (fast,
# reliable) instead of driving a browser tab via CDP. Requires
# OPENROUTER_API_KEY -- see openrouter_api_client.py. Falls back to the
# CDP browser-automation path below when unavailable/unconfigured.
API_ROUTER_AVAILABLE = False
_api_import_error = ""
try:
    import openrouter_api_client as _openrouter_api_client
    API_ROUTER_AVAILABLE = True
except ImportError as e:
    _api_import_error = str(e)
    logger.warning("OpenRouter API router unavailable: %s", e)

# AI profiles considered "free" (no API cost / browser-based free tier)
FREE_PROFILES = {"Gemini", "OpenRouter", "ChatGPT", "Copilot",
                 "Ollama Web UI", "Ollama (Terminal)", "LM Studio"}
CLAUDE_PROFILES = {"Claude"}


@dataclass
class ApiRoutingResult:
    """Result of routing a prompt entirely over the OpenRouter API (no browser).

    `final_claude_prompt` is empty when the whole task was cheap/routine
    enough that the free model handled all of it -- nothing is left to hand
    to Claude in that case.
    """
    classification: "TaskClassification"
    split: "RoutingResult"
    free_response: str
    model_used: str
    model_tier: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    elapsed_sec: float
    final_claude_prompt: str


class SmartRouter:
    """Classify prompts and route between free + Claude sessions."""

    def __init__(self) -> None:
        if not SMART_ROUTER_AVAILABLE:
            raise RuntimeError(f"classifier not importable: {_import_error}")
        self._classifier = PromptClassifier()
        self._splitter = TaskSplitter(self._classifier)

    def classify(self, prompt: str) -> "TaskClassification":
        """Score the prompt and decide routing."""
        return self._classifier.classify(prompt)

    def split(self, prompt: str, cls: "TaskClassification") -> "RoutingResult":
        """Break prompt into free_prompt + claude_prompt."""
        return self._splitter.split(prompt, cls)

    @staticmethod
    def find_free_session(sessions: list) -> Optional[Any]:
        """Pick the first session running a free AI profile."""
        for s in sessions:
            if s.ai_profile.name in FREE_PROFILES and s.is_configured:
                return s
        return None

    @staticmethod
    def find_claude_session(sessions: list) -> Optional[Any]:
        """Pick the first session running Claude."""
        for s in sessions:
            if s.ai_profile.name in CLAUDE_PROFILES and s.is_configured:
                return s
        return None

    @staticmethod
    def inject_free_results(claude_prompt: str, free_response: str) -> str:
        """Replace the {free_model_results} placeholder with actual output."""
        if "{free_model_results}" in claude_prompt:
            return claude_prompt.replace("{free_model_results}", free_response)
        return (
            "The following work was already completed by a free model:\n\n"
            f"--- FREE MODEL OUTPUT ---\n{free_response}\n"
            "--- END FREE MODEL OUTPUT ---\n\n"
            "Now handle the remaining work:\n\n" + claude_prompt
        )

    # ── API-mode routing (direct HTTP, no browser) ──────────────────────

    def route_with_api(
        self,
        prompt: str,
        system: Optional[str] = None,
        model: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> ApiRoutingResult:
        """End-to-end: classify -> split -> send the easy/routine part
        straight to the OpenRouter API -> return everything needed to
        finish the job in Claude and log real savings.

        This is the preferred path whenever OPENROUTER_API_KEY is
        configured: it's faster and far more reliable than driving a
        browser tab through OpenRouter's chat UI via CDP. Callers should
        catch RuntimeError and fall back to find_free_session() +
        inject_free_results() (the CDP path) when this raises.

        Model selection: if `model` is pinned, use it as-is. Otherwise pick
        a tier from `tier`, or -- the default -- derive it from the
        classifier's own complexity_score via tier_for_complexity(). A
        one-line rename gets the cheapest small-tier model; a "split" task
        that's borderline-Claude-worthy gets pulled from the large tier
        instead of whatever happens to be globally cheapest that hour.
        """
        if not SMART_ROUTER_AVAILABLE:
            raise RuntimeError(f"classifier not importable: {_import_error}")
        if not API_ROUTER_AVAILABLE:
            raise RuntimeError(f"openrouter_api_client not importable: {_api_import_error}")

        cls = self.classify(prompt)
        split = self.split(prompt, cls)

        client = _openrouter_api_client.OpenRouterClient()

        resolved_tier = tier or _openrouter_api_client.tier_for_complexity(cls.complexity_score)

        free_response = ""
        gen = None
        if split.free_prompt:
            gen = client.generate_with_usage(
                split.free_prompt,
                model=model,
                tier=None if model else resolved_tier,
                system=system or (
                    "You are handling the routine/easy part of a coding task. "
                    "Be direct and concise -- your output will be handed to "
                    "another model to finish the harder remaining work."
                ),
            )
            free_response = gen.text

        if split.claude_prompt:
            final_claude_prompt = (
                self.inject_free_results(split.claude_prompt, free_response)
                if free_response else split.claude_prompt
            )
        else:
            # Fully handled by the free model -- nothing left for Claude.
            final_claude_prompt = ""

        return ApiRoutingResult(
            classification=cls,
            split=split,
            free_response=free_response,
            model_used=gen.model if gen else "",
            model_tier=resolved_tier if gen else "",
            cost_usd=gen.cost_usd if gen else 0.0,
            input_tokens=gen.input_tokens if gen else 0,
            output_tokens=gen.output_tokens if gen else 0,
            elapsed_sec=gen.elapsed_sec if gen else 0.0,
            final_claude_prompt=final_claude_prompt,
        )
