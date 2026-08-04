"""waterfall.sh router -- classify a prompt, cascade the routine part
through the cheapest capable OpenRouter models (auto-falling back to the
next one if a model is down or rate-limited), and hand back what's left
for Claude plus a ledger of what it saved.

Every module here also imports cleanly bare (`from smart_router import
SmartRouter`) with the router/ directory on sys.path, not just as this
package -- see smart_router.py's import fallback. That's deliberate: it's
how this code got ported out of a larger monorepo, and it's how a future
embedder can drop router/ into another project without pulling in a
package manager.
"""
