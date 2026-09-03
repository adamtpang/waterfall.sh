# waterfall.sh

Cascade to the best model. Automatically.

Classifies every prompt, routes the routine part to the cheapest capable
model on OpenRouter's live Arena-ranked catalog, and only surfaces the
genuinely hard part for Claude. Built to make a Claude Code / Claude Pro
plan's quota last the full day instead of the first hour.

## Layout

```
DESIGN.md, brand/                                   Design system + logo (SVG/PNG/ICO)
index.html, site.css, vercel.json                  Landing page (static, zero build)
leaderboard.html, leaderboard.css/js               Public bang-for-buck table
api/leaderboard.json, api/leaderboard.csv           Generated read-only feeds
config/routing.yaml                                 Versioned coding tiers, models, and promotion rules
data/                                               Dated snapshot, smoke suite, and local run records
about.html, contact.html, privacy.html, llms.txt   Public trust + agent guidance pages
robots.txt, sitemap.xml                            Crawler policy + route index
workshop/                                          Free model, IDE, skill, and MCP catalog
router/                                             The actual routing logic (Python)
  openrouter_api_client.py                          Direct OpenRouter API client
  smart_router.py                                   Classify -> split -> route -> stitch
  tool_inventory.py                                 Private names-only skill and MCP audit
  classifier/                                        Local, zero-API prompt classifier
  tests/                                              Unit tests (no network required)
desktop/                                            Local desktop GUI (dashboard + cascade + agent launcher)
DESKTOP_GUI_LANDSCAPE.md                            OSS research for coding-agent desktop UIs
CLAUDE.md                                           Full project handoff / status -- read this first
```

## Free developer workshop

[`workshop/`](workshop/) is the public, dated ranking of models, coding
surfaces, skills, and MCP servers that survived a real usage audit. It includes
three sanitized starter skills, six quiz-driven developer classes, and
machine-readable `catalog.json` and `packs.json` sources.

The curation rule is simple: every pick names a job, evidence, a reason not to
use it, an official source, and a checked date. Third-party work is linked
upstream instead of copied when licensing is unclear. Private paths,
credentials, account data, and personal automations are never published.

For a Claude plus Codex setup, use both during the week: one owns the change,
the other plans or reviews. Do not wait for one plan to hit zero before moving a
cold project into the other.

Generate a private local inventory without exposing commands, credentials, URLs,
or project paths:

```bash
python -m router.tool_inventory --output local-skill-mcp-inventory.md
```

## Quick start (landing page)

```bash
npx vercel deploy        # ships to a *.vercel.app URL
npx vercel --prod        # deploys production and updates https://waterfall.sh
```

## Quick start (router)

```bash
cd router
pip install -r requirements.txt   # requests + PyYAML
export OPENROUTER_API_KEY=sk-or-...   # get one at https://openrouter.ai/keys
python3 -m unittest discover -s tests -p "test_*.py"

python3 cli.py classify "your prompt here"     # JSON tier decision, no network
python3 cli.py run "fix the flaky auth test"   # author, review, promote on blocking failure
python3 cli.py why                              # inspect the last run and every promotion
python3 cli.py leaderboard                      # print value per solved-task dollar
python3 cli.py route "your prompt here"        # routes + logs to the savings ledger
python3 cli.py stats                           # what's been kept off Claude so far
python3 cli.py desktop                         # local GUI (browser on 127.0.0.1:8765)
```

Or install it as a command (`pip install -e .` from the repo root, then
`waterfall classify/run/why/leaderboard/bench/route/stats/models/desktop ...`).

Run the complete 15-task harness when you intend to spend provider credits:

```bash
waterfall bench --suite coding-smoketest --models grok-4.6,glm-5.3,opus-5,fable-5.1
waterfall leaderboard --publish
```

Use `--dry-run` to inspect the benchmark matrix without contacting a model or writing JSONL.

## Routing policy

1. Peak coding quality is not the same thing as the best dollars per solved task.
2. The versioned policy lives in [`config/routing.yaml`](config/routing.yaml), not scattered conditionals.
3. A Flash-class candidate classifies hardness, language, repository span, and tool need.
4. Draft work starts on DeepSeek V4 Flash, MiniMax M3, or GLM-5.3-Flash.
5. Normal implementation starts on Grok 4.6 or GLM-5.3, with Kimi K3 preferred for frontend work.
6. Repository-spanning work starts at the harden tier on Opus 5 or a GPT-5.6 peer.
7. Fable 5.1 is the quality ceiling, never the ordinary starting model.
8. Fable may start only for an explicit escalation, a can't-be-wrong request, or qualifying high-risk history.
9. The author never reviews its own patch with the same model and tier.
10. Tests, concrete blocking rejects, stuck authors, empty diffs, repo reverts, or user escalation can promote.
11. Style, verbosity, missing comments, elegance, and requests for a smarter model cannot promote.
12. A task gets at most two promotions unless the user passes `--no-cap`.
13. Fable uses adaptive thinking steered by effort; Waterfall never sends `thinking.disabled`.
14. `waterfall why` keeps the route, attempts, costs, skips, and promotion reasons inspectable.
15. [`/leaderboard`](https://waterfall.sh/leaderboard) ranks the dated snapshot and harness rows by quality per solved-task dollar.

## Testing

Run both suites from the repository root. The Python suite covers the router and
deployment contract; the Node 18+ suites execute the catalog and starter-pack interactions.

```bash
python3 -m unittest discover -s router/tests -p "test_*.py"
node --test router/tests/workshop.test.mjs router/tests/starter-packs.test.mjs router/tests/leaderboard.test.mjs
```

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
