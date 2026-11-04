"""Write a Desktop + Start Menu shortcut to the local waterfall board."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BOARD_URL = "http://127.0.0.1:7910"


def _icon() -> Path:
    root = Path(__file__).resolve().parent.parent
    ico = root / "brand" / "logo.ico"
    return ico if ico.is_file() else root / "brand" / "favicon.svg"


def _helium() -> Path | None:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local / "imput" / "Helium" / "Application" / "chrome.exe",
        local / "imput" / "Helium" / "chrome.exe",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _write_url(path: Path, icon: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[InternetShortcut]\n"
        f"URL={BOARD_URL}\n"
        f"IconFile={icon}\n"
        "IconIndex=0\n",
        encoding="utf-8",
    )


def pin() -> dict:
    icon = _icon()
    desktop = Path.home() / "Desktop"
    start = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    written: list[str] = []
    if desktop.is_dir():
        dest = desktop / "waterfall.url"
        _write_url(dest, icon)
        written.append(str(dest))
    start.mkdir(parents=True, exist_ok=True)
    dest = start / "waterfall.url"
    _write_url(dest, icon)
    written.append(str(dest))
    return {"ok": True, "written": written, "url": BOARD_URL, "helium": str(_helium() or "")}


def open_app_window() -> bool:
    helium = _helium()
    if helium:
        subprocess.Popen(
            [str(helium), f"--app={BOARD_URL}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "", BOARD_URL], shell=False)
        return True
    return False
