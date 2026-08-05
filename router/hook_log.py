"""Hook-firing log -- append-only JSONL record of every time a waterfall
hook actually did something: injected a nudge, or denied a tool call.
Exists so "is waterfall actually doing anything" has a real, checkable
answer instead of an inference from noisy day-to-day token volume.

Deliberately narrow: this logs the meaningful events only (a nudge fired,
a call was denied), not every hook invocation -- logging every allowed
Read/Bash call would be high-volume noise that defeats the point of a
quick "did it fire" check. `waterfall hook-log` reads this back.

Logging is a side effect, never a gate: a failure here must never
prevent a hook's real decision (the nudge/deny JSON) from being
returned. Both hook scripts wrap their log call in a bare try/except.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DEFAULT_LOG_PATH = Path.home() / ".claude" / "waterfall_hook_log.jsonl"


@dataclass
class HookLogEntry:
    timestamp: str
    hook: str       # "nudge" | "ringer"
    project: str    # basename of the session's cwd at fire time
    action: str     # "nudged" | "denied"
    detail: str     # short human-readable reason


def project_label(cwd: str) -> str:
    return Path(cwd).name if cwd else "(unknown)"


def append_entry(entry: HookLogEntry, log_path: Optional[Path] = None) -> None:
    path = Path(log_path) if log_path else DEFAULT_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def log_nudge(cwd: str, detail: str, log_path: Optional[Path] = None) -> None:
    append_entry(HookLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        hook="nudge", project=project_label(cwd), action="nudged", detail=detail,
    ), log_path)


def log_deny(cwd: str, detail: str, log_path: Optional[Path] = None) -> None:
    append_entry(HookLogEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        hook="ringer", project=project_label(cwd), action="denied", detail=detail,
    ), log_path)


def load_entries(
    log_path: Optional[Path] = None, since: Optional[datetime] = None
) -> list[HookLogEntry]:
    path = Path(log_path) if log_path else DEFAULT_LOG_PATH
    if not path.is_file():
        return []

    entries: list[HookLogEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            entry = HookLogEntry(**data)
        except (json.JSONDecodeError, TypeError):
            continue  # skip corrupt/partial lines rather than fail the whole read
        if since is not None:
            try:
                ts = datetime.fromisoformat(entry.timestamp)
            except ValueError:
                ts = None
            if ts is not None and ts < since:
                continue
        entries.append(entry)
    return entries
