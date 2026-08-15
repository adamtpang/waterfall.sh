# Waterfall CLI handoff: 2026-08-11

**For:** next chat opened in `waterfall.sh` (Grok Build CLI / Claude Code / Codex).  
**Read this first**, then `GAP_VS_CLAUDE_CODE.md`, then code under `desktop-app/`.

## Last user asks (this Grok Build session)

1. Pin projects (sidebar stars)  
2. Enter should send (not newline only); save model choice  
3. Grok must run **inside** waterfall (not open a terminal)  
4. Verbose stream + performant UI (no freeze-then-work)  
5. **Hand off to waterfall CLI**; drag-reorder projects; sort/filter; gap-analyze Claude Code Desktop for true feature parity  

## What works now

| Area | Detail |
|------|--------|
| App | Tauri 2 `waterfall.sh/desktop-app` → `dist/waterfall.exe` |
| In-app Grok | `run_agent_local`: `grok --single … --always-approve --output-format streaming-json --include-partial-messages`, **CREATE_NO_WINDOW** |
| Stream | Events `agent-stream`: start/status/tick/tool/log/thought/text/usage/error/done; dual-thread stdout+stderr; 500ms heartbeat |
| UI chat | Message list, rAF-batched tokens, activity log, elapsed timer; Enter = send; Shift+Enter = newline |
| Model | `agent-select` persists to `~/.waterfall/profile.json` `default_agent` |
| Projects | Pin, archive, add; **filter**, **sort** (activity/name/sessions/path/manual), **drag-reorder** → `order` + `sort_mode` in `~/.waterfall/projects.json` |
| **Chat sessions (P1 partial)** | Nested under project; status filter all/running/idle/error; New chat; delete; transcripts on disk `~/.waterfall/sessions/{id}.json` |
| Cascade | Classify / Dry-run / Route via local Python backend `:8765` |
| Peers | CC Switch, AionUi, OpenCode Desktop, OpenChamber launchers |
| Open TUI | Still available as external console for full interactive CLIs |
| Marketing research | `MARKETING_COMPETITIVE.md`: ROI / Godot-vs-Unity landscape (OpenCode, AionUi, RouteLLM, Not Diamond, PointFive, …) |

## Key files

```
waterfall.sh/
  GAP_VS_CLAUDE_CODE.md          ← full Claude Desktop parity map (refreshed)
  HANDOFF_CLI_2026-08-11.md      ← this file
  MARKETING_COMPETITIVE.md       ← ROI / open-source landscape research
  desktop-app/src/main.js        ← UI: sessions, chat persist, filter/sort/drag
  desktop-app/src/index.html
  desktop-app/src/styles.css
  desktop-app/src-tauri/src/lib.rs  ← run_agent_local, projects, chat sessions
  desktop/server.py              ← cascade API
  dist/waterfall.exe             ← ship target
  ~/.waterfall/sessions/*.json   ← per-chat transcripts (runtime)
```

## Commands

```powershell
cd C:\Users\adamp\Aether\waterfall.sh\desktop-app
npx tauri build --no-bundle
Copy-Item src-tauri\target\release\waterfall.exe ..\dist\waterfall.exe -Force
Start-Process ..\dist\waterfall.exe
```

## Next work (priority from gap analysis)

### Shipped this pass (P1 partial, 2026-08-11 Grok)

1. Sessions nested under project + status filter (running / idle / error)  
2. Persistent transcripts `~/.waterfall/sessions/{id}.json` (create / list / get / append / status / rename / delete)  
3. New chat (sidebar + workspace); load prior transcript on select; auto-title from first user message  

### Still P1

3. **Multi-session / queue**: more than one in-app run without blocking the whole UI (stream events need session_id tagging)  
4. Permission prompts when not always-approve  
5. Optional **embedded terminal** pane  

### Then (P2)

6. File tree + post-turn `git diff` pane  
7. Tool cards (structured) instead of log-only  
8. MCP/skills inventory from disk  

### Do not

- Rebuild full Claude agent tools in Python  
- Open external terminals for default Grok Send  
- Block UI on `list_projects` after every message (already fixed: touch only)  
- Touch paused questlines outside waterfall without Adam  
- Claim public median savings until organic ledger data exists  

## Known sharp edges

- First Grok turn can still take seconds to “first stream byte” (cold CLI + large context); UI should tick, not freeze  
- `claude`/`codex` in-app paths exist but are less polished than Grok  
- Drag reorder switches sort mode to **Manual** and saves `order`  
- Filter is client-side; full list still loaded from backend  
- One in-app run at a time still (`chatBusy`); multi-run not done  
- Status “running” is process-local; after crash/restart may stick until next idle write  

## Suggested first prompt in next CLI session

```text
Read waterfall.sh/HANDOFF_CLI_2026-08-11.md and GAP_VS_CLAUDE_CODE.md.
Continue P1: multi-session queue (tag agent-stream with session_id) + permission prompts.
Do not open external terminals for Grok Send.
```

## Standing product rules

- Cascade savings remains the wedge  
- In-app agent = local CLI glass, not fake reimplementation  
- No em dashes in user-facing copy  
- Honest zero: we are not Claude Code Desktop yet; track the scorecard  
