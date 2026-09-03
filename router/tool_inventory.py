"""Build a private, names-only inventory of local agent skills and MCP servers.

The report deliberately omits commands, arguments, URLs, headers, environment
values, credentials, and project paths. It is intended for local audits, not for
publication as a machine configuration dump.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


_NAME_RE = re.compile(r"^name:\s*[\"']?([^\n\"']+)", re.MULTILINE)
_UNSAFE_LABEL_RE = re.compile(
    r"(?:https?://|[A-Za-z]:[\\/]|(?:^|[\\/])(?:Users|home)[\\/])",
    re.IGNORECASE,
)
_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "env",
    "headers",
    "password",
    "secret",
    "token",
}
_MCP_KEYS = {"mcp", "mcp_servers", "mcpservers"}


@dataclass(frozen=True)
class SkillRecord:
    name: str
    surface: str
    digest: str


@dataclass(frozen=True)
class McpRecord:
    name: str
    host: str
    enabled: bool


def _skill_name(path: Path, text: str) -> str:
    match = _NAME_RE.search(text[:12_000])
    return match.group(1).strip() if match else path.parent.name


def _markdown_label(value: str) -> str:
    compact = " ".join(value.split())
    if not compact:
        return "[unnamed]"
    if _UNSAFE_LABEL_RE.search(compact):
        return "[redacted unsafe name]"
    return compact.replace("|", r"\|")


def _skill_records(root: Path, surface: str, *, top_level_only: bool = False) -> list[SkillRecord]:
    if not root.is_dir():
        return []
    records = []
    for path in root.rglob("SKILL.md"):
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] == ".backups":
            continue
        if top_level_only and len(relative.parts) != 2:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        records.append(
            SkillRecord(
                name=_skill_name(path, text),
                surface=surface,
                digest=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return records


def discover_skills(home: Path) -> list[SkillRecord]:
    """Return skills visible to the user's main agent surfaces.

    Claude's top-level skill directories are included, while nested repository
    internals are excluded. Agent and Codex roots are recursive because they
    intentionally contain grouped skills such as gstack.
    """

    return [
        *_skill_records(home / ".agents" / "skills", "shared agent skills"),
        *_skill_records(home / ".codex" / "skills", "Codex skills"),
        *_skill_records(home / ".claude" / "skills", "Claude skills", top_level_only=True),
        *_skill_records(home / ".codex" / "plugins" / "cache", "Codex plugin skills"),
    ]


def _mcp_sections(value: Any) -> Iterable[tuple[str, bool]]:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if lowered in _SENSITIVE_KEYS:
                continue
            if lowered in _MCP_KEYS and isinstance(child, dict):
                for name, config in child.items():
                    if isinstance(config, dict):
                        yield str(name), bool(config.get("enabled", True))
                continue
            yield from _mcp_sections(child)
    elif isinstance(value, list):
        for child in value:
            yield from _mcp_sections(child)


def _load_config(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".toml":
        return tomllib.loads(text)
    return json.loads(text)


def discover_mcp_servers(home: Path) -> list[McpRecord]:
    configs = {
        "Codex": home / ".codex" / "config.toml",
        "Claude": home / ".claude.json",
        "Claude Desktop": home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json",
        "Cursor": home / ".cursor" / "mcp.json",
        "OpenCode": home / ".config" / "opencode" / "opencode.json",
        "Gemini": home / ".gemini" / "settings.json",
        "Gemini IDE": home / ".gemini" / "antigravity-ide" / "mcp_config.json",
        "Gemini config": home / ".gemini" / "config" / "mcp_config.json",
    }
    records = []
    for host, path in configs.items():
        if not path.is_file():
            continue
        try:
            data = _load_config(path)
        except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError):
            continue
        records.extend(McpRecord(name=name, host=host, enabled=enabled) for name, enabled in _mcp_sections(data))
    return records


def discover_codex_plugins(home: Path) -> list[str]:
    root = home / ".codex" / "plugins" / "cache" / "openai-curated-remote"
    if not root.is_dir():
        return []
    return sorted(
        path.parent.name
        for path in root.glob("*/.codex-remote-plugin-install.json")
        if path.is_file()
    )


def render_markdown(
    skills: list[SkillRecord],
    mcps: list[McpRecord],
    plugins: list[str],
    *,
    checked_at: str | None = None,
) -> str:
    checked_at = checked_at or dt.date.today().isoformat()
    by_skill: dict[str, list[SkillRecord]] = defaultdict(list)
    for record in skills:
        by_skill[record.name].append(record)
    by_mcp: dict[str, list[McpRecord]] = defaultdict(list)
    for record in mcps:
        by_mcp[record.name.casefold()].append(record)

    duplicate_names = sum(len(records) > 1 for records in by_skill.values())
    divergent_names = sum(
        len(records) > 1 and len({record.digest for record in records}) > 1
        for records in by_skill.values()
    )

    lines = [
        "# Local skill and MCP inventory",
        "",
        f"Checked: {checked_at}",
        "",
        "This is a private names-only report. Commands, arguments, URLs, headers,",
        "environment values, credentials, and project paths are deliberately omitted.",
        "",
        "## Summary",
        "",
        f"- Active-surface skill files: {len(skills)}",
        f"- Unique skill names: {len(by_skill)}",
        f"- Names with multiple copies: {duplicate_names}",
        f"- Duplicated names with different contents: {divergent_names}",
        f"- MCP configuration entries across hosts: {len(mcps)}",
        f"- Unique MCP names: {len(by_mcp)}",
        f"- Installed Codex remote plugins: {len(plugins)}",
        "",
        "## All skills",
        "",
        "| Skill | Surfaces | Copies | Drift |",
        "| --- | --- | ---: | --- |",
    ]
    for name in sorted(by_skill, key=str.casefold):
        records = by_skill[name]
        surfaces = ", ".join(sorted({record.surface for record in records}))
        drift = "yes" if len({record.digest for record in records}) > 1 else "no"
        lines.append(f"| {_markdown_label(name)} | {surfaces} | {len(records)} | {drift} |")

    lines.extend(
        [
            "",
            "## All configured MCP servers",
            "",
            "| MCP name | Hosts | Enabled anywhere | Entries |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for folded_name in sorted(by_mcp):
        records = by_mcp[folded_name]
        display_name = sorted({record.name for record in records}, key=str.casefold)[0]
        hosts = ", ".join(sorted({record.host for record in records}))
        enabled = "yes" if any(record.enabled for record in records) else "no"
        lines.append(f"| {_markdown_label(display_name)} | {hosts} | {enabled} | {len(records)} |")

    lines.extend(
        [
            "",
            "## Installed Codex remote plugins",
            "",
            *[f"- {_markdown_label(name)}" for name in plugins],
            "",
            "## Interpretation",
            "",
            "A duplicate name is not automatically a problem. Drift means copies with the",
            "same declared skill name no longer have identical contents, so host behavior may",
            "differ. Review those copies before deleting or synchronizing anything.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--checked-at")
    args = parser.parse_args(argv)

    report = render_markdown(
        discover_skills(args.home),
        discover_mcp_servers(args.home),
        discover_codex_plugins(args.home),
        checked_at=args.checked_at,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
