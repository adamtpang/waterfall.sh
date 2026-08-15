# OSS landscape: desktop GUIs for coding agents

Research for making **watertop** feel like Claude Code Desktop / Codex Desktop,
not a browser tab. Updated 2026-08-11.

## What "desktop like Claude/Codex" actually means

| Surface | What users mean |
|---------|-----------------|
| **Chrome** | Own window, no browser URL bar, tray optional, OS installers |
| **Sessions** | Multi-project / multi-chat sidebar, resume history |
| **Agent work** | Chat + tools + diffs inside the app (not only "launch CLI") |
| **Command center** | Parallel agents, status, usage/cost, approvals |
| **Local** | Files and code stay on machine |

Current **watertop** is: local HTTP + HTML (dashboard / cascade / launch). That is a
**control panel**, not a coding desktop. The gap is real.

## Peers found

| Peer | Stack | License | What it actually is | Source |
|------|-------|---------|---------------------|--------|
| **[OpenCode Desktop](https://github.com/anomalyco/opencode)** | Official desktop (Electron package under `packages/desktop`), plus TUI + IDE | MIT | Full open-source coding agent with real desktop app, tabs, multi-surface | [opencode.ai](https://opencode.ai), [releases](https://github.com/anomalyco/opencode/releases) |
| **[OpenChamber](https://github.com/openchamber/openchamber)** | Desktop + Web/PWA + VS Code + mobile; wraps OpenCode | MIT | Supervisory workspace: multi-session, multi-run, diffs walkthrough, goals, remote | [github.com/openchamber/openchamber](https://github.com/openchamber/openchamber) (~8k stars) |
| **[AionUi](https://github.com/iOfficeAI/AionUi)** | Electron + AionCore backend | Apache-2.0 | Cowork desktop: built-in agent + auto-detect 20+ CLIs (Claude Code, Codex, OpenCode, Grok-adjacent, …), parallel sessions, Team mode | [github.com/iOfficeAI/AionUi](https://github.com/iOfficeAI/AionUi) (~32k stars) |
| **[CC Switch](https://github.com/farion1231/cc-switch)** | **Tauri 2 + React + Rust** | MIT | All-in-one manager for Claude Code, Claude Desktop, Codex, Gemini, **Grok Build**, OpenCode, OpenClaw, Hermes: providers, MCP, skills, usage, sessions, tray | [github.com/farion1231/cc-switch](https://github.com/farion1231/cc-switch), [ccswitch.io](https://ccswitch.io) |
| **[opcode](https://github.com/winfunc/opcode)** (ex-Claudia) | Tauri 2 + React | AGPL-3.0 | Claude Code GUI: projects from `~/.claude/projects`, sessions, usage, custom agents | [github.com/winfunc/opcode](https://github.com/winfunc/opcode) |
| **[Palot](https://github.com/ItsWendell/palot)** | Electron | check repo | Glass over OpenCode: multi-project sessions, diffs | GitHub Palot |
| **[CodePilot](https://github.com/op7418/CodePilot)** | Electron + Next.js | check repo | Multi-model desktop client, MCP/skills | ~6k stars |
| **[Nimbalyst](https://github.com/Nimbalyst/nimbalyst)** | Desktop + iOS | MIT (apps) | Multi-agent workspace with visual tools | [nimbalyst.com comparison](https://nimbalyst.com/blog/best-multi-agent-desktop-apps-claude-code-codex-2026/) |
| **Codex Desktop / Claude Code Desktop** | Proprietary | closed | Reference UX for "command center" + parallel agents | Product UIs, not OSS |

### Saturation check

**This niche is crowded.** Multi-agent and CLI-manager desktops are a real category
in 2026 (CC Switch, AionUi, OpenChamber, OpenCode Desktop, opcode). Waterfall should
not try to out-build a full Claude/Codex clone. It should either:

1. **Borrow the shell** (Tauri/Electron patterns) and stay focused on **cascade + quota**, or  
2. **Integrate** with CC Switch / AionUi / OpenChamber for agent UX and keep watertop thin.

## Architecture patterns (what the winners share)

```
┌─────────────────────────────────────────┐
│  Native shell (Tauri or Electron)       │
│  ┌───────────┐  ┌─────────────────────┐ │
│  │ Sidebar:  │  │ Main: chat / agent  │ │
│  │ projects  │  │ stream, tools, diffs│ │
│  │ sessions  │  │                     │ │
│  │ agents    │  │                     │ │
│  └───────────┘  └─────────────────────┘ │
│         IPC / local API                 │
│  Agent backends: CLI spawn, ACP, HTTP   │
└─────────────────────────────────────────┘
```

| Pattern | Who | Detail |
|---------|-----|--------|
| **Native shell** | CC Switch (Tauri 2), AionUi (Electron), OpenCode desktop (Electron) | Own window + installers, not default browser |
| **Glass over CLI** | AionUi multi-agent, Palot, OpenChamber | Detect/spawn Claude/Codex/OpenCode; don't reimplement agent core |
| **Config manager** | CC Switch | One SQLite SSOT, switch providers, MCP, skills, tray | 
| **Session workspace** | OpenChamber, opcode | Multi-session, history, status, review |
| **Usage chrome** | opcode, CC Switch usage dashboard | Token/cost visibility (waterfall already has ledger/hooks) |

## What to actually borrow for watertop / waterfall

1. **Default to a native window, not Chrome**  
   CC Switch and AionUi never open as "a website you navigated to."  
   **Borrow:** force `pywebview` (or Tauri) as default for `watertop`; browser only with `--browser`.

2. **Tauri 2 + React if we rebuild the shell**  
   CC Switch proves this stack on Windows for Claude/Codex/**Grok Build** management.  
   **Borrow:** same stack if we invest in a real app; MIT-friendly.

3. **Do not reimplement the agent loop**  
   OpenChamber sits on OpenCode; AionUi multi-agent mode wraps existing CLIs.  
   **Borrow:** watertop = cascade control plane + optional embed/launch of Claude/Codex/Grok; agent brains stay external.

4. **Sidebar: projects + sessions + agent status**  
   OpenChamber + opcode layout.  
   **Borrow:** left rail (Aether projects, hook activity, agent online/offline), center cascade/chat later.

5. **Usage is waterfall's wedge**  
   Others track API spend; waterfall tracks **Claude quota saved** (nudges, Ringer, OpenRouter cascade).  
   **Borrow:** keep savings/hooks as the home screen, not a generic chat clone.

6. **Optional: use the mature apps today**  
   Install [CC Switch](https://ccswitch.io) for provider switching across Claude/Codex/Grok,  
   [AionUi](https://github.com/iOfficeAI/AionUi) or [OpenChamber](https://github.com/openchamber/openchamber) for multi-session agent desktop.  
   Point watertop at cascade only until the shell is rebuilt.

## What NOT to borrow

| Anti-pattern | Why |
|--------------|-----|
| Fork opcode (AGPL) into a commercial product without legal review | Copyleft risk |
| Rebuild full multi-agent chat inside waterfall | Crowded; dilutes cascade product |
| Stay on browser-only forever | User already rejected "web app" feel |
| Claim feature parity with Codex Desktop in one sprint | Months of shell + session work |

## Recommended path for waterfall (ordered)

| Step | Outcome | Effort |
|------|---------|--------|
| **0. Now** | `watertop` opens **native window** by default (`pywebview`), frameless-ish title, no browser chrome | Small |
| **1. Near** | Sidebar layout: projects + hooks + cascade (still local API) | Medium |
| **2. Shell** | Scaffold Tauri 2 app (template from official Tauri or CC Switch-like layout), reuse `desktop/server` as backend | Large |
| **3. Agents** | Embed terminal or ACP stream for Claude/Codex/Grok sessions (glass over CLI) | Large |
| **4. Ship** | Windows installer so `watertop` is a Start Menu app | Medium |

## Template rule (Aether standing)

When scaffolding Tauri/Electron: start from official Tauri Vite+React template (or a permissive starter), record URL in CLAUDE.md. Do not hand-roll windowing from empty.

## Out of scope for waterfall v1 desktop

- Mobile remote (OpenChamber Private Relay)
- Full skill marketplace
- Competing with Cursor/Windsurf as an IDE
- Replacing Claude/Codex product subscriptions
