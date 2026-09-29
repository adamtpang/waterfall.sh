"""Tests for jev.py and its wiring into SmartRouter.route_with_api. No network:
urlopen and the OpenRouter client are mocked throughout."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jev
from cache import ResponseCache
from classifier.types import TaskClassification
from openrouter_api_client import GenerateResult
from smart_router import SmartRouter
import openrouter_api_client as _roc


def _cls(routing="free", confidence=0.3, est=1.0):
    return TaskClassification(complexity_score=0.3, task_types=[], domains=[],
                              routing=routing, confidence=confidence, reasoning="local",
                              estimated_free_pct=est)


def _fake_urlopen(choice="claude", probs=None, ctx=0.1, cost=0.00002):
    probs = probs or {choice: 0.9}
    body = json.dumps({"answers": {
        "route": {"type": "choice", "choice": choice, "probabilities": probs},
        "needs_context": {"type": "noul", "noul": ctx}},
        "usage": {"cost": cost}}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        urlopen.last = (req, timeout)
        return _Resp(body)
    return urlopen


class AskTests(unittest.TestCase):
    def test_parses_verdict_and_sends_model(self):
        op = _fake_urlopen("split", {"free": 0.02, "split": 0.97, "claude": 0.01}, ctx=0.9)
        v = jev.ask("do x then y", key="k", urlopen=op)
        self.assertEqual(v.routing, "split")
        self.assertAlmostEqual(v.confidence, 0.97)
        self.assertAlmostEqual(v.needs_context, 0.9)
        req, timeout = op.last
        self.assertEqual(json.loads(req.data)["model"], "~typesafe/jev-latest")
        self.assertEqual(req.get_header("Authorization"), "Bearer k")
        self.assertEqual(timeout, 3.0)

    def test_any_failure_returns_none(self):
        def boom(req, timeout=None):
            raise TimeoutError("slow")
        self.assertIsNone(jev.ask("x", key="k", urlopen=boom))

    def test_no_key_returns_none_without_calling(self):
        called = []
        with mock.patch.object(jev, "_load_key", return_value=""):
            self.assertIsNone(jev.ask("x", urlopen=lambda *a, **k: called.append(1)))
        self.assertEqual(called, [])

    def test_unknown_choice_returns_none(self):
        self.assertIsNone(jev.ask("x", key="k", urlopen=_fake_urlopen("maybe")))


class RefineTests(unittest.TestCase):
    def test_confident_jev_overrides_local(self):
        out = jev.refine(_cls("free"), jev.JevVerdict("claude", 0.8, 0.9))
        self.assertEqual(out.routing, "claude")
        self.assertEqual(out.estimated_free_pct, 0.0)
        self.assertIn("jev: claude", out.reasoning)

    def test_low_confidence_keeps_local(self):
        cls = _cls("free")
        self.assertIs(jev.refine(cls, jev.JevVerdict("claude", 0.4, 0.1)), cls)

    def test_free_that_needs_context_becomes_claude(self):
        # "fix it": Jev picks free, but the prompt alone can't be served.
        out = jev.refine(_cls("free"), jev.JevVerdict("free", 0.49, 0.93))
        self.assertEqual(out.routing, "claude")

    def test_self_contained_free_stays_free(self):
        cls = _cls("free")
        self.assertIs(jev.refine(cls, jev.JevVerdict("free", 1.0, 0.03)), cls)

    def test_none_verdict_keeps_local(self):
        cls = _cls("split", est=0.4)
        self.assertIs(jev.refine(cls, None), cls)

    def test_should_ask_only_when_local_unsure(self):
        self.assertTrue(jev.should_ask(_cls(confidence=0.3)))
        self.assertFalse(jev.should_ask(_cls(confidence=0.8)))

    def test_env_switch(self):
        with mock.patch.dict("os.environ", {"WATERFALL_JEV": "0"}):
            self.assertFalse(jev.enabled())
        with mock.patch.dict("os.environ", {"WATERFALL_JEV": "1"}):
            self.assertTrue(jev.enabled())


def _tier_urlopen(probs, cost=0.00002):
    body = json.dumps({"answers": {"tier": {"type": "score", "score": 1.0,
                                            "probabilities": probs}},
                       "usage": {"cost": cost}}).encode()

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        urlopen.last = (req, timeout)
        return _Resp(body)
    return urlopen


class TierTests(unittest.TestCase):
    def test_ask_tier_takes_top_probability_level(self):
        # score is continuous (1.02 here), so the level must come from probabilities.
        v = jev.ask_tier("implement an LRU cache", key="k",
                         urlopen=_tier_urlopen({"0": 0.0, "1": 0.07, "2": 0.93}))
        self.assertEqual((v.tier, round(v.confidence, 2)), ("large", 0.93))

    def test_ask_tier_failure_returns_none(self):
        def boom(req, timeout=None):
            raise TimeoutError()
        self.assertIsNone(jev.ask_tier("x", key="k", urlopen=boom))

    def test_pick_tier_uses_jev_when_confident(self):
        self.assertEqual(jev.pick_tier(jev.TierVerdict("large", 0.9), "small"), ("large", "jev"))

    def test_pick_tier_falls_back_when_unsure_or_missing(self):
        self.assertEqual(jev.pick_tier(jev.TierVerdict("medium", 0.63), "small"), ("small", "local"))
        self.assertEqual(jev.pick_tier(None, "small"), ("small", "local"))


class RouteWithApiJevTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cache = ResponseCache(cache_path=Path(self._tmp.name) / "c.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _route(self, prompt, verdict, use_jev=True, tier_verdict=None, **kw):
        router = SmartRouter(cache=self.cache, use_jev=use_jev)
        gen = GenerateResult(text="ok", model="m", input_tokens=1, output_tokens=1,
                             cost_usd=0.0, elapsed_sec=0.0)
        with mock.patch.object(jev, "ask", return_value=verdict) as ask, \
             mock.patch.object(jev, "ask_tier", return_value=tier_verdict) as ask_tier, \
             mock.patch("openrouter_api_client.OpenRouterClient") as client:
            client.return_value.generate_with_usage.return_value = gen
            self.ask_tier = ask_tier
            return router.route_with_api(prompt, **kw), ask, client

    def test_confident_jev_tier_is_used_and_logged(self):
        res, _, client = self._route("Implement an LRU cache in Python",
                                     jev.JevVerdict("free", 0.99, 0.02),
                                     tier_verdict=jev.TierVerdict("large", 0.93))
        self.assertEqual((res.model_tier, res.tier_source), ("large", "jev"))
        self.assertEqual(client.return_value.generate_with_usage.call_args.kwargs["tier"], "large")
        self.assertEqual(res.jev["tier"], "large")

    def test_unsure_jev_tier_falls_back_to_local(self):
        res, _, _ = self._route("Implement an LRU cache in Python",
                                jev.JevVerdict("free", 0.99, 0.02),
                                tier_verdict=jev.TierVerdict("large", 0.5))
        self.assertEqual(res.tier_source, "local")
        self.assertEqual(res.model_tier, _roc.tier_for_complexity(res.classification.complexity_score))

    def test_jev_tier_failure_falls_back_to_local(self):
        res, _, _ = self._route("Implement an LRU cache in Python",
                                jev.JevVerdict("free", 0.99, 0.02), tier_verdict=None)
        self.assertEqual(res.tier_source, "local")

    def test_pinned_tier_never_asks_jev(self):
        res, _, _ = self._route("Implement an LRU cache in Python",
                                jev.JevVerdict("free", 0.99, 0.02), tier="medium")
        self.ask_tier.assert_not_called()
        self.assertEqual((res.model_tier, res.tier_source), ("medium", "pinned"))

    def test_cache_hit_skips_tier_call(self):
        prompt = "Write a regex for a zip code"
        self._route(prompt, jev.JevVerdict("free", 0.99, 0.02),
                    tier_verdict=jev.TierVerdict("small", 0.99))
        self._route(prompt, jev.JevVerdict("free", 0.99, 0.02),
                    tier_verdict=jev.TierVerdict("small", 0.99))
        self.ask_tier.assert_not_called()

    def test_jev_upgrades_follow_up_to_claude_and_skips_free_model(self):
        res, ask, client = self._route("yes look into why", jev.JevVerdict("claude", 0.51, 0.87))
        ask.assert_called_once()
        self.assertEqual(res.classification.routing, "claude")
        self.assertTrue(res.jev["changed"])
        client.return_value.generate_with_usage.assert_not_called()
        self.assertEqual(res.final_claude_prompt, "yes look into why")

    def test_jev_failure_falls_back_silently(self):
        res, ask, _ = self._route("yes look into why", None)
        ask.assert_called_once()
        self.assertIsNone(res.jev)
        self.assertEqual(res.classification.routing, SmartRouter(use_jev=False).classify(
            "yes look into why").routing)

    def test_disabled_never_calls_jev(self):
        _, ask, _ = self._route("yes look into why", None, use_jev=False)
        ask.assert_not_called()

    def test_classify_alone_never_calls_jev(self):
        # The prompt hook uses classify(); it must stay local and offline.
        with mock.patch.object(jev, "ask") as ask:
            SmartRouter(cache=self.cache, use_jev=True).classify("fix it")
        ask.assert_not_called()


if __name__ == "__main__":
    unittest.main()
