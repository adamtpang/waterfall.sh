# waterfall.sh design system

Not a full Figma kit. The **source of truth** is this file + `brand/logo.svg`.
Tokens first appeared inline in `index.html` (deep-water chalkboard, vercel.school-adjacent).

## Brand mark

| Element | Meaning |
|---------|---------|
| **Blue W** | Primary logo: stylized W on deep water (cascade legs) |
| **Waterfall blue** `#5ec6ff` | Accent, install commands, links, W fill |
| **Deep water** `#0b1220` | Background / board |
| **▽** | Secondary cascade glyph in mono eyebrows (marketing) |

**Logo:** `brand/logo.svg` / `brand/logo.png`: rounded deep-water tile with a bold blue **W**. Desktop `.exe` icon, favicon, sidebar mark.

**Wordmark:** lowercase `waterfall` in system sans, weight 650–700, tight tracking.

## Desktop UX refs (best-in-class patterns we use)

| App | Borrowed |
|-----|----------|
| Linear | Quiet chrome, strong type hierarchy, accent sparingly |
| Figma | Left rail as product home, not decoration |
| VS Code | Activity-style navigation, fullscreen-first work surface |
| Raycast | Fast actions, minimal ornament |
| Notion | Density toggles, soft cards |

Copy rule: **no em dashes** in product UI.

## Color tokens

| Token | Hex | Use |
|-------|-----|-----|
| `--board` | `#0b1220` | Page / app background |
| `--board2` | `#0f1830` | Cards, elevated surfaces |
| `--rail` | `#08101c` | Desktop sidebar |
| `--chalk` | `#e9edf2` | Primary text |
| `--dust` | `#9aa6b2` | Secondary text |
| `--faint` | `#5c6873` | Labels, meta |
| `--line` | `#1c2740` | Borders |
| `--accent` | `#5ec6ff` | Links, focus, brand |
| `--accent-dim` | `#173447` | Accent wash |
| `--good` | `#3dd68c` | Success / online |
| `--warn` | `#f5a524` | Warning |
| `--bad` | `#f31260` | Error / deny |

## Type

| Role | Stack |
|------|--------|
| UI sans | `-apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, Roboto, Helvetica, sans-serif` |
| Mono | `ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace` |
| Hand (marketing only) | `Caveat` (Google Fonts), accent color |

Labels: mono, 10–12px, uppercase, letter-spacing ~0.12–0.22em.

## Shape & motion

- Card radius: **10–14px**
- Buttons: **9px**
- Borders: **1px solid `--line`**
- Hero underline: freehand stroke `#5ec6ff` (see `index.html` SVG path)
- Prefer quiet UI; no gradients except soft radial wash on board

## shadcn/ui token layer (added 2026-08-23)

`desktop/app.html` was rebuilt in **shadcn/ui's design language**, ported by
hand as plain CSS. shadcn itself is React plus Tailwind plus a build step, and
the desktop app is deliberately zero-build stdlib HTML served by the Python
HTTP server, so adopting the library outright would have put Node in the middle
of `pip install -e .`. The tokens, component anatomy, and layout are shadcn's;
the delivery stays dependency-free.

The brand hexes in the table above were **converted to OKLCH exactly** (not
re-picked by eye), so the deep-water palette survives the port unchanged:

| DESIGN.md hex | OKLCH | shadcn role (dark) |
|---|---|---|
| `#0b1220` | `oklch(0.1831 0.0309 263.38)` | `--background` |
| `#0f1830` | `oklch(0.2149 0.0492 266.79)` | `--card`, `--popover` |
| `#08101c` | `oklch(0.1719 0.0281 257.96)` | `--sidebar` |
| `#e9edf2` | `oklch(0.9445 0.0080 253.85)` | `--foreground` |
| `#9aa6b2` | `oklch(0.7195 0.0221 248.14)` | `--muted-foreground` |
| `#5ec6ff` | `oklch(0.7877 0.1258 235.50)` | `--primary`, `--ring` |

