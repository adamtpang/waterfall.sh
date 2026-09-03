# Public skill and MCP audit

Snapshot: 2026-09-03

This is the public-safe result of a local audit across shared agent, Claude, Codex,
and Codex plugin skill surfaces plus configured MCP servers. Raw histories,
configuration files, credentials, private paths, and quarantine manifests are not
part of this repository.

## Current inventory result

- 565 active-surface skill files were found across four agent surfaces.
- Those files declared 352 unique skill names.
- 183 names had multiple copies across surfaces.
- 61 duplicated names had different contents, so behavior can vary by host.
- 30 MCP configuration entries resolved to 17 unique names across the inspected
  hosts.
- 21 Codex remote plugin packages were installed.

The full names-only report stays local. It deliberately excludes commands,
arguments, URLs, headers, environment values, credentials, and project paths.
The strongest finding is consolidation, not expansion: duplicated skills and
drifted copies create more immediate risk than a missing general-purpose skill.

## Earlier cleanup baseline

- 214 standalone skill names were reviewed.
- 84 names with no observed invocation or read were removed from active roots.
- 130 active standalone skills remained after cleanup.
- Mirrored copies were quarantined locally instead of deleted, so the cleanup was
  reversible.

Observed local usage is a routing signal, not a quality score. A skill can be useful
but rare, or heavily invoked because a hook keeps rediscovering it.

| Skill or class | Observed signal | Public decision | Reason |
|---|---:|---|---|
| `browser-harness` | 154 reads | keep private | Contains machine-specific browser and authentication behavior |
| `land-and-deploy` | 123 reads | link upstream | Maintained as part of gstack |
| private inbox processing | 105 reads | keep private | Operates on personal notes and local files |
| document tools | 83 reads | link upstream | Bundled or vendor-maintained implementations |
| `repos-chat` | 68 reads | link upstream | Already has a public source repository |
| `next` | 47 reads | publish sanitized | General project decision pattern, no private data required |
| private cross-agent sync | 46 reads | keep private | Contains machine paths and local ledgers |
| `ship` | 29 reads | link upstream | Maintained as part of gstack |
| `research-report` | recurring | publish sanitized | General research discipline, safe after removing personal references |
| `waterfall` | project skill | publish sanitized | Core routine-work routing behavior for this repository |

## Three-skill bundle review

A supplied bundle containing `direct-response-copy`, `seo-content`, and
`content-atomizer` was extracted into a local quarantine but not installed or
copied into this repository.

- The bundle contains no redistribution license.
- Its `CLAUDE.md` files contain local activity-memory material that must not be
  published.
- The skills and reference files are large enough to impose substantial context
  cost.
- `content-atomizer` asks the agent to inspect `.env` for social scheduling keys
  and can connect to publishing workflows. That violates a least-secret-access,
  draft-only posture.
- Several instructions assume private memory files that are not included.

The safe path is to measure whether these workflows recur, then write smaller
project-scoped skills with explicit inputs. Any content workflow should produce
drafts only and leave external publishing to the user.

## MCP result

The audit found one clear daily default: a local JavaScript scratchpad used for
small computations and data shaping. Everything else earned an optional state.

| MCP class | Observed signal | Default | Public decision |
|---|---:|---|---|
| local JavaScript scratchpad | 478 calls | daily | document the pattern, no machine config |
| Firecrawl | 56 calls | optional | link official source and docs |
| Neon | 10 calls | optional | link official source and require scoped credentials |
| browser, messaging, music, and project-specific servers | mixed | off | omit private configuration and publish only safe upstream links |

The 2026-09-03 directory pass produced one practical MCP pilot: Context7 for
version-specific public library documentation. It also produced one narrowly
useful skill candidate: GitHub's MCP security audit. Neither was installed during
the audit. Existing GitHub, Firecrawl, filesystem, database, notes, and browser
capabilities should be consolidated before adding equivalents from a directory.

## What was not published

- API keys, bearer headers, environment values, account IDs, and database URLs.
- Absolute paths, hostnames, local ports, and private repository names.
- Skills that read personal notes, communications, finances, or account state.
- Tool-call transcripts and raw prompt history.
- Third-party skill source copied without a clear redistribution license.

The catalog publishes decisions and source links, not a clone of a personal machine.
