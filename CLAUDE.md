# CLAUDE.md - waterfall.sh

Context for Claude Code, Codex, and humans working in this folder. This is
the live handoff — the source of truth for current progress, decisions,
and open tasks. Update it as things change so future sessions (and other
agents) stay in sync.

## What this is

waterfall.sh is a dev tool: it classifies a prompt, routes the routine
part to the cheapest capable model on OpenRouter's live Arena-ranked
catalog, and only surfaces the genuinely hard part for Claude — so a
Claude Code / Claude Pro plan's quota goes further. Born out of a Cowork
session extending the (unrelated, Windows-only) `Claude-Token-Saver` repo
at github.com/awesomo913/Claude-Token-Saver, then pulled out into its own
project once the naming/branding direction was clear.

## Current state (as of this handoff)

- **Domain**: not purchased yet, Adam explicitly declined on 2026-08-04
  ($22/yr quoted, confirmed available, he said not yet). Live now at
  https://waterfallsh.vercel.app instead -- project `waterfall.sh` under
  team `adamtpangs-projects`, linked to the
  github.com/adamtpang/waterfall.sh repo (auto-deploys on push to `main`).
  Buy the domain and attach it to this same project whenever Adam says go
  (`get_purchase_quote` -> confirm with him -> `buy_domain`; already
  quoted once, quote expires in 5 min so re-quote when it's time).
- **Landing page**: `index.html` + `vercel.json` + `robots.txt` +
  `sitemap.xml` — plain static HTML, zero build step. **Needs
  `.vercelignore` excluding `router/` and `pyproject.toml`, and
  `"framework": null` in `vercel.json`** -- without both, Vercel
  auto-detects the sibling Python CLI (`pyproject.toml` at repo root) and
  tries to build this as a Python serverless app instead of a static site,
  which fails with "No python entrypoint found." Hit and fixed 2026-08-04;
  don't remove either fix. Visual style is intentionally reused from vercel.school
  (same dark chalkboard-style theme, mono/hand font pairing) for
  consistency across Adam's project portfolio — swap the accent color /
  copy freely, the structure is just a starting point.
- **Router core**: `router/` — this is real, tested, working Python, not a
  stub:
  - `router/openrouter_api_client.py` — direct HTTP client for OpenRouter's
    API (model catalog fetch+cache, cheapest-capable-model auto-selection,
    chat completions with cost accounting). `generate_with_usage()` now
    **cascades through the N cheapest capable models** — if the cheapest
    one is down/rate-limited/errors out after its retries, it automatically
    tries the next-cheapest candidate before giving up (`pick_cheap_models(n)`
    supplies the ranked candidate list). This is the literal "auto falls
    back to the next best model" behavior the tool is named for — it only
    covered picking one model before 2026-08-04, no actual fallback chain.
  - `router/smart_router.py` — `SmartRouter.route_with_api()`: classify →
    split → send the easy part to OpenRouter → return what's left for
    Claude with the free model's output already stitched in.
  - `router/classifier/` — local, zero-API prompt classifier (pure
    stdlib) that decides free/split/claude routing and estimates the
    free/Claude token split.
  - `router/tracker.py` — `SavingsTracker`: append-only JSONL ledger at
    `~/.claude/token_savings.jsonl` (same pattern as the Claude-Token-Saver
    fork this was ported from) + `summarize()` for aggregate stats.
  - `router/cli.py` — the CLI: `classify` / `route [--dry-run]` / `stats` /
    `models`. Runs bare (`python3 router/cli.py ...`) or as a package
    (`python3 -m router.cli ...` from repo root, or `waterfall ...` after
    `pip install -e .` — see `pyproject.toml`). `classify` and
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
  - `router/hooks/user_prompt_submit.py` — a `UserPromptSubmit` command hook
    (project-scoped, wired in `.claude/settings.json`). Classifies every
    prompt submitted in this project (local, no network) and, when it looks
    routine, injects a one-line nudge via `hookSpecificOutput.additionalContext`
    suggesting the `waterfall` skill route the mechanical part instead of
    generating it inline. Never blocks, never raises -- any failure is a
    silent no-op. Needs `/hooks` (reload config) or a session restart to
    start firing, since `.claude/` didn't exist in this project when the
    hook was added.
  - `router/hooks/pre_tool_use.py` — a `PreToolUse` command hook
    (project-scoped, wired in `.claude/settings.json`, matcher
    `Read|Bash|PowerShell`). The "Ringer" from `TOKEN_COMPOUNDING.md`:
    hard-blocks (not nudges) a `Read` with no offset/limit, or a bare
    `cat`/`Get-Content`/`type`, against a file over
    `WATERFALL_RINGER_CAP_TOKENS` (default 8,000 est. tokens). Narrowed
    reads (offset/limit given) and piped/redirected shell commands are
    never capped. Fails open on any error/missing file/unparseable
    command. Verified live 2026-08-05 in a running session with no
    `/hooks` reload or restart needed -- `.claude/settings.json` picked
    up the new `PreToolUse` entry automatically; denied a blind Read of
    a 57KB scratch file with the exact reason text, then let the same
    Read through once `limit` was added.
  - `router/tests/` — 63 passing unit tests (client, cascade fallback,
    tiering, sentinel-price regression, tracker, claude-usage, the
    Ringer hook), no network calls required.
  - Verified end-to-end for real, twice: once with an invalid test key
    (correctly surfaced a 401), and again on 2026-08-04 with Adam's real
    `OPENROUTER_API_KEY` -- `route "Write a one-line docstring..."` actually
    called OpenRouter, got real usage/cost back, and logged a ledger entry.
- **Level 2 skill**: `~/.claude/skills/waterfall/SKILL.md` (user-scoped, not
  project-scoped -- available in every Claude Code session, not just this
  repo). Claude self-triggers it on small/mechanical sub-tasks: classify,
  and if routine, run `route` and use the cheap model's actual output
  instead of generating the answer itself. Verified live 2026-08-04 (loaded
  correctly, classified a real sub-task as `free`/`small`).
- **CLI on PATH**: installed via `pip install --user -e .`, but the
  `Scripts` dir isn't on this machine's PATH (known issue, see
  `feedback_windows_path_poison` memory) -- always invoke by full path
  (`python3 "C:/Users/adamp/Aether/waterfall.sh/router/cli.py" ...`), never
  bare `waterfall`.

## Design principles (from the 2026-08-04 token-saving pass)

Distilled from a Nate B. Jones transcript on why LLM token usage compounds
(every turn resends the whole conversation) and the countermeasures. These
now shape both how this tool is used and what it should still grow into.
**See `TOKEN_COMPOUNDING.md`** for the standalone version of this
distillation plus a status table of which countermeasures are actually
shipped vs. still just a habit (8 of 9 shipped as of 2026-08-05, now
including the hard per-call cap — the "Ringer",
`router/hooks/pre_tool_use.py` — added 2026-08-05. The one still-open
item, cross-session dedup, is the most invasive: it needs persistent
memory across sessions, not just routing/enforcement within one).

- **Classify/split before you send** (`classify`, `route --dry-run`) — free,
  no network, the equivalent of "edit your mistake instead of retrying" and
  "ask for only what you need" turned into a command instead of a habit.
- **Auto-fallback across models, not just retries** — shipped in
  `openrouter_api_client.py` (see above). A skill/CLI can't shrink a request
  that's already been sent; it *can* make sure a down/rate-limited cheap
  model doesn't force the whole call up to Claude.
- **Ledger everything that gets routed away** (`tracker.py` / `stats`) — so
  "is this tool actually saving tokens" is answerable from data, not vibes.
  This is the `~/.claude/token_savings.jsonl` pattern, now implemented.
- **Right model for the right job, not just "cheapest"** — model tiering
  (see above). "I don't want to use a powerful model for small tasks" is now
  a real selection axis, not just "always grab whatever's #1 by price."
- **Level 2 shipped**: the `waterfall` skill (self-triggering) and the
  `UserPromptSubmit` hook (fully automatic, no Claude judgment call needed)
  — both live as of 2026-08-04.
- **Still open, matching the transcript's Level 3 idea**: hard per-call
  token/size limits enforced client-side (Nate's "Ringer" idea) — the hook
  only *nudges*, it doesn't cap or block anything yet.
- **Two fixes from live testing (2026-08-04)**:
  1. Hook's `MIN_WORDS` threshold lowered 12 → 6 — a real routine 8-word ask
     ("rename the variable x to userCount throughout utils.py") was getting
     silently skipped.
  2. Skill hardened with a verified-failure warning: routing that same
     prompt with no real `utils.py` in the repo made the free model
     **fabricate** a plausible-looking file from scratch and present it as
     the real result — it didn't flag anything wrong. The skill now has a
     hard rule (not just a caveat) to read the real file and embed its
     actual content before routing any "edit this existing file" task, or
     not route it at all. This is a load-bearing safety fix, not polish.

## Not done yet

- Landing page copy is placeholder-honest — no fabricated usage stats.
  Fill in real numbers once there's real usage (see the "proof" stat row
  in `index.html`).
- No offer/pricing/buyer defined yet — this is a tool for Adam's own use
  first; productizing it is a later decision, not blocking anything here.
- Not yet run through Adam's "Summon" standardization pass (the
  NORTH_STAR.md / EVIDENCE.md / company/ORGANIZATION.md pattern seen in
  the sibling `vercel.school` folder) — intentionally skipped since this
  isn't a company yet, just a tool. Run Summon on it if/when that's next.

## How to keep this useful

- Update this file when Claude Code or Codex learns new project facts.
- Keep `AGENTS.md` synchronized so Codex sees the same context inline.
- `router/.env.example` shows the two ways to configure
  `OPENROUTER_API_KEY` (env var or `~/.claude/openrouter_key.txt`).
