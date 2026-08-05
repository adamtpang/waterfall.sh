"""Tests for smart_router.py's cross-session response cache short-circuit
-- no network calls. split() is monkeypatched to a fixed RoutingResult so
these don't depend on the live classifier's exact behavior for any given
sample text; only cache.py's own tests need to cover the classifier-facing
edge cases.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smart_router import SmartRouter
from cache import ResponseCache
from openrouter_api_client import GenerateResult
from classifier.types import RoutingResult


def _routing_result(free_prompt: str, claude_prompt: str = "") -> RoutingResult:
    return RoutingResult(
        original_prompt=free_prompt,
        subtasks=[],
        free_prompt=free_prompt,
        claude_prompt=claude_prompt,
        free_token_estimate=10,
        claude_token_estimate=0,
        savings_pct=1.0,
    )


class RouteWithApiCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = ResponseCache(cache_path=Path(self._tmp.name) / "cache.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _router(self) -> SmartRouter:
        return SmartRouter(cache=self.cache)

    @staticmethod
    def _fake_client(response_text: str = "renamed") -> mock.MagicMock:
        client = mock.MagicMock()
        client.generate_with_usage.return_value = GenerateResult(
            text=response_text, model="cheap/text-model",
            input_tokens=10, output_tokens=5, cost_usd=0.0001, elapsed_sec=0.2,
        )
        return client

    def test_second_identical_call_served_from_cache(self) -> None:
        router = self._router()
        fake_client = self._fake_client()

        with mock.patch.object(router, "split", return_value=_routing_result("format this JSON")):
            with mock.patch(
                "smart_router._openrouter_api_client.OpenRouterClient", return_value=fake_client
            ):
                first = router.route_with_api("format this JSON")
                second = router.route_with_api("format this JSON")

        self.assertFalse(first.cache_hit)
        self.assertTrue(second.cache_hit)
        self.assertEqual(second.free_response, first.free_response)
        self.assertEqual(second.cost_usd, 0.0)
        self.assertEqual(second.input_tokens, 0)
        self.assertEqual(second.output_tokens, 0)
        self.assertEqual(fake_client.generate_with_usage.call_count, 1)

    def test_different_routed_text_both_call_the_client(self) -> None:
        router = self._router()
        fake_client = self._fake_client()

        results = []
        with mock.patch(
            "smart_router._openrouter_api_client.OpenRouterClient", return_value=fake_client
        ):
            for free_prompt in ("format this JSON", "sort this list"):
                with mock.patch.object(router, "split", return_value=_routing_result(free_prompt)):
                    results.append(router.route_with_api(free_prompt))

        self.assertFalse(results[0].cache_hit)
        self.assertFalse(results[1].cache_hit)
        self.assertEqual(fake_client.generate_with_usage.call_count, 2)

    def test_cache_hit_still_produces_a_final_claude_prompt(self) -> None:
        router = self._router()
        fake_client = self._fake_client(response_text="42")
        routing = _routing_result("what is 6*7", claude_prompt="use {free_model_results} to answer")

        with mock.patch.object(router, "split", return_value=routing):
            with mock.patch(
                "smart_router._openrouter_api_client.OpenRouterClient", return_value=fake_client
            ):
                router.route_with_api("what is 6*7")
                second = router.route_with_api("what is 6*7")

        self.assertTrue(second.cache_hit)
        self.assertIn("42", second.final_claude_prompt)

    def test_no_cache_backend_never_short_circuits(self) -> None:
        router = SmartRouter(cache=None)
        router._cache = None  # simulate cache.py being unimportable
        fake_client = self._fake_client()

        with mock.patch.object(router, "split", return_value=_routing_result("format this JSON")):
            with mock.patch(
                "smart_router._openrouter_api_client.OpenRouterClient", return_value=fake_client
            ):
                router.route_with_api("format this JSON")
                second = router.route_with_api("format this JSON")

        self.assertFalse(second.cache_hit)
        self.assertEqual(fake_client.generate_with_usage.call_count, 2)


if __name__ == "__main__":
    unittest.main()
