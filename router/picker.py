"""Interactive project sidebar for the waterfall CLI."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import projects as projmod
import tabs

REMOTE_URL = "http://127.0.0.1:7910"


def spawn_remote(project: projmod.Project) -> tuple[bool, str]:
    body = json.dumps({"name": project.name, "cwd": project.path}).encode("utf-8")
    req = urllib.request.Request(
        f"{REMOTE_URL}/api/agents",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return False, f"waterfall board is down ({exc}). Start it with: waterfall remote"
    except TimeoutError:
        return False, "waterfall board timed out. Start it with: waterfall remote"
    agent_id = data.get("id") or ""
    return True, f"{REMOTE_URL}/#/agents/{agent_id}" if agent_id else REMOTE_URL


def open_tab(project: projmod.Project, agent: str) -> tuple[bool, str]:
    found = tabs.TabProject(project.name, Path(project.path), pinned=project.pinned)
    host = tabs.pick_host()
    if not host or host.id != "wt":
        return False, "Windows Terminal (wt) not on PATH"
    try:
        cmd = tabs.build_wt_command([found], agent, new_window=False)
    except ValueError as exc:
        return False, str(exc)
    code = tabs.launch(cmd, dry_run=False)
    return code == 0, "opened Windows Terminal tab" if code == 0 else "wt launch failed"


def _read_key() -> str:
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            extra = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(extra, extra)
        if ch == "\r":
            return "enter"
        if ch == "\x1b":
            return "quit"
        return ch.lower()
    import tty
    import termios

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if ch == "\r" or ch == "\n":
        return "enter"
    if ch == "\x1b":
        rest = sys.stdin.read(2) if sys.stdin.isatty() else ""
        return {"[A": "up", "[B": "down"}.get(rest, "quit")
    return ch.lower()


def _draw(items: list[projmod.Project], idx: int) -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.write("waterfall projects\n")
    sys.stdout.write("j/k or arrows  enter=remote  t=tab  b=both  q=quit\n\n")
    for i, item in enumerate(items):
        mark = ">" if i == idx else " "
        pin = "*" if item.pinned else " "
        sys.stdout.write(f" {mark}{pin} {item.name:<28} {item.path}\n")
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_picker(action: str = "remote", agent: str | None = None) -> int:
    items = projmod.list_projects()
    if not items:
        print("no Aether projects found", file=sys.stderr)
        return 1
    agent = agent or tabs.default_agent()
    if not sys.stdin.isatty():
        for item in items:
            pin = "*" if item.pinned else " "
            print(f" {pin} {item.name:<28} {item.path}")
        return 0

    idx = 0
    while True:
        _draw(items, idx)
        key = _read_key()
        if key in ("q", "quit"):
            sys.stdout.write("\x1b[2J\x1b[H")
            return 0
        if key in ("j", "down"):
            idx = min(idx + 1, len(items) - 1)
            continue
        if key in ("k", "up"):
            idx = max(idx - 1, 0)
            continue
        chosen = action
        if key == "t":
            chosen = "tab"
        elif key == "r" or key == "enter":
            chosen = "remote" if action != "tab" else action
        elif key == "b":
            chosen = "both"
        elif key != "enter":
            continue
        return act_on(items[idx], chosen, agent)


def act_on(project: projmod.Project, action: str, agent: str) -> int:
    print(f"{project.name}\n{project.path}")
    ok = True
    if action in ("remote", "both"):
        fine, msg = spawn_remote(project)
        print(msg)
        ok = ok and fine
        if fine:
            try:
                import webbrowser

                webbrowser.open(msg if msg.startswith("http") else REMOTE_URL)
            except Exception:
                pass
    if action in ("tab", "both"):
        fine, msg = open_tab(project, agent)
        print(msg)
        ok = ok and fine
    return 0 if ok else 1
