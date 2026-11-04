"""Local waterfall license. Soft gate until a Stripe webhook exists."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LICENSE_PATH = Path.home() / ".waterfall" / "license.json"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load() -> dict:
    try:
        data = json.loads(LICENSE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict) -> Path:
    LICENSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LICENSE_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return LICENSE_PATH


def is_founder_machine() -> bool:
    if os.environ.get("WATERFALL_FOUNDER") == "1":
        return True
    aether = Path.home() / "Aether"
    return Path.home().name.lower() == "adamp" and aether.is_dir()


def status() -> dict:
    data = load()
    kind = data.get("kind")
    if kind in {"paid", "founder"}:
        return {"ok": True, "kind": kind, "path": str(LICENSE_PATH), **data}
    if is_founder_machine():
        return {"ok": True, "kind": "founder-auto", "path": str(LICENSE_PATH)}
    return {"ok": False, "kind": "none", "path": str(LICENSE_PATH)}


def mark_paid() -> dict:
    data = {
        "kind": "paid",
        "product": "waterfall",
        "price_usd": 30,
        "buy_url": "https://buy.stripe.com/4gM14n0wy7cFbIAecVaMU1J",
        "marked_at": _now(),
        "note": "honor-system unlock after Stripe. webhook comes later.",
    }
    save(data)
    return status()


def mark_founder() -> dict:
    data = {
        "kind": "founder",
        "product": "waterfall",
        "marked_at": _now(),
    }
    save(data)
    return status()
