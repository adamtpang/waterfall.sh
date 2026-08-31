# Contributing to waterfall

waterfall is source-available: the code here is real and working, not a stub, and
issues and pull requests are genuinely welcome. It isn't openly licensed, since the
cascade CLI and local board are also sold as a $30 founding license (see `OFFER.md`)
-- browsing, running locally, and contributing back are fine; redistributing or
reselling the code is not.

## Before opening a PR

- Check `CLAUDE.md` first. It's the live, current source of truth for what's built,
  what's in progress, and what's deliberately not done yet (see its "Not done yet"
  section) -- a real handoff doc, not marketing copy.
- Run the existing test suite (`router/tests/`) before and after your change. It's
  real: client, cascade fallback, tiering, the Ringer hook, the response cache, the
  hook log, the usage-pace calculator, and more, all with no network calls required.
- Keep changes scoped. This repo has a documented history of narrow, verified fixes
  (see `CLAUDE.md`'s entries) rather than broad rewrites -- match that style.

## Good first issues

- The reused-input compounding problem (`TOKEN_COMPOUNDING.md`'s "The gap" section):
  the 9 shipped countermeasures each attack a specific footgun, not a long thread's
  accumulated, non-repeating history, which is what actually drives the 65-96%
  reused-input share seen in real usage. A real fix here would be a genuine
  contribution, not a cosmetic one.
- Quality-aware model selection: `pick_cheap_models()` currently picks purely by
  price. LMArena's Agent Arena leaderboard (model-vs-model performance across 48
  models) is a real, live data source that isn't wired in yet.
- Anything in `CLAUDE.md`'s "Not done yet" section.

## Workshop submissions

The free resource catalog lives in `workshop/catalog.json`. A catalog change
must include an official source, the recurring task it serves, a checked date,
and one honest reason not to enable it. Treat pricing, plan access, and benchmark
ranks as dated snapshots.

Do not submit affiliate links, copied credentials, local configuration, absolute
paths, account identifiers, private project details, or third-party skill source
without a license that clearly covers the exact artifact. Registry presence and
GitHub stars are discovery signals, not security or quality endorsements.

## Reporting a bug

Open a GitHub issue with the real command you ran, the real output, and (if
relevant) which OS -- this project has already caught several real cross-platform
bugs (Windows path escaping, `HOME` not overriding `Path.home()`), so platform
specifics matter here more than in most CLIs.
