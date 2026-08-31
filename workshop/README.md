# Waterfall Workshop

Waterfall is a working developer workshop: a dated, evidence-backed collection of
models, coding surfaces, agent skills, and MCP servers that have earned a place in
a real Claude and Codex workflow.

The public catalog is available at [`/workshop/`](./index.html). Its machine-readable
source is [`catalog.json`](./catalog.json).

## Start here

Use Claude and Codex together. Do not wait to exhaust one plan before opening the
other.

1. Give one agent ownership of implementation.
2. Give the other a different job: planning, adversarial review, or a clean-room
   investigation.
3. Run independent work in separate worktrees.
4. Keep shared project policy in `AGENTS.md`, with provider-specific notes kept
   small.
5. Transfer only when quota or task shape changes. A compact handoff beats copying
   a whole transcript.

Current default:

- **Claude** for ambiguity, product judgment, architecture, and hard review.
- **Codex Sol** for complex implementation and autonomous repository work.
- **Codex Terra** for everyday engineering.
- **Codex Luna or a cheap OpenRouter model** for clear, repeatable work.
- **One implements, one reviews** for any change where correctness matters.

This is a working policy, not a universal benchmark result. Check the dated model
sources in the catalog before treating any model name or rank as current.

## What “best” means here

There is no single best model, IDE, skill, or MCP server. Every catalog entry has:

- a task it is best for;
- evidence for why it is included;
- a reason not to enable it;
- a default state: hard-work, daily, routine, optional, pilot, or reference;
- a source and a checked date.

Arena rank is one signal. Local usage is another. Price, first-pass success, tool
reliability, privacy, and setup cost all matter.

## Public starter skills

These are sanitized, provider-neutral versions of high-value workshop skills:

- [`next`](./skills/next/SKILL.md): inspect the project, present grounded choices,
  and wait for the user to choose.
- [`research-report`](./skills/research-report/SKILL.md): current, sourced research
  with explicit uncertainty.
- [`waterfall`](./skills/waterfall/SKILL.md): route routine work to a cheaper model
  without routing secrets or context-heavy tasks.

Copy a skill directory into the skill location supported by your agent. Tool names
vary across Claude, Codex, and other hosts, so read the file before installing it.

## Audit policy

The source audit covered all active standalone skills and custom MCP definitions on
the maintainer's machine. The public result is deliberately smaller.

- Observed use is evidence of usefulness, not proof of quality.
- Never-used entries leave the active set before the catalog is curated.
- Third-party skills are linked to their source instead of copied.
- Personal automations, credentials, account identifiers, local paths, message
  integrations, and private project knowledge are never published.
- MCP servers stay optional unless their benefit clearly exceeds the context,
  permission, and maintenance cost they add.

See [`AUDIT.md`](./AUDIT.md) for the public-safe audit record.

## Refresh cadence

- Arena snapshots: weekly.
- Vendor model and plan pages: monthly or after a release.
- OpenRouter metadata: live at route time.
- IDE, skill, and MCP entries: quarterly, plus whenever a source moves or a tool is
  removed from the working setup.
- Waterfall's own task evaluation: after every meaningful model or harness change.

## Contribute a resource

Open a pull request that changes `catalog.json`. Include an official source, the
task it is for, a checked date, and one honest reason not to use it. Affiliate links
and unsourced “best” claims will not be accepted.

“Free” means no Waterfall paywall. Every linked project's own license, pricing, and
terms still apply.
