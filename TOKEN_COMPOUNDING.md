# Token compounding: source notes and mitigation status

Reference doc, not the original source. This is the distilled summary that
was already living inside `CLAUDE.md`'s "Design principles" section,
pulled out on 2026-08-05 so it stands on its own. **The original
transcript itself isn't saved anywhere in this repo or the Obsidian
vault**. If you want it re-derived faithfully, it needs to come from
wherever that Nate B. Jones source actually lives (not reconstructed from
memory here).

## The core mechanism

Every turn in a conversation resends the whole prior conversation as
input; there's no native memory. Claude Code's prompt caching discounts
that resend heavily (cache-read tokens bill far below fresh-input price),
but it doesn't eliminate the resend: reused tokens still count against
raw volume, and volume is what trips session/weekly usage limits. This
is confirmed against this machine's own transcripts (see
`waterfall claude-usage --by-day`): reused-input share has sat at
65–96% on every single day since transcripts started (2026-04-25), and
raw daily volume grew from ~15–30M reused tokens/day in April to
1–2.5 **billion**/day by July.

## Proposed countermeasures, and what's actually been built

| # | Countermeasure | Status | Where |
|---|---|---|---|
| 1 | Classify/split before sending: decide free/split/claude before generating | **Shipped** | `router/classifier/`, `waterfall classify` |
| 2 | Auto-fallback across models so a down/rate-limited cheap model doesn't force the call up to Claude | **Shipped** | `router/openrouter_api_client.py` cascade |
| 3 | Ledger everything routed away, so savings are data not vibes | **Shipped** | `router/tracker.py`, `waterfall stats` |
| 4 | Ledger Claude's *own* real consumption as a baseline | **Shipped** (2026-08-05) | `router/claude_usage.py`, `waterfall claude-usage` |
| 5 | Right model for the job, not just cheapest | **Shipped** | model tiering in `openrouter_api_client.py` |
| 6 | Level 2: skill self-triggers on routine sub-tasks | **Shipped** | `~/.claude/skills/waterfall/SKILL.md` |
| 7 | Level 2: automatic nudge hook, no judgment call needed | **Shipped** | `router/hooks/user_prompt_submit.py` |
| 8 | Level 3: hard per-call token/size limits ("the Ringer") | **Shipped** (2026-08-05) | `router/hooks/pre_tool_use.py` |
| 9 | Cross-session "have I already answered this" cache | **Shipped** (2026-08-05) | `router/cache.py` |

**9 of 9 proposals are now shipped as code.**

### The Ringer (#8), specifically

`router/hooks/pre_tool_use.py` is a `PreToolUse` hook that hard-blocks
(not nudges) a tool call that would dump an entire large file into
context in one shot: a `Read` with no `offset`/`limit` against a file
over the cap (default 8,000 estimated tokens, `WATERFALL_RINGER_CAP_TOKENS`
to override), or a single output-heavy shell command invoked against
exactly one file with nothing else on the line -- Bash
`cat`/`less`/`more`/`xxd`/`hexdump`/`od`/`base64`, PowerShell
`Get-Content`/`type`/`Format-Hex`. Reads that already specify
`offset`/`limit` are trusted and never capped. Any pipe, redirect, `;`,
`&&`, or a second file argument takes a shell command out of scope
entirely -- only a bare whole-file-to-stdout dump matches, by design, to
keep false positives near zero. Denial reasons are shown back to Claude
so it can retry narrower (offset/limit, or Grep) instead of just
failing. Fails open (allows) on any error, missing file, or unparseable
command. A bug here must never be able to brick every tool call in a
session.

**Explicitly out of scope, not silently dropped**: commands whose
output size isn't tied to a single file's on-disk size -- `find`,
`git log`, unbounded `grep`/`rg`, `curl`. A pre-execution hard cap on
those isn't possible without running them first; that's a real
boundary of what a PreToolUse hook can enforce, not an oversight.

