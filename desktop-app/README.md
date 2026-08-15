# waterfall desktop (native `.exe`)

Native Windows shell for [waterfall.sh](../README.md).

## Lineage (fork / merge of peers)

| Borrowed from | What we took |
|---------------|--------------|
| **Official Tauri template** | `npm create tauri-app@latest -- --template vanilla` (scaffold, not hand-rolled) |
| **[CC Switch](https://github.com/farion1231/cc-switch)** | Tauri 2 + web UI shell; Windows-native manager pattern |
| **[AionUi](https://github.com/iOfficeAI/AionUi)** | Multi-agent peer launch cards (glass over installed CLIs/apps) |
| **[OpenChamber](https://github.com/openchamber/openchamber)** | Sidebar workspace layout (rail + stage) |
| **waterfall `desktop/`** | Cascade API (classify / route / stats / hooks) |

We did **not** fork multi-thousand-commit agent monorepos. We merged the
**patterns** into a small product-focused app named **waterfall**.

## Dev

```bash
cd desktop-app
npm install
npm run dev
```

Requires: Node 18+, Rust (rustc/cargo), WebView2 (Windows).

Python cascade backend: from repo root `pip install -e .` so
`python -m desktop.server` works when the app starts.

## Build Windows exe

```bash
cd desktop-app
npm install
npm run build
```

Outputs (typical):

- `src-tauri/target/release/waterfall.exe`: portable binary
- `src-tauri/target/release/bundle/nsis/*.exe`: installer
- `src-tauri/target/release/bundle/msi/*.msi`: MSI

Copy the release binary to a fixed place:

```powershell
Copy-Item src-tauri\target\release\waterfall.exe ..\dist\waterfall.exe -Force
```

Then run `waterfall.exe` from Explorer or pin to taskbar.

## Env

| Variable | Purpose |
|----------|---------|
| `WATERFALL_ROOT` | Path to waterfall.sh checkout if the exe can't find `desktop/server.py` |
| `OPENROUTER_API_KEY` | Live cascade routing (or `~/.claude/openrouter_key.txt`) |
