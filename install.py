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


def install_package(repo_dir: Path) -> None:
    """Installs waterfall as an editable package, not just its one
    dependency -- this is what actually registers the `waterfall` console
    command (pyproject.toml's [project.scripts] entry), so `waterfall` on
    its own works after this instead of only `python3 router/cli.py ...`."""
    print("Installing waterfall ...")
    _run([sys.executable, "-m", "pip", "install", "-q", "-e", str(repo_dir)])


def check_waterfall_on_path() -> None:
    """pip installs the console script into Python's user-scripts
    directory, which isn't always on PATH (a known issue on Windows in
    particular). Report the truth instead of silently leaving `waterfall`
    broken with no explanation."""
    if shutil.which("waterfall") is not None:
        print("`waterfall` is on PATH and ready to use.")
        return
    print(
        "\nNOTE: `waterfall` installed but isn't on PATH yet, so the bare "
        "command won't resolve in a new terminal.\n"
        "This is a real, known issue, not a bug in this installer -- pip "
        "puts console scripts in a user-scripts directory that many "
        "systems don't add to PATH automatically.\n"
        "Until that's fixed, invoke it by full path instead:\n"
        f'  python3 "{(INSTALL_DIR / "router" / "cli.py").as_posix()}" ...'
    )


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
    install_package(repo_dir)
    wire_hooks(repo_dir)
    check_waterfall_on_path()
    print(
        "\nDone. Start a new Claude Code session for the hooks to take effect.\n"
        "\nAfter a few days of normal use, run `waterfall` on its own to see "
        "the dashboard (or the full path shown above if it's not on PATH yet)."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        _fail(f"command failed: {' '.join(e.cmd)}")
    except KeyboardInterrupt:
        _fail("interrupted")
