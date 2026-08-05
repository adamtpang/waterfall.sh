# Token compounding — source notes and mitigation status

Reference doc, not the original source. This is the distilled summary that
was already living inside `CLAUDE.md`'s "Design principles" section,
pulled out on 2026-08-05 so it stands on its own. **The original
transcript itself isn't saved anywhere in this repo or the Obsidian
vault** — if you want it re-derived faithfully, it needs to come from
wherever that Nate B. Jones source actually lives (not reconstructed from
memory here).

## The core mechanism

Every turn in a conversation resends the whole prior conversation as
input — there's no native memory. Claude Code's prompt caching discounts
that resend heavily (cache-read tokens bill far below fresh-input price),
but it doesn't eliminate the resend: reused tokens still count against
raw volume, and volume is what trips session/weekly usage limits. This
is confirmed against this machine's own transcripts (see
`waterfall claude-usage --by-day`) — reused-input share has sat at
65–96% on every single day since transcripts started (2026-04-25), and
raw daily volume grew from ~15–30M reused tokens/day in April to
1–2.5 **billion**/day by July.

## Proposed countermeasures, and what's actually been built

| # | Countermeasure | Status | Where |
|---|---|---|---|
| 1 | Classify/split before sending — decide free/split/claude before generating | **Shipped** | `router/classifier/`, `waterfall classify` |
| 2 | Auto-fallback across models so a down/rate-limited cheap model doesn't force the call up to Claude | **Shipped** | `router/openrouter_api_client.py` cascade |
| 3 | Ledger everything routed away, so savings are data not vibes | **Shipped** | `router/tracker.py`, `waterfall stats` |
| 4 | Ledger Claude's *own* real consumption as a baseline | **Shipped** (2026-08-05) | `router/claude_usage.py`, `waterfall claude-usage` |
| 5 | Right model for the job, not just cheapest | **Shipped** | model tiering in `openrouter_api_client.py` |
| 6 | Level 2 — skill self-triggers on routine sub-tasks | **Shipped** | `~/.claude/skills/waterfall/SKILL.md` |
| 7 | Level 2 — automatic nudge hook, no judgment call needed | **Shipped** | `router/hooks/user_prompt_submit.py` |
| 8 | Level 3 — hard per-call token/size limits ("the Ringer") | **Not built** | — |
| 9 | Cross-session "have I already answered this" cache | **Not built** | — |

**7 of 9 concrete proposals are shipped as code.** The other two are the
harder, more invasive ones — enforcement rather than routing.

Alongside those, the transcript's other recommendations were always
behavioral, not mechanical, and stay that way: edit-not-retry, batch
related asks, start a clean thread when the job changes, ask for only
the length you need, search narrowly instead of dumping whole files.
Nothing enforces these — they're a discipline this session is supposed
to hold itself to, not a control.

## The gap the shipped tools don't close

`classify`/`route` only act on **new** work before it's generated — they
keep mechanical output from being generated inline by Claude in the
first place. They do **not** shrink reused-input for a thread that's
already long: once anything (Claude's own output, or a routed model's
output stitched back in) lands in conversation history, it gets resent
and re-billed as reused-input on every subsequent turn in that session,
regardless of who originally produced it.

The single biggest lever against reused-input specifically is session
hygiene — starting a fresh thread when the topic changes, `/compact`ing
instead of letting a thread run forever, not re-reading/re-pasting large
files repeatedly. That's habit #9 above in list form, unenforced by any
of the shipped code. The unbuilt hard-cap idea (#8) is the only proposed
mechanism that would actually force this rather than rely on discipline.
