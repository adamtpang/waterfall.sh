"""Local desktop API for waterfall -- stdlib HTTP only.

Serves desktop/app.html and JSON endpoints that wrap the existing router
(classify, route, stats, hooks) plus coding-agent CLI detection/launch.

    python -m desktop.server
    watertop
    waterfall desktop

Inspired by OSS patterns (AionUi multi-agent launch, opcode usage chrome,
Palot glass-over-CLI) without forking those repos. See DESKTOP_GUI_LANDSCAPE.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

DESKTOP_DIR = Path(__file__).resolve().parent
REPO_ROOT = DESKTOP_DIR.parent
ROUTER_DIR = REPO_ROOT / "router"

if str(ROUTER_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTER_DIR))

# Known coding-agent CLIs we can detect and launch (glass-over-CLI pattern).
#
# "lever" entries are launch profiles, not different agents: same `claude`
# binary, launched with an extra --append-system-prompt-file that puts the
# session into a scoped persona (see desktop/profiles/*.md). This is the
# prototype for archimedes.life's Fulcrum Media/Capital/Labor: spin one up
# exactly as easily as Claude Code itself, because it IS Claude Code, just
# pointed at a lever. Media is the first one; Capital and Labor follow the
# same shape once this proves out.
AGENT_SPECS = (
    {"id": "claude", "label": "Claude Code", "commands": ("claude",), "kind": "coding"},
    {"id": "codex", "label": "Codex", "commands": ("codex",), "kind": "coding"},
    {"id": "grok", "label": "Grok Build", "commands": ("grok",), "kind": "coding"},
    {"id": "opencode", "label": "OpenCode", "commands": ("opencode", "opencode-ai"), "kind": "coding"},
    {"id": "gemini", "label": "Gemini CLI", "commands": ("gemini",), "kind": "coding"},
    {"id": "cursor", "label": "Cursor Agent", "commands": ("cursor-agent", "agent"), "kind": "coding"},
    {
        "id": "fulcrum-media",
        "label": "Fulcrum Media",
        "commands": ("claude",),
        "kind": "lever",
        "system_prompt_file": str(DESKTOP_DIR / "profiles" / "fulcrum-media.md"),
    },
    {
        "id": "fulcrum-capital",
        "label": "Fulcrum Capital",
        "commands": ("claude",),
        "kind": "lever",
        "system_prompt_file": str(DESKTOP_DIR / "profiles" / "fulcrum-capital.md"),
    },
    {
        "id": "fulcrum-labor",
        "label": "Fulcrum Labor",
        "commands": ("claude",),
        "kind": "lever",
        "system_prompt_file": str(DESKTOP_DIR / "profiles" / "fulcrum-labor.md"),
    },
)


def detect_agents() -> list[dict[str, Any]]:
    found = []
    for spec in AGENT_SPECS:
        path = None
        for cmd in spec["commands"]:
            path = shutil.which(cmd)
            if path:
                break
        found.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "kind": spec["kind"],
                "available": bool(path),
                "path": path or "",
                "command": spec["commands"][0],
            }
        )
    return found


def launch_agent(agent_id: str, cwd: Optional[str] = None, prompt: Optional[str] = None) -> dict[str, Any]:
    agents = {a["id"]: a for a in detect_agents()}
    agent = agents.get(agent_id)
    if not agent:
        return {"ok": False, "error": f"unknown agent: {agent_id}"}
    if not agent["available"]:
        return {"ok": False, "error": f"{agent['label']} not found on PATH"}

    workdir = Path(cwd).expanduser() if cwd else Path.cwd()
    if not workdir.is_dir():
        return {"ok": False, "error": f"cwd not a directory: {workdir}"}

    cmd = [agent["command"]]
    spec = next((s for s in AGENT_SPECS if s["id"] == agent_id), None)
    system_prompt_file = spec.get("system_prompt_file") if spec else None
    if system_prompt_file:
        if not Path(system_prompt_file).is_file():
            return {"ok": False, "error": f"profile system prompt missing: {system_prompt_file}"}
        cmd += ["--append-system-prompt-file", system_prompt_file]

    # Best-effort prompt passthrough; each CLI differs. Prefer interactive shell.
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    try:
        subprocess.Popen(
            cmd,
            cwd=str(workdir),
            creationflags=creationflags,
            stdin=None,
            stdout=None,
            stderr=None,
        )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "agent": agent_id,
        "command": agent["command"],
        "cwd": str(workdir),
        "note": "Opened in a new terminal/console. Paste prompts there if needed."
        + (f" Suggested first prompt: {prompt[:200]}" if prompt else ""),
    }


def _json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def api_status() -> dict[str, Any]:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    key_file = Path.home() / ".claude" / "openrouter_key.txt"
    if not key and key_file.is_file():
        key = key_file.read_text(encoding="utf-8").strip()
    return {
        "product": "waterfall.sh",
        "surface": "desktop",
        "openrouter_configured": bool(key),
        "repo_root": str(REPO_ROOT),
        "agents": detect_agents(),
    }


def api_stats(since_days: Optional[int] = None) -> dict[str, Any]:
    from tracker import SavingsTracker

    since = None
    if since_days:
        since = datetime.now(timezone.utc) - timedelta(days=since_days)
    tracker = SavingsTracker()
    events = tracker.load_events(since=since)
    summary = tracker.summarize(events)
    openrouter_tokens = sum(e.tokens_saved for e in events if e.backend_used == "openrouter")
    cache_tokens = sum(e.tokens_saved for e in events if e.backend_used == "cache")
    return {
        "total_prompts": summary.total_prompts,
        "tokens_avoided": summary.tokens_avoided,
        "estimated_cost_saved": summary.estimated_cost_saved,
        "openrouter_tokens_avoided": openrouter_tokens,
        "cache_tokens_avoided": cache_tokens,
        "event_count": len(events),
    }


def api_hooks(since_days: Optional[int] = 14) -> dict[str, Any]:
    import hook_log as hl

    since = datetime.now(timezone.utc) - timedelta(days=since_days) if since_days else None
    entries = hl.load_entries(since=since)
    nudges = [e for e in entries if e.hook == "nudge"]
    denials = [e for e in entries if e.hook == "ringer"]
    by_day = hl.group_by_day(entries)
    recent = [
        {
            "timestamp": e.timestamp,
            "hook": e.hook,
            "project": e.project,
            "detail": e.detail,
        }
        for e in entries[-30:]
    ]
    return {
        "nudge_count": len(nudges),
        "ringer_count": len(denials),
        "by_day": by_day,
        "recent": list(reversed(recent)),
    }


SGT = timezone(timedelta(hours=8))
RESET_WEEKDAY_NAME = "tuesday"
RESET_HOUR = 16


def _bucket_to_dict(b: Any) -> dict[str, Any]:
    # Status -> a simple color band the UI maps to green/yellow/red, kept
    # here (not guessed client-side in JS) so the one real threshold
    # (usage_pace.STATUS_MARGIN) has a single source of truth.
    import usage_pace

    if b.pace_delta > usage_pace.STATUS_MARGIN:
        color = "red"
    elif b.pace_delta < -usage_pace.STATUS_MARGIN:
        color = "green"
    else:
        color = "yellow"
    return {
        "label": b.label, "used_pct": b.used_pct, "elapsed_pct": b.elapsed_pct,
        "pace_delta": b.pace_delta, "status": b.status, "color": color,
        "window_hours": b.window_hours, "hours_remaining": b.hours_remaining,
    }


def api_pace(qs: dict[str, list[str]]) -> dict[str, Any]:
    """Real usage-pace data for the visual dashboard. Mirrors `waterfall
    usage-pace`'s own bucket-building logic (weekly all-models, 5-hour
    session, per-model weekly, plus --bucket-style independent subscriptions)
    -- same query-param shape as the CLI flags, all optional. When used_pct
    is omitted, falls back to the automatic local-transcript estimate
    (quota_estimate.py) so the dashboard shows *something* real without
    requiring Adam to paste numbers first."""
    import usage_pace
    import quota_estimate as qe

    def _first(key: str) -> Optional[str]:
        v = qs.get(key)
        return v[0] if v else None

    now = datetime.now(SGT)
    reset_boundary = usage_pace._last_reset(now, usage_pace.WEEKDAYS[RESET_WEEKDAY_NAME], RESET_HOUR)

    used_pct_raw = _first("used_pct")
    estimated = False
    if used_pct_raw is not None:
        used_pct = float(used_pct_raw)
    else:
        estimate = qe.get_estimate(reset_boundary, now=now, cache_path=qe.DEFAULT_CACHE_PATH)
        used_pct = estimate.estimated_pct
        estimated = True

    result = usage_pace.compute_pace(
        used_pct=used_pct, now=now,
        reset_weekday=usage_pace.WEEKDAYS[RESET_WEEKDAY_NAME], reset_hour=RESET_HOUR,
    )
    buckets = [usage_pace.BucketResult(
        label="weekly (all models)" + (" (est.)" if estimated else ""),
        used_pct=result.used_pct, elapsed_pct=result.elapsed_pct,
        pace_delta=result.pace_delta, status=result.status,
        window_hours=usage_pace.HOURS_PER_WEEK, hours_remaining=result.hours_remaining,
    )]

    session_pct = _first("session_pct")
    session_hours_remaining = _first("session_hours_remaining")
    if session_pct is not None and session_hours_remaining is not None:
        window = float(_first("session_window_hours") or 5.0)
        buckets.append(usage_pace.compute_bucket_pace(
            "5-hour session", float(session_pct), window, float(session_hours_remaining),
        ))

    for raw in qs.get("model_pct", []):
        model, _, pct = raw.partition("=")
        if model and pct:
            buckets.append(usage_pace.compute_bucket_pace(
                f"weekly ({model.strip()})", float(pct), usage_pace.HOURS_PER_WEEK, result.hours_remaining,
            ))

    for raw in qs.get("bucket", []):
        label, _, rest = raw.partition("=")
        parts = rest.split(":")
        if label and len(parts) == 3:
            try:
                u, w, r = (float(x) for x in parts)
                buckets.append(usage_pace.compute_bucket_pace(label.strip(), u, w, r))
            except ValueError:
                pass

    # Day-of-week ceiling reference: elapsed_pct if you checked at each
    # day's reset-hour mark, so the UI can show "today's ceiling is X%".
    ceiling_by_day = []
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i in range(8):
        mark = reset_boundary + timedelta(hours=24 * i)
        elapsed_pct = round(min(100.0, i * 24 / usage_pace.HOURS_PER_WEEK * 100), 1)
        ceiling_by_day.append({"day": day_names[mark.weekday()], "date": mark.strftime("%Y-%m-%d"), "ceiling_pct": elapsed_pct})

    return {
        "now": now.isoformat(),
        "reset_boundary": reset_boundary.isoformat(),
        "next_reset": result.next_reset.isoformat(),
        "buckets": [_bucket_to_dict(b) for b in buckets],
        "guidance": usage_pace.guidance(buckets) if len(buckets) > 1 else None,
        "ceiling_by_day": ceiling_by_day,
        "estimated": estimated,
    }


def api_classify(prompt: str) -> dict[str, Any]:
    from smart_router import SmartRouter

    router = SmartRouter()
    cls = router.classify(prompt)
    split = router.split(prompt, cls)
    return {
        "routing": cls.routing,
        "complexity": cls.complexity_score,
        "confidence": cls.confidence,
        "estimated_free_pct": cls.estimated_free_pct,
        "task_types": list(cls.task_types),
        "domains": list(cls.domains),
        "reasoning": cls.reasoning,
        "free_prompt": split.free_prompt or "",
        "claude_prompt": split.claude_prompt or "",
        "savings_pct": split.savings_pct,
    }


def api_route(prompt: str, dry_run: bool = True, log: bool = True) -> dict[str, Any]:
    from smart_router import SmartRouter, API_ROUTER_AVAILABLE
    from tracker import SavingsTracker, estimate_cost_saved
    from classifier.types import SavingsEvent

    base = api_classify(prompt)
    if dry_run or not base.get("free_prompt"):
        base["dry_run"] = True
        base["routed"] = False
        return base

    if not API_ROUTER_AVAILABLE:
        base["dry_run"] = False
        base["routed"] = False
        base["error"] = "OpenRouter API unavailable -- set OPENROUTER_API_KEY"
        return base

    router = SmartRouter()
    result = router.route_with_api(prompt)
    base["dry_run"] = False
    base["routed"] = True
    base["cache_hit"] = bool(getattr(result, "cache_hit", False))
    base["model_used"] = getattr(result, "model_used", "") or ""
    base["model_tier"] = getattr(result, "model_tier", "") or ""
    base["cost_usd"] = float(getattr(result, "cost_usd", 0.0) or 0.0)
    base["input_tokens"] = int(getattr(result, "input_tokens", 0) or 0)
    base["output_tokens"] = int(getattr(result, "output_tokens", 0) or 0)
    base["elapsed_sec"] = float(getattr(result, "elapsed_sec", 0.0) or 0.0)
    base["free_response"] = getattr(result, "free_response", "") or ""
    base["final_claude_prompt"] = getattr(result, "final_claude_prompt", "") or ""

    if log:
        split = result.split
        cls = result.classification
        tokens_saved = split.free_token_estimate
        event = SavingsEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            original_tokens=split.free_token_estimate + split.claude_token_estimate,
            free_tokens_sent=split.free_token_estimate,
            claude_tokens_needed=split.claude_token_estimate,
            tokens_saved=tokens_saved,
            cost_saved_usd=estimate_cost_saved(tokens_saved, result.cost_usd),
            backend_used="cache" if result.cache_hit else "openrouter",
            model_used=result.model_used,
            routing_decision=cls.routing,
            task_types=list(cls.task_types),
            elapsed_sec=result.elapsed_sec,
            prompt_preview=prompt[:200],
            model_tier=result.model_tier,
        )
        SavingsTracker().record(event)
        base["logged"] = True
    else:
        base["logged"] = False
    return base


class DesktopHandler(BaseHTTPRequestHandler):
    server_version = "waterfall-desktop/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Quiet by default; useful when debugging: set WATERFALL_DESKTOP_VERBOSE=1
        if os.environ.get("WATERFALL_DESKTOP_VERBOSE"):
            super().log_message(fmt, *args)

    def _cors(self) -> None:
        # Tauri webview is not same-origin with 127.0.0.1; without CORS,
        # fetch() fails with "Failed to fetch" even when the server is up.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path in ("/", "/index.html", "/app.html"):
            html_path = DESKTOP_DIR / "app.html"
            if not html_path.is_file():
                self._send_json(404, {"error": "app.html missing"})
                return
            self._send(200, html_path.read_bytes(), "text/html; charset=utf-8")
            return

        if path in ("/pace", "/pace.html"):
            html_path = DESKTOP_DIR / "pace.html"
            if not html_path.is_file():
                self._send_json(404, {"error": "pace.html missing"})
                return
            self._send(200, html_path.read_bytes(), "text/html; charset=utf-8")
            return

        if path == "/tokens.css":
            css_path = DESKTOP_DIR / "tokens.css"
            if not css_path.is_file():
                self._send_json(404, {"error": "tokens.css missing"})
                return
            self._send(200, css_path.read_bytes(), "text/css; charset=utf-8")
            return

        if path == "/api/pace":
            try:
                self._send_json(200, api_pace(qs))
            except Exception as exc:  # noqa: BLE001 -- surface to UI, never crash server thread
                self._send_json(500, {"error": str(exc), "type": type(exc).__name__})
            return

        if path == "/api/status":
            self._send_json(200, api_status())
            return
        if path == "/api/stats":
            days = int(qs.get("since_days", ["14"])[0] or 14)
            self._send_json(200, api_stats(since_days=days))
            return
        if path == "/api/hooks":
            days = int(qs.get("since_days", ["14"])[0] or 14)
            self._send_json(200, api_hooks(since_days=days))
            return
        if path == "/api/agents":
            self._send_json(200, {"agents": detect_agents()})
            return

        self._send_json(404, {"error": "not found", "path": path})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        data = _json_body(self)

        try:
            if path == "/api/classify":
                prompt = str(data.get("prompt") or "").strip()
                if not prompt:
                    self._send_json(400, {"error": "prompt required"})
                    return
                self._send_json(200, api_classify(prompt))
                return

            if path == "/api/route":
                prompt = str(data.get("prompt") or "").strip()
                if not prompt:
                    self._send_json(400, {"error": "prompt required"})
                    return
                dry_run = bool(data.get("dry_run", True))
                log = bool(data.get("log", True))
                self._send_json(200, api_route(prompt, dry_run=dry_run, log=log))
                return

            if path == "/api/launch":
                agent_id = str(data.get("agent") or "").strip()
                cwd = data.get("cwd")
                prompt = data.get("prompt")
                self._send_json(200, launch_agent(agent_id, cwd=cwd, prompt=prompt))
                return
        except Exception as exc:  # noqa: BLE001 -- surface to UI, never crash server thread
            self._send_json(500, {"error": str(exc), "type": type(exc).__name__})
            return

        self._send_json(404, {"error": "not found", "path": path})


def run_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), DesktopHandler)
    return httpd


def open_ui(url: str, native: bool = False) -> None:
    if native:
        try:
            import webview  # type: ignore

            webview.create_window("waterfall.sh", url, width=1100, height=760)
            webview.start()
            return
        except ImportError:
            print("pywebview not installed -- opening system browser. "
                  "Optional: pip install pywebview", file=sys.stderr)
    webbrowser.open(url)


def _safe_stdio() -> None:
    """Avoid UnicodeEncodeError on Windows consoles (cp1252) for any leftover
    non-ASCII prints. Best-effort; never fatal."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    _safe_stdio()

    p = argparse.ArgumentParser(description="waterfall desktop command center")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true", help="don't open a browser/window")
    p.add_argument("--native", action="store_true",
                   help="use pywebview native window if installed")
    p.add_argument("--bind-only", action="store_true",
                   help="start server only (for tests); still blocks until Ctrl+C")
    args = p.parse_args(argv)

    httpd = run_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}/"
    # ASCII-only: Windows Git Bash / cmd often use cp1252 and choke on arrows.
    print(f"watertop -> {url}")
    print("Ctrl+C to stop.")

    if not args.no_open and not args.bind_only:
        # Open after bind so first paint isn't a connection error
        threading.Timer(0.35, lambda: open_ui(url, native=args.native)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
