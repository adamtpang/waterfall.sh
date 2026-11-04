# waterfall.sh design system

Shapeable contract 0.1.0. Status: owner-approved. This file is generated from `.shapeable/design-system.json`. Edit the JSON source, then render again.

## Read this first

- Read repo://waterfall.sh/DESIGN.md, PERFECT.md, and this design system before any visual change.
- Read the waterfall.sh entry in shapeable.art preferences/owner-preferences.json, including its feedback.
- Read waterfall.sh/site.css :root before adding styles.

## Intent and north star

Keep waterfall.sh's dark deep-water identity and blue W, and bring it to the accepted shapeable.art level of polish: one type scale, airy rhythm, restraint, and one clear path to the $30 founding license.

A developer understands in one pass that waterfall.sh is a local board that routes routine prompts to the cheapest capable model and keeps hard work for Claude or Grok, sees the real board, and either buys the $30 license or downloads it.

## Owner preference contract

Ledger: preferences/owner-preferences.json

Site record: waterfall.sh

Latest feedback: waterfall-redesign-previews-abc-rejection

## Identity

Signature: A deep-water board (#0b1220) with chalk text and a single waterfall blue (#5ec6ff); the blue W tile; mono uppercase eyebrows; large tight sans headlines; one illustrative still of the real local board.

Traits: quiet, technical, frugal, fast, honest about limits, developer-native.

Preserve:

- The dark deep-water palette and the blue W mark (brand/logo.svg, brand/favicon.svg).
- Lowercase waterfall wordmark with the .sh in waterfall blue.
- System sans for interface and system mono for labels and commands; no web fonts.
- Waterfall blue as the single signal color; good green only for savings and success.
- Honest status about what works today, what is being wired up, and what is pending.
- The tagline: Flip projects. Pay the least for the job.

Never become:

- Shapeable's light paper look; Adam chose Same quality, keep dark.
- A generic SaaS gradient landing page.
- Crypto neon or glow-heavy styling.
- A wall of text or a long promotional explainer.
- A page that shows fabricated savings, users, or model results as real.
- A logo wall of third-party AI products used as decoration.

## Color

Dark only. Deep-water surfaces carry everything; waterfall blue is scarce and means action, focus, links, or the mark. Good green is reserved for savings and success figures. Secondary text never drops below the AA floor of #7f8c99. The light column records that no light theme exists rather than inventing one.

| Token | Role | Light | Dark | Usage |
| --- | --- | --- | --- | --- |
| `board` | page canvas | unspecified: dark-only identity | #0b1220 | Body background on every route, with at most one soft radial wash. |
| `board2` | elevated surface | unspecified: dark-only identity | #0f1830 | Cards, the price panel, and the product frame. |
| `rail` | deepest surface | unspecified: dark-only identity | #08101c | Code blocks, table bodies, the board sidebar in the still. |
| `chalk` | primary text | unspecified: dark-only identity | #e9edf2 | Headlines, body, and primary labels. |
| `dust` | secondary text | unspecified: dark-only identity | #aab4be | Ledes, card copy, and inactive navigation. |
| `faint` | tertiary text | unspecified: dark-only identity | #7f8c99 | Meta, captions, and labels. AA floor: never use the retired #5c6873. |
| `line` | structural border | unspecified: dark-only identity | #27334a | One-pixel borders and rules. |
| `accent` | waterfall blue signal | unspecified: dark-only identity | #5ec6ff | Primary buttons, links, focus rings, eyebrows, and the W. |
| `accent-dim` | signal wash | unspecified: dark-only identity | #173447 | Selected or highlighted rows and chips. |
| `good` | savings and success | unspecified: dark-only identity | #3dd68c | Savings figures and success states only. |
| `warn` | warning | unspecified: dark-only identity | #f5a524 | Real warnings only, always with text. |

## Typography

One scale replaces the 13 measured sizes and 5 weights. Sans carries headlines and reading; mono is semantic for eyebrows, labels, commands, and numbers. Weights are 400, 600, and 700 only. Nothing essential renders below 12px.

| Role | Family | Fallback | Usage |
| --- | --- | --- | --- |
| interface and display | system sans | -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, Roboto, Helvetica, sans-serif | Headlines, body, navigation, and buttons. |
| labels, commands, numbers | system mono | ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace | Eyebrows, meta, code blocks, and figures. |

| Token | Size | Line height | Weight | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| `h1` | 64px desktop, 44px mobile | 1.04 | 700 | -0.045em | The single page headline. |
| `h2` | 40px | 1.04 | 700 | -0.035em | Section titles. |
| `h3` | 28px | 1.2 | 600 | -0.02em | Large card and step titles. |
| `lede` | 20px | 1.6 | 400 | 0 | The one-sentence intro under a headline. |
| `body` | 16px | 1.6 | 400 | 0 | Reading copy. |
| `ui` | 14px | 1.5 | 600 | 0 | Navigation, buttons, and small copy. |
| `label` | 12px | 1.4 | 600 | 0.16em uppercase (mono) | Eyebrows and meta. 12px is the floor. |

## Spatial and visual foundations

Spacing: 4px base, Airy. Sections are separated by 120px on desktop and 72px on mobile; one idea per section. Density is allowed only inside data tables and the product still. density, scale 4, 8, 12, 16, 24, 32, 48, 72, 120px.

Shape: radii 10, 14, 16px. Border: One-pixel line-colored borders where containment explains structure. Elevation: Flat surfaces. Only the product frame carries a deep shadow so it reads as a window on the board. Signature: Rounded 10px controls, 14px cards, and a 16px product frame around the illustrative board.

Layout: Home has at most five sections: hero (headline, one sentence, Buy $30 and Download, trust line, then the product still), how it falls, workshop and leaderboard, honest status, and install. Every page shares one nav: cascade, leaderboard, workshop, docs (about), and a compact Buy $30. Each section intro is at most two short sentences. Maximum content width 1120px, 12 columns, 24px default gutter, breakpoints 390, 650, 900, 1120, 1440px.

Motion: Motion confirms state (hover, focus, a still easing into view) and never decorates. Durations 0, 200, 400ms. Easing cubic-bezier(.22, 1, .36, 1) Reduced motion: Under prefers-reduced-motion: reduce, transitions, animations, and smooth scrolling are off and every state renders complete and static.

Focus: 3px solid #5ec6ff Offset: 3px to 4px Rule: Every interactive element shows a visible focus-visible ring, and a skip link reaches the main content first.

Imagery: Show the real product: one stageshow-style still of the local board built from its real UI (sidebar Dashboard, Cascade, Agents, Pace; card Classify and route; metrics Prompts routed, Tokens avoided, Est. saved), captioned Illustrative board. Example numbers.

Allowed:

- Code-built product stills of the real board, aria-hidden with data-shapeable-illustration and a visible caption of at least 12px.
- Real command lines and real feature names.
- The W mark and wordmark.

Forbidden:

- Third-party product logos used as decoration.
- Fabricated savings, usage, or users presented as real.
- Stock photography or mascots.
- Glowing neon gradients.

## Product patterns

### unified-nav

Make every page read as one product.

Rules:

- Brand left; cascade, leaderboard, workshop, docs, then a compact Buy $30 on the right.
- Every link has a 44px hit area; non-essential links collapse on narrow screens while Buy $30 stays.
- The current page is marked with aria-current.

Required states:

- default
- current-page
- hover
- focus-visible
- collapsed-mobile

### hero-buy-path

One clear path to the founding license.

Rules:

- The $30 price and the primary Buy action appear once, in the hero.
- Download for Windows is the secondary action.
- A mono trust line states one-time, your own keys, no token markup, and the unsigned installer.

Required states:

- default
- hover
- focus-visible

### board-still

Show the real local board without exposing private data.

Rules:

- Build the still from the board's real structure and labels.
- Wrap it in aria-hidden plus data-shapeable-illustration with a visible caption.
- Use example numbers and say so in the caption.

Required states:

- static
- reduced-motion

### honest-status

Keep trust by separating shipped behavior from unfinished work.

Rules:

- Three columns: works today, being wired up, pending code or evidence.
- The pending column is labelled a roadmap, not a guarantee.

Required states:

- default

## Content and voice

A terse developer explaining a tool to another developer: plain, specific, frugal, and honest about limits.

Rules:

- Lead with what it does in one sentence.
- Every number has a source or is labelled an example.
- State limits (unsigned installer, Windows-only desktop package) next to the download.
- Keep each section intro to two short sentences at most.

Banned patterns:

- Hype words such as revolutionary, magic, or 10x.
- Invented testimonials, logos, or savings.
- Long promotional paragraphs.
- Em dashes.

## Responsive rules

### mobile-sequence

At 390px the headline, one sentence, Buy and Download, trust line, then the product still read in that order with no horizontal page overflow.

Acceptance: Site audit reports zero horizontal overflow and zero offscreen page text at 390 x 844.

### touch-and-type-floors

No text below 12px and every non-inline control at least 44 by 44px at every width.

Acceptance: Site audit reports zero tiny page text and zero comfortable touch-target shortfalls.

## Accessibility rules

### contrast

All text meets WCAG 2.2 AA on deep-water surfaces; secondary text uses dust or faint, never the retired #5c6873.

Acceptance: axe-core reports zero color-contrast violations at both viewports.

### semantics-and-focus

Every page has a title, lang, one h1, a skip link, labelled controls, and a visible 3px accent focus ring.

Acceptance: axe-core reports zero critical or serious violations; manual keyboard pass reaches every control.

### reduced-motion

No transition or animation remains active under prefers-reduced-motion.

Acceptance: Site audit reports zero motion-active-under-reduce elements.

## Attributed influences

Use the principles. Never transfer proprietary assets, layouts, source code, screenshots, or trade dress.

### [Linear](https://linear.app/)

Author: Linear

Principle: Quiet chrome and a strong type hierarchy, with the accent used sparingly.

Take: A calm nav and restrained use of waterfall blue.

Do not copy: Do not copy Linear's assets, layouts, gradients, or trade dress.

### [Raycast](https://www.raycast.com/)

Author: Raycast

Principle: Minimal ornament and fast, obvious actions.

Take: Primary actions are short and immediate; no decorative motion.

Do not copy: Do not copy Raycast's assets, layouts, or visual identity.

### [stageshow product-still technique](https://github.com/benjitaylor/skills)

Author: benjitaylor/skills (MIT)

Principle: Show the product as a composed still built from real UI primitives, with real words only where they carry meaning.

Take: The illustrative still of the local board in the hero.

Do not copy: Do not reuse the kit's example scenes, names, or compositions.

### [benji-taylor-design-eval skill](https://github.com/dvdarkin/claude-skills/blob/main/skills/benji-taylor-design-eval/SKILL.md)

Author: Denis Darkin (community skill inferred from Benji Taylor's public work; MIT)

Principle: Progressive disclosure, motion as meaning, the simplicity, fluidity, and delight triad, craft in edge states, trust through clarity.

Take: One clear buy path and progressive disclosure: details live on workshop, leaderboard, and docs pages, not the home page.

Do not copy: Do not adopt any product's visual language or imply endorsement by Benji Taylor.

## Agent decision rules

- Keep the dark deep-water identity; never adopt Shapeable's light look for this site.
- Use only the type scale 12, 14, 16, 20, 28, 40, 64 (44 on mobile) and weights 400, 600, 700.
- Use the spacing scale and 120px desktop section rhythm.
- State the $30 price and Buy action once in the hero; keep the compact Buy $30 in the nav.
- Keep text at 12px or larger and targets at 44px or larger.
- Label every example number as an example.

Forbidden:

- Hand-drawn redesign mockups that skip this pack (rejected 2026-11-04).
- The retired #5c6873 text color.
- Third-party logos as decoration.
- Claiming owner approval or production acceptance without durable evidence.

Review checklist:

- Shapeable audit:sitewide reports 100/100 with full route coverage on two identical passes.
- The page meets the five-section and two-sentence limits on home.
- The owner has reviewed the exact preview on localhost before any push.

## Governance

Owner: Adam Pang (waterfall.sh owner)

Source of truth: This design-system.json plus repo://waterfall.sh/DESIGN.md; the Claude guide is rendered from this file deterministically. Runtime tokens live in waterfall.sh/site.css :root and must match.

Versioning: Semantic versioning. Patch clarifies evidence, minor adds compatible rules or tokens, major changes identity.

Adoption: Draft. Redesign previews A, B, and C were rejected on 2026-11-04 because they did not come out of the Shapeable workflow; this pack is the first workflow step. The owner must accept the exact reviewed preview before this becomes owner-approved.

Deviations: Record each deviation with rationale, affected page, owner, and expiry in the next pack version.

Review cadence: Re-audit the full site after any material visual, interaction, or route change; persist every owner direction or rejection to the ledger before the next revision.

## Runnable evidence

- Run: `npm run audit:sitewide -- --url https://waterfall.sh --output artifacts/audits/waterfall-sh-production-20261104`
  Scope: Production waterfall.sh before the redesign; run from shapeable.art.
  Expected: 100/100, 100% profile coverage, 7 of 7 eligible routes (recorded as site-audit-20261104175147). This is the pre-redesign baseline.
- Run: `npm run audit:sitewide -- --url https://waterfall.sh --output artifacts/audits/waterfall-sh-redesign-production-20261104`
  Scope: Production waterfall.sh after the Shapeable redesign; run from shapeable.art.
  Expected: 100/100, 100% profile coverage, 7 of 7 eligible routes on production after the redesign (commit 21465a3), following four identical 100/100 preview passes with zero findings.
- Run: `npm run validate:contracts`
  Scope: Run from the shapeable.art repository.
  Expected: All contracts and fixtures validate.
