"""Tests for the waterfall desktop command center (no browser, no network)."""

from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "router"))

from desktop import server as desktop_server  # noqa: E402


def _pin_desktop_clock():
    """Pin desktop_server's clock to mid-week (Saturday noon 2026-10-03
    SGT, ~2.8 days after the Tuesday 4pm reset) so /api/pace output is
    deterministic. With the real clock, "5% used" read as on pace, not
    under it, for the first hours after every reset, so the color test
    failed early each week."""
    from datetime import datetime as _real_dt

    class _MidWeek(_real_dt):
        @classmethod
        def now(cls, tz=None):
            return _real_dt(2026, 10, 3, 12, 0, tzinfo=tz)

    return mock.patch.object(desktop_server, "datetime", _MidWeek)


class DetectAgentsTests(unittest.TestCase):
    def test_detect_agents_returns_known_ids(self):
        agents = desktop_server.detect_agents()
        ids = {a["id"] for a in agents}
        self.assertIn("claude", ids)
        self.assertIn("codex", ids)
        self.assertIn("grok", ids)
        for a in agents:
            self.assertIn("available", a)
            self.assertIn("label", a)
            self.assertIsInstance(a["available"], bool)

    def test_launch_unknown_agent(self):
        result = desktop_server.launch_agent("not-a-real-agent")
        self.assertFalse(result["ok"])
        self.assertIn("unknown", result["error"])


class WatertopLauncherTests(unittest.TestCase):
    def test_watertop_help(self):
        from desktop import watertop

        self.assertEqual(watertop.main(["--help"]), 0)

    def test_watertop_entry_point_importable(self):
        from desktop.watertop import main

        self.assertTrue(callable(main))


class ClassifyApiTests(unittest.TestCase):
    def test_classify_simple_prompt(self):
        out = desktop_server.api_classify("rename this variable from foo to bar")
        self.assertIn("routing", out)
        self.assertIn("complexity", out)
        self.assertIn("reasoning", out)

    def test_route_dry_run(self):
        out = desktop_server.api_route(
            "Write a one-line docstring for a function that adds two numbers.",
            dry_run=True,
        )
        self.assertTrue(out.get("dry_run"))
        self.assertFalse(out.get("routed"))

    def _live(self, prompt, jev_verdict):
        """Live route with Jev and the OpenRouter client mocked: no network."""
        from unittest import mock
        import jev
        from openrouter_api_client import GenerateResult
        gen = GenerateResult(text="def f(): pass", model="cheap/m", input_tokens=20,
                             output_tokens=10, cost_usd=0.0, elapsed_sec=0.1)
        with mock.patch.dict("os.environ", {"WATERFALL_JEV": "1"}), \
             mock.patch.object(jev, "ask", return_value=jev_verdict), \
             mock.patch.object(jev, "ask_tier", return_value=None), \
             mock.patch("smart_router.CACHE_AVAILABLE", False), \
             mock.patch("openrouter_api_client.OpenRouterClient") as client:
            client.return_value.generate_with_usage.return_value = gen
            return desktop_server.api_route(prompt, dry_run=False, log=False), client

    def test_live_route_asks_jev_even_when_local_routes_all_to_claude(self):
        import jev
        prompt = "Refactor our auth middleware across 6 files to fix an intermittent race condition in session refresh."
        self.assertEqual(desktop_server.api_classify(prompt)["routing"], "claude")
        out, client = self._live(prompt, jev.JevVerdict("claude", 0.9, 0.9))
        self.assertEqual(out["routing"], "claude")
        self.assertEqual(out["jev"]["routing"], "claude")
        self.assertFalse(out["routed"])
        self.assertIsNone(out["savings"])
        client.return_value.generate_with_usage.assert_not_called()

    def test_live_route_reports_jevs_final_decision_and_savings(self):
        import jev
        prompt = "Write a Python function that reverses a string."
        out, client = self._live(prompt, jev.JevVerdict("free", 0.99, 0.02))
        self.assertEqual(out["routing"], "free")
        self.assertTrue(out["routed"])
        self.assertEqual(out["free_response"], "def f(): pass")
        self.assertGreater(out["savings"]["claude_equivalent_usd"], 0)
        client.return_value.generate_with_usage.assert_called_once()


class HttpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Port 0 = ephemeral free port
        cls.httpd = desktop_server.run_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path: str):
        with urlopen(self.base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, body: dict):
        req = Request(
            self.base + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_status_endpoint(self):
        status, data = self._get("/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(data["product"], "waterfall.sh")
        self.assertIn("agents", data)

    def test_app_html_served(self):
        with urlopen(self.base + "/", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("waterfall", body.lower())
            self.assertIn("Cascade", body)

    def test_classify_endpoint(self):
        status, data = self._post("/api/classify", {"prompt": "fix a typo in README"})
        self.assertEqual(status, 200)
        self.assertIn("routing", data)

    def test_classify_requires_prompt(self):
        req = Request(
            self.base + "/api/classify",
            data=json.dumps({}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_pace_page_served(self):
        with urlopen(self.base + "/pace", timeout=5) as resp:
            body = resp.read().decode("utf-8")
            self.assertEqual(resp.status, 200)
            self.assertIn("usage pace", body)

    def test_pace_endpoint_no_params_falls_back_to_estimate(self):
        import quota_estimate
        # Stub get_estimate so the pinned clock never triggers a real
        # transcript scan or a real ~/.claude cache write keyed to a fake
        # 2026 reset boundary; the estimate math has its own test file.
        fake = SimpleNamespace(estimated_pct=42.0)
        with _pin_desktop_clock(), \
                mock.patch.object(quota_estimate, "get_estimate", return_value=fake):
            status, data = self._get("/api/pace")
            self.assertEqual(status, 200)
            self.assertTrue(data["estimated"])
            self.assertEqual(len(data["buckets"]), 1)
            self.assertIn("(est.)", data["buckets"][0]["label"])
            self.assertEqual(len(data["ceiling_by_day"]), 8)

    def test_pace_endpoint_with_used_pct_is_not_estimated(self):
        with _pin_desktop_clock():
            status, data = self._get("/api/pace?used_pct=30")
            self.assertEqual(status, 200)
            self.assertFalse(data["estimated"])
            self.assertEqual(data["buckets"][0]["used_pct"], 30.0)
            self.assertNotIn("(est.)", data["buckets"][0]["label"])

    def test_pace_endpoint_multiple_buckets_include_guidance(self):
        with _pin_desktop_clock():
            status, data = self._get(
                "/api/pace?used_pct=30&session_pct=13&session_hours_remaining=3.45&model_pct=fable=3"
            )
            self.assertEqual(status, 200)
            self.assertEqual(len(data["buckets"]), 3)
            self.assertIsNotNone(data["guidance"])
            self.assertIn("binding constraint", data["guidance"])

    def test_pace_endpoint_color_coding(self):
        with _pin_desktop_clock():
            # Comfortably under pace -> green
            status, data = self._get("/api/pace?used_pct=5")
            self.assertEqual(data["buckets"][0]["color"], "green")
            # Way over pace -> red
            status, data = self._get("/api/pace?used_pct=95")
            self.assertEqual(data["buckets"][0]["color"], "red")


if __name__ == "__main__":
    unittest.main()
