# waterfall.sh design system

Shapeable contract 1.0.0. Status: owner-approved. This file is generated from `.shapeable/design-system.json`. Edit the JSON source, then render again.

## Read this first

- Read this design-system.json and repo://waterfall.sh/ribbon.css before changing any page.
- Read contracts/waterfall-sh-owner-feedback-20261104.md for the owner's rejections and choices.
- Read shapeable.art reference/premium-pipeline-20261104.md for the build and review pipeline.

## Intent and north star

Make waterfall.sh feel as considered as Stripe while staying its own: a light page, one luminous cascade ribbon that reads as falling water, and the real local board shown large, so a developer sees the product and the price in one pass.

A developer understands in one pass that waterfall.sh is a local board that sends each prompt to the cheapest model that can do it, sees the product itself, and can buy the $30 founding license or download in one click.

## Owner preference contract

Ledger: preferences/owner-preferences.json

Site record: waterfall.sh

Latest feedback: waterfall-ribbon-home-accepted

## Identity

Signature: A single cascade ribbon (a conic gradient of #5ec6ff, #2f6bff, #6b5cff, #12c2b3, and #a7f3ff with fine diagonal white striations, clipped to a polygon and masked to fade into white) falling behind a light-weight Inter Tight headline, with the dark local board overlapping it and bleeding off the right edge. The ribbon returns once in the navy closing band.

Traits: luminous, calm, confident, precise, honest, generous with space.

Preserve:

- The light white page with ink #0a2540 type.
- One cascade ribbon in the hero and its return in the closing band, nowhere else.
- Light-weight (300) display headlines with negative tracking.
- The product shown large: the dark board still overlaps the ribbon and bleeds off the right edge on desktop.
- Pill-shaped actions, 22px tiles, and soft layered shadows for depth.
- Sentence-case labels; honest status, the unsigned-installer note, and labelled example figures.

Never become:

- Dark generic SaaS. Adam rejected the earlier dark v3 system on 2026-11-04 ('i still dont like the waterfall design system').
- Hand-drawn mockups that skip the Shapeable pipeline (previews A, B, and C were rejected on 2026-11-04).
- Stripe trade dress: no Stripe gradient shape, wave, logo, product imagery, or copy. Learn principles only.
- Tracked micro-caps eyebrows over every section (the measured top generated-look tell).
- Uniform grids of three identical cards.
- Fabricated savings or results presented as measured.

## Color

Light only. White and a pale tint carry the page; ink type sits on them. Blue is for links and the one highlighted phrase. The ribbon stops appear only inside the ribbon art layer. Good green is reserved for savings figures and success. The dark board keeps its own sub-palette as an illustration and never leaks into page chrome.

| Token | Role | Light | Dark | Usage |
| --- | --- | --- | --- | --- |
| `ink` | primary text and dark surfaces | #0a2540 | unspecified: light-only identity | Headlines, body emphasis, the dark pill, code blocks, and the navy closing band. |
| `mute` | secondary text | #425466 | unspecified: light-only identity | Ledes, section subtitles, and tile copy. |
| `soft` | tertiary text | #5f6f84 | unspecified: light-only identity | Fine print, captions, and meta. Minimum 12px. |
| `line` | hairline | #e3e8ee | unspecified: light-only identity | Card outlines (as 1px box-shadow), band borders, and dividers. |
| `tint` | pale surface | #f6f9fc | unspecified: light-only identity | The full-bleed cascade band, bento tiles, install cards, and inner-page cards. |
| `white` | page canvas | #ffffff | unspecified: light-only identity | Body background on every route. |
| `blue` | accent on white | #0a6fd6 | unspecified: light-only identity | Home links, the highlighted headline phrase, focus rings, and the hard-step outline. |
| `accent-inner` | accent on light tints | #0859ad | unspecified: light-only identity | Inner-page accent (leaderboard, workshop, docs) so blue text stays AA on #e6f0fb and #eaf3fd tints. |
| `good` | savings and success | #08744e | unspecified: light-only identity | Savings figures, per-step costs, and the works-today status dot only. |
| `warn` | caution | #9a5b00 | unspecified: light-only identity | Pilot or caution states on inner pages. |
| `ribbon-cyan` | ribbon stop | #5ec6ff | unspecified: light-only identity | Cascade ribbon gradient stop and the cascade line in the routing band. |
| `ribbon-blue` | ribbon stop | #2f6bff | unspecified: light-only identity | Cascade ribbon gradient stop and step markers. |
| `ribbon-violet` | ribbon stop | #6b5cff | unspecified: light-only identity | Cascade ribbon gradient stop. |
| `ribbon-teal` | ribbon stop | #12c2b3 | unspecified: light-only identity | Cascade ribbon gradient stop. |
| `ribbon-mist` | ribbon stop | #a7f3ff | unspecified: light-only identity | Cascade ribbon highlight stop. |
| `board-bg` | board canvas | #0b1220 | unspecified: light-only identity | Illustration-only sub-palette for the dark local board still. Board chat area. |
| `board-rail` | board rail | #08101c | unspecified: light-only identity | Illustration-only sub-palette for the dark local board still. Board sidebar, title bar, and side panel. |
| `board-card` | board card | #0f1830 | unspecified: light-only identity | Illustration-only sub-palette for the dark local board still. Board message cards and the active project row. |
| `board-accent` | board accent | #5ec6ff | unspecified: light-only identity | Illustration-only sub-palette for the dark local board still. Hard-route badge and sparkline. |
| `board-good` | board success | #3dd68c | unspecified: light-only identity | Illustration-only sub-palette for the dark local board still. Cheap-route badge, live dots, and the saved metric. |

## Typography

Inter Tight, self-hosted as one variable woff2 (weights 300 to 600, SIL Open Font License), carries everything except code, which uses system mono. Display type is large and light (300) with negative tracking; body is 17px. Labels are sentence case, never tracked uppercase. Nothing renders below 12px.

| Role | Family | Fallback | Usage |
| --- | --- | --- | --- |
| interface and display | Inter Tight | -apple-system, "Segoe UI", system-ui, sans-serif | Headlines, body, navigation, pills, labels. Served from /fonts/inter-tight-latin.woff2 and preloaded. |
| code and figures | system mono | ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace | Code blocks, the prompt line, per-step costs, and board figures. |

| Token | Size | Line height | Weight | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| `h1` | 72px desktop, 48px tablet (900px and below), 40px phone (480px and below) | 1.02 | 300 | -0.035em | The single hero headline, with one highlighted phrase in blue. |
| `close-h2` | 56px desktop, 34px mobile | 1.04 | 300 | -0.035em | The closing band headline on navy. |
| `h2` | 48px desktop, 34px mobile | 1.06 | 300 | -0.03em | Section and cascade band headlines. |
| `tile-title` | 24px to 28px | 1.2 | 400 | -0.02em to -0.025em | Bento tiles and ranking link cards. |
| `lede` | 21px desktop, 18px mobile | 1.5 | 400 | 0 | The one hero sentence; section subtitles use 19px. |
| `body` | 17px | 1.6 | 400 | 0 | Reading text and lists. |
| `small` | 13px to 15px (12px minimum) | 1.5 | 400 | 0 | Captions, notes, fine print, and sentence-case labels at 15px weight 500. |

## Spatial and visual foundations

Spacing: 4px base, Generous. Sections are separated by 128px on desktop and 88px on mobile; the hero opens with 112px (64px mobile). One idea per section. Density is allowed only inside the board still and data tables. density, scale 8, 12, 16, 24, 32, 48, 56, 72, 88, 112, 128px.

Shape: radii 999, 22, 18, 14, 12px. Border: Hairlines are drawn as 1px box-shadow in #e3e8ee (or ink at low alpha) rather than CSS borders, except the cascade band's top and bottom rules. Elevation: Soft layered shadows are part of the identity: for example 0 30px 60px -20px #0a254040 on the floating savings card and 0 50px 100px -20px #0a254066 on the board. Steps and tabs use 0 1px 2px #0a25400d plus a soft 0 8px 24px -12px lift. Never hairline-only flatness. Signature: Pills (999px) for every action, 22px tiles and cards, 18px for the floating savings card, 14px for the board and routing steps, 12px for code blocks and tab rows.

Layout: Max content width 1200px with a 32px gutter (20px under 480px). The hero is a 660px text column with the ribbon behind the right side; the stage below lets the board run off the right edge. The cascade is a full-bleed tint band with copy left and the routing picture right. Promises are a bento: one wide tile plus two stacked tiles, never three identical cards. At most one sentence-case label per section, and no tracked caps. Maximum content width 1200px, 12 columns, 32px default gutter, breakpoints 480, 900, 960px.

Motion: Motion only confirms hover and focus: background and box-shadow transitions on pills and link cards. Nothing animates on load or on scroll. Durations 0, 300ms. Easing cubic-bezier(.22, 1, .36, 1) Reduced motion: Under prefers-reduced-motion: reduce, all transitions are off and every state renders complete.

Focus: 3px solid #0a6fd6 Offset: 3px Rule: Every link, pill, and summary shows a visible focus-visible ring with a 6px radius; the skip link becomes visible on focus.

Imagery: One art layer and one product. The cascade ribbon is pure CSS (conic gradient, polygon clip-path, linear mask, repeating diagonal striations). The product is a stageshow-style still of the real local board (rail, tabs, chat with routed badges, savings side panel), aria-hidden with data-shapeable-illustration and captioned 'Illustrative board. Example numbers, not measured savings.'

Allowed:

- The cascade ribbon in the hero and once in the closing band.
- Code-built stills of the real board and the routing flow, with labelled example figures.
- The floating savings card overlapping the board.

Forbidden:

- Third-party logos or Stripe imagery as decoration.
- Stock photos or AI-generated people.
- More than one ribbon per view, or ribbon colors outside the ribbon.
- Unlabelled figures that could read as measured savings.

## Product patterns

### hero

Product, promise, and price in one pass.

Rules:

- One h1 at weight 300 with one blue phrase.
- One 21px sentence.
- Dark pill 'Buy the founding license · $30' and light pill 'Download for Windows'.
- One fine-print line: one-time, own keys, no markup, unsigned installer.

Required states:

- default
- hover
- focus-visible
- stacked-mobile

### board-stage

Show the real product large, with depth.

Rules:

- The board (1040px) overlaps the ribbon and bleeds off the right edge on desktop.
- A white savings card floats in front at the left.
- On mobile the board becomes one column (rail and side panel hidden) and the card is hidden.
- Always captioned as illustrative with example numbers.

Required states:

- desktop-bleed
- mobile-column

### cascade-band

Explain routing as a picture, not a paragraph.

Rules:

- Full-bleed tint band with top and bottom hairlines.
- A dark prompt line, three white routing steps on a cyan-to-teal line, the hard step outlined in blue.
- Per-step costs in good green mono, then an all-Claude comparison.
- A note that costs are examples and real prices come from OpenRouter at run time.

Required states:

- default
- compact-mobile

### bento

Three promises in three shapes.

Rules:

- One wide tile with live project rows plus two stacked tiles.
- One tile carries the large blue 0% markup figure.
- Never three identical cards.

Required states:

- desktop-bento
- stacked-mobile

### close-band

End on the offer with the ribbon's return.

Rules:

- Navy band, ribbon masked in from the right.
- 56px weight 300 headline, three checked inclusions, white Buy pill and a contact pill.

Required states:

- default
- focus-visible

### inner-pages

Every page reads as the same product.

Rules:

- Same Ribbon nav and footer on every page, current page marked with aria-current.
- A soft radial wash replaces the ribbon on inner pages.
- Legacy dark tokens are remapped to the light palette in ribbon-pages.css; former uppercase labels are sentence case.

Required states:

- default
- current-page

## Content and voice

A calm, precise developer explaining a tool to another developer: plain verbs, short sentences, real numbers, and the limits stated up front.

Rules:

- Lead with what it does in one sentence.
- State the price once in the hero, once in the close, and compactly in the nav.
- Label every example figure as an example.
- Keep honest status: works today, being wired up, pending.
- Use sentence case for every label.

Banned patterns:

- Hype words such as revolutionary, magic, or 10x.
- Em dashes.
- Tracked all-caps eyebrows.
- Claims of measured savings without evidence.

## Responsive rules

### mobile-sequence

At 390px: headline, sentence, stacked full-width pills, fine print, then the one-column board, with no horizontal page overflow.

Acceptance: Site audit reports zero horizontal overflow and zero offscreen page text at 390 x 844.

### ribbon-mobile

Under 900px the ribbon spans the viewport width at 45% opacity behind the hero and never sits behind the Buy pill.

Acceptance: Rendered 390px frame shows the nav and pills fully legible over the ribbon.

### bands-full-bleed

The cascade band and close band run edge to edge while their content stays on the 1200px grid.

Acceptance: No horizontal overflow at 1440 or 390.

## Accessibility rules

### contrast

All text meets WCAG 2.2 AA; blue on tints uses #0859ad, savings green is #08744e.

Acceptance: axe-core reports zero color-contrast violations at both viewports on every route.

### targets

Every link, pill, nav item, and footer link has at least a 44 by 44px hit area.

Acceptance: Shapeable touch-target checks report zero shortfalls.

### illustrations

The ribbon, board still, savings card, and tab rows are aria-hidden; decorative regions carry data-shapeable-illustration.

Acceptance: No illustrative text appears in the accessibility tree; captions carry the meaning.

### reduced-motion

Transitions are off under prefers-reduced-motion.

Acceptance: Shapeable reduced-motion check reports no active transitions.

## Attributed influences

Use the principles. Never transfer proprietary assets, layouts, source code, screenshots, or trade dress.

### [Stripe](https://stripe.com/)

Author: Stripe design team

Principle: A light page, very light display type, one luminous art layer, and dense product proof shown with depth.

Take: Light-weight headlines, a single gradient art layer, product shown large with layered shadows. Adam's primary gold reference.

Do not copy: Do not copy Stripe's gradient shape, wave, colors as a set, logos, product imagery, layouts, or copy.

### [Framer](https://www.framer.com/)

Author: Framer

Principle: The product canvas is the hero and runs large.

Take: Let the board be big and real rather than a small boxed still.

Do not copy: Do not copy Framer's glow treatment, typography, or assets.

### [Family](https://family.co/)

Author: Benji Taylor and the Family team

Principle: Warmth and friendliness in a trust-critical product, with zero tracked caps.

Take: Friendly sentence-case copy and generous rounding.

Do not copy: Do not copy Family's characters, illustrations, or brand.

### [Cursor](https://cursor.com/)

Author: Anysphere

Principle: Show the actual app window framed by an art layer.

Take: The board still framed by the ribbon art layer.

Do not copy: Do not copy Cursor's paintings, app chrome, or typography.

### [stageshow](https://github.com/benjitaylor/skills)

Author: Benji Taylor

Principle: Product stills with a word budget, cropped off the edge, never boxed with even margins.

Take: The board's few real strings, the right-edge bleed, and the illustrative caption.

Do not copy: Do not ship the stageshow kit's brand marks or components as page UI.

## Agent decision rules

- Keep the page light; never return to the rejected dark system.
- Use only the tokens above; no one-off colors or sizes.
- One cascade ribbon in the hero and one in the close, nowhere else.
- Show the product large; never a boxed window with even margins.
- Use sentence-case labels; never tracked uppercase eyebrows.
- Prefer bento layouts; never three identical cards.
- Label every example figure.

Forbidden:

- Stripe trade dress or any third-party logos as decoration.
- Dark generic SaaS styling.
- Hand-drawn mockups that skip the Shapeable pipeline.
- Inline style attributes (the site CSP forbids them).

Review checklist:

- Shapeable audit:sitewide reports 100/100 with full route coverage.
- The taste tells report zero tracked micro-caps and zero uniform card grids.
- A fresh-eye reviewer compares frames against the Stripe gold reference and names the one difference.

## Governance

Owner: Adam Pang (waterfall.sh owner)

Source of truth: This design-system.json, extracted from repo://waterfall.sh/ribbon.css and ribbon-pages.css. The Claude guide is rendered from this file deterministically. Runtime tokens live in body.ribbon in those stylesheets and must match.

Versioning: Semantic versioning. Patch clarifies evidence, minor adds compatible rules or tokens, major changes identity. 1.0.0 is the first version of the Ribbon identity and replaces the rejected dark v3 pack (0.1.0).

Adoption: Owner-approved. Adam previewed the Ribbon home on localhost and answered 'accept' on 2026-11-04, after choosing direction A from three pipeline-built directions (gold references Stripe, Framer, Family, Cursor). The inner-page rollout (leaderboard, workshop, starter packs, about, contact, privacy, thanks, design) follows the accepted home and carries its tokens; it needs the owner's review before production.

Deviations: The board still keeps a dark illustration-only sub-palette. Inner pages use #0859ad instead of #0a6fd6 so blue stays AA on light tints. Record any further deviation with rationale, page, owner, and expiry in the next version.

Review cadence: Re-audit the full site after any material visual, interaction, or route change; persist every owner direction or rejection to the ledger before the next revision.

## Runnable evidence

- Run: `npm run audit:sitewide -- --url http://127.0.0.1:4100 --allow-loopback true --public-url https://waterfall.sh --output artifacts/audits/waterfall-sh-ribbon-20261104-pass4`
  Scope: Local preview of branch shapeable-ribbon-20261104; run from shapeable.art.
  Expected: 100/100, 100% profile coverage, 8 of 8 eligible routes, zero findings (site-audit-20261104190810). The accepted Ribbon home.
- Run: `npm run audit:sitewide -- --url http://127.0.0.1:4100 --allow-loopback true --public-url https://waterfall.sh --include /design --output artifacts/audits/waterfall-sh-ribbon-rollout-20261104-pass4`
  Scope: Local preview of the inner-page rollout; run from shapeable.art.
  Expected: 100/100, 100% profile coverage, 8 of 8 eligible routes (site-audit-20261104191533). Ribbon carried to every page.
