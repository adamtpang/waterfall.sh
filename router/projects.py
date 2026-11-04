"""Aether project catalog for the CLI picker and waterfall board sidebar."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import tabs

SKIP_NAMES = {
    "node_modules",
    "archive",
    "Spawn",
    "site",
    "site-studies",
    "lovable-export",
    "tools",
    "desktop-app",
    "desktop",
    "router",
    "dist",
}

SKIP_PREFIXES = (".", "check-", "summon-", "_")

@dataclass(frozen=True)
class Project:
    name: str
    path: str
    pinned: bool
    source: str

    def as_dict(self) -> dict:
        return asdict(self)


def _is_project_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    name = path.name
    if name in SKIP_NAMES:
        return False
    if name.startswith(SKIP_PREFIXES):
        return False
    return any(
        (path / marker).exists()
        for marker in (
            "GROK_CONTINUE_FROM_CLAUDE.md",
            "GROK_CONTINUE_FROM_CODEX.md",
            "CLAUDE.md",
            "AGENTS.md",
            "package.json",
            "pyproject.toml",
            ".git",
        )
    )


def list_projects(root: Path | None = None) -> list[Project]:
    root = root or tabs.aether_root()
    out: list[Project] = []
    seen: set[str] = set()

    def add(name: str, path: Path, pinned: bool, source: str) -> None:
        key = tabs._norm(path)
        if key in seen or not path.is_dir():
            return
        seen.add(key)
        out.append(Project(name=name, path=str(path.resolve()), pinned=pinned, source=source))

    for item in tabs.list_fleet(root):
        add(item.name, item.path, True, "pinned")

    if root.is_dir():
        add(root.name, root, True, "pinned")
        for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if _is_project_dir(child):
                add(child.name, child, False, "aether")

    out.sort(key=lambda p: (not p.pinned, p.name.lower()))
    return out
