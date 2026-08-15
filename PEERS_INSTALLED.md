# Installed peer desktops (2026-08-11)

Claude/Codex-class **agent desktops** installed on this machine.  
**watertop** stays the cascade/quota control panel (not a coding agent shell).

## What was installed

| App | Version | How | Role |
|-----|---------|-----|------|
| **CC Switch** | 3.19.2 | `winget install farion1231.CC-Switch` | Switch providers across Claude Code, Codex, Gemini, **Grok Build**, OpenCode, … MCP/skills/usage |
| **AionUi** | 2.1.47 | `winget install HaiYing.AionUi` | Multi-agent cowork desktop (Claude Code, Codex, OpenCode, … side by side) |
| **OpenCode Desktop** | 1.18.16 | `winget install SST.OpenCodeDesktop` | Official open-source coding agent desktop |
| **OpenChamber** | 1.18.2 | GitHub release `OpenChamber-1.18.2-win-x64.exe` | Multi-session workspace on top of OpenCode (sessions, multi-run, diffs) |

Install locations (typical):

- CC Switch: `%LOCALAPPDATA%\Programs\CC Switch`
- AionUi: `%LOCALAPPDATA%\Programs\AionUi`
- OpenCode: `%LOCALAPPDATA%\Programs\@opencode-aidesktop`
- OpenChamber: `%LOCALAPPDATA%\Programs\@openchamberelectron`

Start Menu shortcuts were created for all four.

## How to use the stack

```text
Native cascade shell     waterfall.exe / waterfall-app   (desktop-app Tauri)
Quota / cascade (CLI)    watertop                        (browser/pywebview)
Provider switching       CC Switch
Cowork multi-CLI         AionUi
Coding agent desktop     OpenCode Desktop
Session/workspace UX     OpenChamber
```

`waterfall.exe` is a **native window** that hosts cascade stats + one-click
launch of the peer apps above. It is not a fork of AionUi/OpenCode source;
it merges their UX patterns into a waterfall-branded Tauri shell
(see `desktop-app/README.md`).

1. **CC Switch** first: import Claude/Codex/Grok providers so CLIs share clean configs.  
2. **AionUi** when you want one window over several agent CLIs.  
3. **OpenCode Desktop** or **OpenChamber** when you want a full agent chat + projects surface (Open source Claude/Codex-like).  
4. **watertop** when you care about Claude quota: classify/route, hooks, savings ledger.

## Reinstall / upgrade

```powershell
winget upgrade farion1231.CC-Switch
winget upgrade HaiYing.AionUi
winget upgrade SST.OpenCodeDesktop
# OpenChamber: download latest win-x64 from
# https://github.com/openchamber/openchamber/releases/latest
```

## Not installed (optional later)

| App | Why skipped |
|-----|-------------|
| **opcode** (AGPL) | Claude-only GUI; AionUi/OpenChamber cover more |
| **Nimbalyst** | Available on winget (`Nimbalyst.Nimbalyst`) if you want another multi-agent workspace |

## License notes

- CC Switch: MIT  
- OpenCode / OpenChamber: MIT  
- AionUi: Apache-2.0  
Use as installed apps; do not vendor AGPL opcode into waterfall without a license review.
