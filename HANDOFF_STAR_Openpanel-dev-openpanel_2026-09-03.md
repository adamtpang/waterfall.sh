# Handoff: learn from Openpanel-dev/openpanel

Written 2026-09-03 by the Aether root session, using the github-star-match skill. This
repo was on Adam's GitHub stars; it was reviewed against waterfall.sh, this file was
written, and the star was removed. Popularity is not evidence of fit; the verdict
below is about a concrete local seam or the lack of one.

- **Verdict:** `defer`. Real product-analytics platform, but self-hosting needs Postgres, ClickHouse, and Redis, and AGPL means run it as a service, never copy its code into the product.
- **Local owner repository:** `waterfall.sh`
- **Local evidence paths:**
  - waterfall.sh/CLAUDE.md (analytics is not a current section)
  - Aether/AETHER_STANDARD.md item on analytics (Vercel Analytics is the fleet default)
- **Upstream:** https://github.com/Openpanel-dev/openpanel
- **Reviewed commit:** `3060ca1` on `main` (2026-09-04)
- **Upstream layout at that commit:** .claude,.github,.vscode,.zed,admin,apps,docker,packages,patches,scripts,self-hosting,sh,te
- **License conclusion:** AGPL-3.0. AGPL-3.0: hosted use is fine; code must not be vendored into waterfall.sh.
- **Smallest experiment, or deferred trigger:** Trigger: waterfall.sh has at least one non-Adam user whose behavior is worth measuring. Then stand it up on one project only, per the earlier pilot decision.
- **Validation before adoption:** run the local project's own tests after any change, keep the reviewed commit pinned above, and preserve upstream license notices if any file is copied.

Boundary, per the skill: this analysis authorizes no installation or code change.
Implement only when Adam asks in that project's own session. Do not add the upstream
repo as `kin` in repos.yaml; it is a reference, not a Repo Rep.
