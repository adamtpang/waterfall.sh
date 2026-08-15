"""watertop — one-word launcher for the waterfall desktop GUI.

    watertop
    watertop --port 9000
    watertop --browser          # force system browser (skip pywebview)
    watertop --no-open          # server only

Defaults: open a native window when pywebview is installed, otherwise the
system browser. Same server as `waterfall desktop`.
"""

from __future__ import annotations

import sys
from typing import Optional


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    # Friendly help without pulling argparse until needed
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0

    force_browser = "--browser" in args
    if force_browser:
        args = [a for a in args if a != "--browser"]

    # Prefer native glass when available (unless --browser or already --native)
    if not force_browser and "--native" not in args and "--no-open" not in args:
        try:
            import webview  # noqa: F401

            args = ["--native", *args]
        except ImportError:
            pass

    from desktop.server import main as desktop_main

    return desktop_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
