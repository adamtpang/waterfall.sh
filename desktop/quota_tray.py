"""waterfall quota tray -- a real system tray icon (like f.lux) that
watches Claude's quota automatically and pings you with a notification and
a recommended action when you're going overboard.

Covers only what's automatically derivable from local data: Claude's
weekly-all-models estimate, 5-hour rolling session estimate, and per-tier
(e.g. Fable) weekly estimate -- all rough proxies (see claude_usage.py's
EST_TOKENS_PER_PERCENT), all clearly labeled as such in the notification
text. Codex and Grok have no local usage signal (see CLAUDE.md's 2026-08-18
entry) so they aren't covered here; `waterfall usage-pace --bucket ...`
still handles those with manual input.

Run: python3 desktop/quota_tray.py
"""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "router"))

import claude_usage as cu  # noqa: E402
import quota_estimate as qe  # noqa: E402
import usage_pace  # noqa: E402

SGT = timezone(timedelta(hours=8))
RESET_WEEKDAY = usage_pace.WEEKDAYS["tuesday"]
RESET_HOUR = 16
SESSION_WINDOW_HOURS = 5.0
POLL_INTERVAL_SECONDS = 5 * 60  # 5 minutes -- more frequent than the hook's
# 30-minute cap is fine here: the tray is a dedicated, always-on process,
# not something running on every single prompt submission, so the transcript
# scan cost is paid rarely relative to how often Claude is actually used.

CACHE_DIR = Path.home() / ".claude"
WEEKLY_CACHE = CACHE_DIR / "waterfall_quota_estimate_cache.json"  # shared with the hook
SESSION_CACHE = CACHE_DIR / "waterfall_quota_estimate_cache_session.json"
FABLE_CACHE = CACHE_DIR / "waterfall_quota_estimate_cache_fable.json"

ICON_PATH = REPO_ROOT / "brand" / "logo.png"


def _now() -> datetime:
    return datetime.now(SGT)


def compute_buckets():
    """Weekly (all-models) and weekly-fable have a real, known reset time,
    so they get real pace comparison via BucketResult. The 5-hour session
    estimate does NOT -- Claude's actual session window start time isn't
    known locally (only Adam telling us "resets in Xh Ym" gives that), so
    treating "last 5 hours of local volume" as "0% of the window elapsed"
    would be a real, misleading bug: it would make the session estimate
    look permanently over-pace regardless of the real number. It's
    reported as a raw %-used signal with its own tier check instead, no
    pace claim attached."""
    now = _now()
    weekly_reset = usage_pace._last_reset(now, RESET_WEEKDAY, RESET_HOUR)
    session_start = now - timedelta(hours=SESSION_WINDOW_HOURS)

    weekly_est = qe.get_estimate(weekly_reset, now=now, cache_path=WEEKLY_CACHE)
    session_est = qe.get_estimate(session_start, now=now, cache_path=SESSION_CACHE,
                                   compute_fn=cu.estimate_pct_used_rolling)
    fable_est = qe.get_estimate(weekly_reset, now=now, cache_path=FABLE_CACHE,
                                 compute_fn=lambda rb: cu.estimate_pct_used_by_tier(rb, "fable"))

    weekly_hours_remaining = (weekly_reset + timedelta(hours=usage_pace.HOURS_PER_WEEK) - now).total_seconds() / 3600

    pace_buckets = [
        usage_pace.compute_bucket_pace("weekly (all models, est.)", weekly_est.estimated_pct,
                                        usage_pace.HOURS_PER_WEEK, weekly_hours_remaining),
        usage_pace.compute_bucket_pace("weekly fable (est.)", fable_est.estimated_pct,
                                        usage_pace.HOURS_PER_WEEK, weekly_hours_remaining),
    ]
    tiers_crossed = {
        "weekly (all models, est.)": qe.check_tier_crossing(weekly_est, cache_path=WEEKLY_CACHE),
        "5-hour session (est., raw signal)": qe.check_tier_crossing(session_est, cache_path=SESSION_CACHE),
        "weekly fable (est.)": qe.check_tier_crossing(fable_est, cache_path=FABLE_CACHE),
    }
    return pace_buckets, session_est.estimated_pct, tiers_crossed


def check_and_notify(icon) -> None:
    try:
        pace_buckets, session_pct, tiers_crossed = compute_buckets()
    except Exception as exc:
        icon.title = f"waterfall -- estimate failed: {exc}"
        return

    icon.title = (
        f"waterfall  weekly:{pace_buckets[0].used_pct:.0f}%  "
        f"session(5h):{session_pct:.0f}%  fable:{pace_buckets[1].used_pct:.0f}%"
    )

    newly_crossed = {label: tier for label, tier in tiers_crossed.items() if tier is not None}
    if not newly_crossed:
        return

    lines = [f"{label} crossed ~{tier}%" for label, tier in newly_crossed.items()]
    lines.append("")
    if pace_buckets:
        lines.append(usage_pace.guidance(pace_buckets))
    lines.append("")
    lines.append("(rough local estimate, not Claude Code's own number)")

    try:
        icon.notify("\n".join(lines), "waterfall: quota check")
    except Exception:
        pass  # notification backend unavailable -- tray keeps running regardless


def poll_loop(icon) -> None:
    check_and_notify(icon)  # check once immediately on startup
    while icon.visible:
        time.sleep(POLL_INTERVAL_SECONDS)
        if icon.visible:
            check_and_notify(icon)


def build_icon():
    import pystray
    from PIL import Image

    image = Image.open(ICON_PATH) if ICON_PATH.is_file() else Image.new("RGB", (32, 32), (94, 198, 255))

    def on_check_now(icon, item):
        threading.Thread(target=check_and_notify, args=(icon,), daemon=True).start()

    def on_quit(icon, item):
        icon.visible = False
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Check now", on_check_now),
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("waterfall", image, "waterfall", menu)
    return icon


def main() -> int:
    icon = build_icon()
    icon.run(setup=lambda icon: threading.Thread(target=poll_loop, args=(icon,), daemon=True).start())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