**Real bug this caught in its own build**: the first version parsed
shell commands with `shlex.split(cmd, posix=True)`. POSIX mode treats
backslash as an escape character, so on this Windows machine it silently
stripped the backslashes out of every path (`C:\Users\...` →
`C:UsersAppData...`), which broke the file-size lookup and made the cap
fail open on *every single call*, cat included -- undetected until the
test suite (which does construct real Windows paths) turned red across
14 tests. Fixed with `posix=False` plus manual quote-stripping. A
reminder that "fail open on error" as a safety default can mask a bug
that defeats the feature entirely if nothing is actually exercising the
success path with realistic inputs.

This is the one mechanism from the list above that actually shrinks
reused-input on an *already-running* thread, rather than just diverting
new work before it's generated; see "The gap" below, which this now
partly closes for the single-large-file case specifically. It does not
address the general reused-input compounding problem (a long thread's
accumulated history still gets resent every turn); that's still a
session-hygiene problem, not a per-call one.

### Cross-session cache (#9), specifically

`router/cache.py` is a disk-backed, exact-match cache
(`~/.claude/waterfall_response_cache.json`) keyed by a normalized
(whitespace/case-collapsed) hash of the *routed* text: the sub-task
text `SmartRouter.route_with_api()` sends to the free model, not the raw
human prompt. Wired into `route_with_api()`: on an identical routed ask
within 7 days (`ttl_seconds`, configurable), the cached response is
served instead of a second real OpenRouter call: `waterfall route`
prints `served from cache`, cost/tokens/elapsed all report `0`. A miss
calls the model as before and writes the result to cache. Entries past
the TTL are treated as a miss, not silently served stale.

Deliberately **not** a semantic cache: two differently-worded asks for
the same thing are two different keys and both cost a real call. It only
catches byte-identical (post-normalization) repeats, which is a narrow
but real case: the same mechanical sub-task asked again, maybe in a
different session days later.

Verified live 2026-08-05 against the real OpenRouter API and a real key:
`waterfall route "write a one-line docstring for a function that adds
two numbers"` cost $9.2e-07 and took 1.15s the first time; the identical
call immediately after printed `served from cache`, cost `$0.0`, `0 in /
0 out` tokens, and returned the exact same text, instantly.

Alongside those, the transcript's other recommendations were always
behavioral, not mechanical, and stay that way: edit-not-retry, batch
related asks, start a clean thread when the job changes, ask for only
the length you need, search narrowly instead of dumping whole files.
Nothing enforces these: they're a discipline this session is supposed
to hold itself to, not a control.

## The gap the shipped tools don't close

`classify`/`route` only act on **new** work before it's generated: they
keep mechanical output from being generated inline by Claude in the
first place. They do **not** shrink reused-input for a thread that's
already long: once anything (Claude's own output, or a routed model's
output stitched back in) lands in conversation history, it gets resent
and re-billed as reused-input on every subsequent turn in that session,
regardless of who originally produced it.

The single biggest lever against reused-input specifically is session
hygiene: starting a fresh thread when the topic changes, `/compact`ing
instead of letting a thread run forever, not re-reading/re-pasting large
files repeatedly. That's still mostly an unenforced habit: the Ringer
(#8) forces the "don't dump one huge file whole" case specifically, and
the cache (#9) forces the "don't redo an identical routed sub-task"
case specifically, but a long thread built up from many small,
individually-under-cap, non-repeating turns is still unaddressed.
**All 9 proposed countermeasures are now shipped, and the core
reused-input compounding problem still isn't solved**: every mechanism
above attacks a specific, narrow footgun (one huge file, one repeated
ask); none of them cap or shrink a long thread's *accumulated*, varied
history, which is what `waterfall claude-usage --by-day` actually shows
driving the 65–96% reused-input share. That would need something that
doesn't exist yet in any proposed form here: a real cap on session/
thread length itself, or automatic compaction, enforced rather than
habitual.
