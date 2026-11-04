"""CLI project tabs: glass over the host multiplexer, not a nested TUI.

Grok/Claude/Codex already occupy the full alt-screen. Nesting them inside
another TUI is a bad fit. The platonic move (tmux/zellij on Unix, Windows
Terminal here) is one real tab per project, each running `grok --cwd`.

Waterfall is the distro config: fleet list, default agent, host detection.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

AETHER_DEFAULT = Path(r"C:\Users\adamp\Aether")
WATERFALL_HOME = Path.home() / ".waterfall"
PROJECTS_FILE = WATERFALL_HOME / "projects.json"
PROFILE_FILE = WATERFALL_HOME / "profile.json"
TABS_FILE = WATERFALL_HOME / "tabs.json"

AGENTS = ("grok", "claude", "codex", "opencode")


@dataclass(frozen=True)
class TabProject:
    name: str
    path: Path
    pinned: bool = False


@dataclass(frozen=True)
class Host:
    id: str
    available: bool


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def aether_root() -> Path:
    tabs = load_json(TABS_FILE)
    raw = tabs.get("aether") or os.environ.get("AETHER_ROOT")
    if raw:
        return Path(raw)
    if AETHER_DEFAULT.is_dir():
        return AETHER_DEFAULT
    return Path.cwd()


def default_agent() -> str:
    tabs = load_json(TABS_FILE)
    if tabs.get("default_agent") in AGENTS:
        return str(tabs["default_agent"])
    profile = load_json(PROFILE_FILE)
    agent = profile.get("default_agent")
    if agent in AGENTS:
        return agent
    if agent == "auto":
        return "grok"
    return "grok"


def detect_hosts() -> list[Host]:
    return [
        Host("wt", shutil.which("wt") is not None),
        Host("wezterm", shutil.which("wezterm") is not None),
        Host("tmux", shutil.which("tmux") is not None),
        Host("zellij", shutil.which("zellij") is not None),
    ]


def pick_host(preferred: str | None = None) -> Host | None:
    tabs = load_json(TABS_FILE)
    want = preferred or tabs.get("host")
    hosts = detect_hosts()
    by_id = {h.id: h for h in hosts}
    if want and want in by_id and by_id[want].available:
        return by_id[want]
    for hid in ("wt", "wezterm", "tmux", "zellij"):
        if by_id[hid].available:
            return by_id[hid]
    return None


def _norm(p: str | Path) -> str:
    return str(Path(p)).replace("/", "\\").rstrip("\\").lower()


def resolve_project(name_or_path: str, root: Path | None = None) -> TabProject | None:
    raw = name_or_path.strip().strip('"')
    if not raw:
        return None
    direct = Path(raw).expanduser()
    if direct.is_dir():
        return TabProject(direct.name, direct.resolve())
    root = root or aether_root()
    child = root / raw
    if child.is_dir():
        return TabProject(child.name, child.resolve())
    store = load_json(PROJECTS_FILE)
    for entry in store.get("manual") or []:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "")
        path = Path(str(entry.get("path") or ""))
        if path.is_dir() and (label.lower() == raw.lower() or path.name.lower() == raw.lower()):
            return TabProject(label or path.name, path.resolve(), pinned=True)
    return None


def list_fleet(root: Path | None = None) -> list[TabProject]:
    root = root or aether_root()
    store = load_json(PROJECTS_FILE)
    tabs = load_json(TABS_FILE)
    out: list[TabProject] = []
    seen: set[str] = set()

    def add(proj: TabProject) -> None:
        key = _norm(proj.path)
        if key in seen or not proj.path.is_dir():
            return
        seen.add(key)
        out.append(proj)

    for raw in tabs.get("fleet") or []:
        found = resolve_project(str(raw), root)
        if found:
            add(TabProject(found.name, found.path, pinned=True))

    for raw in store.get("pinned") or []:
        found = resolve_project(str(raw), root)
        if found:
            add(TabProject(found.name, found.path, pinned=True))

    for entry in store.get("manual") or []:
        if isinstance(entry, dict) and entry.get("path"):
            found = resolve_project(str(entry["path"]), root)
            if found:
                add(found)

    if not out:
        add(TabProject(root.name, root.resolve(), pinned=True))
    return out


def pin_project(name_or_path: str) -> TabProject:
    found = resolve_project(name_or_path)
    if not found:
        raise ValueError(f"not a project folder: {name_or_path}")
    WATERFALL_HOME.mkdir(parents=True, exist_ok=True)
    store = load_json(PROJECTS_FILE)
    pinned = [str(p) for p in store.get("pinned") or []]
    path = str(found.path)
    if not any(_norm(p) == _norm(path) for p in pinned):
        pinned.append(path)
    store["pinned"] = pinned
    store.setdefault("archived", [])
    store.setdefault("manual", [])
    store.setdefault("last_prompt", {})
    store.setdefault("order", [])
    store.setdefault("sort_mode", store.get("sort_mode") or "")
    PROJECTS_FILE.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    return TabProject(found.name, found.path, pinned=True)


def agent_argv(agent: str, cwd: Path) -> list[str]:
    if agent not in AGENTS:
        raise ValueError(f"unknown agent {agent!r}; choose one of {', '.join(AGENTS)}")
    exe = shutil.which(agent)
    if not exe:
        raise ValueError(f"{agent} is not on PATH")
    if agent == "grok":
        return [exe, "--cwd", str(cwd)]
    return [exe]


def build_wt_command(projects: Iterable[TabProject], agent: str, new_window: bool) -> list[str]:
    rows = list(projects)
    if not rows:
        raise ValueError("no projects to open")
    window = ["-w", "new"] if new_window else ["-w", "0"]
    cmd: list[str] = ["wt", *window]
    for i, proj in enumerate(rows):
        if i:
            cmd.append(";")
        cmd.extend(["nt", "--title", proj.name, "-d", str(proj.path), *agent_argv(agent, proj.path)])
    return cmd


def build_wezterm_commands(projects: Iterable[TabProject], agent: str) -> list[list[str]]:
    cmds: list[list[str]] = []
    for proj in projects:
        argv = agent_argv(agent, proj.path)
        cmds.append(
            [
                "wezterm",
                "cli",
                "spawn",
                "--cwd",
                str(proj.path),
                "--",
                *argv,
            ]
        )
    return cmds


def build_tmux_command(projects: Iterable[TabProject], agent: str, session: str = "waterfall") -> list[str]:
    rows = list(projects)
    if not rows:
        raise ValueError("no projects to open")
    first = rows[0]
    argv = agent_argv(agent, first.path)
    # tmux new-session is one process; extra windows appended by the caller.
    return ["tmux", "new-session", "-A", "-s", session, "-c", str(first.path), *argv]


def launch(cmd: list[str], dry_run: bool = False) -> int:
    printable = subprocess.list2cmdline(cmd)
    if dry_run:
        print(printable)
        return 0
    try:
        subprocess.Popen(cmd)
    except OSError as exc:
        print(f"failed to launch: {exc}", flush=True)
        return 1
    print(printable)
    return 0
