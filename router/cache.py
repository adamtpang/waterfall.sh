"""Cross-session response cache -- the "have I already answered this"
countermeasure from TOKEN_COMPOUNDING.md (#9). Keyed by a normalized hash
of the exact text routed to the free model, persisted to disk so a hit
survives across sessions, not just within one: an identical mechanical
sub-task (same normalized routed text) sent twice -- maybe in two
different sessions days apart -- gets served from cache instead of a
second real OpenRouter call.

Scope, deliberately narrow: this only short-circuits `SmartRouter.
route_with_api()`'s free-model call for an *exact* (whitespace/case
normalized) repeat of the routed sub-task text. It is NOT a semantic
cache -- two differently-worded asks for the same thing are two
different cache keys and both cost a real call. It does NOT address the
general reused-input compounding problem documented elsewhere in
TOKEN_COMPOUNDING.md: a long thread's accumulated conversation history
still gets resent every turn regardless of this cache. It only prevents
redoing *identical* routed work across calls/sessions, a narrower,
complementary saving.

Entries expire after `ttl_seconds` (default 7 days) -- long enough to
catch real repeats, short enough that a stale answer against code that's
since changed doesn't get served forever. An expired entry is a cache
miss, not silently reused.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_CACHE_PATH = Path.home() / ".claude" / "waterfall_response_cache.json"
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def normalize_prompt(prompt: str) -> str:
    """Collapse whitespace and case so trivially different formatting of
    the same routed text still hits the same cache key."""
    return re.sub(r"\s+", " ", prompt.strip().lower())


def cache_key(prompt: str) -> str:
    return hashlib.sha256(normalize_prompt(prompt).encode("utf-8")).hexdigest()


@dataclass
class CacheEntry:
    prompt_hash: str
    response: str
    model_used: str
    backend_used: str
    created_at: float
    hit_count: int = 0


class ResponseCache:
    """Disk-backed exact-match cache, one JSON file, keyed by prompt hash."""

    def __init__(self, cache_path: Path | None = None, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self.ttl_seconds = ttl_seconds

    def _load(self) -> dict:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, prompt: str, now: float | None = None) -> CacheEntry | None:
        """Return the cached entry for `prompt`, or None on a miss/expiry.
        A hit increments and persists the entry's hit_count."""
        now = time.time() if now is None else now
        key = cache_key(prompt)
        data = self._load()
        raw = data.get(key)
        if raw is None:
            return None

        entry = CacheEntry(**raw)
        if now - entry.created_at > self.ttl_seconds:
            return None  # stale -- treat as a miss rather than serving outdated content

        entry.hit_count += 1
        data[key] = asdict(entry)
        self._save(data)
        return entry

    def put(
        self, prompt: str, response: str, model_used: str, backend_used: str,
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        key = cache_key(prompt)
        data = self._load()
        data[key] = asdict(CacheEntry(
            prompt_hash=key,
            response=response,
            model_used=model_used,
            backend_used=backend_used,
            created_at=now,
        ))
        self._save(data)

    def size(self) -> int:
        return len(self._load())

    def purge_expired(self, now: float | None = None) -> int:
        """Drop expired entries from disk; return how many were removed."""
        now = time.time() if now is None else now
        data = self._load()
        fresh = {
            k: v for k, v in data.items()
            if now - v.get("created_at", 0) <= self.ttl_seconds
        }
        removed = len(data) - len(fresh)
        if removed:
            self._save(fresh)
        return removed
