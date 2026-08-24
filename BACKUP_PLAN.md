# BACKUP_PLAN.md

What to do when Claude runs out, so progress continues instead of stopping.

Written 2026-08-24, at 93% of the weekly Claude quota with 29.7h to reset.

---

## The ladder

```text
Claude  ->  Codex  ->  Grok  ->  waterfall / OpenRouter
$200        $20        $30       ~$0 (free models)
```

**Pick the rung when you open the session. You will not switch mid-session.**

That is not a preference, it is what the data says. waterfall's own nudge hook
fired 3,920 times and produced 6 actual routes. A plan that depends on noticing
a limit and switching in the moment fails the same way. The choice has to
happen before work starts.

### What each rung is for

| Rung | Give it | Why |
|---|---|---|
| **Claude** | Architecture, subtle bugs, taste calls, multi-file refactors | Work where being wrong is expensive and the fix is not obvious |
| **Codex** | Well-specified implementation with clear acceptance criteria | You already know what "done" looks like before starting |
| **Grok** | Parallel per-project work | `waterfall tabs` already opens Grok per project |
| **waterfall** | Mechanical generation needing no repo context | Exactly what the classifier scores `free` |

### The thing waterfall does NOT solve

waterfall routes **sub-tasks** to cheap models. Claude quota burn comes from
**long conversations with accumulating context**, which is a different problem.
`TOKEN_COMPOUNDING.md` says so plainly: 93.3% reused-input share, and all 9
shipped countermeasures attack narrow footguns, not a thread's non-repeating
history.

So waterfall cannot absorb Claude's load. **The ladder works by moving whole
workstreams to other subscriptions, not by shaving sub-tasks off Claude.**
Expecting otherwise is how you end up at 93% again.

---

## Before you switch: run the sync

The handoff files other agents read are generated, not hand-written. They go
stale silently. On 2026-08-24 they were 6 to 8 days behind and knew nothing
about a week of work.

From `C:\Users\adamp\Aether` (not the project directory):

```bash
node .codex/sync-claude-to-codex.js
```

For Grok:

```bash
node .grok/sync-to-grok.js
```

### What the sync actually gives you, and what it does not

**It gives you mechanical continuity**: last session id, last user ask, files
recently touched, per-project `CODEX_CONTINUE_FROM_CLAUDE.md`, and a refreshed
`AGENTS.md`.

**It does not give you semantic continuity.** It is a transcript-pointer
generator, not a decision log. It will tell Codex which files were edited. It
will not tell Codex *why*, or what was decided, or what was tried and rejected.

**That knowledge lives in `CLAUDE.md`, and `AGENTS.md` is a mirror of it.**
Which means the sync is only as good as `CLAUDE.md` is current. If `CLAUDE.md`
is stale, the mirror faithfully propagates the staleness. This is exactly how
the 2026-08-24 gap happened: a week of work went into `DESIGN.md` and commit
messages, `CLAUDE.md` was not updated, so `AGENTS.md` inherited the hole.

**So the real sync ritual is two steps, in this order:**

1. Update `CLAUDE.md` with what was decided and why. This is the load-bearing
   step. Do it before the quota runs out, not after.
2. Run the sync script so `AGENTS.md` and the CONTINUE files mirror it.

Doing step 2 without step 1 produces a confident-looking handoff with nothing
in it.

---

## Resuming in another agent

**In Codex**: it reads `AGENTS.md` on open. Also point it at
`CODEX_CONTINUE_FROM_CLAUDE.md` for the last stop point.

**In Grok**: `GROK_CONTINUE_FROM_CLAUDE.md`, plus `.grok/TODAY.md`.

**Back in Claude later**: `CLAUDE_CONTINUE_FROM_GROK.md`, then `CLAUDE.md`.

First message to the new agent, roughly:

> Read `AGENTS.md` and `CODEX_CONTINUE_FROM_CLAUDE.md` in this repo. Then
> continue: <the specific next task>. Do not re-derive state.

Give it the specific task. "Continue where Claude left off" invites it to
rediscover context you already paid for.

---

## Checking which rung has room

```bash
waterfall usage-pace --used-pct 93 --reset-day tuesday --reset-hour 16 \
  --session-pct 7 --session-hours-remaining 1.72 --model-pct fable=54
```

For a subscription on its own reset clock (Codex, Grok), use `--bucket`:

```bash
waterfall usage-pace --used-pct 93 --bucket codex=15:720:400 --bucket grok=60:720:200
```

It names the binding constraint and the rung with the most headroom.

**Known gap**: Codex exposes no local usage data. Verified 2026-08-18 across
all 31 `.codex-global-state.json` files: no usage, token, or cost keys. Grok's
monitoring is OpenTelemetry export to an external collector, off by default.
So Codex and Grok numbers are self-reported by hand, not measured.

---

## Open decisions

**The $80 Codex 5x upgrade: deferred.** You cannot currently tell whether you
are maxing the $20 tier, because Codex exposes no usage data. Buying 5x without
evidence you have exhausted 1x, at $250/mo going to $330/mo against $0 MRR,
is spending against a guess.

The test that settles it: run the ladder for one full week. If Codex visibly
caps out mid-week while Claude is also dry, buy it. If not, that is $960/year
kept.

**Two things to do by hand, neither needing an agent:**

1. **Cap the OpenRouter key.** It is pay-as-you-go with no limit set. $0 spent
   so far only because ox-alpha is free. Set a hard credit limit at
   <https://openrouter.ai/keys> so "one OpenRouter budget" is enforced rather
   than hoped.
2. **Find where `OPENROUTER_API_KEY` is set.** Not in `.bashrc`,
   `.bash_profile`, `.profile`, or any Windows env scope, yet `bash -lc` has
   it. Until that is known, the revoked-key-file failure can silently recur.
