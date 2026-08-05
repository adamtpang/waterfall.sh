"""Tests for cache.py -- no network calls."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cache import ResponseCache, cache_key, normalize_prompt


class NormalizeAndKeyTests(unittest.TestCase):
    def test_normalize_collapses_whitespace_and_case(self) -> None:
        self.assertEqual(
            normalize_prompt("  Rename   X\nto   userCount  "),
            "rename x to usercount",
        )

    def test_cache_key_stable_for_equivalent_text(self) -> None:
        self.assertEqual(
            cache_key("Rename X to userCount"),
            cache_key("  rename   x  to   usercount  "),
        )

    def test_cache_key_differs_for_different_text(self) -> None:
        self.assertNotEqual(cache_key("rename x"), cache_key("rename y"))


class ResponseCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache_path = Path(self._tmp.name) / "cache.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _cache(self, ttl_seconds: int = 7 * 24 * 3600) -> ResponseCache:
        return ResponseCache(cache_path=self.cache_path, ttl_seconds=ttl_seconds)

    def test_miss_when_empty(self) -> None:
        cache = self._cache()
        self.assertIsNone(cache.get("anything"))

    def test_put_then_get_round_trip(self) -> None:
        cache = self._cache()
        cache.put("format this JSON", "{\"a\": 1}", "cheap/model", "openrouter", now=1000.0)

        entry = cache.get("format this JSON", now=1000.0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.response, "{\"a\": 1}")
        self.assertEqual(entry.model_used, "cheap/model")
        self.assertEqual(entry.backend_used, "openrouter")

    def test_get_is_case_and_whitespace_insensitive(self) -> None:
        cache = self._cache()
        cache.put("Format This JSON", "{}", "cheap/model", "openrouter", now=1000.0)
        entry = cache.get("  format   this   json  ", now=1000.0)
        self.assertIsNotNone(entry)

    def test_hit_count_increments_and_persists(self) -> None:
        cache = self._cache()
        cache.put("x", "y", "m", "openrouter", now=1000.0)
        cache.get("x", now=1000.0)
        cache.get("x", now=1000.0)
        entry = cache.get("x", now=1000.0)
        self.assertEqual(entry.hit_count, 3)

    def test_expired_entry_is_a_miss(self) -> None:
        cache = self._cache(ttl_seconds=100)
        cache.put("x", "y", "m", "openrouter", now=1000.0)
        self.assertIsNone(cache.get("x", now=1000.0 + 101))

    def test_entry_within_ttl_is_a_hit(self) -> None:
        cache = self._cache(ttl_seconds=100)
        cache.put("x", "y", "m", "openrouter", now=1000.0)
        self.assertIsNotNone(cache.get("x", now=1000.0 + 99))

    def test_put_overwrites_existing_entry(self) -> None:
        cache = self._cache()
        cache.put("x", "first", "m", "openrouter", now=1000.0)
        cache.put("x", "second", "m", "openrouter", now=2000.0)
        entry = cache.get("x", now=2000.0)
        self.assertEqual(entry.response, "second")

    def test_persists_across_instances(self) -> None:
        self._cache().put("x", "y", "m", "openrouter", now=1000.0)
        entry = self._cache().get("x", now=1000.0)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.response, "y")

    def test_corrupt_cache_file_treated_as_empty(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text("not json", encoding="utf-8")
        cache = self._cache()
        self.assertIsNone(cache.get("x"))

    def test_size_reports_entry_count(self) -> None:
        cache = self._cache()
        self.assertEqual(cache.size(), 0)
        cache.put("a", "1", "m", "openrouter", now=1000.0)
        cache.put("b", "2", "m", "openrouter", now=1000.0)
        self.assertEqual(cache.size(), 2)

    def test_purge_expired_removes_only_stale_entries(self) -> None:
        cache = self._cache(ttl_seconds=100)
        cache.put("old", "1", "m", "openrouter", now=1000.0)
        cache.put("fresh", "2", "m", "openrouter", now=1990.0)

        removed = cache.purge_expired(now=2000.0)

        self.assertEqual(removed, 1)
        self.assertEqual(cache.size(), 1)
        self.assertIsNotNone(cache.get("fresh", now=2000.0))


if __name__ == "__main__":
    unittest.main()
