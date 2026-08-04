# waterfall.sh

Cascade to the best model. Automatically.

Classifies every prompt, routes the routine part to the cheapest capable
model on OpenRouter's live Arena-ranked catalog, and only surfaces the
genuinely hard part for Claude. Built to make a Claude Code / Claude Pro
plan's quota last the full day instead of the first hour.

## Layout

```
index.html, vercel.json, robots.txt, sitemap.xml   Landing page (static, zero build)
router/                                             The actual routing logic (Python)
  openrouter_api_client.py                          Direct OpenRouter API client
  smart_router.py                                   Classify -> split -> route -> stitch
  classifier/                                        Local, zero-API prompt classifier
  tests/                                              Unit tests (no network required)
CLAUDE.md                                           Full project handoff / status -- read this first
```

## Quick start (landing page)

```bash
npx vercel deploy        # ships to a *.vercel.app URL
npx vercel --prod        # once waterfall.sh is purchased and attached
```

## Quick start (router)

```bash
cd router
pip install -r requirements.txt   # just `requests`
export OPENROUTER_API_KEY=sk-or-...   # get one at https://openrouter.ai/keys
python3 -m unittest discover -s tests -p "test_*.py"

python3 cli.py classify "your prompt here"     # free, no network
python3 cli.py route "your prompt here"        # routes + logs to the savings ledger
python3 cli.py stats                           # what's been kept off Claude so far
```

Or install it as a command (`pip install -e .` from the repo root, then
`waterfall classify/route/stats/models ...`).

`route` auto-falls back through the next-cheapest OpenRouter model if the
cheapest one is down or rate-limited — that's the "cascade" the name
refers to, not just a single cheapest-model pick.

See `CLAUDE.md` for full status, what's built, and what's still open.
