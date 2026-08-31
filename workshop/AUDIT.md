# Public skill and MCP audit

Snapshot: 2026-08-30

This is the public-safe result of a local audit across Claude, Codex, and Grok skill
roots plus configured MCP servers. Raw histories, configuration files, credentials,
private paths, and quarantine manifests are not part of this repository.

## Skill result

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

## MCP result

The audit found one clear daily default: a local JavaScript scratchpad used for
small computations and data shaping. Everything else earned an optional state.

| MCP class | Observed signal | Default | Public decision |
|---|---:|---|---|
| local JavaScript scratchpad | 478 calls | daily | document the pattern, no machine config |
| Firecrawl | 56 calls | optional | link official source and docs |
| Neon | 10 calls | optional | link official source and require scoped credentials |
| browser, messaging, music, and project-specific servers | mixed | off | omit private configuration and publish only safe upstream links |

## What was not published

- API keys, bearer headers, environment values, account IDs, and database URLs.
- Absolute paths, hostnames, local ports, and private repository names.
- Skills that read personal notes, communications, finances, or account state.
- Tool-call transcripts and raw prompt history.
- Third-party skill source copied without a clear redistribution license.

The catalog publishes decisions and source links, not a clone of a personal machine.
