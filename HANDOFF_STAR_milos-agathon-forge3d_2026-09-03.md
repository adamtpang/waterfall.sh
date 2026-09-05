# Handoff: learn from milos-agathon/forge3d

Written 2026-09-03 by the Aether root session, using the github-star-match skill. This
repo was on Adam's GitHub stars; it was reviewed against waterfall.sh, this file was
written, and the star was removed. Popularity is not evidence of fit; the verdict
below is about a concrete local seam or the lack of one.

- **Verdict:** `defer`. A Rust, headless WebGPU renderer exposed to Python; the demo video's shader backgrounds failed precisely because headless Chrome could not render WebGL.
- **Local owner repository:** `waterfall.sh`
- **Local evidence paths:**
  - waterfall.sh/demo-video/src/components/remocn/shader-grain-gradient.tsx
  - waterfall.sh/demo-video/remotion.config.ts
- **Upstream:** https://github.com/milos-agathon/forge3d
- **Reviewed commit:** `caf2319` on `main` (2026-08-29)
- **Upstream layout at that commit:** .cargo,.claude,.github,assets,bench,benches,cmake,data,docs,examples,python,scripts,shader
- **License conclusion:** MIT. MIT. Python plus Rust toolchain is a real install cost; only worth it if the trigger fires.
- **Smallest experiment, or deferred trigger:** Trigger: a second attempt at shader backgrounds for the demo. Then render one frame headlessly with forge3d and composite it, instead of fighting Chrome.
- **Validation before adoption:** run the local project's own tests after any change, keep the reviewed commit pinned above, and preserve upstream license notices if any file is copied.

Boundary, per the skill: this analysis authorizes no installation or code change.
Implement only when Adam asks in that project's own session. Do not add the upstream
repo as `kin` in repos.yaml; it is a reference, not a Repo Rep.
