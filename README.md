# waterfall.sh

Cascade to the best model. Automatically.

Classifies every prompt, routes the routine part to the cheapest capable
model on OpenRouter's live Arena-ranked catalog, and only surfaces the
genuinely hard part for Claude. Built to make a Claude Code / Claude Pro
plan's quota last the full day instead of the first hour.

## Layout

```
DESIGN.md, brand/                                   Design system + logo (SVG/PNG/ICO)
index.html, vercel.json, robots.txt, sitemap.xml   Landing page (static, zero build)
workshop/                                           Free model, IDE, skill, and MCP catalog
router/                                             The actual routing logic (Python)
  openrouter_api_client.py                          Direct OpenRouter API client
  smart_router.py                                   Classify -> split -> route -> stitch
  classifier/                                        Local, zero-API prompt classifier
  tests/                                              Unit tests (no network required)
desktop/                                            Local desktop GUI (dashboard + cascade + agent launcher)
DESKTOP_GUI_LANDSCAPE.md                            OSS research for coding-agent desktop UIs
CLAUDE.md                                           Full project handoff / status -- read this first
```

## Free developer workshop

[`workshop/`](workshop/) is the public, dated catalog of models, coding
surfaces, skills, and MCP servers that survived a real usage audit. It includes
three sanitized starter skills and a machine-readable `catalog.json`.

The curation rule is simple: every pick names a job, evidence, a reason not to
use it, an official source, and a checked date. Third-party work is linked
upstream instead of copied when licensing is unclear. Private paths,
credentials, account data, and personal automations are never published.

For a Claude plus Codex setup, use both during the week: one owns the change,
the other plans or reviews. Do not wait for one plan to hit zero before moving a
cold project into the other.

## Quick start (landing page)

```bash
npx vercel deploy        # ships to a *.vercel.app URL
npx vercel --prod        # once waterfall.sh is purchased and attached
```

## Quick start (router)

```bash
cd router
pip install -r requirements.txt   # just `requests`
export OPENROUTER_API_KEY=sk-or-...   # get one at https://openrouter.ai/keys
python3 -m unittest discover -s tests -p "test_*.py"

python3 cli.py classify "your prompt here"     # free, no network
python3 cli.py route "your prompt here"        # routes + logs to the savings ledger
python3 cli.py stats                           # what's been kept off Claude so far
python3 cli.py desktop                         # local GUI (browser on 127.0.0.1:8765)
```

Or install it as a command (`pip install -e .` from the repo root, then
`waterfall classify/route/stats/models/desktop ...`).

### Desktop GUI (`watertop`)

After install, one word (works in **Git Bash**, PowerShell, and cmd):

```bash
watertop
```

That opens the local command center (native window if `pywebview` is
installed, otherwise your browser on `127.0.0.1:8765`).

If bash says `command not found`, your install only had `.cmd` shims.
Re-run from the repo:

```bash
python install.py
# or just refresh shims:
python -c "import install; install.install_command_shims()"
hash -r
watertop
```

```bash
watertop --browser             # force system browser
watertop --port 9000           # custom port
watertop --no-open             # server only
# same thing, longer form:
waterfall desktop
```

Tabs: **Dashboard** (savings + hooks), **Cascade** (classify / dry-run / live route),
**Agents** (detect + launch Claude Code, Codex, Grok Build, OpenCode, …).

Optional native chrome: `pip install -e ".[desktop]"` then `watertop` uses
pywebview automatically.

Learned from open-source agent desktops (AionUi, opcode, OpenCode, Palot)
without forking them. See `DESKTOP_GUI_LANDSCAPE.md`.

**Claude/Codex-class agent desktops** are installed separately as peers
(CC Switch, AionUi, OpenCode Desktop, OpenChamber). `watertop` is cascade
+ quota only. See `PEERS_INSTALLED.md` for versions, paths, and the daily
stack map.

### Native `waterfall.exe` (Tauri)

Real Windows desktop app (not a browser tab), pattern-merged from peer
shells:

```text
dist/waterfall.exe
desktop-app/src-tauri/target/release/waterfall.exe
# installer:
desktop-app/src-tauri/target/release/bundle/nsis/waterfall_0.1.0_x64-setup.exe
```

Double-click `dist/waterfall.exe`, or from Git Bash:

```bash
waterfall-app
# rebuild:
cd desktop-app && npm run build
```

See `desktop-app/README.md` for lineage (Tauri template + CC Switch /
AionUi / OpenChamber patterns).

`route` auto-falls back through the next-cheapest OpenRouter model if the
cheapest one is down or rate-limited, that's the "cascade" the name
refers to, not just a single cheapest-model pick.

See `CLAUDE.md` for full status, what's built, and what's still open.
See `SETUP.md` to also wire up the automatic hooks (nudge + hard cap)
on another machine, needed before any real savings numbers can be
measured across more than one user.
