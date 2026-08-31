---
name: waterfall
description: Classify self-contained routine work before using an expensive model, route eligible work through the Waterfall CLI, and keep architecture, security, secrets, and context-heavy changes with the primary agent.
---

# Waterfall

Use the cheapest capable model for routine work without sacrificing correctness or
privacy.

## Classify before generating

Run classification before writing any substantial subtask in these categories:

1. Renaming or reformatting existing text without a logic change.
2. Boilerplate such as fixtures, stubs, and repetitive configuration.
3. Extracting, transforming, or summarizing self-contained supplied text.
4. Mechanical one-off work with no architecture or product decision.

```bash
waterfall classify "<self-contained subtask>"
```

- `claude`: keep the task with the primary agent.
- `free` or `split`: route the eligible part.

```bash
waterfall route "<self-contained subtask>"
```

Review the routed result. Use it when correct. Fix or discard it when it is not.

## Existing-file safety rule

Never route a bare request such as “edit file X.” The routed model cannot inspect the
repository unless the host explicitly gives it that capability.

1. Read the real file first.
2. Include the relevant current content in the routed prompt.
3. If the required context does not fit cleanly, do not route the task.
4. Verify the result against the actual file before applying it.

## Never route

- Secrets, credentials, private customer data, or confidential business material.
- Security decisions, architecture, migrations, or irreversible operations.
- Work that depends on conversation history or broad repository context not included
  in the routed prompt.
- Any task where a cheap answer is more expensive to verify than doing it correctly
  with the primary agent.

## Check the ledger

```bash
waterfall stats
```

Treat measured completed work as the signal. A nudge, classification, or routed call
that produced no usable result is not a saving.
