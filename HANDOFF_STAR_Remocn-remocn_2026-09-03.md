# Handoff: learn from Remocn/remocn

Written 2026-09-03 by the Aether root session, using the github-star-match skill. This
repo was on Adam's GitHub stars; it was reviewed against waterfall.sh, this file was
written, and the star was removed. Popularity is not evidence of fit; the verdict
below is about a concrete local seam or the lack of one.

- **Verdict:** `adopt`. Already in use for the waterfall.sh demo video (demo-video/); this records the reviewed commit and the one proven failure.
- **Local owner repository:** `waterfall.sh`
- **Local evidence paths:**
  - waterfall.sh/demo-video/src/Composition.tsx
  - waterfall.sh/demo-video/components.json (registry @remocn)
  - waterfall.sh/demo-video/remotion.config.ts
- **Upstream:** https://github.com/Remocn/remocn
- **Reviewed commit:** `2534877` on `main` (2026-09-04)
- **Upstream layout at that commit:** .github,app,components,config,content,docs,hooks,lib,public,registry-artifacts,registry,sc
- **License conclusion:** MIT. MIT. Components are copied into the repo (shadcn model), so pin this commit in the handoff and re-diff before pulling newer registry versions.
- **Smallest experiment, or deferred trigger:** Retry the shader background (shader-grain-gradient) with a headless Chrome that has WebGL, or a software GL flag; the delayRender gate timed out twice in Remotion's Chrome Headless Shell 149.
- **Validation before adoption:** run the local project's own tests after any change, keep the reviewed commit pinned above, and preserve upstream license notices if any file is copied.

Boundary, per the skill: this analysis authorizes no installation or code change.
Implement only when Adam asks in that project's own session. Do not add the upstream
repo as `kin` in repos.yaml; it is a reference, not a Repo Rep.
