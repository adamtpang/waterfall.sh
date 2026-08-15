# router

The actual routing logic. Ported (unchanged) from a Claude-Token-Saver
fork built in the same Cowork session, stripped of everything that was
Windows-GUI / browser-automation specific; this half was always plain,
portable Python.

- `openrouter_api_client.py` -- real HTTP calls to OpenRouter, no browser.
  `generate_with_usage()` cascades through the N cheapest capable models
  (`pick_cheap_models(n)`) -- if one is down or rate-limited it
  automatically falls back to the next-cheapest instead of failing.
- `smart_router.py` -- classify, split, route the easy part, stitch the
  result back into what's left for Claude.
- `classifier/` -- local zero-API prompt classifier (needs
  `classifier/data/keywords.json` at runtime -- it's included).
- `tracker.py` -- append-only JSONL savings ledger
  (`~/.claude/token_savings.jsonl`) + summary stats.
- `cli.py` -- `classify` / `route [--dry-run]` / `stats` / `models`. Run
  with `python3 cli.py ...`, `python3 -m router.cli ...` from the repo
  root, or as the `waterfall` command after `pip install -e ..`.
- `tests/` -- 21 unit tests, no network calls.

Run `python3 -m unittest discover -s tests -p "test_*.py"` from this
directory to verify (or `pytest tests/ -q` if pytest is installed).
