"""OpenRouter API client -- real HTTP calls to openrouter.ai, no browser needed.

This fills in the module NeoAutocoder/provider_chain.py already expects at
`from openrouter_api_client import OpenRouterClient`, and gives smart_router.py
a fast, reliable path for the "free/cheap" side of routing. Previously the
only way to reach OpenRouter was CDP browser automation of its chat UI
(driving a real Chrome tab, clicking around) -- this talks to the documented
REST API directly instead.

Setup:
    1. Get a key at https://openrouter.ai/keys (pay-as-you-go; most cheap
       coding models run a fraction of a cent per call).
    2. Set the OPENROUTER_API_KEY environment variable, OR write the key as
       a single line to ~/.claude/openrouter_key.txt.

Usage:
    from openrouter_api_client import OpenRouterClient
    client = OpenRouterClient()
    text = client.generate("Write a haiku about tokens.")

    # With cost/usage accounting (used by smart_router.py for the savings ledger):
    result = client.generate_with_usage("Explain this traceback: ...")
    print(result.text, result.model, result.cost_usd)
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

API_BASE = "https://openrouter.ai/api/v1"
MODELS_URL = f"{API_BASE}/models"
CHAT_URL = f"{API_BASE}/chat/completions"

MODELS_CACHE_TTL_SEC = 6 * 3600  # 6 hours -- pricing/catalog changes slowly

# Conservative fallback if the live /models fetch fails (offline, network
# blip, etc). Prices and availability drift over time -- live selection via
# pick_cheap_model() is always preferred; this is just a last resort.
FALLBACK_MODELS = [
    "deepseek/deepseek-v4-flash",
    "qwen/qwen3.8-max",
    "meta-llama/llama-3.3-70b-instruct",
]

MIN_CONTEXT_LENGTH = 8000  # skip toy-context models when auto-selecting

DEFAULT_KEY_FILE = Path.home() / ".claude" / "openrouter_key.txt"

# Model tiers: price-sorted candidates get split into three equal bands so a
# task's complexity picks *which band* to draw the cheapest model from,
# instead of always grabbing the single cheapest model on the catalog
# regardless of how much reasoning the task needs. "small" is still far
# cheaper than Claude -- this only decides which non-Claude model handles
# the work the classifier already decided doesn't need Claude at all.
TIERS = ("small", "medium", "large")

# complexity_score upper bound -> tier. A prompt above the "large" bound
# should have been routed straight to Claude by the classifier already;
# this is just a safety fallback if it wasn't.
TIER_COMPLEXITY_BOUNDS = (
    (0.35, "small"),
    (0.65, "medium"),
    (1.01, "large"),
)


def tier_for_complexity(complexity: float) -> str:
    """Map a classifier complexity_score (0.0-1.0) to a model tier."""
    for bound, tier in TIER_COMPLEXITY_BOUNDS:
        if complexity < bound:
            return tier
    return "large"


class OpenRouterError(RuntimeError):
    """Raised on auth failures, exhausted retries, or malformed responses."""


@dataclass
class GenerateResult:
    """Full result of a generate() call, with token/cost accounting."""
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    elapsed_sec: float = 0.0


class OpenRouterClient:
    """Thin, dependency-light client for OpenRouter's chat completions API.

    The `generate(prompt, temperature=...)` method matches the interface
    NeoAutocoder/provider_chain.py's ProviderChain already expects from any
    provider client, so this drops in as the "OpenRouter_API" provider with
    no changes needed there.
    """

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.config_dir = Path(config_dir) if config_dir else (Path.home() / ".claude")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path = self.config_dir / "openrouter_models_cache.json"
        self.timeout = timeout
        self.api_key = api_key or self._load_api_key()
        self._models: Optional[list[dict]] = None

        if not self.api_key:
            raise OpenRouterError(
                "No OpenRouter API key found. Set OPENROUTER_API_KEY, or write "
                f"one line to {DEFAULT_KEY_FILE}. Get a key at "
                "https://openrouter.ai/keys"
            )

    # ── key + model discovery ──────────────────────────────────────────

    @staticmethod
    def _load_api_key() -> str:
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if key:
            return key
        if DEFAULT_KEY_FILE.is_file():
            try:
                return DEFAULT_KEY_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                pass
        return ""

    def list_models(self, force_refresh: bool = False) -> list[dict]:
        """Fetch (and cache locally for MODELS_CACHE_TTL_SEC) the live
        OpenRouter model catalog, including pricing and context length."""
        if self._models is not None and not force_refresh:
            return self._models

        if not force_refresh and self._cache_path.is_file():
            try:
                cached = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if time.time() - cached.get("fetched_at", 0) < MODELS_CACHE_TTL_SEC:
                    self._models = cached.get("models", [])
                    return self._models
            except (json.JSONDecodeError, OSError):
                pass

        import requests

        try:
            resp = requests.get(MODELS_URL, timeout=self.timeout)
            resp.raise_for_status()
            models = resp.json().get("data", [])
        except Exception as e:
            logger.warning("Failed to fetch OpenRouter model list: %s", e)
            self._models = []
            return self._models

        self._models = models
        try:
            self._cache_path.write_text(
                json.dumps({"fetched_at": time.time(), "models": models}),
                encoding="utf-8",
            )
        except OSError:
            pass
        return models

    def _priced_candidates(self, min_context: int) -> list[tuple[float, str]]:
        """Capable text-in/text-out models with a real, non-sentinel prompt
        price, cheapest first. Shared by pick_cheap_models() and the tier
        picker so the filtering (and its bugs) only live in one place.

        Excludes models with a NEGATIVE prompt price -- that's OpenRouter's
        `-1` sentinel for meta-routers like `openrouter/auto` whose actual
        price varies by whatever they route to internally. Sorting on that
        sentinel put them first in every pick regardless of real cost, which
        silently defeated both cheapest-selection and tiering until it was
        caught against the live catalog.

        A price of exactly 0 is NOT the sentinel -- it's a genuinely free
        model, and those are the cheapest capable models in the catalog by
        definition. The original guard used `<= 0`, which threw them out
        along with the sentinel: 22 real free models (checked against the
        live catalog on 2026-08-22), including `stealth/ox-alpha` at 1M
        context, were invisible to a router whose entire job is finding the
        cheapest capable model. Free models do carry tighter rate limits,
        but that is exactly what the cascade fallback already handles.
        """
        models = self.list_models()
        candidates: list[tuple[float, str]] = []
        for m in models:
            model_id = m.get("id", "")
            if not model_id or model_id.startswith("~"):
                continue  # alias/router entries -- resolve to a real id instead
            arch = m.get("architecture", {}) or {}
            if "text" not in (arch.get("output_modalities") or []):
                continue
            if "text" not in (arch.get("input_modalities") or []):
                continue
            if (m.get("context_length") or 0) < min_context:
                continue
            pricing = m.get("pricing", {}) or {}
            try:
                prompt_price = float(pricing.get("prompt", "inf"))
            except (TypeError, ValueError):
                continue
            if prompt_price < 0:
                continue
            candidates.append((prompt_price, model_id))
        candidates.sort(key=lambda c: c[0])
        return candidates

    def pick_cheap_models(
        self, n: int = 3, min_context: int = MIN_CONTEXT_LENGTH
    ) -> list[str]:
        """Return up to `n` cheapest capable text-in/text-out models on the
        live catalog, cheapest first. This is the candidate list
        generate_with_usage() cascades through -- if the cheapest model is
        down, rate-limited, or errors out, it automatically falls back to
        the next one instead of failing the whole call. Falls back to a
        small curated list if the catalog can't be fetched at all."""
        candidates = self._priced_candidates(min_context)
        if not candidates:
            return list(FALLBACK_MODELS[:n]) or [FALLBACK_MODELS[0]]
        return [model_id for _, model_id in candidates[:n]]

    def pick_cheap_model(self, min_context: int = MIN_CONTEXT_LENGTH) -> str:
        """Return the single cheapest capable model. Kept for callers that
        just want one id; prefer pick_cheap_models() for the fallback
        cascade generate_with_usage() uses internally."""
        return self.pick_cheap_models(n=1, min_context=min_context)[0]

    def _price_sorted_candidates(self, min_context: int) -> list[str]:
        """All capable model ids, cheapest first -- the full pool tiers get
        carved out of (unlike pick_cheap_models(), which truncates to n)."""
        return [model_id for _, model_id in self._priced_candidates(min_context)]

    def pick_cheap_models_by_tier(
        self, tier: str, n: int = 3, min_context: int = MIN_CONTEXT_LENGTH
    ) -> list[str]:
        """Return up to `n` cheapest-first model ids from the requested tier
        band ("small"/"medium"/"large") of the price-sorted catalog, instead
        of always the global cheapest. A small/mechanical task (tier
        "small") gets the cheapest of the cheap models; a task the
        classifier still routed away from Claude but that clearly needs more
        reasoning (tier "large") gets the cheapest model *within the more
        capable third of the catalog* -- still nowhere near Claude pricing,
        but not the bottom-of-the-barrel pick either.

        Falls back to the flat cheapest-overall list if the catalog is too
        small to split into three real bands (e.g. offline, using
        FALLBACK_MODELS).
        """
        if tier not in TIERS:
            raise ValueError(f"Unknown tier {tier!r}, expected one of {TIERS}")

        pool = self._price_sorted_candidates(min_context)
        if len(pool) < len(TIERS):
            return self.pick_cheap_models(n=n, min_context=min_context)

        band_size = max(1, len(pool) // len(TIERS))
        start = TIERS.index(tier) * band_size
        end = start + band_size if tier != TIERS[-1] else len(pool)
        band = pool[start:end] or pool  # never return an empty band

        return band[:n]

    # ── generation ────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: Optional[str] = None,
    ) -> str:
        """Simple string-in, string-out generation. Matches ProviderChain's
        `client.generate(prompt, temperature=...)` call site exactly."""
        return self.generate_with_usage(
            prompt, model=model, temperature=temperature,
            max_tokens=max_tokens, system=system,
        ).text

    def generate_with_usage(
        self,
        prompt: str,
        model: Optional[str] = None,
        tier: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        system: Optional[str] = None,
        retries: int = 1,
        fallback_models: int = 3,
    ) -> GenerateResult:
        """Full generation with token/cost accounting, for the savings ledger.

        When `model` isn't pinned, this cascades through candidate models in
        order: each candidate gets `retries + 1` attempts (retrying on
        429/5xx with backoff), and if it's still down the client moves on to
        the next candidate automatically. Only raises once every candidate
        has failed. A 401 (bad API key) always raises immediately --
        switching models can't fix a rejected key.

        `tier` ("small"/"medium"/"large", see pick_cheap_models_by_tier)
        picks which price band the candidates come from -- a small
        mechanical task shouldn't draw the same model as one that's borderline
        Claude-worthy. Ignored when `model` is pinned. Defaults to the flat
        cheapest-overall list when neither is given.
        """
        import requests

        if model:
            candidates = [model]
        elif tier:
            candidates = self.pick_cheap_models_by_tier(tier, n=max(1, fallback_models))
        else:
            candidates = self.pick_cheap_models(n=max(1, fallback_models))
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional but recommended by OpenRouter for attribution/analytics.
            "HTTP-Referer": "https://github.com/awesomo913/Claude-Token-Saver",
            "X-Title": "Claude Token Saver - Smart Router",
        }

        last_error: Optional[Exception] = None
        for candidate_model in candidates:
            payload = {
                "model": candidate_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            for attempt in range(retries + 1):
                start = time.time()
                try:
                    resp = requests.post(
                        CHAT_URL, headers=headers, json=payload, timeout=self.timeout,
                    )
                except requests.RequestException as e:
                    last_error = e
                    time.sleep(1.5 * (attempt + 1))
                    continue

                elapsed = time.time() - start

                if resp.status_code == 401:
                    raise OpenRouterError(
                        "OpenRouter rejected the API key (401). Check OPENROUTER_API_KEY."
                    )
                if resp.status_code == 429:
                    last_error = OpenRouterError(f"Rate limited (429) on {candidate_model}.")
                    time.sleep(3.0 * (attempt + 1))
                    continue
                if resp.status_code >= 500:
                    last_error = OpenRouterError(
                        f"OpenRouter server error {resp.status_code} on {candidate_model}."
                    )
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if resp.status_code >= 400:
                    # Model-specific failure (bad model id, unsupported params,
                    # etc) -- no point retrying the same model, but a
                    # different candidate might work fine.
                    last_error = OpenRouterError(
                        f"OpenRouter request failed {resp.status_code} on "
                        f"{candidate_model}: {resp.text[:300]}"
                    )
                    break

                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    last_error = OpenRouterError(
                        f"OpenRouter returned no choices from {candidate_model}: "
                        f"{json.dumps(data)[:300]}"
                    )
                    break

                text = choices[0].get("message", {}).get("content", "") or ""
                if not text.strip():
                    # Empty content is a real failure, not a successful empty
                    # answer, so cascade to the next candidate instead of
                    # reporting success with nothing in it.
                    #
                    # Caught live against stealth/ox-alpha on 2026-08-23: it is
                    # a reasoning model that emits its chain into a separate
                    # `reasoning` field FIRST and only then writes `content`.
                    # Given a modest max_tokens it spends the whole budget
                    # reasoning and returns content=None with
                    # finish_reason="stop" -- indistinguishable from success by
                    # status code alone. It matters because free models sort
                    # first, so ox-alpha is currently the top pick.
                    last_error = OpenRouterError(
                        f"{candidate_model} returned empty content "
                        f"(finish_reason={choices[0].get('finish_reason')!r}); "
                        "likely spent the whole token budget on reasoning"
                    )
                    break

                usage = data.get("usage", {}) or {}
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                cost = usage.get("cost")
                if cost is None:
                    cost = self._estimate_cost(candidate_model, input_tokens, output_tokens)

                return GenerateResult(
                    text=text,
                    model=candidate_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    elapsed_sec=round(elapsed, 2),
                )

            logger.warning(
                "Model %s exhausted (%d attempt(s)), falling back to next candidate: %s",
                candidate_model, retries + 1, last_error,
            )

        raise OpenRouterError(
            f"All {len(candidates)} candidate model(s) failed: {candidates}. "
            f"Last error: {last_error}"
        )

    def _estimate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate $ cost from cached pricing when the API response omits
        `usage.cost` (some providers don't return it)."""
        for m in self._models or []:
            if m.get("id") == model_id:
                pricing = m.get("pricing", {}) or {}
                try:
                    p = float(pricing.get("prompt", 0))
                    c = float(pricing.get("completion", 0))
                    return round(p * input_tokens + c * output_tokens, 6)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0
