"""Coverage rows for the leaderboard: borrowed scores for models we have not measured.

The board's `rows` are the product: dollars per solved task, measured in the
waterfall harness or seeded from dated public priors, for about ten models.
That is deliberately small and it should stay that way.

This module answers the other question a reader has: "what about the other
two hundred models?" OpenRouter's /models catalog carries, per model, list
pricing, an Artificial Analysis score block (`intelligence_index`,
`coding_index`, `agentic_index`), Design Arena per-category Elo, and the
thinking-effort levels the model accepts. None of that is a waterfall
measurement, so coverage rows:

- live under a separate `coverage` key, never inside `rows`
- carry `quality_borrowed` and `quality_source`, never `quality`
- have NO `cost_per_solved` and NO `value`, because the public formula is
  value = quality / cost_per_solved and cost_per_solved is unmeasured here.
  Inventing a value for them would put borrowed numbers next to measured ones
  as if they were the same thing, which is exactly what the board's
  methodology page promises not to do.
- exclude every model that already has a measured row, by provider id

Borrowed quality prefers AA `coding_index` (this is a coding board), then AA
`intelligence_index`, then mean Design Arena Elo rescaled to 0-100 across the
catalog so it can share a column. `quality_source` says which, per row.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTING_PATH = ROOT / "config" / "routing.yaml"
DEFAULT_CATALOG_CACHE = Path.home() / ".claude" / "openrouter_models_cache.json"

MIN_CONTEXT = 8000
INPUT_WEIGHT, OUTPUT_WEIGHT = 3.0, 1.0   # same blend convention AA and OpenRouter use


def _f(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_id(model_id: str) -> str:
    """`anthropic/claude-fable-5-1` and `anthropic/claude-fable-5.1` are the same
    model written two ways (routing.yaml uses the first, the catalog the second).
    Compare on letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", str(model_id).lower())


def price_per_1m(per_token: Any) -> Optional[float]:
    p = _f(per_token)
    if p is None or p < 0:          # -1 is OpenRouter's "varies" sentinel
        return None
    return round(p * 1_000_000, 4)


def borrowed_quality(benchmarks: Any, elo_lo: float, elo_span: float) -> tuple[Optional[float], Optional[str]]:
    """Return (score on 0-100, source label) or (None, None)."""
    if not isinstance(benchmarks, Mapping):
        return None, None
    aa = benchmarks.get("artificial_analysis")
    if isinstance(aa, Mapping):
        for key in ("coding_index", "intelligence_index"):
            v = _f(aa.get(key))
            if v is not None:
                return round(v, 1), f"aa:{key}"
    da = benchmarks.get("design_arena")
    if isinstance(da, list):
        elos = [e for e in (_f(i.get("elo")) for i in da if isinstance(i, Mapping)) if e is not None]
        if elos:
            mean = statistics.fmean(elos)
            return round((mean - elo_lo) / elo_span * 100, 1), "design_arena:elo_rescaled"
    return None, None


def _elo_bounds(models: Iterable[Mapping[str, Any]]) -> tuple[float, float]:
    pool: list[float] = []
    for m in models:
        da = (m.get("benchmarks") or {}).get("design_arena") if isinstance(m.get("benchmarks"), Mapping) else None
        if isinstance(da, list):
            for item in da:
                e = _f(item.get("elo")) if isinstance(item, Mapping) else None
                if e is not None:
                    pool.append(e)
    if not pool:
        return 0.0, 1.0
    lo, hi = min(pool), max(pool)
    return lo, (hi - lo) or 1.0


def measured_provider_ids(
    board_rows: Iterable[Mapping[str, Any]],
    routing_path: Path = DEFAULT_ROUTING_PATH,
) -> set[str]:
    """Normalized provider ids for every model that has a measured/seeded row,
    bridged through config/routing.yaml's display_name -> provider_id."""
    names = {str(r.get("model")) for r in board_rows}
    ids: set[str] = set()
    try:
        import yaml  # already a router dependency (routing.yaml)
        data = yaml.safe_load(Path(routing_path).read_text(encoding="utf-8")) or {}
        for entry in (data.get("models") or {}).values():
            if not isinstance(entry, Mapping):
                continue
            if str(entry.get("display_name")) in names and entry.get("provider_id"):
                ids.add(normalize_id(entry["provider_id"]))
    except Exception as exc:  # noqa: BLE001 -- coverage is best-effort, never fatal
        logger.warning("could not read %s for measured ids: %s", routing_path, exc)
    return ids


