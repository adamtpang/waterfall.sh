"""Tests for openrouter_api_client.py -- no network calls.

Run with: python -m pytest tests/test_openrouter_api_client.py
      or: python -m unittest tests.test_openrouter_api_client
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openrouter_api_client import (
    OpenRouterClient, OpenRouterError, FALLBACK_MODELS, tier_for_complexity,
)


SAMPLE_MODELS = [
    {
        "id": "cheap/text-model",
        "context_length": 32000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0.0000001", "completion": "0.0000002"},
    },
    {
        "id": "pricey/text-model",
        "context_length": 32000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0.00005", "completion": "0.0001"},
    },
    {
        "id": "tiny-context/model",
        "context_length": 1000,  # below MIN_CONTEXT_LENGTH -- should be skipped
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0.00000001", "completion": "0.00000001"},
    },
    {
        "id": "~alias/router-entry",  # alias entries should be skipped
        "context_length": 100000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": "0.00000001", "completion": "0.00000001"},
    },
    {
        "id": "image-only/model",  # missing text output -- should be skipped
        "context_length": 100000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["image"]},
        "pricing": {"prompt": "0.00000001", "completion": "0.00000001"},
    },
]

# Nine capable models, evenly priced $0.01 .. $0.09 -- enough to split into
# three clean tier bands of three for the tiering tests.
TIERED_MODELS = [
    {
        "id": f"tier-model/{i}",
        "context_length": 32000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "pricing": {"prompt": str(i * 0.01), "completion": str(i * 0.02)},
    }
    for i in range(1, 10)
]


class OpenRouterClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _client(self) -> OpenRouterClient:
        return OpenRouterClient(config_dir=self.config_dir, api_key="test-key-123")

    def test_missing_api_key_raises(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(OpenRouterClient, "_load_api_key", return_value=""):
                with self.assertRaises(OpenRouterError):
                    OpenRouterClient(config_dir=self.config_dir)

    def test_api_key_from_env(self) -> None:
        with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "env-key"}):
            client = OpenRouterClient(config_dir=self.config_dir)
            self.assertEqual(client.api_key, "env-key")

    def test_pick_cheap_model_selects_cheapest_capable(self) -> None:
        client = self._client()
        client._models = SAMPLE_MODELS
        chosen = client.pick_cheap_model()
        self.assertEqual(chosen, "cheap/text-model")

    def test_pick_cheap_model_falls_back_when_no_candidates(self) -> None:
        client = self._client()
        client._models = []
        self.assertEqual(client.pick_cheap_model(), FALLBACK_MODELS[0])

    def test_estimate_cost_uses_cached_pricing(self) -> None:
        client = self._client()
        client._models = SAMPLE_MODELS
        cost = client._estimate_cost("cheap/text-model", input_tokens=1000, output_tokens=500)
        expected = round(0.0000001 * 1000 + 0.0000002 * 500, 6)
        self.assertEqual(cost, expected)

    def test_estimate_cost_unknown_model_is_zero(self) -> None:
        client = self._client()
        client._models = SAMPLE_MODELS
        self.assertEqual(client._estimate_cost("nonexistent/model", 100, 100), 0.0)

    def test_models_cache_round_trip(self) -> None:
        client = self._client()
        client._models = SAMPLE_MODELS
        import json
        import time

        client._cache_path.write_text(
            json.dumps({"fetched_at": time.time(), "models": SAMPLE_MODELS}),
            encoding="utf-8",
        )
        fresh = self._client()
        models = fresh.list_models()
        self.assertEqual(len(models), len(SAMPLE_MODELS))

    def test_pick_cheap_models_returns_top_n_cheapest_first(self) -> None:
        client = self._client()
        client._models = SAMPLE_MODELS
        chosen = client.pick_cheap_models(n=2)
        self.assertEqual(chosen, ["cheap/text-model", "pricey/text-model"])

    def test_pick_cheap_models_falls_back_when_no_candidates(self) -> None:
        client = self._client()
        client._models = []
        self.assertEqual(client.pick_cheap_models(n=2), list(FALLBACK_MODELS[:2]))

    def test_pick_cheap_model_skips_negative_sentinel_pricing(self) -> None:
        # Regression: openrouter/auto* reports pricing "-1" (a "varies by
        # what it routes to internally" sentinel, not an actual price).
        # float("-1") parses fine, so it used to sort as cheapest-of-all
        # and win every pick regardless of real cost.
        meta_router = {
            "id": "openrouter/auto",
            "context_length": 2000000,
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "-1", "completion": "-1"},
        }
        client = self._client()
        client._models = [meta_router] + SAMPLE_MODELS
        self.assertEqual(client.pick_cheap_model(), "cheap/text-model")
        self.assertNotIn("openrouter/auto", client.pick_cheap_models(n=10))

    def test_pick_cheap_model_keeps_genuinely_free_models(self) -> None:
        # Regression, the inverse of the sentinel bug above: the guard that
        # rejects the "-1" sentinel was written as `<= 0`, so it also threw
        # out models priced at exactly 0 -- genuinely free, and by definition
        # the cheapest capable models in the catalog. 22 real ones were being
        # dropped against the live catalog (checked 2026-08-22), including
        # stealth/ox-alpha at 1M context.
        free_model = {
            "id": "stealth/ox-alpha",
            "context_length": 1048576,
            "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0", "completion": "0"},
        }
        client = self._client()
        client._models = [free_model] + SAMPLE_MODELS
        # free beats every paid model, and the sentinel is still excluded
        self.assertEqual(client.pick_cheap_model(), "stealth/ox-alpha")
        self.assertIn("stealth/ox-alpha", client.pick_cheap_models(n=10))

    def test_pick_cheap_models_by_tier_splits_into_price_bands(self) -> None:
        client = self._client()
        client._models = TIERED_MODELS
        small = client.pick_cheap_models_by_tier("small", n=3)
        medium = client.pick_cheap_models_by_tier("medium", n=3)
        large = client.pick_cheap_models_by_tier("large", n=3)

        self.assertEqual(small, ["tier-model/1", "tier-model/2", "tier-model/3"])
        self.assertEqual(medium, ["tier-model/4", "tier-model/5", "tier-model/6"])
        self.assertEqual(large, ["tier-model/7", "tier-model/8", "tier-model/9"])

    def test_pick_cheap_models_by_tier_falls_back_when_catalog_too_small(self) -> None:
        client = self._client()
        client._models = SAMPLE_MODELS  # only 2 real candidates after filtering
        result = client.pick_cheap_models_by_tier("large", n=2)
        self.assertEqual(result, client.pick_cheap_models(n=2))

    def test_pick_cheap_models_by_tier_rejects_unknown_tier(self) -> None:
        client = self._client()
        client._models = TIERED_MODELS
        with self.assertRaises(ValueError):
            client.pick_cheap_models_by_tier("gigantic")

    def test_tier_for_complexity_boundaries(self) -> None:
        self.assertEqual(tier_for_complexity(0.0), "small")
        self.assertEqual(tier_for_complexity(0.34), "small")
        self.assertEqual(tier_for_complexity(0.35), "medium")
        self.assertEqual(tier_for_complexity(0.64), "medium")
        self.assertEqual(tier_for_complexity(0.65), "large")
        self.assertEqual(tier_for_complexity(1.0), "large")


def _fake_response(status_code: int, json_body: dict | None = None, text: str = "") -> mock.Mock:
    resp = mock.Mock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_body or {}
    return resp


class GenerateWithUsageFallbackTests(unittest.TestCase):
    """generate_with_usage() should cascade through candidate models on
    failure -- the "auto falls back to the next best model" behavior."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.config_dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _client(self) -> OpenRouterClient:
        client = OpenRouterClient(config_dir=self.config_dir, api_key="test-key-123")
        client._models = SAMPLE_MODELS
        return client

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_falls_back_to_next_model_after_server_error(self, mock_post, _sleep) -> None:
        client = self._client()
        ok_body = {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001},
        }
        # First candidate (cheap/text-model) errors on every attempt (retries=0 -> 1 try),
        # second candidate (pricey/text-model) succeeds.
        mock_post.side_effect = [
            _fake_response(500, text="server on fire"),
            _fake_response(200, ok_body),
        ]

        result = client.generate_with_usage("hello", retries=0, fallback_models=2)

        self.assertEqual(result.model, "pricey/text-model")
        self.assertEqual(result.text, "hi")
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_records_queue_and_attempts_on_first_pick(self, mock_post, _sleep) -> None:
        # The cascade always ranked its candidates; it used to throw that away
        # and report only the winner. The queue must survive even when the
        # first model answers and nothing else is contacted.
        client = self._client()
        mock_post.side_effect = [
            _fake_response(200, {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001},
            }),
        ]

        result = client.generate_with_usage("hello", retries=0, fallback_models=2)

        self.assertEqual(result.queue, ["cheap/text-model", "pricey/text-model"])
        self.assertEqual(len(result.attempts), 1)
        self.assertEqual(result.attempts[0]["model"], "cheap/text-model")
        self.assertEqual(result.attempts[0]["status"], "ok")
        # the second candidate was ranked but never contacted
        self.assertEqual(mock_post.call_count, 1)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_attempts_record_the_failure_that_caused_a_fallback(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.side_effect = [
            _fake_response(500, text="server on fire"),
            _fake_response(200, {
                "choices": [{"message": {"content": "hi"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001},
            }),
        ]

        result = client.generate_with_usage("hello", retries=0, fallback_models=2)

        self.assertEqual([a["status"] for a in result.attempts], ["failed", "ok"])
        self.assertEqual(result.attempts[0]["model"], "cheap/text-model")
        self.assertTrue(result.attempts[0]["reason"], "a failed attempt must say why")
        self.assertEqual(result.attempts[1]["model"], "pricey/text-model")
        self.assertEqual(result.model, "pricey/text-model")

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_falls_back_when_a_model_returns_empty_content(self, mock_post, _sleep) -> None:
        # Regression: a reasoning model can answer HTTP 200 with
        # finish_reason="stop" and content=None, having spent its whole token
        # budget on a separate `reasoning` field. Caught live against
        # stealth/ox-alpha (2026-08-23), which matters because free models sort
        # first and it is currently the top pick. That used to be reported as a
        # successful route with an empty answer; it must cascade instead.
        client = self._client()
        mock_post.side_effect = [
            _fake_response(
                200,
                {
                    "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 900, "cost": 0},
                },
            ),
            _fake_response(
                200,
                {
                    "choices": [{"message": {"content": "real answer"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001},
                },
            ),
        ]

        result = client.generate_with_usage("hello", retries=0, fallback_models=2)

        self.assertEqual(result.model, "pricey/text-model")
        self.assertEqual(result.text, "real answer")
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_whitespace_only_content_also_falls_back(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.side_effect = [
            _fake_response(
                200,
                {
                    "choices": [{"message": {"content": "   \n  "}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "cost": 0},
                },
            ),
            _fake_response(
                200,
                {
                    "choices": [{"message": {"content": "real answer"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001},
                },
            ),
        ]

        result = client.generate_with_usage("hello", retries=0, fallback_models=2)

        self.assertEqual(result.text, "real answer")
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_raises_after_all_candidates_exhausted(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.return_value = _fake_response(500, text="down")

        with self.assertRaises(OpenRouterError):
            client.generate_with_usage("hello", retries=0, fallback_models=2)
        self.assertEqual(mock_post.call_count, 2)  # one try per candidate model

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_401_raises_immediately_without_cascading(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.return_value = _fake_response(401, text="bad key")

        with self.assertRaises(OpenRouterError):
            client.generate_with_usage("hello", retries=1, fallback_models=2)
        self.assertEqual(mock_post.call_count, 1)  # no retry, no fallback to next model

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_tier_selects_candidates_from_that_price_band(self, mock_post, _sleep) -> None:
        client = self._client()
        client._models = TIERED_MODELS
        ok_body = {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.0001},
        }
        mock_post.return_value = _fake_response(200, ok_body)

        result = client.generate_with_usage("hello", tier="large", retries=0, fallback_models=3)

        self.assertEqual(result.model, "tier-model/7")  # cheapest of the "large" band

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_pinned_model_never_cascades(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.return_value = _fake_response(500, text="down")

        with self.assertRaises(OpenRouterError):
            client.generate_with_usage("hello", model="cheap/text-model", retries=1)
        # retries=1 -> 2 attempts on the single pinned model, no other candidates tried
        self.assertEqual(mock_post.call_count, 2)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_fable_uses_output_effort_without_disabling_thinking(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.return_value = _fake_response(200, {
            "choices": [{"message": {"content": "done"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.01},
        })

        client.generate_with_usage(
            "hello", model="anthropic/claude-fable-5-1", output_effort="xhigh", retries=0
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual({"effort": "xhigh"}, payload["output_config"])
        self.assertNotIn("thinking", payload)
        self.assertNotIn("reasoning", payload)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_non_fable_effort_uses_reasoning_control(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.return_value = _fake_response(200, {
            "choices": [{"message": {"content": "done"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.01},
        })

        client.generate_with_usage(
            "hello", model="x-ai/grok-4.6", output_effort="medium", retries=0
        )

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual({"effort": "medium"}, payload["reasoning"])
        self.assertNotIn("output_config", payload)

    @mock.patch("time.sleep", return_value=None)
    @mock.patch("requests.post")
    def test_cache_read_tokens_survive_usage_accounting(self, mock_post, _sleep) -> None:
        client = self._client()
        mock_post.return_value = _fake_response(200, {
            "choices": [{"message": {"content": "done"}}],
            "usage": {
                "prompt_tokens": 50,
                "completion_tokens": 2,
                "cost": 0.01,
                "prompt_tokens_details": {"cached_tokens": 40},
            },
        })

        result = client.generate_with_usage("hello", model="cheap/text-model", retries=0)

        self.assertEqual(40, result.cache_read_tokens)


if __name__ == "__main__":
    unittest.main()
