"""waterfall.sh one-line installer.

    curl -sSL https://raw.githubusercontent.com/adamtpang/waterfall.sh/main/install.py | python3

Stdlib only -- this has to run *before* anything from requirements.txt is
available. Clones (or updates) the repo into ~/.waterfall, installs the
one real dependency, and wires the two hooks (nudge + Ringer) into your
global ~/.claude/settings.json -- merging into whatever's already there,
never overwriting it. Safe to re-run: idempotent on both the clone and
the hook entries, and always backs up settings.json before touching it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_URL = "https://github.com/adamtpang/waterfall.sh"
INSTALL_DIR = Path.home() / ".waterfall"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kwargs)


def _fail(message: str) -> None:
    print(f"waterfall install FAILED: {message}", file=sys.stderr)
    sys.exit(1)


def clone_or_update() -> Path:
    if shutil.which("git") is None:
        _fail("git is required (used to fetch and update the repo) but isn't on PATH.")

    if (INSTALL_DIR / ".git").is_dir():
        print(f"Updating existing install at {INSTALL_DIR} ...")
        _run(["git", "pull", "--ff-only"], cwd=INSTALL_DIR)
    else:
        print(f"Cloning {REPO_URL} into {INSTALL_DIR} ...")
        _run(["git", "clone", REPO_URL, str(INSTALL_DIR)])
    return INSTALL_DIR


def install_dependencies(repo_dir: Path) -> None:
    print("Installing dependencies ...")
    _run([sys.executable, "-m", "pip", "install", "-q", "-r", str(repo_dir / "router" / "requirements.txt")])


def _hook_entry(script_path: Path, matcher: str | None = None) -> dict:
    entry = {
        "hooks": [
            {
                "type": "command",
                "command": f'python3 "{script_path.as_posix()}"',
                "timeout": 10,
            }
        ]
    }
    if matcher:
        entry["matcher"] = matcher
    return entry


def _entry_already_present(existing: list[dict], script_path: Path) -> bool:
    needle = script_path.as_posix()
    for entry in existing:
        for h in entry.get("hooks", []):
            if needle in h.get("command", ""):
                return True
    return False


def wire_hooks(repo_dir: Path) -> None:
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)

    if CLAUDE_SETTINGS.exists():
        backup = CLAUDE_SETTINGS.with_name(
            f"settings.json.bak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        shutil.copy2(CLAUDE_SETTINGS, backup)
        print(f"Backed up existing settings to {backup}")
        try:
            settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            _fail(f"{CLAUDE_SETTINGS} exists but isn't valid JSON -- fix or remove it, then re-run.")
    else:
        settings = {}

    settings.setdefault("hooks", {})
    nudge_script = repo_dir / "router" / "hooks" / "user_prompt_submit.py"
    ringer_script = repo_dir / "router" / "hooks" / "pre_tool_use.py"

    settings["hooks"].setdefault("UserPromptSubmit", [])
    if not _entry_already_present(settings["hooks"]["UserPromptSubmit"], nudge_script):
        settings["hooks"]["UserPromptSubmit"].append(_hook_entry(nudge_script))
        print("Added the nudge hook (UserPromptSubmit).")
    else:
        print("Nudge hook already present -- left as-is.")

    settings["hooks"].setdefault("PreToolUse", [])
    if not _entry_already_present(settings["hooks"]["PreToolUse"], ringer_script):
        settings["hooks"]["PreToolUse"].append(_hook_entry(ringer_script, matcher="Read|Bash|PowerShell"))
        print("Added the Ringer hook (PreToolUse).")
    else:
        print("Ringer hook already present -- left as-is.")

    CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def main() -> int:
    print("waterfall.sh installer\n")
    repo_dir = clone_or_update()
    install_dependencies(repo_dir)
    wire_hooks(repo_dir)
    print(
        "\nDone. Start a new Claude Code session for the hooks to take effect.\n"
        "\nAfter a few days of normal use, report back with:\n"
        f'  python3 "{(repo_dir / "router" / "cli.py").as_posix()}" hook-log --since-days 5\n'
        f'  python3 "{(repo_dir / "router" / "cli.py").as_posix()}" stats'
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        _fail(f"command failed: {' '.join(e.cmd)}")
    except KeyboardInterrupt:
        _fail("interrupted")
