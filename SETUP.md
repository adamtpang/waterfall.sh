# Beta setup: measuring real savings across more than one user

The CLI (`classify`/`route`/`stats`) is covered in `README.md`. This
covers the two automatic hooks, the nudge and the Ringer, since those
are what actually need to be running on someone else's machine before
their numbers mean anything. Nothing here works without a real person
running Claude Code normally for a few days afterward; there's no way to
simulate that.

## Fast path: one-line install

```bash
curl -sSL https://raw.githubusercontent.com/adamtpang/waterfall.sh/main/install.py | python3
```

Requires `git` and `python3` on PATH. This clones into `~/.waterfall`,
installs the one dependency, and wires the two hooks into your
`~/.claude/settings.json` automatically, merging into whatever's
already there, backing it up first. Safe to re-run. If this works,
skip straight to step 3 below. If you'd rather see exactly what it's
doing (or it doesn't work for some reason), the manual steps follow.

## 1. Clone and install

```bash
git clone https://github.com/adamtpang/waterfall.sh
cd waterfall.sh
pip install -r router/requirements.txt
```

Note the **full absolute path** to wherever you cloned this; you'll
need it in step 2. Example: `/home/alex/dev/waterfall.sh` or
`C:/Users/alex/dev/waterfall.sh`.

## 2. Wire the hooks into your global Claude Code config

Open `~/.claude/settings.json` (create it if it doesn't exist, just
`{}` to start). Add a `"hooks"` key with these two entries, replacing
`<WATERFALL_PATH>` with your actual path from step 1:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"<WATERFALL_PATH>/router/hooks/user_prompt_submit.py\"",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read|Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"<WATERFALL_PATH>/router/hooks/pre_tool_use.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

If your `~/.claude/settings.json` already has other keys (permissions,
other hooks, etc.), merge these into the existing `"hooks"` object
instead of replacing the file, don't clobber your existing config.

**If you already have your own `PreToolUse`/`UserPromptSubmit` hooks**,
append these as additional entries in the same array rather than
replacing what's there (multiple hook entries per event are normal and
all run).

Start a new Claude Code session (or restart) for the config to take
effect.

## 3. Just use Claude Code normally

No behavior change to notice: the nudge only adds a one-line suggestion
after routine-looking prompts, and the Ringer only blocks a whole-file
`Read`/`cat`/etc. against something over ~8,000 estimated tokens (a real
mistake, not normal work) with a message telling Claude how to retry
narrower. Neither should get in your way if you're not hitting either
case.

## 4. After a few days, report back

```bash
python3 router/cli.py dashboard --since-days 5
```

or the two commands it's built from, if you'd rather send raw numbers:

```bash
python3 router/cli.py hook-log --since-days 5
python3 router/cli.py stats
```

Send the output back (a screenshot of `dashboard` is fine). That's the
whole ask: no code changes, no config beyond step 2, no need to touch
OpenRouter/`route` at all unless you want to try that separately (needs
its own `OPENROUTER_API_KEY`, see `README.md`). Fair warning:
`dashboard` scans your full local Claude Code transcript history for
the reused-input trend, which can take a couple of minutes if you have
a lot of history.

## Why this matters before claiming any real number publicly

The first real numbers here came from one unusually heavy user (19
simultaneous projects in under a week), not representative of a normal
single-project workflow, and not enough people to know if the pattern
holds. A dollar or token figure from one person, however real, isn't
evidence of what a typical user would see. This file exists so that
changes before anything gets marketed.