**Semantic pairs** (shadcn naming, use these, not the raw brand names):
`--background/--foreground`, `--card/--card-foreground`,
`--popover/--popover-foreground`, `--primary/--primary-foreground`,
`--secondary/--secondary-foreground`, `--muted/--muted-foreground`,
`--accent/--accent-foreground`, `--destructive`, `--success`, `--warning`,
`--border`, `--input`, `--ring`, `--sidebar*`, `--chart-1` through `--chart-5`.

**Radius scale** is derived from one source, shadcn style:
`--radius: 0.625rem`, then `--radius-sm/md/lg/xl` via `calc()`. Change the base
to restyle every corner at once. This supersedes the fixed "card 10-14px,
buttons 9px" numbers above.

**Light and dark are both complete passes**, so the old "do not mix light
theme" rule is now satisfied rather than violated: dark is the default when the
viewer expresses no preference (`prefers-color-scheme`), an explicit choice is
stamped as `data-theme` on the root and persisted to `localStorage`, and every
token is redefined in all three states. Never define a color only inside a
media query or only inside `[data-theme]`.

**Verified 2026-08-23** against the running app, not eyeballed: OKLCH resolves
natively, the derived radius scale computes (`--radius-xl` renders 14px), the
metric numerals use `tabular-nums`, the sidebar collapses to a scrollable bar
under 820px, the metric grid reflows 4 to 2 to 1, and there is no horizontal
page overflow at 1280 or 375. WCAG AA contrast passes on every text pair in
both themes (dark: body 15.9, sidebar nav 16.2, muted 7.1; light: body 18.2,
muted 5.7, primary button 5.2).

One real layout bug was caught and fixed during that pass: the shell grid used
`var(--rail-w) 1fr`, and a grid track's default `min-width:auto` refused to
shrink below the 1180px content, forcing the whole page to scroll sideways.
`minmax(0,1fr)` is required, not optional.

**Tokens live in `desktop/tokens.css`**, served at `/tokens.css` and linked by
both `app.html` and `pace.html`. That file is the single source of truth for
the palette; do not re-declare colors per page, which is exactly how surfaces
drift out of sync. Page-specific component CSS stays inline in each page.

**Navigation is a top bar, not a sidebar** (changed 2026-08-23). With three
sections a rail is the wrong control: the convention is a top bar under about
five destinations, and a sidebar only once a product has real hierarchy (six or
more sections). The old rail also carried a "Workspace" heading over three
items and a status footer, which is what made it read as busy. Sections sit on
the left of the bar, global utilities (OpenRouter status dot, theme, refresh)
on the right. Revisit only if the app grows past five real sections.

**Component classes** available in `desktop/app.html`: `.card` with
`.card-header`/`.card-title`/`.card-desc`/`.card-content`, `.metric` section
cards, `.badge` (`-primary/-secondary/-outline/-success/-warning/-destructive`,
plus `-mono`), `.btn` (`-primary/-secondary/-outline/-ghost`, plus `-sm`/`-icon`),
`.input`, `.textarea`, `.skel` shimmer placeholders, and `.empty` states.

## Surfaces that must match

1. Landing: `index.html`
2. Desktop webview: `desktop-app/src/styles.css` + `desktop/app.html`
3. Native icon set: `desktop-app/src-tauri/icons/*` (generated from `brand/logo.png`)
4. Web favicon: `brand/favicon.svg` linked from `index.html`
5. Cascade board: `grok-remote/` (launch `waterfall remote`) uses these tokens
6. Perfect product spec: `PERFECT.md`. Offer: `OFFER.md`

## Do not

- Generic Tauri/Electron default icons in shipping builds
- Purple AI-slop gradients
- Mix light theme without a full token pass (the desktop app HAS a full pass; match it rather than half-adopting it)
