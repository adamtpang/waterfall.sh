---
name: next
description: Inspect a project's real current state, present two to four evidence-grounded next-step choices, and stop for the user's selection. Use when the user asks what to do next or how to move a project forward. Do not implement an option before the user chooses it.
---

# Next

The question is the deliverable. Inspect first, present real choices, and wait.

## Gather evidence quickly

Spend at most a few minutes checking what exists:

1. Read `git status` and the latest ten commits, or the equivalent history for a
   non-code project.
2. Read `NORTH_STAR.md`, a roadmap, or the current milestone if one exists.
3. Search README files, task lists, and TODO or FIXME markers for open work.
4. Account for anything explicitly deferred in the current conversation.
5. Check recently modified files to identify work already in motion.

Skip missing sources without turning the inspection into a blocker.

## Build the choice set

Present two to four candidates. Every option must cite evidence found above and say
roughly how large the work is. Do not add generic filler to reach four choices.

If only one sensible move exists, present it plus the host's normal free-form answer
path. If the repository is empty, say so and ask which first artifact to create.

## Ask and stop

Use the host's structured user-input tool when available. Otherwise present the
choices in the final response and ask the user to reply with a letter or title.

Do not choose silently. Do not start implementing. After the user picks, proceed
without asking them to reconfirm the same choice.

## Output shape

```text
Current state: one to three concrete lines.

A. Candidate, evidence, and rough size
B. Candidate, evidence, and rough size
C. Candidate, evidence, and rough size

Which should I do?
```

Keep it short and mobile-friendly. Do not use em dashes.
