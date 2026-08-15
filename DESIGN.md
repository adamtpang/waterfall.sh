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

## Surfaces that must match

1. Landing: `index.html`
2. Desktop webview: `desktop-app/src/styles.css` + `desktop/app.html`
3. Native icon set: `desktop-app/src-tauri/icons/*` (generated from `brand/logo.png`)
4. Web favicon: `brand/favicon.svg` linked from `index.html`

## Do not

- Generic Tauri/Electron default icons in shipping builds
- Purple AI-slop gradients
- Mix light theme without a full token pass
