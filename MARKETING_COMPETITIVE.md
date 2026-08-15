# Competitive landscape: money-saving / open AI coding shells

Date: 2026-08-11  
Thesis: waterfall = **the ROI coding shell** (cascade + 9 token countermeasures + savings ledger + multi-agent glass). Open-source optional. Positioning sketch: **if Claude Code Desktop is Unity, waterfall is Godot**: open, cheaper path, cascade as the wedge.

## Positioning map

| Cluster | What they sell | Closest to waterfall? | Gap vs waterfall wedge |
|---------|----------------|----------------------|-------------------------|
| **Agent harnesses** (OpenCode, Cline, Aider, Goose) | Coding agent quality / BYOK / local | OpenCode Desktop = peer | Rarely lead with **measured $ saved** or Claude-quota protection |
| **Multi-agent desktops** (AionUi, OpenChamber, Claude Squad, Emdash) | One UI over many CLIs | High (peers already installed) | Cowork/orchestration, not cascade classify→cheap model |
| **Model routers** (RouteLLM, LiteLLM, Not Diamond, Martian, OpenRouter auto) | Route cheap vs strong | High on **routing idea** | Infra/proxy, not a Claude-quota desktop + hooks |
| **Cost FinOps** (Langfuse, Helicone, PointFive TokenShift) | Observe / compress / budget | High on **tracking** | Not an agent IDE; PointFive is closest on agent spend |
| **Closed IDEs** (Cursor, Windsurf, Claude Desktop) | Best-in-class agent UX | Product bar for P1 surfaces | Expensive; savings is not the brand |

## Named peers (same general angle)

### Open-source Claude Desktop / agent shells
- **[OpenCode](https://opencode.ai/)**: MIT, TUI + desktop + IDE; 75+ providers; strongest “Godot of coding agents” star gravity. Wedge: open + any model. **Not** cascade/quota ledger as hero.
- **[AionUi](https://www.aionui.com/)**: free OSS multi-agent cowork desktop (Claude Code, Codex, Gemini, …). Wedge: parallel agents, one window. Cost story: “app free, you still pay models.”
- **OpenChamber / CC Switch**: session/provider switchers; already peer-launch targets in waterfall.
- **Cline / Continue / Kilo / Aider**: IDE-native or CLI agents; BYOK cost control via model choice, weak productized savings dashboard.
- **cdesktop** and similar one-off OSS Claude Desktop clones: surface parity, not savings science.

### Cost / routing (closest *message*, different product shape)
- **[RouteLLM](https://github.com/lm-sys/routellm)** (LMSYS): up to ~85% cost cut at ~95% GPT-4 quality on MT Bench. Academic/router server, not a coding desktop.
- **Not Diamond Code**: step-level routing inside coding agents; claims ~20%+ / 39–61% in agent sequences. Closest commercial **routing-for-agents** pitch.
- **LiteLLM**: proxy, budgets, auto-routing tiers. Ops layer.
- **OpenRouter** free tier + provider sort price: raw rails waterfall already uses for cascade.
- **PointFive TokenShift**: on-device agent cost visibility across Claude Code / Cursor / Windsurf. Closest **median savings / ROI** marketing motion; not cascade + open shell.
- **Morph / FinOps writeups**: document that coding agents burn 4 bills (context, loops, tool output, reasoning); 70–85% stack savings if routing+cache+compact+batch.

### Multi-agent orchestration
- Claude Squad, Vibe Kanban, Maestro, Emdash: parallel worktrees / mission control. Compete on **sessions** (our P1), not on cascade savings.

## White space (why waterfall can own a lane)

1. **Claude Max/Pro quota** as the pain (weekly reset), not only API $: few desktops market “make your plan last the week.”
2. **Nine named countermeasures** with an honest dashboard (only 3 have real token numbers; the rest are decision/delivery): rare honesty in a noisy “save 90%” market.
3. **Cascade product** (classify → split → cheap model → stitch) **plus** in-app multi-agent glass **plus** local ledger: OpenCode/AionUi don’t own this combo; routers don’t own the desktop.
4. **Median savings per user** as the buy trigger: needs enough organic ledger data first (still mostly test traffic as of handoff). Do not claim median until real.

## Godot vs Unity analogy (use carefully)

| | Unity ≈ Claude Desktop | Godot ≈ waterfall (aspiration) |
|--|------------------------|--------------------------------|
| Strength | Best agent + polish | Open/own stack, lower lock-in |
| Cost | Sub / plan pressure | Cascade + cheap routes + visible ROI |
| Risk | Clone theater without agent quality | Stay shell + savings; peers for full tool-loop |

**Do not** claim feature parity with Claude agent intelligence. Claim: **workflow shell + proven token economics**, with OpenCode/AionUi as optional peers for heavier multi-agent.

## Open source decision (not decided)

| Option | Pros | Cons |
|--------|------|------|
| Full OSS (MIT/Apache) | Godot energy, trust, stars path OpenCode took | Harder paid shell later; copycats |
| OSS core (router + hooks) + free desktop | Landing + install.py already OSS-shaped | Split brand |
| Source-available / freemium | ROI SaaS later | Weaker “Godot” story |

Recommendation: **ship P1–P2 desktop honesty first**; open-source the cascade/router/hooks aggressively (already the public repo); keep licensing of the Tauri shell explicit when productizing. Marketing “median savings” only after a real beta cohort.

## Messaging candidates (for later landing)

- “The AI coding shell that pays for itself.”
- “Cascade the routine. Keep Claude for the hard part.”
- “Track every dollar (and quota point) you didn’t burn.”
- “Open glass over Grok, Claude, Codex, with a savings ledger, not vibes.”

## Sources to re-check before any public claim

- OpenCode positioning and desktop features  
- AionUi multi-agent free/OSS  
- RouteLLM / Not Diamond Code savings ranges  
- PointFive agent cost tooling  
- Internal: `TOKEN_COMPOUNDING.md`, dashboard countermeasures, real `token_savings.jsonl`
