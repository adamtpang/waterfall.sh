# CLAUDE.md - waterfall.sh

Context for Claude Code, Codex, and humans working in this folder. This is
the live handoff: the source of truth for current progress, decisions,
and open tasks. Update it as things change so future sessions (and other
agents) stay in sync.

## What this is

waterfall.sh is a dev tool: it classifies a prompt, routes the routine
part to the cheapest capable model on OpenRouter's live Arena-ranked
catalog, and only surfaces the genuinely hard part for Claude, so a
Claude Code / Claude Pro plan's quota goes further. Born out of a Cowork
session extending the (unrelated, Windows-only) `Claude-Token-Saver` repo
at github.com/awesomo913/Claude-Token-Saver, then pulled out into its own
project once the naming/branding direction was clear.

## Current state (as of this handoff)

- **Domain**: https://waterfall.sh is live and aliased to the `waterfall.sh`
  Vercel project under team `adamtpangs-projects`, linked to
  github.com/adamtpang/waterfall.sh (auto-deploys on push to `main`). The
  older 2026-08-04 notes saying the custom domain was not yet live are stale.
- **Landing page**: `index.html`, shared `site.css`, static About/Contact/
  Privacy pages, `llms.txt`, `robots.txt`, and `sitemap.xml`: plain static
  files with zero application build step. **Needs `.vercelignore` to exclude
  the Python/router/desktop source and internal Markdown handoffs, and
  `"framework": null` in `vercel.json`** -- without both, Vercel
  auto-detects the sibling Python CLI (`pyproject.toml` at repo root) and
  tries to build this as a Python serverless app instead of a static site,
  which fails with "No python entrypoint found." Hit and fixed 2026-08-04;
  don't remove either fix. Visual style is intentionally reused from vercel.school
  (same dark chalkboard-style theme, mono/hand font pairing) for
  consistency across Adam's project portfolio. Swap the accent color /
  copy freely, the structure is just a starting point.
- **Lightmark production pass, 2026-08-29**: https://waterfall.sh scored
  exactly 100/A with all 11 scorecards at 100 and zero findings at
  `2026-08-29T06:31:01.325Z`. The pass added truthful Organization,
  WebSite, and SoftwareApplication JSON-LD; CSP and `nosniff`; explicit
  image dimensions; substantial trust pages; `/llms.txt`; a public
  GitHub/X contact path; and self-contained product copy. Feature cards no
  longer use `<article>`, because the landing page is product content, not
  editorial content requiring invented author/date provenance. Keep the
  root rewrite to `/index`: prebuilt Vercel deployments otherwise expose
  the clean `/index` asset but return 404 for `/`.
- **Developer workshop**: `workshop/` is the public, no-paywall resource hub
  for dated model, IDE, agent-skill, and MCP rankings. `catalog.json` is the
  machine-readable source; `index.html` renders it without a build step;
  `starter-packs.html` plus `packs.json` provide six quiz-driven developer
  classes and generate an approval-first setup prompt entirely in the browser;
  `AUDIT.md` records the public-safe audit; and three sanitized Waterfall-authored
  starter skills live under `workshop/skills/`. A 2026-09-03 rescan found 565
  active-surface skill files, 352 unique names, 183 duplicated names, 61 drifted
  duplicate names, 30 MCP configuration entries, 17 unique MCP names, and 21
  installed Codex remote plugins. The full names-only report stays private.
  `router/tool_inventory.py` can regenerate it while suppressing commands,
  arguments, URLs, headers, environment values, credentials, and project paths.
  Third-party material is linked upstream by default. Never publish raw configs,
  credentials, account identifiers, absolute paths, private project names, or
  personal-only skills. The root `llms.txt` makes the workshop agent-readable.
  The same review added GitHub's `mcp-security-audit` skill and Upstash Context7
  as pilot candidates, not automatic installs. A supplied three-skill content
  bundle was extracted locally but not installed or republished because it lacked
  a redistribution license, included private activity-memory files, imposed high
  context cost, and included secret-scanning or publishing behavior.