def coverage_rows(
    catalog_models: Iterable[Mapping[str, Any]],
    exclude_ids: Iterable[str] = (),
) -> list[dict[str, Any]]:
    models = list(catalog_models)
    excluded = {normalize_id(i) for i in exclude_ids}
    elo_lo, elo_span = _elo_bounds(models)

    rows: list[dict[str, Any]] = []
    for m in models:
        mid = str(m.get("id") or "")
        if not mid:
            continue
        # `anthropic/claude-opus-5:batch` and `minimax/minimax-m3:free` are
        # pricing variants of models the board already measured, not other
        # models. Compare on the base id (before any ":variant" suffix) so the
        # top of "unmeasured" is not a list of :batch twins of the measured ten.
        if normalize_id(mid) in excluded or normalize_id(mid.split(":", 1)[0]) in excluded:
            continue
        if (m.get("context_length") or 0) < MIN_CONTEXT:
            continue
        # OpenRouter writes modality as "input->output", e.g. "text+image->text"
        # or "text+image->text+image". A coding board wants models whose OUTPUT
        # is text only. Two real leaks caught here: "text->image" passed a
        # whole-string check because it contains "text", and image generators
        # that also emit text ("->text+image") passed an output-contains-text
        # check. So: output side must contain text and no image/video/audio.
        modality = str(((m.get("architecture") or {}).get("modality")) or "")
        if modality:
            _, arrow, out = modality.partition("->")
            out = out if arrow else modality
            if "text" not in out or any(k in out for k in ("image", "video", "audio")):
                continue
        pricing = m.get("pricing") or {}
        price_in = price_per_1m(pricing.get("prompt"))
        price_out = price_per_1m(pricing.get("completion"))
        if price_in is None or price_out is None:
            continue
        quality, source = borrowed_quality(m.get("benchmarks"), elo_lo, elo_span)
        if quality is None:
            continue
        reasoning = m.get("reasoning") or {}
        efforts = list(reasoning.get("supported_efforts") or [])
        rows.append({
            "model": mid,
            "display": str(m.get("name") or mid),
            "quality_borrowed": quality,
            "quality_source": source,
            "price_in": price_in,
            "price_out": price_out,
            "price_blended": round((INPUT_WEIGHT * price_in + OUTPUT_WEIGHT * price_out) / (INPUT_WEIGHT + OUTPUT_WEIGHT), 4),
            "free": price_in == 0 and price_out == 0,
            "context": m.get("context_length"),
            "efforts": efforts,
            "source": "catalog",
            "measured": False,
        })

    rows = collapse_variants(rows)
    rows.sort(key=lambda r: (-r["quality_borrowed"], r["price_blended"], r["model"]))
    return rows


# Variant suffixes that are the same weights at a different price and belong
# folded into the base model's row. ":free" is deliberately NOT here: a free
# tier is a materially different offer (rate limits, data policy) and it is
# the thing this board exists to surface, so it keeps its own row.
COLLAPSE_SUFFIXES = frozenset({"batch"})


def collapse_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold `model:batch` into the `model` row as a `variants` entry.

    The suffix-free row is canonical: its price stays the headline and its
    borrowed quality is the row's quality (same weights, so they agree). A
    :batch row with no base row in the set stays as its own row, suffix and
    all, since there is nothing to fold it into. Every row gets a `variants`
    list, empty when there is nothing to say."""
    by_id = {r["model"]: r for r in rows}
    folded: set[str] = set()
    for r in rows:
        base, sep, suffix = r["model"].partition(":")
        if not sep or suffix not in COLLAPSE_SUFFIXES or base not in by_id:
            continue
        by_id[base].setdefault("variants", []).append({
            "suffix": suffix,
            "model": r["model"],
            "price_in": r["price_in"],
            "price_out": r["price_out"],
            "price_blended": r["price_blended"],
            "free": r["free"],
        })
        folded.add(r["model"])
    out = []
    for r in rows:
        if r["model"] in folded:
            continue
        r.setdefault("variants", [])
        r["variants"].sort(key=lambda v: v["price_blended"])
        out.append(r)
    return out


def load_catalog_models(cache_path: Path = DEFAULT_CATALOG_CACHE) -> list[dict[str, Any]]:
    """Live catalog via the OpenRouter client when a key is present, else the
    on-disk cache, else nothing. Never raises: coverage is optional and the
    publish step must not fail because a laptop has no key."""
    try:
        from openrouter_api_client import OpenRouterClient
        return list(OpenRouterClient().list_models())
    except Exception as exc:  # noqa: BLE001
        logger.info("no live catalog (%s); trying cache %s", exc, cache_path)
    try:
        data = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        return list(data.get("models") or [])
    except Exception as exc:  # noqa: BLE001
        logger.warning("no catalog cache either: %s", exc)
        return []


def build_coverage(
    board_rows: Iterable[Mapping[str, Any]],
    catalog_models: Optional[Iterable[Mapping[str, Any]]] = None,
    routing_path: Path = DEFAULT_ROUTING_PATH,
) -> dict[str, Any]:
    board_rows = list(board_rows)
    models = list(catalog_models) if catalog_models is not None else []
    rows = coverage_rows(models, measured_provider_ids(board_rows, routing_path)) if models else []
    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r["quality_source"]] = by_source.get(r["quality_source"], 0) + 1
    return {
        "note": (
            "Borrowed scores for models the harness has not measured. quality_borrowed "
            "is Artificial Analysis coding_index where available, else intelligence_index, "
            "else Design Arena Elo rescaled to 0-100; quality_source says which. "
            "No cost_per_solved and no value: those exist only for measured rows above. "
            "Prices are OpenRouter list prices per 1M tokens."
        ),
        "catalog_models_seen": len(models),
        "count": len(rows),
        "variants_folded": sum(len(r.get("variants") or []) for r in rows),
        "by_source": by_source,
        "rows": rows,
    }
