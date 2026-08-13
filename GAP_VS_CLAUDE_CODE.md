# Gap analysis: waterfall desktop vs Claude Code Desktop

Date: 2026-08-11 (refreshed after in-app Grok + sidebar sort/filter/drag)  
Sources: [Claude Code Desktop docs](https://code.claude.com/docs/en/desktop), [quickstart](https://code.claude.com/docs/en/desktop-quickstart), April 2026 redesign writeups.  
Honest zero: waterfall is a **cascade + multi-agent shell**. True “feature parity” means matching the **surfaces and workflows** of Claude Code Desktop, not reimplementing Anthropic’s agent brain.

## Positioning (do not blur)

```text
Claude Code Desktop  = best in-app agent brain + tools + multi-session mission control
waterfall.exe        = cascade/quota savings + in-app local agents (Grok/Claude/Codex CLI)
                       + peer launchers + project fleet UI
```

Parity of **workflow** (pick project, chat, stream tools, arrange work, resume) is the goal.  
Parity of **agent intelligence** is subscription + local CLIs (Grok Build, Claude Code, Codex), not a from-scratch tool loop in Python.

---

## Claude Code Desktop surface (2026)

| Surface | What users get |
|---------|----------------|
| **Code tab** | Software-dev sessions with project folder, chat, code changes |
| **Session sidebar** | Parallel sessions; filter by status / project / environment; archive |
| **Session model** | Each session = own context + cwd + changes; run many at once |
| **Workspace panes** | Drag-and-drop: chat, diff, terminal, file, plan, tasks, browser, subagent |
| **Integrated terminal** | Ctrl+` ; agent and user share workspace |
| **File tree + editor** | Live tree as agent works; open paths in pane |
| **Diff / PR** | Visual diff; PR CI watch; auto-merge paths |
| **Browser preview** | Dev server / external sites; agent can see app |
| **Side chat** | Ask without derailing main thread |
| **Tasks / subagents** | Pane for background work and spawned agents |
| **Git worktrees** | Isolate parallel sessions |
| **Cloud / remote** | Long runs continue; continue on web/IDE |
| **Scheduled tasks** | Routines (daily review, audits) |
| **Plugins / MCP / skills** | First-class install from UI |
| **Permissions** | Per-tool allow / modes |
| **Auth** | Claude account OAuth |

---

## Scorecard (waterfall vs that surface)

| Dimension | Claude Code Desktop | waterfall now | Gap | Parity path |
|-----------|---------------------|---------------|-----|-------------|
| Native desktop window | Yes | Yes (`waterfall.exe` Tauri) | Closed | Keep |
| Project / session sidebar | Multi-session, filters, archive | Projects + **nested chat sessions**, pin/archive/filter/sort/drag, **status filter** | Low–Medium | Flat session-first list optional; multi-run status live |
| Parallel live sessions | Many agents concurrent in UI | One in-app run at a time per window; peers separate | **High** | Multi-tab/session state; background jobs list |
| In-app agent chat | Full tool loop + stream | **In-app Grok local** + **disk transcripts** (`~/.waterfall/sessions/`) | Medium | Multi-run; Claude/Codex polish; richer tool cards |
| Streaming UI | First-class | Stream + heartbeat + rAF batch + tool/log lines | Low | Partial messages already; richer tool cards |
| Permissions UI | Per-tool | CLI `--always-approve` / profile | High | Surface allow/deny prompts in chat |
| Integrated terminal | Yes | Open TUI external only | High | Embed PTY pane (xterm.js) |
| File tree / editor | Yes | No | High | Read-only tree first; click path → open |
| Diff pane | Yes | No | High | Show git diff after agent turn |
| Browser preview | Yes | No | Medium | Later; or launch system browser |
| Side chat | Yes | No | Medium | Second thread per project |
| Subagents pane | Yes | Tools stream as log lines only | High | Parse tool events into task list |
| MCP / plugins UI | Yes | Peer: CC Switch | Medium | Inventory from disk + launch CC Switch |
| Skills / slash | Yes | No UI (CLIs have them) | Medium | `/` palette routing to agent |
| Git worktrees | Yes | No | Medium | Optional `grok --worktree` / git CLI |
| Cloud remote sessions | Yes | No | Out of scope short-term | Peer cloud tools |
| Scheduled agents | Yes | No | Medium | Local scheduler later |
| Model picker | In-product | Agent select (Grok/Claude/Codex/Auto) + cascade Route | Different | Keep multi-agent + cascade as wedge |
| Token / quota UX | Plan usage | Savings mini + cascade stats | Partial | Stronger savings dashboard in shell |
| **Cascade / cheap route** | Manual | Core product (Classify / Dry / Route) | **Lead** | Keep as differentiator |
| Peer multi-agent desktops | N/A | AionUi, OpenCode, OpenChamber, CC Switch | Closed | Maintain |
| OAuth aesthetic profile | Claude account | Local profile scaffold | Medium | Real waterfall OAuth later |

---

## What “true feature parity” means (ordered)

### P0 — Already shipping (do not regress)

1. Native maximized shell, W logo, aesthetic prefs  
2. Project list from Claude sessions + manual add  
3. Pin / archive / **filter / sort / drag-reorder**  
4. In-app **Grok local** chat (no terminal): stream, verbose tools/logs, heartbeat  
5. Model choice persisted (`~/.waterfall/profile.json`)  
6. Cascade classify / dry-run / route + savings  
7. Peer launchers + Open TUI fallback  
8. **Chat sessions + disk transcripts** (P1 partial): nested rows, status filter, `~/.waterfall/sessions/`  

### P1 — Workflow parity (remaining)

| # | Deliverable | Why it closes Claude gap | Status |
|---|-------------|---------------------------|--------|
| 1 | **Session rows under project** (or flat session list with project filter) | Claude sidebar is session-first, not folder-first | **Done** (nested) |
| 2 | **Persistent chat transcript** per project/session on disk | Survive restart like Claude | **Done** |
| 3 | **Multi-session**: run/queue more than one agent; switch without kill | Mission control | Next |
| 4 | **Status filters**: running / idle / error / archived | Claude filter bar | **Done** (running/idle/error) |
| 5 | **Permission prompts** in UI for non-yolo mode | Trust + control | Next |
| 6 | **Embedded terminal pane** (optional) | Ctrl+` parity | Later |

### P2 — Workspace parity

| # | Deliverable |
|---|-------------|
| 7 | File tree (read-only) for selected project |
| 8 | Diff pane after agent edits (`git diff`) |
| 9 | Tool/task cards (not only log lines) |
| 10 | Side chat / second thread |
| 11 | MCP + skills inventory panels (read from `~/.claude` / `~/.grok`) |

Reference for #11, not a fork: [OpenMausBot](https://github.com/milind-soni/OpenMausBot)
(evaluated 2026-08-11, not incorporated) wires connected-app access through
the Composio Connect marketplace (500+ services: Gmail, Slack, GitHub,
Notion, Linear) rather than a bespoke per-service integration. Worth
studying that approach when #11 gets built, same as AionUi/opcode/Palot
were studied for the rest of this shell without forking them. The rest of
OpenMausBot (Electron multi-agent chat, one conversation per agent) is the
same category as AionUi/OpenChamber, already covered by peers, see the
"Never" list above.

### P3 — Stretch / enterprise Claude surfaces

| # | Deliverable |
|---|-------------|
| 12 | Browser preview pane |
| 13 | PR CI monitor |
| 14 | Scheduled local routines |
| 15 | Cloud/remote handoff |

### Never (wrong product)

- Rebuilding Anthropic’s full agent + tools in waterfall Python  
- Beating Claude Code on multi-file coding quality without their model/subscription  
- Cloning AionUi/OpenChamber when those are already installed peers  

---

## Waterfall-unique wedge (keep)

1. **Cascade**: route easy work off Claude quota (OpenRouter / cache)  
2. **Multi-CLI brain**: Grok / Claude / Codex from one shell  
3. **Fleet of Aether projects** with pin, filter, drag order  
4. **Token savings** visible in chrome  

Claude does not own (1) or (4). That is the product reason waterfall exists.

---

## Honest distance to “true feature parity”

| Band | Estimate |
|------|----------|
| Shell + project fleet + in-app Grok stream | ~35–40% of Claude Desktop **workflow surface** |
| + sessions + multi-run + transcript + terminal | ~60–70% |
| + file/diff/tasks/MCP panes | ~85% |
| Full Claude (cloud, PR, browser, worktrees, plugins marketplace) | Not the goal; use Claude Desktop / peers |

---

## Verification notes

- Build: `waterfall.sh/desktop-app` → `npx tauri build --no-bundle` → `dist/waterfall.exe`  
- Store: `~/.waterfall/projects.json` (`order`, `sort_mode`, pin, archive)  
- Profile: `~/.waterfall/profile.json` (`default_agent`, aesthetic)  
- In-app agent: `run_agent_local` (CREATE_NO_WINDOW, dual-thread pipes, stream events)  
- Cascade backend: Python `desktop.server` on `127.0.0.1:8765`  

See `HANDOFF_CLI_2026-08-11.md` for the next CLI session pickup.