- **Router core**: `router/`: this is real, tested, working Python, not a
  stub:
  - `router/openrouter_api_client.py`: direct HTTP client for OpenRouter's
    API (model catalog fetch+cache, cheapest-capable-model auto-selection,
    chat completions with cost accounting). `generate_with_usage()` now
    **cascades through the N cheapest capable models**: if the cheapest
    one is down/rate-limited/errors out after its retries, it automatically
    tries the next-cheapest candidate before giving up (`pick_cheap_models(n)`
    supplies the ranked candidate list). This is the literal "auto falls
    back to the next best model" behavior the tool is named for. It only
    covered picking one model before 2026-08-04, no actual fallback chain.
  - `router/smart_router.py`: `SmartRouter.route_with_api()`: classify →
    split → send the easy part to OpenRouter → return what's left for
    Claude with the free model's output already stitched in.
  - `router/classifier/`: local, zero-API prompt classifier (pure
    stdlib) that decides free/split/claude routing and estimates the
    free/Claude token split.
  - `router/tracker.py`: `SavingsTracker`: append-only JSONL ledger at
    `~/.claude/token_savings.jsonl` (same pattern as the Claude-Token-Saver
    fork this was ported from) + `summarize()` for aggregate stats.
  - `router/tabs.py` + `waterfall tabs`: CLI project tabs. Does **not**
    nest Grok's TUI. Opens real Windows Terminal tabs (`wt`) with
    `grok --cwd <project>`. Fleet = pins in `~/.waterfall/projects.json`
    plus optional `~/.waterfall/tabs.json`. Flip with Ctrl+Tab.
  - `grok-remote/`: waterfall.sh board. ACP host started from Farina's
    grok-remote (MIT), branded and cataloged for Aether. Launch:
    `waterfall remote`. See `grok-remote/WINDOWS.md`.
  - `router/cli.py`: the CLI: `classify` / `route [--dry-run]` / `stats` /
    `models` / `tabs`. Runs bare (`python3 router/cli.py ...`) or as a package
    (`python3 -m router.cli ...` from repo root, or `waterfall ...` after
    `pip install -e .`, see `pyproject.toml`). `classify` and
    `route --dry-run` never touch the network.
  - **Model tiering**: `pick_cheap_models_by_tier("small"/"medium"/"large")`
    splits the price-sorted catalog into three bands; `tier_for_complexity()`
    maps the classifier's complexity score to a band. `route_with_api()`
    uses this by default (unless a model/tier is pinned) so a one-line
    rename and a borderline-Claude-worthy "split" task don't draw from the
    same model regardless of scope.
  - **Real bug caught against the live catalog**: `openrouter/auto` and
    `openrouter/auto-beta` report pricing as `"-1"` (a "varies by what it
    routes to internally" sentinel). `float("-1")` parses fine, so it sorted
    as cheapest-of-all and won every pick, silently defeating both
    cheapest-selection and tiering. Fixed by rejecting `prompt_price <= 0` in
    the shared `_priced_candidates()` filter (2026-08-04); has a regression
    test (`test_pick_cheap_model_skips_negative_sentinel_pricing`).
  - `router/hooks/user_prompt_submit.py`: a `UserPromptSubmit` command hook
    (project-scoped, wired in `.claude/settings.json`). Classifies every
    prompt submitted in this project (local, no network) and, when it looks
    routine, injects a one-line nudge via `hookSpecificOutput.additionalContext`
    suggesting the `waterfall` skill route the mechanical part instead of
    generating it inline. Never blocks, never raises -- any failure is a
    silent no-op. Needs `/hooks` (reload config) or a session restart to
    start firing, since `.claude/` didn't exist in this project when the
    hook was added.
  - `router/hooks/pre_tool_use.py`: a `PreToolUse` command hook
    (project-scoped, wired in `.claude/settings.json`, matcher
    `Read|Bash|PowerShell`). The "Ringer" from `TOKEN_COMPOUNDING.md`:
    hard-blocks (not nudges) a `Read` with no offset/limit, or a single
    output-heavy shell command (Bash `cat`/`less`/`more`/`xxd`/`hexdump`/
    `od`/`base64`; PowerShell `Get-Content`/`type`/`Format-Hex`) invoked
    against exactly one file with no pipe/redirect/`;`/`&&`, over
    `WATERFALL_RINGER_CAP_TOKENS` (default 8,000 est. tokens). Narrowed
    reads and piped/redirected/chained/multi-file shell commands are
    never capped -- deliberately, to keep false positives at zero.
    Known, documented gap: commands whose output size isn't tied to one
    file's on-disk size (`find`, `git log`, unbounded `grep`/`rg`,
    `curl`) can't be pre-sized without running them, so aren't covered.
    Fails open on any error/missing file/unparseable command. **Real bug
    caught in its own build** (2026-08-05): the command parser first
    used `shlex.split(cmd, posix=True)`, which treats backslash as an
    escape character -- on this all-Windows-paths machine that silently
    mangled every path (`C:\Users\...` lost its backslashes), corrupting
    the stat lookup and making the cap fail open on every single call,
    completely undetected until the test suite ran red. Fixed with
    `posix=False` plus manual quote-stripping; regression-tested. Live
    end-to-end (57KB scratch file, real `Bash` tool `cat`, real `Read`)
    on 2026-08-05 with no `/hooks` reload or restart needed --
    `.claude/settings.json` picked up the change automatically both
    times.
  - `router/cache.py`: the last open item from `TOKEN_COMPOUNDING.md`
    (#9, cross-session dedup), shipped 2026-08-05. Disk-backed exact-match
    cache (`~/.claude/waterfall_response_cache.json`) keyed by a
    normalized hash of the *routed* text; wired into
    `SmartRouter.route_with_api()` so an identical routed sub-task within
    7 days (`ttl_seconds`) is served from cache instead of a second real
    OpenRouter call -- `waterfall route` reports `served from cache`,
    cost/tokens/elapsed all `0`. Not semantic -- only byte-identical
    (post-normalization) repeats hit. Verified live against the real API
    with a real key: first call cost $9.2e-07 and took 1.15s; the
    identical call right after was instant, `$0.0`, `0 in / 0 out`, same
    output. All 9 countermeasures from `TOKEN_COMPOUNDING.md` are now
    shipped -- see that file's "The gap" section for what still isn't
    solved (the general reused-input compounding problem, as opposed to
    these specific footguns).
  - `router/hook_log.py` + `waterfall hook-log`: append-only JSONL log
    (`~/.claude/waterfall_hook_log.jsonl`) of every real nudge/deny the
    two hooks fire, added 2026-08-05 so "is waterfall actually doing
    anything" has a real answer instead of an inference from noisy daily
    token-volume swings. Only logs the meaningful events (a nudge
    injected, a call denied), not every allowed call -- that would be
    high-volume noise. `waterfall hook-log --verbose` lists real events
    with timestamp/project/detail; logging is a side effect wrapped in
    its own try/except in both hooks, never able to block the hook's
    real decision.
  - **Both hooks installed globally** (`~/.claude/settings.json`,
    2026-08-05), not just project-scoped to this repo -- the whole
    point of a token-saving tool is to save tokens on Adam's *other*
    projects too, and hooks wired only here couldn't do that. **Real
    bug caught immediately via the hook log**: for a few minutes,
    working inside `waterfall.sh` itself fired both the project-scoped
    hooks (`waterfall.sh/.claude/settings.json`) and the new global
    ones simultaneously, double-logging every event here (confirmed
    live: one `cat` denial produced two identical log entries 6ms
    apart). Fixed by emptying `waterfall.sh/.claude/settings.json` to
    `{}` -- the global hooks now cover this repo too, so every project
    fires exactly once. That settings.json edit had to be made by Adam
    directly; Claude Code's own auto-mode classifier hard-blocks
    programmatic edits to `.claude/settings.json` hook/permission
    config, with no way to route around it from within a session --
    a real, working guardrail, not a bug. First real cross-project
    evidence the same day: `themain.quest` and `pangaea.blog` (other
    repos, real sessions, not test data) both showed up nudged in the
    hook log within the hour.
  - `router/usage_pace.py` + `waterfall usage-pace`: added 2026-08-07.
    Claude Max/Pro plan quota %-used has to come from Claude Code's own
    usage display (Anthropic weighs cached/reused tokens far lighter
    than fresh ones for quota purposes, and neither that formula nor a
    plan's ceiling is derivable from local transcripts) -- this just
    takes that self-reported number plus the weekly reset schedule
    (`--reset-day`/`--reset-hour`/`--utc-offset`, defaults tuesday
    17:00 UTC+8) and reports whether it's ahead of, on, or behind a
    flat linear share of the week elapsed. Verified live 2026-08-07:
    Adam at 22% used, 38.3% of the week elapsed (Fri 09:24, reset
    Tue 17:00 SGT) -> -16.3 points, "comfortable cushion."
  - **`usage-pace` extended to multiple quota buckets, 2026-08-13**,
    prompted by a real screenshot of Claude Code's own usage panel
    showing three separate clocks at once (5-hour session limit, weekly
    all-models, weekly per-model e.g. Fable), each with its own reset.
    The original `compute_pace()` only ever handled the single weekly
    bucket. Added `BucketResult` + `compute_bucket_pace()` -- same pace
    math, generalized to any window length, driven by an
    hours-remaining countdown (what the panel actually shows, "resets
    in 3h 27m") instead of a weekday+hour schedule -- and `guidance()`,
    which names the tightest bucket (relative to its own elapsed time,
    not raw %-used) as the binding constraint to ease off, and the
    roomiest as safe to lean on harder. Wired into the CLI via
    `--session-pct`/`--session-hours-remaining`/`--session-window-hours`
    and repeatable `--model-pct MODEL=PCT`. Verified live against
    Adam's real numbers (13% used/3.45h remaining on a 5h session, 24%
    weekly all-models, 3% weekly Fable, both weekly resetting Tue
    ~4pm): weekly all-models -1.7 points ("tracking evenly"), session
    -18.0 ("comfortable cushion"), Fable -22.7 ("comfortable cushion"),
    guidance correctly named weekly all-models as the binding
    constraint (least-negative, still comfortable) and weekly Fable as
    having the most headroom. 20 new tests
    (`ComputeBucketPaceTests`, `GuidanceTests`), full suite still green
    at 200 tests.
  - **`usage-pace` guidance surfaced inside `dashboard`, 2026-08-13**:
    `dashboard.render_usage_pace()` plus the same `--used-pct`/
    `--session-pct`/`--session-hours-remaining`/`--model-pct` flags added
    to the `dashboard` subparser (all optional there, unlike
    `usage-pace`'s required `--used-pct`). A shared
    `cli._build_usage_pace_buckets(args)` builds the bucket list for both
    commands so their guidance can never disagree. The section is skipped
    entirely when no `--used-pct` is given, so the plain `waterfall`
    dashboard is unchanged. Live-verified with
    `waterfall dashboard --used-pct 24 --session-pct 13
    --session-hours-remaining 3.45 --model-pct fable=3`: guidance section
    rendered in the right place alongside the existing hook/routing/
    reuse/countermeasures sections, and a flag-less `dashboard` run
    confirmed the section is cleanly absent otherwise. 6 new tests
    (`RenderUsagePaceTests` + 3 `RenderFullDashboardTests` cases), full
    suite green at 206 tests.
  - `router/dashboard.py` + `waterfall dashboard`: added 2026-08-09.
    Terminal ASCII bar charts (no browser/server) over real hook-log,
    savings-ledger, and claude-usage data: nudges/denials by day, total
    Ringer prevention (denials, tokens, $ equivalent -- parsed from the
    hook log's own denial-reason text via `hook_log.denial_tokens()`),
    routing savings, and the reused-input % trend. Built so a beta
    tester can self-report results without needing a browser -- just
    run it and paste/screenshot the output back. **Known cost**: the
    reuse-trend section scans the full local transcript history via
    `claude_usage.load_usage_turns()`, which took over 2 minutes on
    Adam's own multi-project history during live testing -- not fast,
    documented rather than silently shipped.
  - **Model-tier breakdown added to the dashboard, 2026-08-11**, via
    `/next`: a "model usage by day" section and a "top projects by opus
    usage" section, both from two new `claude_usage.py` helpers
    (`simplify_model()` collapses raw model strings like
    `claude-haiku-4-5-20251001` down to a tier name; `group_by_day_and_
    model()` and `top_projects_by_model()` do the aggregation). Real
    finding this surfaced immediately: **98.9% of every turn across
    every project, last 7 days, is Sonnet** -- 220 Opus turns (nearly
    all in themain.quest), 104 Haiku, 10 Fable, out of ~39,000 total.
    Zero differentiation happening in practice. Separately confirmed
    (via a fresh claude-code-guide check) that Claude Code hooks cannot
    force a model switch -- no `model`/`modelOverride` field exists in
    any hook's output, and there's no per-prompt auto-routing mechanism
    at all, only the manual `/model` command or a static session
    default -- so a full "auto-route to the optimal Claude model"
    feature isn't buildable today. The dashboard section ships as a
    reporting tool only; if a suggestion nudge gets built on top of
    this later, expect the same low real-world conversion the routing
    nudge already showed (97 nudges fired, 5 real routes followed).
  - **Per-countermeasure breakdown added 2026-08-11**, for Adam's
    pitch to Claude power users hitting usage limits even on Max
    plans: `waterfall dashboard` now has a "the 9 countermeasures,
    what each actually saves" section, `dashboard.
    render_countermeasures_breakdown()`. Deliberately honest rather
    than tidy: only 3 of the 9 (#3 routing ledger, #8 the Ringer, #9
    cross-session cache) have their own real, distinct token number.
    The other 6 (classify, auto-fallback, the usage ledger itself,
    model tiering, the skill, the nudge hook) are decision, delivery,
    reliability, or measurement mechanisms that feed those 3 -- they
    don't save tokens on their own, and the breakdown says so plainly
    instead of inventing a number for each to make all 9 look equally
    impressive. #3 and #9 are computed as separate, non-overlapping
    sums from the tracker ledger (split by `backend_used`) so cache
    hits aren't double-counted inside the routing total.
  - **Desktop GUI shipped 2026-08-11** (`desktop/`, `waterfall desktop`):
    local command center on `127.0.0.1:8765` with three tabs:
    Dashboard (ledger + hooks), Cascade (classify / dry-run / live
    route), Agents (detect + launch Claude Code, Codex, Grok Build,
    OpenCode, Gemini, Cursor Agent). Stdlib HTTP + HTML only; optional
    `pywebview` via `waterfall desktop --native` or
    `pip install -e ".[desktop]"`. Patterns learned from OSS landscape
    (AionUi multi-agent glass, opcode usage chrome, Palot GUI-over-CLI,
    OpenCode multi-surface) without forking; research recorded in
    `DESKTOP_GUI_LANDSCAPE.md`. Template rule satisfied by reusing this
    repo's own `index.html` visual system rather than scaffolding a new
    Electron app from empty.
  - **`watertop` one-word launcher (2026-08-11)**: console script
    `watertop = desktop.watertop:main` in pyproject.toml. Defaults to
    native window when pywebview is present, else browser. Same as
    `waterfall desktop` with less typing. Install path still
    `pip install -e .` (or `install.py`); installer now checks both
    `waterfall` and `watertop` on PATH.
  - **Peer desktops installed 2026-08-11** (Path "install peers"):
    CC Switch 3.19.2, AionUi 2.1.47, OpenCode Desktop 1.18.16 via
    winget; OpenChamber 1.18.2 via GitHub win-x64 installer. Documented
    in `PEERS_INSTALLED.md`. Product split: peers = Claude/Codex-class
    agent UI; watertop = cascade/quota only.
  - **Native `waterfall.exe` (2026-08-11)**: Tauri 2 app in
    `desktop-app/`, scaffolded from official
    `create-tauri-app --template vanilla`, customized with CC Switch
    (Tauri shell), AionUi (peer launch), OpenChamber (sidebar) patterns
    + existing cascade Python API. Built release binary:
    `dist/waterfall.exe`, also
    `desktop-app/src-tauri/target/release/waterfall.exe`, NSIS setup
    `waterfall_0.1.0_x64-setup.exe`, MSI
    `waterfall_0.1.0_x64_en-US.msi`. Run `waterfall-app` (bash) or
    double-click `dist/waterfall.exe`. Not a full fork of AionUi monorepo
    (would be wrong product); pattern-merge into waterfall-branded shell.
  - **Parity pass vs Claude Code (2026-08-11)**: gap doc
    `GAP_VS_CLAUDE_CODE.md`. PowerShell process was Claude Desktop
    parent, not waterfall. P1 shipped: CREATE_NO_WINDOW backend,
    Claude session browser (`~/.claude/projects`), launch Claude/Codex/
    Grok CLI into project cwd. Still not full agent tool-loop (by design;
    peers own that).
  - **Design system + logo (2026-08-11)**: tokens in `DESIGN.md`. Brand mark
    is a **blue W** on deep water (`brand/logo.svg` / `logo.png`). Desktop
    icons via `npx tauri icon brand/logo.png`. Favicon `brand/favicon.svg`.
  - **Desktop UX overhaul (2026-08-11)**: maximized window on open; Home
    token-savings hero; Projects (agent-modular, not Claude-default);
    Savings tab; Settings with theme/accent/density + local OAuth scaffold
    (`~/.waterfall/profile.json`). UX refs Linear/Figma/VS Code/Raycast.
    No em dashes in product UI. Full agent tool-loop still via peer CLIs
    (honest gap in `GAP_VS_CLAUDE_CODE.md`).
  - `router/tests/`: unit tests (client, cascade fallback,
    tiering, sentinel-price regression, tracker, claude-usage, the
    Ringer hook, the response cache, the hook log, the nudge hook, the
    usage-pace calculator, the dashboard renderer, the installer's
    settings-merge logic, the model-tier breakdown, the countermeasures
    breakdown, desktop API/server), no network calls required.
  - Verified end-to-end for real, twice: once with an invalid test key
    (correctly surfaced a 401), and again on 2026-08-04 with Adam's real
    `OPENROUTER_API_KEY` -- `route "Write a one-line docstring..."` actually
    called OpenRouter, got real usage/cost back, and logged a ledger entry.
  - `router/tool_inventory.py`: a private, names-only cross-host inventory of
    active skill surfaces, configured MCP names, enabled state, duplicate skill
    copies, content drift, and installed Codex remote plugin package names. It
    deliberately excludes commands, arguments, URLs, headers, environment values,
    credentials, and project paths. `router/tests/test_tool_inventory.py` covers
    backup exclusion, nested-repository exclusion, secret suppression, duplicate
    drift, and plugin listing. The completed 2026-09-03 pass left the full Python
    suite green at 269 tests and both workshop Node suites green at 23 tests.
- **`install.py`**: one-line installer (`curl -sSL .../install.py |
  python3`) for a beta tester's machine: clones/updates into
  `~/.waterfall`, installs the one dependency, and merges (never
  overwrites) the two hook entries into the tester's own
  `~/.claude/settings.json`, with an automatic backup first. **Real
  incident, 2026-08-09**: the first live smoke test used
  `HOME=/tmp/... python3 install.py` to sandbox it, assuming that would
  redirect `Path.home()` the way it does on Linux/Mac. On this Windows
  machine `Path.home()` resolves via `USERPROFILE`, which `HOME` doesn't
  override -- the "isolated" test silently ran for real, cloning a
  second copy of the repo to `C:\Users\adamp\.waterfall` and adding a
  *third*, duplicate set of hook entries to Adam's real global
  `settings.json` (re-triggering the exact double-firing bug fixed
  earlier that same day). The duplicate hook entries were removed via
  Edit (that specific edit went through the auto-mode classifier this
  time, unlike earlier attempts -- inconsistent, not something to rely
  on); the stray `.waterfall` clone directory is still there, since
  directory deletion is blocked by the same permission rules
  (`rm -rf`/`Remove-Item -Recurse` are deny-listed) and routing around
  that block (e.g. via `shutil.rmtree` in a script) was explicitly
  avoided as against the intent of the guardrail -- Adam needs to
  delete `C:\Users\adamp\.waterfall` by hand. Lesson: verify a sandbox
  actually took effect before running anything that writes to a
  developer's real global config, especially cross-platform.
- **Level 2 skill**: `~/.claude/skills/waterfall/SKILL.md` (user-scoped, not
  project-scoped -- available in every Claude Code session, not just this
  repo). Claude self-triggers it on small/mechanical sub-tasks: classify,
  and if routine, run `route` and use the cheap model's actual output
  instead of generating the answer itself. Verified live 2026-08-04 (loaded
  correctly, classified a real sub-task as `free`/`small`).
- **Self-trigger compliance investigated, 2026-08-05**: after global hook
  install, the hook log showed 97 real nudges fired across 16 projects in
  24h but `waterfall stats` still showed only 5 routed prompts, all from
  this session's own testing -- organic self-triggering essentially never
  happens. Root-caused, not guessed: (1) the classifier only ever sees the
  current prompt's raw text -- no conversation history, no file content --
  so it fires on short conversational follow-ups ("yes, look into why")
  that can never be safely routed regardless of what Claude does; (2)
  `SKILL.md`'s own "never route" rules correctly decline most of the
  remainder (anything needing repo/conversation context beyond the bare
  prompt string) -- this part is the safety net working as designed, not
  a bug; (3) even for the genuinely-eligible remainder -- a small
  mechanical chunk generated *within* Claude's own response -- compliance
  is separately low because nothing enforces the proactive check: there is
  no tool call to intercept for "chose to generate inline instead of
  routing," so no Ringer-style hard gate is possible here. Considered and
  **rejected** building a `Stop`-hook heuristic to retroactively flag
  "this response looks mechanical" -- the classifier is built to score
  *requests*, not completed prose/code, and a fuzzy proxy metric here
  would repeat the exact mistake already made and reversed with
  reused-input % (a number that looked like signal but wasn't measuring
  the real thing). Tried instead: tightened `SKILL.md`'s "When to
  self-trigger" section from a soft "when it feels worth it" judgment call
  into an unconditional checklist ("if it matches this list, CLASSIFY
  before writing a word -- not a vibe") plus a mid-generation recovery
  clause. Cheap to try, honestly uncertain to work -- self-triggering
  compliance has a real ceiling that prompting alone may not fully close;
  not yet re-measured.
- **Re-measured, 2026-08-14: the 2026-08-05 checklist tightening did not
  move the needle.** All-time totals: nudges 97 -> 3,920 (+3,823), routed
  prompts 5 -> 6 (+1). Nearly 4,000 additional nudges produced one
  additional real route. This confirms the "honestly uncertain to work"
  flag from 2026-08-05 -- wording clarity was never the bottleneck; there
  is still no enforcement point that intercepts "chose to generate inline
  instead of routing," and a second round of stricter checklist wording
  can't create one. Adam asked to tighten it again anyway; done, but
  framed differently this time rather than just re-emphasizing the same
  checklist: `SKILL.md` now leads with the raw 3,920-vs-6 numbers before
  any instructions, and explicitly names the actual rationalization
  ("this one's obviously simple enough that checking is overkill") as the
  failure mode itself rather than a valid exception. Whether making the
  failure mode visible in-context changes anything is unverified -- this
  is a real experiment, not a confirmed fix; re-measure before claiming
  it worked.
- **CLI on PATH: fixed for real, 2026-08-11.** `pip install --user -e .`
  put `waterfall.exe` in `C:\Users\adamp\AppData\Roaming\Python\Python314\
  Scripts`, but that directory was never on this machine's PATH (this
  machine has several Python versions installed and PATH only covers
  3.11/3.12/3.13's Scripts dirs, not the 3.14 user-install one `--user`
  actually used). Fixed by adding that directory to PATH via
  `~/.bashrc` specifically (scoped to Git Bash, not a system-wide
  Windows environment variable change) -- `export PATH="$HOME/AppData/
  Roaming/Python/Python314/Scripts:$PATH"`. Verified live: bare
  `waterfall` now resolves and renders the real dashboard in this
  shell, and will in any new Git Bash session too since it's in
  `.bashrc`, not just this session's environment. The old workaround
  (always invoke by full path) is no longer necessary on this machine.
  A fresh install elsewhere hitting the same gap gets a clear message
  from `install.py` itself now (2026-08-11) instead of a silent
  "command not found" -- see the install.py entry below.
- **`waterfall` (bare, no subcommand) now shows the dashboard**, added
  2026-08-11 -- was previously just an argparse usage error.
  `install.py` also fixed the same day: it used to only run
  `pip install -r requirements.txt`, which installs the dependency but
  never registers the `waterfall` console script
  (`pyproject.toml`'s `[project.scripts]` entry needs `pip install -e .`
  on the repo itself). A fresh one-line install never actually gave
  anyone a working bare `waterfall` command before this. Verified for
  real in an isolated venv this time (not an environment-variable trick
  again, after the earlier `HOME` override silently failed to sandbox
  anything on Windows): `pip install -e .` produced a real
  `waterfall.exe`, and running it bare rendered the full real dashboard.

## Testing

Run both suites from the repository root:

```bash
python3 -m unittest discover -s router/tests -p "test_*.py"
node --test router/tests/workshop.test.mjs router/tests/starter-packs.test.mjs
```

The Python suite covers the router and static deployment contract. The Node 18+
suites execute the catalog and starter-pack filtering, quiz, prompt, URL, copy,
recovery, and escaping paths. Run both before committing changes to `workshop/`, `.vercelignore`, or
`vercel.json`.

## Design principles (from the 2026-08-04 token-saving pass)

Distilled from a Nate B. Jones transcript on why LLM token usage compounds
(every turn resends the whole conversation) and the countermeasures. These
now shape both how this tool is used and what it should still grow into.
**See `TOKEN_COMPOUNDING.md`** for the standalone version of this
distillation plus a status table of countermeasures: **9 of 9 shipped
as of 2026-08-05** (the hard per-call cap, `router/hooks/pre_tool_use.py`,
and the cross-session response cache, `router/cache.py`, both landed
that day). That file's "The gap" section is the important honest part:
shipping all 9 doesn't mean reused-input compounding is solved: every
mechanism here attacks a specific, narrow footgun (one huge file, one
repeated ask), not a long thread's accumulated, non-repeating history,
which is what actually drives the 65–96% reused-input share.

- **Classify/split before you send** (`classify`, `route --dry-run`): free,
  no network, the equivalent of "edit your mistake instead of retrying" and
  "ask for only what you need" turned into a command instead of a habit.
- **Auto-fallback across models, not just retries**: shipped in
  `openrouter_api_client.py` (see above). A skill/CLI can't shrink a request
  that's already been sent; it *can* make sure a down/rate-limited cheap
  model doesn't force the whole call up to Claude.
- **Ledger everything that gets routed away** (`tracker.py` / `stats`), so
  "is this tool actually saving tokens" is answerable from data, not vibes.
  This is the `~/.claude/token_savings.jsonl` pattern, now implemented.
- **Right model for the right job, not just "cheapest"**: model tiering
  (see above). "I don't want to use a powerful model for small tasks" is now
  a real selection axis, not just "always grab whatever's #1 by price."
- **Level 2 shipped**: the `waterfall` skill (self-triggering) and the
  `UserPromptSubmit` hook (fully automatic, no Claude judgment call needed)
  , both live as of 2026-08-04.
- **Still open, matching the transcript's Level 3 idea**: hard per-call
  token/size limits enforced client-side (Nate's "Ringer" idea): the hook
  only *nudges*, it doesn't cap or block anything yet.
- **Two fixes from live testing (2026-08-04)**:
  1. Hook's `MIN_WORDS` threshold lowered 12 → 6: a real routine 8-word ask
     ("rename the variable x to userCount throughout utils.py") was getting
     silently skipped.
  2. Skill hardened with a verified-failure warning: routing that same
     prompt with no real `utils.py` in the repo made the free model
     **fabricate** a plausible-looking file from scratch and present it as
     the real result; it didn't flag anything wrong. The skill now has a
     hard rule (not just a caveat) to read the real file and embed its
     actual content before routing any "edit this existing file" task, or
     not route it at all. This is a load-bearing safety fix, not polish.
- **Bare-arithmetic carve-out, 2026-08-14**: Adam's real complaint was
  "we dont want to do 2+2 with fable" -- checked, and the classifier
  already scored `2+2` correctly (`routing='free'`, 100% free). The
  actual bug was the nudge hook's `MIN_WORDS=6` gate: it exists to
  filter short conversational follow-ups the classifier can't safely
  route without context (`"yes, look into why"`), but it gates on raw
  length, so it silently swallowed short *self-contained* prompts like
  `2+2` too -- exactly the case waterfall is supposed to catch. Fixed
  with a narrow regex carve-out (`_ARITHMETIC_RE`) that lets bare
  arithmetic bypass `MIN_WORDS`, without loosening the gate generally
  -- deliberately not a broader "is this short prompt self-contained"
  detector, since that's the same fuzzy-proxy-metric trap already
  rejected once this session (the Stop-hook idea for flagging "looks
  mechanical" responses). Live-verified: `2+2` now nudges
  (`routing='free'`), `"yes, look into why"` still doesn't. 2 new
  tests, full suite green at 208.
  - Also checked and corrected a real misunderstanding in the same ask:
    Adam pointed at `https://arena.ai/leaderboard/agent` expecting
    per-user subscription/credit data to drive routing decisions --
    fetched it and confirmed it's LMArena's Agent Arena, a
    model-vs-model performance leaderboard (confirmed success,
    steerability, tool hallucination, etc across 48 models), with zero
    subscription/account data. Not the same site as Viberank (the real
    per-user-usage leaderboard used earlier this session to find ICP
    candidates). Flagged rather than silently building against a
    misread source. A real, not-yet-built idea did fall out of this:
    using Arena's per-model performance signals to make
    `pick_cheap_models()` quality-aware instead of pure lowest-price.
- **Global Claude Code model/effort hygiene, 2026-08-19** -- outside this
  repo's own files, but the real answer to "how do we get all my Claude
  Code sessions to use the optimal model/effort automatically." Verified
  against the real, current docs (not recalled from training data) plus
  Adam's actual `~/.claude/settings.json` before acting:
  1. **Global default fixed**: `~/.claude/settings.json` had
     `"model": "claude-fable-5"` as the blanket default for every project
     -- a real, concrete finding, not hypothetical, and plausibly a real
     contributor to the heavy Fable usage seen in the dashboard earlier
     this session. Changed to `"model": "sonnet"` +
     `"effortLevel": "medium"`. Verified valid JSON after the edit.
  2. **Per-project overrides**: real mechanism (a project's own
     `.claude/settings.json` can set its own `model`/`effortLevel`,
     overriding the global default just there), but deliberately NOT
     applied blanket across the ~100+ Aether projects -- no grounded basis
     to classify which ones genuinely need more than the new Sonnet/medium
     default. Asked Adam directly; he said log the mechanism, don't guess.
     Apply per-project only when a real need is named or the dashboard
     (item 4) surfaces one.
  3. **Real correction caught before shipping**: the original plan was to
     add `model:`/`effort:` frontmatter to waterfall's own inline skill
     for automatic cheap-model routing on known-routine invocations.
     Checked the actual skills docs before building -- frontmatter model
     override only takes effect when a skill runs via `context: fork`
     (which forks it into a subagent, with the model coming from the
     subagent's own `agent:`/frontmatter, not a bare `model:` key on a
     plain inline skill). Would have silently done nothing. The real,
     verified mechanism for "known routine task type -> automatically
     cheap" is a genuine custom subagent (`.claude/agents/*.md`) with
     `model:` in ITS OWN frontmatter, dispatched via the Agent tool's
     `model` param (already used correctly earlier this session for
     background research agents) or a `context: fork` skill pointing at
     it. No fabricated example built -- no concrete, already-proven
     routine task type was named to build one around.
  4. **The feedback loop**: `waterfall dashboard`'s existing model-usage-
     by-day / top-projects-by-model breakdown (shipped 2026-08-11) is the
     real mechanism for catching drift -- periodically check which
     projects show heavy Opus/Fable/high-effort use for what turned out
     to be routine work, and correct that project's default via #2.
     Calibration habit, not full automation, because full automation
     isn't real here: confirmed (again) that no mechanism -- hook,
     setting, anything -- lets model/effort vary automatically per-prompt
     within a running session. `/model`/`/effort` are session-start
     defaults or manual mid-session commands only.
- **Fleet-wide Aether project classification, 2026-08-20**: applied the
  per-project override mechanism from item 2 above for real, across the
  whole ~117-project fleet, not just logged as a mechanism. Built a
  cheap, deterministic (no LLM-per-project) classifier in a scratchpad
  script over real filesystem/dependency signals (real agent/LLM SDK
  dependency + file count for "complex", zero deps + near-empty for
  "minimal", everything else inherits the sonnet/medium global default
  as "routine"). Caught and fixed two real false positives before
  writing anything: a "financial complexity" signal that was actually
  matching the Aether Standard scaffold's generic Stripe boilerplate on
  ~20 unrelated projects (dropped the signal entirely), and 6
  `summon-*` CI/PR worktree directories that needed the same paused
  treatment as `summon.company` without also catching the real, active
  `summon.guide`. Result: 81 routine / 18 complex / 10 minimal / 8
  paused-skipped. Wrote `.claude/settings.json` in 28 projects (merged
  into existing settings, never overwrote; 16 more already had a real
  `model` set and were left untouched), committed individually in each
  of the 9 real git repos among them. Cross-referenced against those 16
  pre-existing projects and found 12 of them used `sonnet` for what my
  heuristic called "complex," not `opus` -- adjusted the 4 newly-written
  complex projects (antlist, estimate, mastra-work, strummer-daw) from
  opus/high to sonnet/high to match the apparently-deliberate existing
  pattern rather than silently trusting the heuristic over real prior
  signal.
- **Visual color-coded usage-pace dashboard, 2026-08-20**: replaced the
  terminal ASCII dashboard for the usage-pace feature specifically with
  a real web page, `desktop/pace.html`, served at `/pace` on the
  existing `waterfall desktop` server (127.0.0.1:8765). New
  `desktop/server.py:api_pace()` reuses `usage_pace`/`quota_estimate`
  exactly as the CLI does (single source of truth for the
  green/yellow/red threshold, `STATUS_MARGIN`, computed server-side so
  the color logic can't drift between the CLI and the page), falls back
  to the automatic local estimate when no real `used_pct` is supplied,
  and renders color-coded cards with progress bars (an elapsed-time
  marker line), a day-of-week ceiling reference chart, and
  live-editable inputs for weekly/session/per-model percentages. No new
  dependencies, matches `DESIGN.md`'s brand token system. Live-verified
  end to end with Adam's real numbers (30% weekly / 13% session / 3%
  fable): guidance text matched the CLI's output exactly. 5 new tests,
  full suite green at 261.

- **stealth/ox-alpha characterized live through the desktop GUI,
  2026-08-23**, because the free-model fix made it waterfall's #1 pick and
  a default pick deserves to be tested, not assumed. Driven through
  `waterfall desktop`'s Cascade tab (real clicks, real routes), then every
  returned snippet was actually executed rather than eyeballed. Two real
  findings, in order of how much they matter:
  1. **It returns empty content when reasoning eats the token budget.**
     ox-alpha writes its chain into a separate `reasoning` field FIRST and
     only then writes `content`. At `max_tokens=900` it spent all 900 on
     reasoning and answered HTTP 200 / `finish_reason="stop"` /
     `content=None`; at 2000 it answered correctly. `reasoning_tokens`
     reports `0` throughout, so the usage block does not reveal it either.
     waterfall used to report that as a successful route with an empty
     answer. Fixed: empty/whitespace content now cascades to the next
     candidate (commit 368fc5f, 2 regression tests).
  2. **Its code is good; its tests are not, on edge-case-heavy prompts.**
     On a plain task (`chunk_by_size`) it produced correct code whose own
     3 tests passed on execution. On a prompt with a deliberate trap
     (`merge_intervals`, where sharing an endpoint must merge but a gap
     must not) the implementation was correct against both stated spec
     examples, but 2 of the 4 tests it wrote asserted the opposite of the
     rule the function correctly implements, and the file failed on
     import. Concretely: it asserted `(8,10)+(10,12)` stay separate when
     they share endpoint 10 and must merge to `(8,12)`.
     The failure mode to remember is that the output *looks* complete
     (code plus tests) while containing tests that contradict the code, so
     it reads as more verified than it is. This is why routed output gets
     executed, not skimmed. Not a reason to drop ox-alpha as the top pick
     -- it is free, fast, and its implementations held up -- but a real
     reason to treat model-authored tests as unverified until run.
  Also confirmed in the same pass: the response cache works end to end
  through the GUI (identical routed text came back instantly, `$0`, `0 in
  / 0 out`, `cache_hit: true`), and the OpenRouter key is pay-as-you-go
  with no cap and $0 spent so far, with every ox-alpha call billing $0.

- **UI rebuilt in shadcn's design language, model queue made visible,
  2026-08-23/24.** Four things landed; the last one is the one to read first
  if you are resuming cold.
  1. **`desktop/tokens.css` is now the single source of truth for the
     palette**, served at `/tokens.css` and linked by BOTH `app.html` and
     `pace.html`. shadcn's semantic OKLCH token pairs plus the derived
     `--radius` scale, hand-ported as plain CSS. Deliberately NOT the real
     shadcn library: that is React plus Tailwind plus a build step, and these
     pages are served off the stdlib HTTP server, so `pip install -e .` has to
     stay the whole install story. Brand hexes were converted to OKLCH
     numerically, not re-picked, so deep water is still
     `oklch(0.1831 0.0309 263.38)`. Full token table in `DESIGN.md`.
  2. **Navigation is a top bar, not a sidebar.** With three sections a rail is
     the wrong control (convention: top bar under ~5 destinations, sidebar at
     6+). Do not re-add a sidebar unless the app grows past five real
     sections.
  3. **The model queue is now visible** (`waterfall route`, and the Cascade
     tab). `GenerateResult` carries `queue` (ranked candidates) and `attempts`
     (what happened to each), threaded through `ApiRoutingResult` to the CLI
     and the desktop API. The cascade always had this and used to discard it,
     which made "why that model" and "did it fall back" unanswerable. It paid
     off on the first live run: ox-alpha returned **429 rate limited** and the
     cascade silently fell through to `dots-3-note-preview`. That had been
     invisible.
  4. **Real incident worth remembering: `~/.claude/openrouter_key.txt` held a
     REVOKED key.** Everything worked only because a valid key lives in the
     login-shell environment and was masking it. Any non-login shell, or a
     fresh install following the documented setup, got a 401. Repaired from
     the login env (old file backed up alongside). **Still unresolved: nobody
     knows where that env var is actually set.** It is not in `.bashrc`,
     `.bash_profile`, `.profile`, or any Windows env scope (User, Machine, or
     Process), yet `bash -lc` has it. Until that is found, the same silent
     breakage can recur.
  Also fixed in passing: `/favicon.svg` had no server route (404 on both
  pages); a stray `}` left by a bad edit silently killed the mobile media
  block AND the active-tab styling; a mangled newline escape broke a JS string
  literal and left the whole page inert. Suite green at 266.

- **New global skill: `beautify`** (`~/.claude/skills/beautify/`, user-scoped,
  available in every project, NOT in this repo). Its job is to refuse to
  design from scratch: source real prior art first, then apply shadcn's system
  to whatever stack the project actually is, including stacks the shadcn CLI
  cannot touch (plain HTML, Python-served templates, Tauri, no build step).
  Ships `scripts/hex_to_oklch.py` (exact brand conversion, verified against
  this repo's four shipped values) and `scripts/verify_ui.js` (WCAG contrast,
  overflow, token resolution against a live page, for when screenshots are
  unavailable). `references/design-sources.md` records every design resource
  with its real HTTP status. **Key finding: Mobbin is 403 to agents and its
  free tier is 4 apps / 3 collections, so it cannot be an agent research
  source.** Refero is JS-rendered and returns only a page title. The
  agent-usable sources are shadcn blocks/themes/registries, tweakcn, Godly,
  SaaS Landing Page.

- **Leaderboard coverage idea, 2026-09-03 (Claude, logged not built).** While
  building a duplicate of the leaderboard Codex had already shipped (caught
  before push; the duplicate is parked on branch
  `backup/claude-leaderboard-2026-09-03` and should not be merged), one
  finding surfaced that the shipped board does not use: OpenRouter's
  `/models` catalog natively carries `benchmarks.artificial_analysis` (the AA
  Intelligence Index, 169 models), `benchmarks.design_arena` (per-category
  Elo, 230 models), and `reasoning.supported_efforts` per model. The shipped
  board is the right design, measured dollars-per-solved-task on a real
  smoketest, and it covers roughly ten models. The catalog fields are a
  cheap way to show a borrowed score for the other ~230, clearly labeled as
  "not measured here, from AA / Arena" so they never get confused with the
  smoketest numbers. `perf_source` per row. Worth doing only if coverage
  becomes a real complaint; the measured ten are the product.
  Lesson recorded plainly: this session resumed after ten days and never ran
  `git fetch` before building. BACKUP_PLAN.md's sync ritual is now amended
  to start with a fetch.

## Not done yet

- **A/B/C/D quota-safety plan shipped, 2026-08-18**, in response to Adam
  running out of Claude usage the prior week and asking for everything
  buildable to stop it happening again. Real fleet picture first
  (checked, not assumed): of the four paid tools (Claude $200, Codex $20,
  Grok $30, OpenRouter pay-per-token), only Claude exposes usable local
  transcript data -- Codex's `.codex-global-state.json` has no usage/
  token/cost keys (checked all 31), and Grok's usage monitoring is
  OpenTelemetry-export-to-an-external-collector, enterprise-oriented and
  off by default, not a local file. So: **A** `--bucket
  LABEL=USED_PCT:WINDOW_HOURS:HOURS_REMAINING` on `usage-pace`/
  `dashboard`, for a subscription with its own reset schedule (the
  existing `--model-pct` wrongly assumes Claude's own weekly clock).
  Also fixed the `--reset-hour` default (17 -> 16, the real reset is
  4pm, not 5pm -- this session had been manually overriding it every
  single call). **B** `router/quota_estimate.py`: a cached, tiered
  (70/85/95%) automatic warning built on a rough local-transcript-volume
  proxy (`claude_usage.estimate_pct_used`, calibrated from one real data
  point -- 11.2B tokens at a real self-reported 92%), wired into the
  nudge hook as a second check independent of the routing nudge, capped
  to one real transcript scan per 30 minutes (a full scan takes tens of
  seconds mid-session, so this is a real, documented cost, not free).
  Also `waterfall claude-estimate` for on-demand checks. **C**
  `router/scripts/quota_checkin.ps1` + two Windows Scheduled Tasks
  (10am, 5pm daily), a native WinForms MessageBox reminder -- `msg.exe`
  was the first idea, confirmed absent on this Windows Home machine
  before building around it, a real dead end caught early rather than
  discovered after scheduling something broken. **D** the Codex
  investigation above. 42 new tests, full suite green at 251. Honest
  limit: B's estimate is a rough proxy, not Anthropic's real formula --
  it's a fallback for when Adam hasn't checked the real panel, never a
  replacement for it.
  **C is OFF as of 2026-08-22**, at Adam's direct request ("stop the
  periodic terminal reports"). Three separate things were producing
  them, all found and stopped: the two Windows Scheduled Tasks
  (`waterfall-quota-checkin-morning` / `-evening`) are **disabled**, not
  deleted; the `desktop/quota_tray.py` tray app was killed; and its
  autostart shortcut in the Startup folder was renamed to
  `waterfall-quota-tray.lnk.disabled` so it does not come back at login.
  All three are deliberately reversible (`Enable-ScheduledTask` for the
  tasks, rename the `.lnk.disabled` back for the tray) -- nothing was
  destroyed. This is consistent with the standing preference already
  recorded in memory (no casually-spawned background processes or UIs;
  monitoring stays alert-only), so treat C as an experiment that was
  tried and switched off, not as infrastructure to restore by default.
  A/B/D are untouched and still live.
- **Re-check nudge-vs-routed compliance around 2026-08-17 (~3 days after
  the 2026-08-14 SKILL.md re-tightening)**: run `waterfall hook-log` and
  `waterfall stats`, compare nudges-fired and prompts-routed against the
  2026-08-14 baseline (3,920 nudges, 6 routed), and report the delta
  plainly. No local cron survives a closed session and no cloud routine
  can see `~/.claude/waterfall_hook_log.jsonl` or the savings ledger (both
  local-only), so this can't be scheduled automatically -- whichever
  session next works in this repo around that date should just run it.
  Don't overclaim if it's still flat; see the 2026-08-14 entry above for
  why a third wording pass likely wouldn't help either.
- **The actual before/after Adam wants, in progress as of 2026-08-05**:
  save real tokens/money across his own projects (not just this repo),
  show a real before-vs-after transformation, and only *then* buy the
  domain and post it where he originally found this idea. Sequence:
  (1) hooks now global ✅, (2) "before" baseline already captured from
  real transcript history (`waterfall claude-usage --since-days 7` =
  93.3% reused, 6.57B reused tokens, $20,408.78 list-price-equivalent
  as of 2026-08-05) ✅, (3) hook-log now proves the hooks are firing for
  real across projects ✅, (4) still needed: let a real stretch of normal
  work accumulate (a week+), then re-run the same `claude-usage` command
  and compare. Don't buy the domain or post anywhere until that
  comparison is in hand -- that's the whole point of this sequencing.
- Landing page proof stats were updated 2026-08-05 with real,
  verifiable numbers (9/9 countermeasures shipped, 300+ live OpenRouter
  models) -- deliberately *not* real usage-ledger numbers yet (still
  just 5 test prompts / $0.0002 saved, all dev testing, not organic
  use). Revisit once the before/after above gives something worth
  showing.
- Offer is live: $30 founding one-time, `OFFER.md` / `offer.json`.
  Spec for the product people buy: `PERFECT.md`.
- Not yet run through Adam's "Summon" standardization pass (the
  NORTH_STAR.md / EVIDENCE.md / company/ORGANIZATION.md pattern seen in
  the sibling `vercel.school` folder), intentionally skipped since this
  isn't a company yet, just a tool. Run Summon on it if/when that's next.

## How to keep this useful

- Update this file when Claude Code or Codex learns new project facts.
- Keep `AGENTS.md` synchronized so Codex sees the same context inline.
- `router/.env.example` shows the two ways to configure
  `OPENROUTER_API_KEY` (env var or `~/.claude/openrouter_key.txt`).

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
