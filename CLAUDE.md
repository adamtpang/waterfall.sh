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
  - `router/cache.py` — the last open item from `TOKEN_COMPOUNDING.md`
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
  - `router/hook_log.py` + `waterfall hook-log` — append-only JSONL log
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
  - `router/tests/` — 110 passing unit tests (client, cascade fallback,
    tiering, sentinel-price regression, tracker, claude-usage, the
    Ringer hook, the response cache, the hook log, the nudge hook), no
    network calls required.
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
distillation plus a status table of countermeasures — **9 of 9 shipped
as of 2026-08-05** (the hard per-call cap, `router/hooks/pre_tool_use.py`,
and the cross-session response cache, `router/cache.py`, both landed
that day). That file's "The gap" section is the important honest part:
shipping all 9 doesn't mean reused-input compounding is solved — every
mechanism here attacks a specific, narrow footgun (one huge file, one
repeated ask), not a long thread's accumulated, non-repeating history,
which is what actually drives the 65–96% reused-input share.

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
