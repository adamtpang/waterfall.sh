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


def user_bin_dir() -> Path:
    return Path.home() / "bin"


def _write_shim(name: str, python_module: str) -> Path:
    """Write launchers in ~/bin so `watertop` / `waterfall` work even when
    pip's Scripts directory is not on PATH.

    On Windows we write BOTH:
      - name.cmd  for PowerShell / cmd
      - name      (bash script, no extension) for Git Bash / MSYS
    Git Bash does not run bare `watertop` against watertop.cmd — it needs
    an extensionless executable on PATH.
    """
    bin_dir = user_bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    # Git Bash wants POSIX-ish paths inside the script body
    py_posix = py.replace("\\", "/")

    written: list[Path] = []
    if sys.platform == "win32":
        cmd_path = bin_dir / f"{name}.cmd"
        cmd_path.write_text(
            "@echo off\r\n"
            f'"{py}" -m {python_module} %*\r\n',
            encoding="utf-8",
        )
        written.append(cmd_path)

    # Extensionless bash shim (Git Bash, macOS, Linux, WSL)
    bash_path = bin_dir / name
    bash_path.write_text(
        "#!/usr/bin/env bash\n"
        f"# waterfall.sh — {name}\n"
        f'exec "{py_posix}" -m {python_module} "$@"\n',
        encoding="utf-8",
        newline="\n",  # critical: LF only so Git Bash can exec it
    )
    try:
        bash_path.chmod(bash_path.stat().st_mode | 0o111)
    except OSError:
        pass
    written.append(bash_path)
    return written[0]


def ensure_user_bin_on_path() -> bool:
    """Add ~/bin to the user PATH if missing. Returns True if a new shell
    is needed for PATH to take effect."""
    bin_dir = str(user_bin_dir())
    if shutil.which("watertop") is not None:
        return False

    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Environment",
                0,
                winreg.KEY_READ | winreg.KEY_SET_VALUE,
            )
            try:
                current, _ = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current = ""
            parts = [p for p in current.split(";") if p]
            if any(p.lower().rstrip("\\") == bin_dir.lower().rstrip("\\") for p in parts):
                winreg.CloseKey(key)
                return True  # already on user PATH; shell just hasn't picked it up
            new_path = f"{bin_dir};{current}" if current else bin_dir
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            winreg.CloseKey(key)
            # Broadcast PATH change so new processes can see it (best-effort)
            try:
                import ctypes

                ctypes.windll.user32.SendMessageTimeoutW(  # type: ignore[attr-defined]
                    0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None
                )
            except Exception:
                pass
            return True
        except OSError as exc:
            print(f"Could not update user PATH automatically: {exc}", file=sys.stderr)
            print(f"Add this folder to PATH manually: {bin_dir}")
            return True

    # Unix: append to ~/.profile if not present
    profile = Path.home() / ".profile"
    export_line = f'export PATH="{bin_dir}:$PATH"'
    existing = profile.read_text(encoding="utf-8") if profile.is_file() else ""
    if bin_dir not in existing:
        with profile.open("a", encoding="utf-8") as f:
            f.write(f"\n# waterfall.sh\n{export_line}\n")
        print(f"Added {bin_dir} to PATH in {profile}")
    return True


def install_command_shims() -> None:
    """Make `watertop` and `waterfall` one-word commands via ~/bin shims."""
    _write_shim("waterfall", "router.cli")
    _write_shim("watertop", "desktop.watertop")
    bin_dir = user_bin_dir()
    print(f"Wrote shims in {bin_dir}:")
    for name in ("waterfall", "watertop"):
        for p in sorted(bin_dir.glob(f"{name}*")):
            print(f"  {p}")
    needs_new_shell = ensure_user_bin_on_path()
    if needs_new_shell and shutil.which("watertop") is None:
        print(
            "\nOpen a **new terminal**, then:\n"
            "  watertop\n"
            f"Or run now:\n  {bin_dir / 'watertop'}\n"
            f"  {bin_dir / 'watertop.cmd'}   (PowerShell/cmd)"
        )


def check_waterfall_on_path() -> None:
    """Confirm one-word commands resolve; install ~/bin shims if not."""
    has_waterfall = shutil.which("waterfall") is not None
    has_watertop = shutil.which("watertop") is not None
    if has_waterfall and has_watertop:
        print("`waterfall` and `watertop` are on PATH and ready to use.")
        print("  waterfall  - classify / route / stats CLI")
        print("  watertop   - desktop GUI (one word)")
        return

    print("Installing ~/bin shims so one-word commands work...")
    install_command_shims()
    has_waterfall = shutil.which("waterfall") is not None
    has_watertop = shutil.which("watertop") is not None
    if has_waterfall and has_watertop:
        print("`waterfall` and `watertop` are on PATH and ready to use.")
        print("  watertop   - desktop GUI")
        return
    print(
        "Shims written. If `watertop` still isn't found in this shell, open a "
        "new terminal (PATH updates often need that on Windows)."
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
    try:
        sys.path.insert(0, str(repo_dir / "router"))
        import pin_app
        pin_app.pin()
    except Exception:
        pass
    print(
        "\nDone.\n"
        "\n  waterfall license paid   # after the $30 Stripe checkout\n"
        "  waterfall remote open    # local board, project rail, cascade\n"
        "  waterfall classify ...   # cheapest capable model for the job\n"
        "  watertop                 # older desktop shell\n"
    )
    print(
        "\nKnown limits, stated plainly:\n"
        "  - No signed installer yet. This script is the real download, on every OS.\n"
        "  - The native desktop board (waterfall.exe, NSIS/MSI) is a Windows-only local\n"
        "    build today, not a published release -- build it yourself:\n"
        "    cd desktop-app && npm run tauri build\n"
        "  - That desktop board hasn't been packaged for macOS or Linux yet.\n"
        "    watertop (this install) is the real cross-platform board until it is.\n"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as e:
        _fail(f"command failed: {' '.join(e.cmd)}")
    except KeyboardInterrupt:
        _fail("interrupted")
