//! waterfall desktop shell
//!
//! Stack pattern: Tauri 2 + web UI (same approach as CC Switch).
//! Layout pattern: sidebar + main panes (OpenChamber / AionUi).
//! Domain: cascade/quota + launch installed peer desktops + Claude sessions.

use serde::{Deserialize, Serialize};
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime};
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

struct BackendState {
    child: Mutex<Option<std::process::Child>>,
}

#[derive(Serialize, Clone)]
struct PeerApp {
    id: String,
    label: String,
    kind: String,
    available: bool,
    path: Option<String>,
}

#[derive(Serialize, Clone)]
struct AgentCli {
    id: String,
    label: String,
    available: bool,
    path: Option<String>,
}

#[derive(Serialize, Clone)]
struct ClaudeSessionRow {
    project: String,
    project_path: String,
    session_id: String,
    mtime: String,
    size_bytes: u64,
    file: String,
    /// How many session files exist under this project (for display).
    session_count: u32,
}

/// Sidebar project row (discovered + manual + pin/archive).
#[derive(Serialize, Clone)]
struct ProjectRow {
    project: String,
    project_path: String,
    session_id: String,
    /// Unix seconds of last activity (session mtime or last prompt).
    mtime: String,
    size_bytes: u64,
    file: String,
    session_count: u32,
    pinned: bool,
    archived: bool,
    /// discovered | manual
    source: String,
}

#[derive(Serialize, Deserialize, Clone, Default)]
struct ManualProject {
    path: String,
    label: String,
    added_at: String,
}

#[derive(Serialize, Deserialize, Clone, Default)]
struct ProjectStore {
    /// Normalized absolute paths
    pinned: Vec<String>,
    archived: Vec<String>,
    manual: Vec<ManualProject>,
    /// path -> unix last prompt / activity override
    last_prompt: std::collections::HashMap<String, String>,
    /// Explicit sidebar order (absolute paths). Used when sort_mode is "manual".
    #[serde(default)]
    order: Vec<String>,
    /// activity | name | sessions | path | manual
    #[serde(default = "default_sort_mode")]
    sort_mode: String,
    /// norm_project_path -> ordered waterfall chat session ids (manual drag)
    #[serde(default)]
    session_order: std::collections::HashMap<String, Vec<String>>,
}

fn default_sort_mode() -> String {
    "activity".into()
}

fn projects_store_path() -> PathBuf {
    home_dir().join(".waterfall").join("projects.json")
}

fn norm_path(p: &str) -> String {
    let t = p.trim().replace('/', "\\");
    // strip trailing slashes
    let t = t.trim_end_matches('\\').to_string();
    t.to_lowercase()
}

fn load_project_store() -> ProjectStore {
    let path = projects_store_path();
    if !path.is_file() {
        return ProjectStore::default();
    }
    fs::read_to_string(&path)
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn save_project_store(store: &ProjectStore) -> Result<(), String> {
    let path = projects_store_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let raw = serde_json::to_string_pretty(store).map_err(|e| e.to_string())?;
    fs::write(&path, raw).map_err(|e| e.to_string())
}

fn path_in_list(list: &[String], path: &str) -> bool {
    let n = norm_path(path);
    list.iter().any(|x| norm_path(x) == n)
}

fn toggle_path_list(list: &mut Vec<String>, path: &str, on: bool) {
    let n = norm_path(path);
    list.retain(|x| norm_path(x) != n);
    if on {
        list.push(path.trim().replace('/', "\\"));
    }
}

fn local_app_data() -> PathBuf {
    std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn home_dir() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
}

fn command_silent(program: &Path) -> Command {
    let mut cmd = Command::new(program);
    cmd.stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

fn peer_candidates() -> Vec<(String, String, String, Vec<PathBuf>)> {
    let lad = local_app_data();
    vec![
        (
            "cc-switch".into(),
            "CC Switch".into(),
            "providers".into(),
            vec![
                lad.join("Programs").join("CC Switch").join("CC Switch.exe"),
                lad.join("Programs")
                    .join("CC Switch")
                    .join("cc-switch.exe"),
            ],
        ),
        (
            "aionui".into(),
            "AionUi".into(),
            "multi-agent".into(),
            vec![
                lad.join("Programs").join("AionUi").join("AionUi.exe"),
                lad.join("Programs").join("AionUi").join("aionui.exe"),
            ],
        ),
        (
            "opencode".into(),
            "OpenCode Desktop".into(),
            "coding-agent".into(),
            vec![
                lad.join("Programs")
                    .join("@opencode-aidesktop")
                    .join("OpenCode.exe"),
                lad.join("Programs")
                    .join("@opencode-aidesktop")
                    .join("opencode.exe"),
            ],
        ),
        (
            "openchamber".into(),
            "OpenChamber".into(),
            "sessions".into(),
            vec![
                lad.join("Programs")
                    .join("@openchamberelectron")
                    .join("OpenChamber.exe"),
                lad.join("Programs")
                    .join("OpenChamber")
                    .join("OpenChamber.exe"),
            ],
        ),
    ]
}

fn find_first(paths: &[PathBuf]) -> Option<PathBuf> {
    paths.iter().find(|p| p.is_file()).cloned()
}

fn which(cmd: &str) -> Option<PathBuf> {
    // Use `where` on Windows without a console window
    #[cfg(windows)]
    {
        let mut c = Command::new("where");
        c.arg(cmd).stdin(Stdio::null()).stderr(Stdio::null());
        use std::os::windows::process::CommandExt;
        c.creation_flags(CREATE_NO_WINDOW);
        let out = c.output().ok()?;
        if !out.status.success() {
            return None;
        }
        let text = String::from_utf8_lossy(&out.stdout);
        let first = text.lines().next()?.trim();
        if first.is_empty() {
            return None;
        }
        let p = PathBuf::from(first);
        if p.is_file() {
            return Some(p);
        }
    }
    #[cfg(not(windows))]
    {
        let out = Command::new("which").arg(cmd).output().ok()?;
        if !out.status.success() {
            return None;
        }
        let first = String::from_utf8_lossy(&out.stdout).trim().to_string();
        let p = PathBuf::from(first);
        if p.is_file() {
            return Some(p);
        }
    }
    None
}

/// Result of decoding a Claude project slug.
struct DecodedProject {
    /// Display name (top-level project under Aether, or folder name).
    label: String,
    /// Directory to open in Claude/Codex/Grok (top-level project root).
    launch_path: PathBuf,
    /// Grouping key (lowercase), merges OneDrive + nested paths of same project.
    group_key: String,
    /// True if path exists on disk and is not garbage.
    valid: bool,
}

/// Decode Claude project folder slug.
/// Claude stores paths as `C--Users-adamp-Aether-8020-best-server` (drive + -- + hyphenated path;
/// dots in names become hyphens).
fn decode_claude_project_slug(slug: &str) -> DecodedProject {
    let lower = slug.to_lowercase();
    // Garbage / incomplete
    if lower == "c--" || lower == "d--" || lower.len() < 6 {
        return DecodedProject {
            label: slug.into(),
            launch_path: PathBuf::from(slug),
            group_key: format!("invalid:{}", lower),
            valid: false,
        };
    }

    let aether = home_dir().join("Aether");
    let onedrive_aether = home_dir().join("OneDrive").join("Aether");

    // Prefer real Aether roots first
    for (prefix, root) in [
        ("c--users-adamp-aether", aether.clone()),
        ("c--users-adamp-onedrive-aether", onedrive_aether.clone()),
    ] {
        if lower == prefix {
            return DecodedProject {
                label: "Aether".into(),
                launch_path: root.clone(),
                group_key: "aether:root".into(),
                valid: root.is_dir(),
            };
        }
        let pfx = format!("{prefix}-");
        if let Some(rest) = lower.strip_prefix(&pfx) {
            if let Some(full) = resolve_hyphen_path(&root, rest) {
                // One row per *top-level* project under Aether (merge nested + OneDrive)
                let top = top_level_under(&root, &full).unwrap_or(full.clone());
                let label = top
                    .file_name()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_else(|| "Aether".into());
                let group_key = format!("aether:{}", label.to_lowercase());
                // Prefer non-OneDrive launch path when that folder exists
                let preferred = aether.join(&label);
                let launch = if preferred.is_dir() {
                    preferred
                } else {
                    top
                };
                return DecodedProject {
                    label,
                    launch_path: launch,
                    group_key,
                    valid: true,
                };
            }
            // Fallback dotted name under Aether
            let dotted = rest.split('-').collect::<Vec<_>>().join(".");
            // Take first segment as top-level attempt: 8020.best from 8020-best-server
            if let Some(top_name) = first_existing_top_level(&root, rest) {
                let launch = root.join(&top_name);
                return DecodedProject {
                    label: top_name.clone(),
                    launch_path: launch,
                    group_key: format!("aether:{}", top_name.to_lowercase()),
                    valid: true,
                };
            }
            let launch = root.join(&dotted);
            return DecodedProject {
                label: dotted.clone(),
                launch_path: launch.clone(),
                group_key: format!("aether:{}", dotted.to_lowercase()),
                valid: launch.is_dir(),
            };
        }
    }

    // General Windows: C--Users-adamp-ObsidianVault
    if let Some((drive, rest)) = split_drive_slug(&lower) {
        let user_home = home_dir();
        // Walk from home when slug starts with Users-adamp
        let home_pfx = format!(
            "users-{}-",
            user_home
                .file_name()
                .map(|s| s.to_string_lossy().to_lowercase())
                .unwrap_or_else(|| "adamp".into())
        );
        if let Some(rest2) = rest.strip_prefix(&home_pfx).or_else(|| {
            rest.strip_prefix("users-adamp-")
        }) {
            if let Some(full) = resolve_hyphen_path(&user_home, rest2) {
                let label = full
                    .file_name()
                    .map(|s| s.to_string_lossy().to_string())
                    .unwrap_or_else(|| full.display().to_string());
                // If under Aether, re-group as aether project
                if let Some(top) = top_level_under(&aether, &full)
                    .or_else(|| top_level_under(&onedrive_aether, &full))
                {
                    let lab = top
                        .file_name()
                        .map(|s| s.to_string_lossy().to_string())
                        .unwrap_or(label);
                    let preferred = aether.join(&lab);
                    return DecodedProject {
                        label: lab.clone(),
                        launch_path: if preferred.is_dir() { preferred } else { top },
                        group_key: format!("aether:{}", lab.to_lowercase()),
                        valid: true,
                    };
                }
                return DecodedProject {
                    label: label.clone(),
                    launch_path: full.clone(),
                    group_key: format!("path:{}", full.display().to_string().to_lowercase()),
                    valid: full.is_dir(),
                };
            }
        }
        // Last resort: X:\ + hyphen path as single segment chain from drive root
        let drive_root = PathBuf::from(format!("{}:\\", drive.to_uppercase()));
        if let Some(full) = resolve_hyphen_path(&drive_root, rest) {
            let label = full
                .file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| full.display().to_string());
            return DecodedProject {
                label,
                launch_path: full.clone(),
                group_key: format!("path:{}", full.display().to_string().to_lowercase()),
                valid: full.is_dir(),
            };
        }
    }

    DecodedProject {
        label: slug.into(),
        launch_path: PathBuf::from(slug),
        group_key: format!("raw:{}", lower),
        valid: false,
    }
}

fn split_drive_slug(lower: &str) -> Option<(char, &str)> {
    // c--users-...
    let bytes = lower.as_bytes();
    if bytes.len() >= 4 && bytes[1] == b'-' && bytes[2] == b'-' {
        let drive = bytes[0] as char;
        if drive.is_ascii_alphabetic() {
            return Some((drive, &lower[3..]));
        }
    }
    None
}

fn top_level_under(root: &Path, full: &Path) -> Option<PathBuf> {
    let rel = full.strip_prefix(root).ok()?;
    let first = rel.components().next()?;
    Some(root.join(first))
}

/// First path segment under root that exists, using greedy hyphen matching.
fn first_existing_top_level(root: &Path, rest: &str) -> Option<String> {
    let parts: Vec<&str> = rest.split('-').filter(|p| !p.is_empty()).collect();
    for n in (1..=parts.len()).rev() {
        let chunk = parts[..n].join("-");
        let dotted = parts[..n].join(".");
        for name in [dotted.as_str(), chunk.as_str()] {
            if root.join(name).is_dir() {
                return Some(name.to_string());
            }
        }
    }
    None
}

/// Map hyphen slug segments onto real directories under `root`.
fn resolve_hyphen_path(root: &Path, rest: &str) -> Option<PathBuf> {
    let parts: Vec<&str> = rest.split('-').filter(|p| !p.is_empty()).collect();
    if parts.is_empty() {
        return if root.is_dir() {
            Some(root.to_path_buf())
        } else {
            None
        };
    }
    fn walk(cur: &Path, parts: &[&str]) -> Option<PathBuf> {
        if parts.is_empty() {
            return if cur.is_dir() {
                Some(cur.to_path_buf())
            } else {
                None
            };
        }
        for n in (1..=parts.len()).rev() {
            let chunk = parts[..n].join("-");
            let dotted = parts[..n].join(".");
            let spaced = parts[..n].join(" ");
            for name in [chunk.as_str(), dotted.as_str(), spaced.as_str()] {
                let candidate = cur.join(name);
                if candidate.is_dir() {
                    if let Some(found) = walk(&candidate, &parts[n..]) {
                        return Some(found);
                    }
                }
            }
        }
        None
    }
    walk(root, &parts)
}

fn system_time_iso(t: SystemTime) -> String {
    // Simple RFC3339-ish via duration; good enough for sorting/display
    match t.duration_since(SystemTime::UNIX_EPOCH) {
        Ok(d) => format!("{}", d.as_secs()),
        Err(_) => "0".into(),
    }
}

#[tauri::command]
fn list_peers() -> Vec<PeerApp> {
    peer_candidates()
        .into_iter()
        .map(|(id, label, kind, paths)| {
            let found = find_first(&paths);
            PeerApp {
                id,
                label,
                kind,
                available: found.is_some(),
                path: found.map(|p| p.display().to_string()),
            }
        })
        .collect()
}

#[tauri::command]
fn list_agent_clis() -> Vec<AgentCli> {
    let specs = [
        ("claude", "Claude Code"),
        ("codex", "Codex"),
        ("grok", "Grok Build"),
        ("opencode", "OpenCode CLI"),
    ];
    specs
        .into_iter()
        .map(|(id, label)| {
            let path = which(id);
            AgentCli {
                id: id.into(),
                label: label.into(),
                available: path.is_some(),
                path: path.map(|p| p.display().to_string()),
            }
        })
        .collect()
}

#[tauri::command]
fn launch_peer(id: String) -> Result<String, String> {
    let peers = peer_candidates();
    let peer = peers
        .iter()
        .find(|(pid, _, _, _)| pid == &id)
        .ok_or_else(|| format!("unknown peer: {id}"))?;
    let path = find_first(&peer.3).ok_or_else(|| {
        format!(
            "{} not found. Install it first (see PEERS_INSTALLED.md).",
            peer.1
        )
    })?;
    command_silent(&path)
        .spawn()
        .map_err(|e| format!("failed to launch {}: {e}", path.display()))?;
    Ok(format!("launched {}", peer.1))
}

/// Launch a coding CLI agent in a new console at cwd (external TUI).
/// Prefer `run_agent_local` for in-app chat (no terminal).
#[tauri::command]
fn launch_agent_in_project(
    agent: String,
    cwd: String,
    prompt: Option<String>,
) -> Result<String, String> {
    let cwd_path = PathBuf::from(&cwd);
    if !cwd_path.is_dir() {
        return Err(format!("not a directory: {cwd}"));
    }
    let bin = which(&agent).ok_or_else(|| {
        format!("{agent} not on PATH. Install Claude Code / Codex / Grok CLI first.")
    })?;
    let prompt = prompt
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());

    #[cfg(windows)]
    {
        // New console so the agent is interactive (not CREATE_NO_WINDOW)
        use std::os::windows::process::CommandExt;
        const CREATE_NEW_CONSOLE: u32 = 0x0000_0010;
        let mut cmd = Command::new(&bin);
        cmd.current_dir(&cwd_path)
            .creation_flags(CREATE_NEW_CONSOLE);
        if let Some(ref p) = prompt {
            cmd.arg(p);
        }
        cmd.spawn()
            .map_err(|e| format!("failed to launch {agent}: {e}"))?;
    }
    #[cfg(not(windows))]
    {
        let mut cmd = Command::new(&bin);
        cmd.current_dir(&cwd_path);
        if let Some(ref p) = prompt {
            cmd.arg(p);
        }
        cmd.spawn()
            .map_err(|e| format!("failed to launch {agent}: {e}"))?;
    }
    Ok(if prompt.is_some() {
        format!("launched {agent} in {cwd} with prompt")
    } else {
        format!("launched {agent} in {cwd}")
    })
}

#[derive(Clone, Serialize)]
struct AgentStreamEvent {
    /// start | text | thought | status | tool | log | usage | error | done | tick
    kind: String,
    text: String,
    agent: String,
    /// Monotonic ms since run start (for UI timers)
    ms: u64,
    /// Correlates stream events to one in-app run (UI stays free while agent works)
    #[serde(default)]
    run_id: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    ok: Option<bool>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    exit_code: Option<i32>,
}

#[derive(Serialize)]
struct AgentRunResult {
    ok: bool,
    agent: String,
    text: String,
    exit_code: i32,
    mode: String,
    elapsed_ms: u64,
    #[serde(default)]
    run_id: String,
}

/// Returned immediately so the webview is never stuck awaiting a long agent turn.
#[derive(Serialize)]
struct AgentStartResult {
    ok: bool,
    run_id: String,
    agent: String,
    mode: String,
}

/// Cache PATH lookups so we don't shell out to `where` every send.
static WHICH_CACHE: Mutex<Option<std::collections::HashMap<String, Option<PathBuf>>>> =
    Mutex::new(None);

fn which_cached(cmd: &str) -> Option<PathBuf> {
    if let Ok(guard) = WHICH_CACHE.lock() {
        if let Some(map) = guard.as_ref() {
            if let Some(hit) = map.get(cmd) {
                return hit.clone();
            }
        }
    }
    let found = which(cmd);
    if let Ok(mut guard) = WHICH_CACHE.lock() {
        let map = guard.get_or_insert_with(std::collections::HashMap::new);
        map.insert(cmd.to_string(), found.clone());
    }
    found
}

fn emit_agent(app: &AppHandle, kind: &str, text: &str, agent: &str, t0: Instant, run_id: &str) {
    emit_agent_full(app, kind, text, agent, t0, run_id, None, None);
}

fn emit_agent_full(
    app: &AppHandle,
    kind: &str,
    text: &str,
    agent: &str,
    t0: Instant,
    run_id: &str,
    ok: Option<bool>,
    exit_code: Option<i32>,
) {
    let ms = t0.elapsed().as_millis() as u64;
    let _ = app.emit(
        "agent-stream",
        AgentStreamEvent {
            kind: kind.into(),
            text: text.into(),
            agent: agent.into(),
            ms,
            run_id: run_id.into(),
            ok,
            exit_code,
        },
    );
}

/// Flush coalesced assistant text at most ~20x/sec so WebView2 is not event-flooded.
struct TextCoalescer {
    app: AppHandle,
    agent: String,
    run_id: String,
    t0: Instant,
    buf: Mutex<String>,
    last_flush: Mutex<Instant>,
}

impl TextCoalescer {
    fn new(app: AppHandle, agent: String, run_id: String, t0: Instant) -> Arc<Self> {
        Arc::new(Self {
            app,
            agent,
            run_id,
            t0,
            buf: Mutex::new(String::new()),
            last_flush: Mutex::new(t0),
        })
    }

    fn push(self: &Arc<Self>, text: &str) {
        if text.is_empty() {
            return;
        }
        if let Ok(mut b) = self.buf.lock() {
            b.push_str(text);
        }
        let should = self
            .last_flush
            .lock()
            .map(|t| t.elapsed() >= Duration::from_millis(50))
            .unwrap_or(true);
        if should {
            self.flush();
        }
    }

    fn flush(self: &Arc<Self>) {
        let chunk = if let Ok(mut b) = self.buf.lock() {
            if b.is_empty() {
                return;
            }
            std::mem::take(&mut *b)
        } else {
            return;
        };
        if let Ok(mut t) = self.last_flush.lock() {
            *t = Instant::now();
        }
        emit_agent(
            &self.app,
            "text",
            &chunk,
            &self.agent,
            self.t0,
            &self.run_id,
        );
    }
}

/// Build a headless (no TUI / no console) command for in-app agent runs.
fn build_local_agent_command(
    agent: &str,
    bin: &Path,
    cwd: &Path,
    prompt: &str,
    resume: bool,
) -> Result<Command, String> {
    let mut cmd = Command::new(bin);
    match agent {
        "grok" => {
            // Local Grok Build CLI, headless. Verbose streaming NDJSON into waterfall.
            cmd.arg("--single")
                .arg(prompt)
                .arg("--cwd")
                .arg(cwd)
                .arg("--always-approve")
                .arg("--output-format")
                .arg("streaming-json")
                .arg("--include-partial-messages");
            if resume {
                cmd.arg("--continue");
            }
            // Encourage unbuffered progress on Windows
            cmd.env("PYTHONUNBUFFERED", "1");
            cmd.env("NO_COLOR", "1");
        }
        "claude" => {
            cmd.arg("-p")
                .arg(prompt)
                .arg("--output-format")
                .arg("stream-json")
                .arg("--verbose")
                .current_dir(cwd);
            if resume {
                cmd.arg("--continue");
            }
            cmd.env("NO_COLOR", "1");
        }
        "codex" => {
            cmd.arg("exec").arg("--json").arg(prompt).current_dir(cwd);
            cmd.env("NO_COLOR", "1");
        }
        other => {
            return Err(format!(
                "{other} has no in-app local runner yet. Use Open TUI, or pick Grok."
            ));
        }
    }
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    Ok(cmd)
}

fn json_string_field(v: &serde_json::Value, keys: &[&str]) -> String {
    for k in keys {
        if let Some(x) = v.get(*k) {
            if let Some(s) = x.as_str() {
                if !s.is_empty() {
                    return s.to_string();
                }
            }
            if !x.is_null() && !x.is_object() && !x.is_array() {
                return x.to_string();
            }
        }
    }
    String::new()
}

/// Parse one NDJSON / plain line into zero or more (kind, text) events. Verbose.
fn parse_stream_line_verbose(line: &str) -> Vec<(String, String)> {
    let t = line.trim();
    if t.is_empty() {
        return vec![];
    }
    if !t.starts_with('{') {
        return vec![("text".into(), format!("{line}\n"))];
    }
    let Ok(v) = serde_json::from_str::<serde_json::Value>(t) else {
        // Huge or partial JSON — show a short log, not the wall
        let preview: String = t.chars().take(120).collect();
        return vec![("log".into(), format!("raw: {preview}…"))];
    };

    let ty = v
        .get("type")
        .or_else(|| v.get("event"))
        .and_then(|x| x.as_str())
        .unwrap_or("");

    match ty {
        "text" | "assistant" | "message" | "content_block_delta" | "stream_event" => {
            // Prefer delta / data / text
            let mut data = json_string_field(&v, &["data", "text", "delta", "content"]);
            if data.is_empty() {
                if let Some(d) = v.get("delta") {
                    data = json_string_field(d, &["text", "partial_json", "thinking"]);
                    if data.is_empty() {
                        if let Some(s) = d.get("type").and_then(|x| x.as_str()) {
                            if s.contains("thinking") {
                                let th = json_string_field(d, &["thinking", "text"]);
                                if !th.is_empty() {
                                    return vec![("thought".into(), th)];
                                }
                            }
                        }
                    }
                }
            }
            if data.is_empty() {
                return vec![];
            }
            // Heuristic: message-level content arrays
            if let Some(arr) = v.get("content").and_then(|c| c.as_array()) {
                let mut out = vec![];
                for part in arr {
                    let ptype = part.get("type").and_then(|x| x.as_str()).unwrap_or("text");
                    let txt = json_string_field(part, &["text", "thinking", "content"]);
                    if txt.is_empty() {
                        continue;
                    }
                    if ptype.contains("think") {
                        out.push(("thought".into(), txt));
                    } else {
                        out.push(("text".into(), txt));
                    }
                }
                if !out.is_empty() {
                    return out;
                }
            }
            vec![("text".into(), data)]
        }
        "thought" | "thinking" | "reasoning" | "thinking_delta" => {
            let data = json_string_field(&v, &["data", "text", "thinking", "delta"]);
            if data.is_empty() {
                vec![]
            } else {
                vec![("thought".into(), data)]
            }
        }
        "tool_call" | "tool_use" | "tool" | "tool_start" | "function_call" => {
            let name = json_string_field(&v, &["name", "tool", "tool_name", "id"]);
            let name = if name.is_empty() {
                "tool".into()
            } else {
                name
            };
            let input = v
                .get("input")
                .or_else(|| v.get("arguments"))
                .or_else(|| v.get("args"))
                .or_else(|| v.get("data"))
                .map(|x| {
                    let s = if x.is_string() {
                        x.as_str().unwrap_or("").to_string()
                    } else {
                        x.to_string()
                    };
                    if s.len() > 280 {
                        format!("{}…", &s[..280])
                    } else {
                        s
                    }
                })
                .unwrap_or_default();
            let text = if input.is_empty() {
                format!("⚙ {name}")
            } else {
                format!("⚙ {name}  {input}")
            };
            vec![("tool".into(), text)]
        }
        "tool_result" | "tool_end" | "function_call_output" => {
            let name = json_string_field(&v, &["name", "tool", "tool_name"]);
            let preview = json_string_field(&v, &["data", "output", "result", "content"]);
            let preview = if preview.len() > 200 {
                format!("{}…", &preview[..200])
            } else {
                preview
            };
            let text = if preview.is_empty() {
                format!("✓ {}", if name.is_empty() { "tool" } else { &name })
            } else {
                format!(
                    "✓ {} → {}",
                    if name.is_empty() { "tool" } else { &name },
                    preview
                )
            };
            vec![("tool".into(), text)]
        }
        "status" | "progress" | "system" | "info" | "notification" => {
            let data = json_string_field(&v, &["data", "text", "message", "status"]);
            if data.is_empty() {
                vec![("status".into(), ty.into())]
            } else {
                vec![("status".into(), data)]
            }
        }
        "usage" => {
            let u = v.get("usage").cloned().unwrap_or(v.clone());
            let inn = u.get("input_tokens").or_else(|| u.get("input")).and_then(|x| x.as_u64()).unwrap_or(0);
            let out = u
                .get("output_tokens")
                .or_else(|| u.get("output"))
                .and_then(|x| x.as_u64())
                .unwrap_or(0);
            let cache = u
                .get("cache_read_input_tokens")
                .and_then(|x| x.as_u64())
                .unwrap_or(0);
            vec![(
                "usage".into(),
                format!("tokens in={inn} out={out} cache_read={cache}"),
            )]
        }
        "error" => {
            let data = json_string_field(&v, &["data", "message", "error", "text"]);
            vec![("error".into(), if data.is_empty() { "error".into() } else { data })]
        }
        "available_commands" => {
            // Huge payload — one short status only
            let ntools = v
                .get("tools")
                .and_then(|t| t.as_array())
                .map(|a| a.len())
                .unwrap_or(0);
            vec![(
                "status".into(),
                format!("agent ready · {ntools} tools"),
            )]
        }
        "session" | "session_init" | "init" => {
            let id = json_string_field(&v, &["session_id", "id", "data"]);
            vec![(
                "status".into(),
                if id.is_empty() {
                    "session started".into()
                } else {
                    format!("session {id}")
                },
            )]
        }
        "" => {
            // Untyped JSON — try useful fields
            let data = json_string_field(&v, &["text", "data", "message", "content"]);
            if data.is_empty() {
                vec![]
            } else {
                vec![("log".into(), data)]
            }
        }
        other => {
            // Verbose: surface unknown event types briefly
            let preview: String = t.chars().take(100).collect();
            vec![("log".into(), format!("[{other}] {preview}"))]
        }
    }
}

/// Start a local agent CLI run without blocking the UI thread.
/// Returns immediately with `run_id`. Progress/result stream via `agent-stream`.
///
/// Why this shape: a long-awaited `invoke` + token event flood made Windows mark
/// the window "Not Responding" even though work was happening. Detach the wait,
/// coalesce text (~20 Hz), and let the webview keep painting.
#[tauri::command]
fn start_agent_local(
    app: AppHandle,
    agent: String,
    cwd: String,
    prompt: String,
    resume: Option<bool>,
) -> Result<AgentStartResult, String> {
    let prompt = prompt.trim().to_string();
    if prompt.is_empty() {
        return Err("empty prompt".into());
    }
    let cwd_path = PathBuf::from(&cwd);
    if !cwd_path.is_dir() {
        return Err(format!("not a directory: {cwd}"));
    }

    let agent = if agent == "auto" {
        which_cached("grok")
            .map(|_| "grok".to_string())
            .or_else(|| which_cached("claude").map(|_| "claude".to_string()))
            .or_else(|| which_cached("codex").map(|_| "codex".to_string()))
            .ok_or_else(|| "no local agent on PATH (install grok / claude / codex)".to_string())?
    } else {
        agent
    };
    let bin = which_cached(&agent).ok_or_else(|| {
        format!("{agent} not on PATH. Install it first (grok login / claude / codex).")
    })?;
    let resume = resume.unwrap_or(false);
    let run_id = new_session_id(); // unique run correlation id
    let t0 = Instant::now();

    emit_agent(
        &app,
        "start",
        "queued local agent…",
        agent.as_str(),
        t0,
        &run_id,
    );

    let app_bg = app.clone();
    let agent_bg = agent.clone();
    let run_bg = run_id.clone();
    let cwd_s = cwd.clone();

    thread::spawn(move || {
        run_agent_local_worker(app_bg, agent_bg, bin, cwd_path, cwd_s, prompt, resume, run_bg, t0);
    });

    Ok(AgentStartResult {
        ok: true,
        run_id,
        agent,
        mode: "local".into(),
    })
}

/// Blocking worker: spawn CLI, stream, wait. Never called on the UI thread.
fn run_agent_local_worker(
    app: AppHandle,
    agent: String,
    bin: PathBuf,
    cwd_path: PathBuf,
    cwd: String,
    prompt: String,
    resume: bool,
    run_id: String,
    t0: Instant,
) {
    let emit = |kind: &str, text: &str| emit_agent(&app, kind, text, &agent, t0, &run_id);

    emit(
        "status",
        &format!(
            "spawn {agent}{} · {}",
            if resume { " (continue)" } else { "" },
            cwd_path
                .file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| cwd.clone())
        ),
    );

    let mut cmd = match build_local_agent_command(&agent, &bin, &cwd_path, &prompt, resume) {
        Ok(c) => c,
        Err(e) => {
            emit_agent_full(
                &app,
                "done",
                &e,
                &agent,
                t0,
                &run_id,
                Some(false),
                Some(-1),
            );
            return;
        }
    };

    let mut child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            let msg = format!("failed to start {agent}: {e}");
            emit("error", &msg);
            emit_agent_full(
                &app,
                "done",
                &msg,
                &agent,
                t0,
                &run_id,
                Some(false),
                Some(-1),
            );
            return;
        }
    };

    let pid = child.id();
    emit("status", &format!("running pid {pid} · waiting for stream…"));

    let stdout = match child.stdout.take() {
        Some(s) => s,
        None => {
            emit("error", "no stdout from agent");
            emit_agent_full(
                &app,
                "done",
                "no stdout from agent",
                &agent,
                t0,
                &run_id,
                Some(false),
                Some(-1),
            );
            return;
        }
    };
    let stderr = child.stderr.take();

    let full_text = Arc::new(Mutex::new(String::new()));
    let err_buf = Arc::new(Mutex::new(String::new()));
    let first_byte = Arc::new(AtomicU64::new(0));
    let stop_hb = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let coalescer = TextCoalescer::new(app.clone(), agent.clone(), run_id.clone(), t0);

    // Heartbeat — status only, never floods the activity log
    {
        let app_hb = app.clone();
        let agent_hb = agent.clone();
        let run_hb = run_id.clone();
        let stop = Arc::clone(&stop_hb);
        let first = Arc::clone(&first_byte);
        thread::spawn(move || {
            while !stop.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_millis(750));
                if stop.load(Ordering::Relaxed) {
                    break;
                }
                let secs = t0.elapsed().as_secs();
                let phase = if first.load(Ordering::Relaxed) == 0 {
                    "warming up (agent loading context)"
                } else {
                    "working"
                };
                emit_agent(
                    &app_hb,
                    "tick",
                    &format!("{phase} · {secs}s"),
                    &agent_hb,
                    t0,
                    &run_hb,
                );
            }
        });
    }

    // Stderr reader
    let stderr_join = stderr.map(|err| {
        let app_e = app.clone();
        let agent_e = agent.clone();
        let run_e = run_id.clone();
        let err_buf = Arc::clone(&err_buf);
        let first = Arc::clone(&first_byte);
        let mut log_budget = 0u32;
        thread::spawn(move || {
            let mut reader = BufReader::new(err);
            let mut line = String::new();
            loop {
                line.clear();
                match reader.read_line(&mut line) {
                    Ok(0) => break,
                    Ok(_) => {
                        if first.load(Ordering::Relaxed) == 0 {
                            first.store(t0.elapsed().as_millis() as u64, Ordering::Relaxed);
                        }
                        let trimmed = line.trim_end();
                        if trimmed.is_empty() {
                            continue;
                        }
                        if let Ok(mut b) = err_buf.lock() {
                            if b.len() < 8000 {
                                b.push_str(trimmed);
                                b.push('\n');
                            }
                        }
                        // Cap stderr log spam (keeps WebView responsive)
                        log_budget += 1;
                        if log_budget > 60 {
                            continue;
                        }
                        let clean: String = trimmed
                            .chars()
                            .filter(|c| !c.is_control() || *c == '\t')
                            .take(240)
                            .collect();
                        if clean.len() > 2 {
                            emit_agent(&app_e, "log", &clean, &agent_e, t0, &run_e);
                        }
                    }
                    Err(_) => break,
                }
            }
        })
    });

    // Stdout reader — coalesce text tokens
    let app_o = app.clone();
    let agent_o = agent.clone();
    let run_o = run_id.clone();
    let full_o = Arc::clone(&full_text);
    let first_o = Arc::clone(&first_byte);
    let coal = Arc::clone(&coalescer);
    let stdout_join = thread::spawn(move || {
        let mut tool_budget = 0u32;
        let mut reader = BufReader::with_capacity(8 * 1024, stdout);
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line) {
                Ok(0) => break,
                Ok(_) => {
                    if first_o.load(Ordering::Relaxed) == 0 {
                        first_o.store(t0.elapsed().as_millis() as u64, Ordering::Relaxed);
                        emit_agent(
                            &app_o,
                            "status",
                            &format!("first stream byte · {}ms", t0.elapsed().as_millis()),
                            &agent_o,
                            t0,
                            &run_o,
                        );
                    }
                    for (kind, text) in parse_stream_line_verbose(&line) {
                        if kind == "text" {
                            if let Ok(mut f) = full_o.lock() {
                                f.push_str(&text);
                            }
                            coal.push(&text);
                        } else if kind == "thought" {
                            emit_agent(&app_o, "thought", &text, &agent_o, t0, &run_o);
                        } else if kind == "tool" || kind == "log" {
                            tool_budget += 1;
                            if tool_budget <= 80 {
                                emit_agent(&app_o, &kind, &text, &agent_o, t0, &run_o);
                            }
                        } else {
                            emit_agent(&app_o, &kind, &text, &agent_o, t0, &run_o);
                        }
                    }
                }
                Err(e) => {
                    emit_agent(&app_o, "error", &e.to_string(), &agent_o, t0, &run_o);
                    break;
                }
            }
        }
        coal.flush();
    });

    let status = match child.wait() {
        Ok(s) => s,
        Err(e) => {
            stop_hb.store(true, Ordering::Relaxed);
            let msg = format!("agent wait failed: {e}");
            emit("error", &msg);
            emit_agent_full(
                &app,
                "done",
                &msg,
                &agent,
                t0,
                &run_id,
                Some(false),
                Some(-1),
            );
            return;
        }
    };
    let _ = stdout_join.join();
    if let Some(j) = stderr_join {
        let _ = j.join();
    }
    stop_hb.store(true, Ordering::Relaxed);
    coalescer.flush();

    let code = status.code().unwrap_or(-1);
    let ok = status.success();
    let mut full = full_text.lock().map(|g| g.clone()).unwrap_or_default();
    let err_s = err_buf.lock().map(|g| g.clone()).unwrap_or_default();
    let elapsed_ms = t0.elapsed().as_millis() as u64;

    if full.trim().is_empty() && !err_s.trim().is_empty() && !ok {
        emit("error", err_s.trim());
        full = err_s.trim().to_string();
    }

    if full.trim().is_empty() && ok {
        full = "(no text response)".into();
        emit("text", &full);
    }

    // Final full text piggybacks on done (UI may already have streamed it)
    let done_msg = if ok {
        format!("done · {elapsed_ms}ms")
    } else {
        format!("exit {code} · {elapsed_ms}ms")
    };
    // Prefer streaming body; if UI missed tokens, send full in done text after a marker
    let done_payload = if full.len() < 120_000 {
        format!("{done_msg}\n\x1e{full}")
    } else {
        done_msg
    };
    emit_agent_full(
        &app,
        "done",
        &done_payload,
        &agent,
        t0,
        &run_id,
        Some(ok),
        Some(code),
    );
}

/// Alias that starts a detached run and returns immediately (same as start_agent_local).
/// Completion is always via `agent-stream` done events — never blocks the window.
#[tauri::command]
fn run_agent_local(
    app: AppHandle,
    agent: String,
    cwd: String,
    prompt: String,
    resume: Option<bool>,
) -> Result<AgentRunResult, String> {
    let start = start_agent_local(app, agent, cwd, prompt, resume)?;
    Ok(AgentRunResult {
        ok: true,
        agent: start.agent,
        text: String::new(),
        exit_code: 0,
        mode: "local-async".into(),
        elapsed_ms: 0,
        run_id: start.run_id,
    })
}

/// One row per top-level project (merges nested paths + OneDrive duplicates).
#[tauri::command]
fn list_claude_sessions(limit: usize) -> Result<Vec<ClaudeSessionRow>, String> {
    let root = home_dir().join(".claude").join("projects");
    if !root.is_dir() {
        return Ok(vec![]);
    }

    let mut by_project: std::collections::HashMap<String, ClaudeSessionRow> =
        std::collections::HashMap::new();

    let entries = fs::read_dir(&root).map_err(|e| e.to_string())?;
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let slug = path
            .file_name()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        // Skip paperclip/temp workspaces and other noise
        let slug_l = slug.to_lowercase();
        if slug_l.contains("paperclip")
            || slug_l.contains("appdata")
            || slug_l.contains("temp")
            || slug_l.contains("tmp")
        {
            continue;
        }

        let decoded = decode_claude_project_slug(&slug);
        if !decoded.valid {
            continue;
        }
        if !decoded.launch_path.is_dir() {
            continue;
        }

        let files = match fs::read_dir(&path) {
            Ok(f) => f,
            Err(_) => continue,
        };
        for f in files.flatten() {
            let fp = f.path();
            if fp.extension().and_then(|e| e.to_str()) != Some("jsonl") {
                continue;
            }
            if fp.to_string_lossy().contains("subagents") {
                continue;
            }
            let meta = match f.metadata() {
                Ok(m) => m,
                Err(_) => continue,
            };
            let mtime = meta.modified().unwrap_or(SystemTime::UNIX_EPOCH);
            let session_id = fp
                .file_stem()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_default();
            let key = decoded.group_key.clone();
            let candidate = ClaudeSessionRow {
                project: decoded.label.clone(),
                project_path: decoded.launch_path.display().to_string(),
                session_id,
                mtime: system_time_iso(mtime),
                size_bytes: meta.len(),
                file: fp.display().to_string(),
                session_count: 1,
            };
            match by_project.get_mut(&key) {
                Some(existing) => {
                    existing.session_count = existing.session_count.saturating_add(1);
                    if candidate.mtime > existing.mtime {
                        let count = existing.session_count;
                        // Keep preferred non-OneDrive path if we already have one
                        let keep_path = existing.project_path.clone();
                        let keep_label = existing.project.clone();
                        *existing = candidate;
                        existing.session_count = count;
                        if keep_path.to_lowercase().contains("\\aether\\")
                            && !keep_path.to_lowercase().contains("onedrive")
                        {
                            existing.project_path = keep_path;
                            existing.project = keep_label;
                        }
                    }
                }
                None => {
                    by_project.insert(key, candidate);
                }
            }
        }
    }

    let mut rows: Vec<ClaudeSessionRow> = by_project.into_values().collect();
    rows.sort_by(|a, b| b.mtime.cmp(&a.mtime));
    rows.truncate(limit.max(1).min(200));
    Ok(rows)
}

fn find_python() -> Option<PathBuf> {
    let candidates = [
        std::env::var_os("LOCALAPPDATA").map(|p| {
            PathBuf::from(p)
                .join("Python")
                .join("pythoncore-3.14-64")
                .join("python.exe")
        }),
        std::env::var_os("LOCALAPPDATA").map(|p| {
            PathBuf::from(p)
                .join("Programs")
                .join("Python")
                .join("Python313")
                .join("python.exe")
        }),
        Some(PathBuf::from("python")),
        Some(PathBuf::from("python3")),
    ];
    for c in candidates.into_iter().flatten() {
        if c.as_os_str() == "python" || c.as_os_str() == "python3" {
            let mut cmd = Command::new(&c);
            cmd.arg("-c").arg("import desktop.server");
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }
            if cmd.status().map(|s| s.success()).unwrap_or(false) {
                return Some(c);
            }
        } else if c.is_file() {
            return Some(c);
        }
    }
    Some(PathBuf::from("python"))
}

fn aether_waterfall_root() -> Option<PathBuf> {
    if let Some(manifest) = option_env!("CARGO_MANIFEST_DIR") {
        let root = PathBuf::from(manifest).join("..").canonicalize().ok()?;
        if root.join("desktop").join("server.py").is_file() {
            return Some(root);
        }
    }
    if let Ok(p) = std::env::var("WATERFALL_ROOT") {
        let root = PathBuf::from(p);
        if root.join("desktop").join("server.py").is_file() {
            return Some(root);
        }
    }
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?.to_path_buf();
    for _ in 0..6 {
        if dir.join("desktop").join("server.py").is_file() {
            return Some(dir);
        }
        if !dir.pop() {
            break;
        }
    }
    // Default checkout path
    let fallback = home_dir().join("Aether").join("waterfall.sh");
    if fallback.join("desktop").join("server.py").is_file() {
        return Some(fallback);
    }
    None
}

fn backend_reachable(port: u16) -> bool {
    use std::net::TcpStream;
    use std::time::Duration;
    TcpStream::connect_timeout(
        &format!("127.0.0.1:{port}").parse().unwrap(),
        Duration::from_millis(200),
    )
    .is_ok()
}

#[tauri::command]
fn start_backend(state: State<BackendState>, port: u16) -> Result<String, String> {
    if backend_reachable(port) {
        return Ok(format!("backend already listening on 127.0.0.1:{port}"));
    }

    {
        let guard = state.child.lock().map_err(|e| e.to_string())?;
        if guard.is_some() {
            return Ok(format!("backend process already tracked for port {port}"));
        }
    }

    let py = find_python().ok_or("python not found")?;
    let root = aether_waterfall_root()
        .ok_or("could not find waterfall.sh repo (desktop/server.py). Set WATERFALL_ROOT.")?;

    let log_path = std::env::temp_dir().join("waterfall-backend.log");
    let log_file = std::fs::File::create(&log_path)
        .map_err(|e| format!("cannot write {}: {e}", log_path.display()))?;

    let mut cmd = Command::new(&py);
    cmd.arg("-m")
        .arg("desktop.server")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .arg("--no-open")
        .current_dir(&root)
        .env("PYTHONPATH", root.display().to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::from(log_file));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let child = cmd
        .spawn()
        .map_err(|e| format!("failed to start python backend: {e}"))?;

    let mut guard = state.child.lock().map_err(|e| e.to_string())?;
    *guard = Some(child);
    Ok(format!(
        "started cascade backend on 127.0.0.1:{port} cwd={} log={}",
        root.display(),
        log_path.display()
    ))
}

#[tauri::command]
fn backend_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

#[tauri::command]
fn process_note() -> serde_json::Value {
    serde_json::json!({
        "powershell": "waterfall does not start PowerShell. If you see powershell.exe, check Task Manager parent: Claude Desktop often owns it.",
        "waterfall_children": ["msedgewebview2.exe", "python.exe -m desktop.server"],
    })
}

#[derive(Serialize, Deserialize, Clone)]
struct AestheticPrefs {
    /// deep | midnight | slate | sand
    theme: String,
    /// brand accent hex
    accent: String,
    /// comfortable | compact
    density: String,
    /// 0.9 | 1 | 1.1
    scale: f32,
    /// left | right
    rail: String,
    /// show token savings hero on home
    savings_hero: bool,
}

impl Default for AestheticPrefs {
    fn default() -> Self {
        Self {
            theme: "deep".into(),
            accent: "#5ec6ff".into(),
            density: "comfortable".into(),
            scale: 1.0,
            rail: "left".into(),
            savings_hero: true,
        }
    }
}

#[derive(Serialize, Deserialize, Clone)]
struct OAuthState {
    /// local | pending | connected
    status: String,
    user_id: Option<String>,
    email: Option<String>,
    display_name: Option<String>,
    /// reserved for future waterfall OAuth tokens (never log)
    access_token: Option<String>,
    refresh_token: Option<String>,
    updated_at: String,
}

impl Default for OAuthState {
    fn default() -> Self {
        Self {
            status: "local".into(),
            user_id: None,
            email: None,
            display_name: None,
            access_token: None,
            refresh_token: None,
            updated_at: "".into(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone)]
struct UserProfile {
    /// Local device profile; binds to OAuth user when connected
    profile_id: String,
    aesthetic: AestheticPrefs,
    oauth: OAuthState,
    /// Preferred agent id for project launch (claude|codex|grok|opencode)
    default_agent: String,
    /// Agent module order for project rows
    agent_modules: Vec<String>,
}

fn profile_path() -> PathBuf {
    home_dir().join(".waterfall").join("profile.json")
}

fn now_iso() -> String {
    // unix seconds string is fine for local prefs
    system_time_iso(SystemTime::now())
}

fn default_profile() -> UserProfile {
    UserProfile {
        profile_id: format!("local-{}", now_iso()),
        aesthetic: AestheticPrefs::default(),
        oauth: OAuthState {
            status: "local".into(),
            updated_at: now_iso(),
            ..Default::default()
        },
        default_agent: "auto".into(),
        agent_modules: vec![
            "claude".into(),
            "codex".into(),
            "grok".into(),
            "opencode".into(),
        ],
    }
}

#[tauri::command]
fn get_profile() -> Result<UserProfile, String> {
    let path = profile_path();
    if !path.is_file() {
        let p = default_profile();
        save_profile(p.clone())?;
        return Ok(p);
    }
    let raw = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&raw).map_err(|e| e.to_string())
}

#[tauri::command]
fn save_profile(mut profile: UserProfile) -> Result<UserProfile, String> {
    let path = profile_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    profile.oauth.updated_at = now_iso();
    // When OAuth is local-only, keep tokens null
    if profile.oauth.status == "local" {
        profile.oauth.access_token = None;
        profile.oauth.refresh_token = None;
    }
    let raw = serde_json::to_string_pretty(&profile).map_err(|e| e.to_string())?;
    fs::write(&path, raw).map_err(|e| e.to_string())?;
    Ok(profile)
}

/// Begin waterfall OAuth (scaffold). Opens browser when auth host is configured;
/// otherwise creates a local signed-in aesthetic profile.
#[tauri::command]
fn begin_oauth(email: Option<String>) -> Result<UserProfile, String> {
    let mut profile = get_profile()?;
    // Future: open https://waterfall.sh/oauth/start?device=...
    // Today: local profile bind so aesthetics can save per user identity
    let email = email
        .filter(|e| e.contains('@'))
        .unwrap_or_else(|| "you@local.waterfall".into());
    profile.oauth.status = "connected".into();
    profile.oauth.email = Some(email.clone());
    profile.oauth.display_name = Some(email.split('@').next().unwrap_or("you").into());
    profile.oauth.user_id = Some(format!("wf_{}", now_iso()));
    profile.oauth.access_token = None; // real tokens when OAuth host ships
    profile.oauth.updated_at = now_iso();
    save_profile(profile)
}

#[tauri::command]
fn sign_out() -> Result<UserProfile, String> {
    let mut profile = get_profile()?;
    profile.oauth = OAuthState {
        status: "local".into(),
        updated_at: now_iso(),
        ..Default::default()
    };
    save_profile(profile)
}

// ---------------------------------------------------------------------------
// OpenRouter cascade: one key, shared with the CLI.
//
// The key lives at ~/.claude/openrouter_key.txt, the exact same path
// router/openrouter_api_client.py already reads (DEFAULT_KEY_FILE). Saving it
// here means the desktop app and `waterfall route` use ONE key, not two copies
// that drift. The OPENROUTER_API_KEY env var still wins when set, matching the
// CLI's precedence exactly.
//
// Every request is made from Rust, never the webview, so the key is never
// handed to JS. The UI only ever sees a masked preview and a "configured" flag.
// ---------------------------------------------------------------------------

const OPENROUTER_BASE: &str = "https://openrouter.ai/api/v1";

fn openrouter_key_path() -> PathBuf {
    home_dir().join(".claude").join("openrouter_key.txt")
}

/// Resolve the key the same way the CLI does: env var first, then the file.
fn resolve_openrouter_key() -> String {
    if let Ok(k) = std::env::var("OPENROUTER_API_KEY") {
        let k = k.trim().to_string();
        if !k.is_empty() {
            return k;
        }
    }
    fs::read_to_string(openrouter_key_path())
        .map(|s| s.trim().to_string())
        .unwrap_or_default()
}

fn mask_key(key: &str) -> String {
    let n = key.chars().count();
    if n == 0 {
        return String::new();
    }
    if n <= 12 {
        return "*".repeat(n);
    }
    let head: String = key.chars().take(8).collect();
    let tail: String = key.chars().skip(n - 4).collect();
    format!("{head}...{tail}")
}

#[derive(Serialize)]
struct KeyStatus {
    configured: bool,
    /// "env" when OPENROUTER_API_KEY wins, "file" when read from disk, "" when absent.
    source: String,
    masked: String,
    path: String,
}

#[tauri::command]
fn openrouter_key_status() -> KeyStatus {
    let from_env = std::env::var("OPENROUTER_API_KEY")
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false);
    let key = resolve_openrouter_key();
    KeyStatus {
        configured: !key.is_empty(),
        source: if key.is_empty() {
            String::new()
        } else if from_env {
            "env".into()
        } else {
            "file".into()
        },
        masked: mask_key(&key),
        path: openrouter_key_path().to_string_lossy().to_string(),
    }
}

#[tauri::command]
fn save_openrouter_key(key: String) -> Result<KeyStatus, String> {
    let key = key.trim().to_string();
    if key.is_empty() {
        return Err("key is empty".into());
    }
    let path = openrouter_key_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(&path, &key).map_err(|e| e.to_string())?;
    Ok(openrouter_key_status())
}

#[tauri::command]
fn clear_openrouter_key() -> Result<KeyStatus, String> {
    let path = openrouter_key_path();
    if path.is_file() {
        fs::remove_file(&path).map_err(|e| e.to_string())?;
    }
    Ok(openrouter_key_status())
}

#[derive(Serialize, Clone)]
struct CascadeModel {
    id: String,
    name: String,
    context_length: u64,
    prompt_price: f64,
    /// True when prompt price is exactly 0. Free models sort first and are
    /// genuinely the cheapest capable option, not a pricing sentinel.
    free: bool,
}

/// Fetch the live catalog and return capable text models, cheapest first.
///
/// Mirrors router/openrouter_api_client.py::_priced_candidates: text in and
/// text out, a real context length, and NEGATIVE prices excluded (OpenRouter's
/// "-1" sentinel for meta-routers like openrouter/auto whose real price varies
/// by what they route to internally). A price of exactly 0 is kept: those are
/// real free models and belong at the front of a cheapest-first list.
#[tauri::command]
fn list_openrouter_models(min_context: Option<u64>) -> Result<Vec<CascadeModel>, String> {
    let min_context = min_context.unwrap_or(0);
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| e.to_string())?;

    let mut req = client.get(format!("{OPENROUTER_BASE}/models"));
    let key = resolve_openrouter_key();
    if !key.is_empty() {
        req = req.bearer_auth(&key);
    }
    let resp = req.send().map_err(|e| e.to_string())?;
    if !resp.status().is_success() {
        return Err(format!("OpenRouter returned HTTP {}", resp.status()));
    }
    let body: serde_json::Value = resp.json().map_err(|e| e.to_string())?;
    let items = body
        .get("data")
        .and_then(|d| d.as_array())
        .ok_or("unexpected catalog shape: no `data` array")?;

    let mut out: Vec<CascadeModel> = Vec::new();
    for m in items {
        let id = m.get("id").and_then(|v| v.as_str()).unwrap_or("");
        if id.is_empty() || id.starts_with('~') {
            continue;
        }
        let arch = m.get("architecture");
        let has_mod = |field: &str, want: &str| -> bool {
            arch.and_then(|a| a.get(field))
                .and_then(|v| v.as_array())
                .map(|arr| arr.iter().any(|x| x.as_str() == Some(want)))
                .unwrap_or(false)
        };
        if !has_mod("input_modalities", "text") || !has_mod("output_modalities", "text") {
            continue;
        }
        let ctx = m.get("context_length").and_then(|v| v.as_u64()).unwrap_or(0);
        if ctx < min_context {
            continue;
        }
        let price: f64 = match m
            .get("pricing")
            .and_then(|p| p.get("prompt"))
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<f64>().ok())
        {
            Some(p) => p,
            None => continue,
        };
        if price < 0.0 {
            continue; // the "-1" meta-router sentinel, not a real price
        }
        out.push(CascadeModel {
            id: id.to_string(),
            name: m
                .get("name")
                .and_then(|v| v.as_str())
                .unwrap_or(id)
                .to_string(),
            context_length: ctx,
            prompt_price: price,
            free: price == 0.0,
        });
    }
    out.sort_by(|a, b| {
        a.prompt_price
            .partial_cmp(&b.prompt_price)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    Ok(out)
}

#[derive(Serialize)]
struct CascadeReply {
    model: String,
    content: String,
    prompt_tokens: u64,
    completion_tokens: u64,
    cost: f64,
    elapsed_ms: u128,
}

/// Send one prompt to one model. The key never leaves Rust.
#[tauri::command]
fn openrouter_chat(
    model: String,
    prompt: String,
    max_tokens: Option<u64>,
) -> Result<CascadeReply, String> {
    let key = resolve_openrouter_key();
    if key.is_empty() {
        return Err("No OpenRouter key configured. Add one in Settings.".into());
    }
    let started = std::time::Instant::now();
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(180))
        .build()
        .map_err(|e| e.to_string())?;

    let payload = serde_json::json!({
        "model": model,
        "messages": [{ "role": "user", "content": prompt }],
        "max_tokens": max_tokens.unwrap_or(1024),
    });

    let resp = client
        .post(format!("{OPENROUTER_BASE}/chat/completions"))
        .bearer_auth(&key)
        .json(&payload)
        .send()
        .map_err(|e| e.to_string())?;

    let status = resp.status();
    let body: serde_json::Value = resp.json().map_err(|e| e.to_string())?;
    if !status.is_success() {
        let msg = body
            .get("error")
            .and_then(|e| e.get("message"))
            .and_then(|v| v.as_str())
            .unwrap_or("unknown error");
        return Err(format!("HTTP {status}: {msg}"));
    }

    let content = body
        .get("choices")
        .and_then(|c| c.get(0))
        .and_then(|c| c.get("message"))
        .and_then(|m| m.get("content"))
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let usage = body.get("usage");
    let num = |k: &str| -> u64 {
        usage
            .and_then(|u| u.get(k))
            .and_then(|v| v.as_u64())
            .unwrap_or(0)
    };
    Ok(CascadeReply {
        model: body
            .get("model")
            .and_then(|v| v.as_str())
            .unwrap_or(&model)
            .to_string(),
        content,
        prompt_tokens: num("prompt_tokens"),
        completion_tokens: num("completion_tokens"),
        cost: usage
            .and_then(|u| u.get("cost"))
            .and_then(|v| v.as_f64())
            .unwrap_or(0.0),
        elapsed_ms: started.elapsed().as_millis(),
    })
}

#[tauri::command]
fn set_fullscreen(app: tauri::AppHandle, on: bool) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("main") {
        win.set_fullscreen(on).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn maximize_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("main") {
        win.maximize().map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn order_index(store: &ProjectStore, path: &str) -> usize {
    let n = norm_path(path);
    store
        .order
        .iter()
        .position(|p| norm_path(p) == n)
        .unwrap_or(usize::MAX)
}

fn sort_project_rows(rows: &mut [ProjectRow], store: &ProjectStore, mode: &str) {
    match mode {
        "name" => {
            rows.sort_by(|a, b| {
                a.project
                    .to_lowercase()
                    .cmp(&b.project.to_lowercase())
                    .then_with(|| a.project_path.cmp(&b.project_path))
            });
        }
        "sessions" => {
            rows.sort_by(|a, b| {
                b.session_count
                    .cmp(&a.session_count)
                    .then_with(|| b.mtime.cmp(&a.mtime))
            });
        }
        "path" => {
            rows.sort_by(|a, b| {
                a.project_path
                    .to_lowercase()
                    .cmp(&b.project_path.to_lowercase())
            });
        }
        "manual" => {
            rows.sort_by(|a, b| {
                order_index(store, &a.project_path)
                    .cmp(&order_index(store, &b.project_path))
                    .then_with(|| b.mtime.cmp(&a.mtime))
            });
        }
        // activity (default): pinned first, then last activity desc
        _ => {
            rows.sort_by(|a, b| match (a.pinned, b.pinned) {
                (true, false) => std::cmp::Ordering::Less,
                (false, true) => std::cmp::Ordering::Greater,
                _ => b.mtime.cmp(&a.mtime),
            });
        }
    }
}

/// Projects for sidebar: discovered + manual, pin/archive, sort modes.
#[tauri::command]
fn list_projects(limit: usize, include_archived: Option<bool>) -> Result<Vec<ProjectRow>, String> {
    let include_archived = include_archived.unwrap_or(false);
    let store = load_project_store();
    let discovered = list_claude_sessions(500)?;

    let mut by_key: std::collections::HashMap<String, ProjectRow> =
        std::collections::HashMap::new();

    for d in discovered {
        let key = norm_path(&d.project_path);
        let mut mtime = d.mtime.clone();
        if let Some(lp) = store.last_prompt.get(&key) {
            if lp > &mtime {
                mtime = lp.clone();
            }
        }
        // also try original path key variants
        for (k, v) in &store.last_prompt {
            if norm_path(k) == key && v > &mtime {
                mtime = v.clone();
            }
        }
        by_key.insert(
            key.clone(),
            ProjectRow {
                project: d.project,
                project_path: d.project_path.clone(),
                session_id: d.session_id,
                mtime,
                size_bytes: d.size_bytes,
                file: d.file,
                session_count: d.session_count,
                pinned: path_in_list(&store.pinned, &d.project_path),
                archived: path_in_list(&store.archived, &d.project_path),
                source: "discovered".into(),
            },
        );
    }

    for m in &store.manual {
        let key = norm_path(&m.path);
        let entry = by_key.entry(key.clone()).or_insert_with(|| ProjectRow {
            project: m.label.clone(),
            project_path: m.path.clone(),
            session_id: String::new(),
            mtime: m.added_at.clone(),
            size_bytes: 0,
            file: String::new(),
            session_count: 0,
            pinned: path_in_list(&store.pinned, &m.path),
            archived: path_in_list(&store.archived, &m.path),
            source: "manual".into(),
        });
        // Prefer manual label if user set one
        if !m.label.is_empty() && entry.source == "manual" {
            entry.project = m.label.clone();
        }
        entry.pinned = path_in_list(&store.pinned, &m.path) || entry.pinned;
        entry.archived = path_in_list(&store.archived, &m.path) || entry.archived;
        if let Some(lp) = store.last_prompt.get(&key) {
            if lp > &entry.mtime {
                entry.mtime = lp.clone();
            }
        }
    }

    // Re-apply pin/archive from store by path for all
    for row in by_key.values_mut() {
        row.pinned = path_in_list(&store.pinned, &row.project_path);
        row.archived = path_in_list(&store.archived, &row.project_path);
    }

    let mut rows: Vec<ProjectRow> = by_key.into_values().collect();
    if !include_archived {
        rows.retain(|r| !r.archived);
    }

    let mode = if store.sort_mode.is_empty() {
        "activity"
    } else {
        store.sort_mode.as_str()
    };
    sort_project_rows(&mut rows, &store, mode);
    rows.truncate(limit.max(1).min(300));
    Ok(rows)
}

/// Persist drag-and-drop sidebar order and switch sort mode to manual.
#[tauri::command]
fn reorder_projects(paths: Vec<String>) -> Result<ProjectStore, String> {
    let mut store = load_project_store();
    let mut seen = std::collections::HashSet::new();
    let mut order = Vec::new();
    for p in paths {
        let t = p.trim().replace('/', "\\");
        if t.is_empty() {
            continue;
        }
        let n = norm_path(&t);
        if seen.insert(n) {
            order.push(t);
        }
    }
    store.order = order;
    store.sort_mode = "manual".into();
    save_project_store(&store)?;
    Ok(store)
}

/// activity | name | sessions | path | manual
#[tauri::command]
fn set_project_sort(mode: String) -> Result<ProjectStore, String> {
    let mode = mode.trim().to_lowercase();
    let allowed = ["activity", "name", "sessions", "path", "manual"];
    if !allowed.contains(&mode.as_str()) {
        return Err(format!("unknown sort mode: {mode}"));
    }
    let mut store = load_project_store();
    store.sort_mode = mode;
    save_project_store(&store)?;
    Ok(store)
}

#[tauri::command]
fn get_project_prefs() -> Result<serde_json::Value, String> {
    let store = load_project_store();
    Ok(serde_json::json!({
        "sort_mode": if store.sort_mode.is_empty() { "activity" } else { &store.sort_mode },
        "order_len": store.order.len(),
        "pinned_len": store.pinned.len(),
        "archived_len": store.archived.len(),
    }))
}

#[tauri::command]
fn pin_project(path: String, pinned: bool) -> Result<ProjectStore, String> {
    let mut store = load_project_store();
    toggle_path_list(&mut store.pinned, &path, pinned);
    if pinned {
        // pinned projects leave archive
        toggle_path_list(&mut store.archived, &path, false);
    }
    save_project_store(&store)?;
    Ok(store)
}

#[tauri::command]
fn archive_project(path: String, archived: bool) -> Result<ProjectStore, String> {
    let mut store = load_project_store();
    toggle_path_list(&mut store.archived, &path, archived);
    if archived {
        toggle_path_list(&mut store.pinned, &path, false);
    }
    save_project_store(&store)?;
    Ok(store)
}

#[tauri::command]
fn add_project(path: String, label: Option<String>) -> Result<ProjectRow, String> {
    let p = PathBuf::from(path.trim());
    if !p.is_dir() {
        return Err(format!("not a directory: {}", p.display()));
    }
    let abs = p.canonicalize().unwrap_or(p);
    // strip Windows \\?\ prefix
    let abs_s = abs
        .display()
        .to_string()
        .trim_start_matches(r"\\?\")
        .to_string();
    let label = label
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| {
            abs.file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| abs_s.clone())
        });
    let mut store = load_project_store();
    let key = norm_path(&abs_s);
    store.manual.retain(|m| norm_path(&m.path) != key);
    store.manual.push(ManualProject {
        path: abs_s.clone(),
        label: label.clone(),
        added_at: now_iso(),
    });
    // touch activity so it sorts to top
    store.last_prompt.insert(key, now_iso());
    save_project_store(&store)?;
    Ok(ProjectRow {
        project: label,
        project_path: abs_s,
        session_id: String::new(),
        mtime: now_iso(),
        size_bytes: 0,
        file: String::new(),
        session_count: 0,
        pinned: false,
        archived: false,
        source: "manual".into(),
    })
}

#[tauri::command]
fn touch_project(path: String) -> Result<(), String> {
    let mut store = load_project_store();
    store.last_prompt.insert(norm_path(&path), now_iso());
    save_project_store(&store)
}

#[tauri::command]
fn remove_manual_project(path: String) -> Result<(), String> {
    let mut store = load_project_store();
    let key = norm_path(&path);
    store.manual.retain(|m| norm_path(&m.path) != key);
    save_project_store(&store)
}

// ── Waterfall chat sessions (persistent transcripts under ~/.waterfall/sessions/) ──

#[derive(Serialize, Deserialize, Clone, Debug)]
struct ChatMessage {
    role: String,
    text: String,
    #[serde(default)]
    meta: String,
    #[serde(default)]
    thought: String,
    #[serde(default)]
    error: bool,
    #[serde(default)]
    ts: String,
}

/// Full transcript on disk: `~/.waterfall/sessions/{id}.json`
#[derive(Serialize, Deserialize, Clone, Debug)]
struct ChatSession {
    id: String,
    project_path: String,
    project_label: String,
    title: String,
    agent: String,
    /// idle | running | error
    status: String,
    #[serde(default)]
    created_at: String,
    #[serde(default)]
    updated_at: String,
    #[serde(default)]
    messages: Vec<ChatMessage>,
}

/// Lightweight sidebar row (no message bodies).
#[derive(Serialize, Clone, Debug)]
struct SessionRow {
    id: String,
    project_path: String,
    project_label: String,
    title: String,
    agent: String,
    status: String,
    updated_at: String,
    message_count: u32,
}

fn sessions_dir() -> PathBuf {
    home_dir().join(".waterfall").join("sessions")
}

fn session_file(id: &str) -> PathBuf {
    let safe: String = id
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || *c == '_' || *c == '-')
        .collect();
    sessions_dir().join(format!("{safe}.json"))
}

fn ensure_sessions_dir() -> Result<(), String> {
    fs::create_dir_all(sessions_dir()).map_err(|e| e.to_string())
}

fn new_session_id() -> String {
    let t = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    // Mix in process-ish entropy without an extra crate
    let r = (std::process::id() as u64)
        .wrapping_mul(0x9E37_79B9_7F4A_7C15)
        .wrapping_add(t as u64);
    format!("wf_{t:x}_{r:08x}")
}

fn load_chat_session_file(path: &Path) -> Option<ChatSession> {
    let raw = fs::read_to_string(path).ok()?;
    serde_json::from_str(&raw).ok()
}

fn save_chat_session_disk(session: &ChatSession) -> Result<(), String> {
    ensure_sessions_dir()?;
    let path = session_file(&session.id);
    let raw = serde_json::to_string_pretty(session).map_err(|e| e.to_string())?;
    fs::write(path, raw).map_err(|e| e.to_string())
}

fn session_to_row(s: &ChatSession) -> SessionRow {
    SessionRow {
        id: s.id.clone(),
        project_path: s.project_path.clone(),
        project_label: s.project_label.clone(),
        title: s.title.clone(),
        agent: s.agent.clone(),
        status: s.status.clone(),
        updated_at: s.updated_at.clone(),
        message_count: s.messages.len() as u32,
    }
}

fn title_from_prompt(prompt: &str) -> String {
    let t = prompt.trim().replace('\n', " ");
    if t.is_empty() {
        return "New chat".into();
    }
    let mut out: String = t.chars().take(48).collect();
    if t.chars().count() > 48 {
        out.push('…');
    }
    out
}

fn session_order_index(order: &[String], id: &str) -> usize {
    order
        .iter()
        .position(|x| x == id)
        .unwrap_or(usize::MAX)
}

fn push_session_to_order(project_path: &str, session_id: &str) {
    let mut store = load_project_store();
    let key = norm_path(project_path);
    let list = store.session_order.entry(key).or_default();
    list.retain(|id| id != session_id);
    list.insert(0, session_id.to_string());
    let _ = save_project_store(&store);
}

fn remove_session_from_order(session_id: &str) {
    let mut store = load_project_store();
    let mut changed = false;
    for list in store.session_order.values_mut() {
        let before = list.len();
        list.retain(|id| id != session_id);
        if list.len() != before {
            changed = true;
        }
    }
    if changed {
        let _ = save_project_store(&store);
    }
}

/// List waterfall chat sessions (optional project + status filter).
/// When a project has a saved drag order, that order wins; otherwise newest first.
#[tauri::command]
fn list_chat_sessions(
    project_path: Option<String>,
    status: Option<String>,
    limit: Option<usize>,
) -> Result<Vec<SessionRow>, String> {
    let dir = sessions_dir();
    if !dir.is_dir() {
        return Ok(vec![]);
    }
    let want_proj = project_path
        .as_ref()
        .map(|p| norm_path(p))
        .filter(|p| !p.is_empty());
    let want_status = status
        .as_ref()
        .map(|s| s.trim().to_lowercase())
        .filter(|s| !s.is_empty() && s != "all");
    let cap = limit.unwrap_or(100).max(1).min(500);
    let store = load_project_store();

    let mut rows: Vec<SessionRow> = Vec::new();
    let entries = fs::read_dir(&dir).map_err(|e| e.to_string())?;
    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("json") {
            continue;
        }
        // Skip non-session files (e.g. index/order)
        let stem = path
            .file_stem()
            .map(|s| s.to_string_lossy().to_string())
            .unwrap_or_default();
        if stem.starts_with('_') {
            continue;
        }
        let Some(sess) = load_chat_session_file(&path) else {
            continue;
        };
        if let Some(ref np) = want_proj {
            if norm_path(&sess.project_path) != *np {
                continue;
            }
        }
        if let Some(ref st) = want_status {
            if sess.status.to_lowercase() != *st {
                continue;
            }
        }
        rows.push(session_to_row(&sess));
    }

    // Prefer manual order for the filtered project when present
    if let Some(ref np) = want_proj {
        if let Some(order) = store.session_order.get(np) {
            if !order.is_empty() {
                rows.sort_by(|a, b| {
                    session_order_index(order, &a.id)
                        .cmp(&session_order_index(order, &b.id))
                        .then_with(|| b.updated_at.cmp(&a.updated_at))
                });
                rows.truncate(cap);
                return Ok(rows);
            }
        }
    }
    rows.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    rows.truncate(cap);
    Ok(rows)
}

/// Persist drag-and-drop order for chat sessions under one project.
#[tauri::command]
fn reorder_chat_sessions(project_path: String, ids: Vec<String>) -> Result<(), String> {
    let key = norm_path(&project_path);
    if key.is_empty() {
        return Err("project_path required".into());
    }
    let mut store = load_project_store();
    let mut seen = std::collections::HashSet::new();
    let mut order = Vec::new();
    for id in ids {
        let t = id.trim().to_string();
        if t.is_empty() || !seen.insert(t.clone()) {
            continue;
        }
        order.push(t);
    }
    store.session_order.insert(key, order);
    save_project_store(&store)?;
    Ok(())
}

#[tauri::command]
fn create_chat_session(
    project_path: String,
    project_label: Option<String>,
    agent: Option<String>,
) -> Result<ChatSession, String> {
    let path = project_path.trim().replace('/', "\\");
    if path.is_empty() {
        return Err("project_path required".into());
    }
    let label = project_label
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| {
            PathBuf::from(&path)
                .file_name()
                .map(|s| s.to_string_lossy().to_string())
                .unwrap_or_else(|| path.clone())
        });
    let now = now_iso();
    let session = ChatSession {
        id: new_session_id(),
        project_path: path.clone(),
        project_label: label,
        title: "New chat".into(),
        agent: agent.unwrap_or_else(|| "auto".into()),
        status: "idle".into(),
        created_at: now.clone(),
        updated_at: now,
        messages: vec![],
    };
    save_chat_session_disk(&session)?;
    push_session_to_order(&path, &session.id);
    Ok(session)
}

#[tauri::command]
fn get_chat_session(id: String) -> Result<ChatSession, String> {
    let path = session_file(id.trim());
    if !path.is_file() {
        return Err(format!("session not found: {}", id.trim()));
    }
    load_chat_session_file(&path).ok_or_else(|| format!("corrupt session: {}", id.trim()))
}

/// Append one message; auto-titles from first user message.
#[tauri::command]
fn append_chat_message(
    id: String,
    role: String,
    text: String,
    meta: Option<String>,
    thought: Option<String>,
    error: Option<bool>,
) -> Result<ChatSession, String> {
    let path = session_file(id.trim());
    let mut sess = load_chat_session_file(&path)
        .ok_or_else(|| format!("session not found: {}", id.trim()))?;
    let role = role.trim().to_lowercase();
    if role != "user" && role != "assistant" {
        return Err("role must be user or assistant".into());
    }
    let msg = ChatMessage {
        role: role.clone(),
        text: text.clone(),
        meta: meta.unwrap_or_default(),
        thought: thought.unwrap_or_default(),
        error: error.unwrap_or(false),
        ts: now_iso(),
    };
    if sess.title == "New chat" && role == "user" && !text.trim().is_empty() {
        sess.title = title_from_prompt(&text);
    }
    sess.messages.push(msg);
    sess.updated_at = now_iso();
    save_chat_session_disk(&sess)?;
    // Keep project activity fresh
    let mut store = load_project_store();
    store
        .last_prompt
        .insert(norm_path(&sess.project_path), now_iso());
    let _ = save_project_store(&store);
    Ok(sess)
}

#[tauri::command]
fn set_chat_session_status(id: String, status: String) -> Result<ChatSession, String> {
    let st = status.trim().to_lowercase();
    if !["idle", "running", "error"].contains(&st.as_str()) {
        return Err(format!("status must be idle|running|error, got {st}"));
    }
    let path = session_file(id.trim());
    let mut sess = load_chat_session_file(&path)
        .ok_or_else(|| format!("session not found: {}", id.trim()))?;
    sess.status = st;
    sess.updated_at = now_iso();
    save_chat_session_disk(&sess)?;
    Ok(sess)
}

#[tauri::command]
fn rename_chat_session(id: String, title: String) -> Result<ChatSession, String> {
    let path = session_file(id.trim());
    let mut sess = load_chat_session_file(&path)
        .ok_or_else(|| format!("session not found: {}", id.trim()))?;
    let t = title.trim();
    if t.is_empty() {
        return Err("title required".into());
    }
    sess.title = t.chars().take(80).collect();
    sess.updated_at = now_iso();
    save_chat_session_disk(&sess)?;
    Ok(sess)
}

#[tauri::command]
fn delete_chat_session(id: String) -> Result<(), String> {
    let id = id.trim().to_string();
    let path = session_file(&id);
    if path.is_file() {
        fs::remove_file(&path).map_err(|e| e.to_string())?;
    }
    remove_session_from_order(&id);
    Ok(())
}

#[tauri::command]
fn app_info() -> serde_json::Value {
    serde_json::json!({
        "name": "waterfall",
        "version": env!("CARGO_PKG_VERSION"),
        "shell": "tauri-2",
        "logo": "blue W cascade mark",
        "design": "DESIGN.md",
        "ux_refs": ["Linear", "Figma", "VS Code", "Raycast", "Notion"],
        "profile_path": profile_path().display().to_string(),
        "sessions_path": sessions_dir().display().to_string(),
        "oauth": "local profile now; waterfall.sh OAuth host later",
        "parity": {
            "native_window": true,
            "fullscreen_maximize": true,
            "cascade": true,
            "token_savings": true,
            "modular_projects": true,
            "peer_launch": true,
            "agent_in_project": true,
            "aesthetic_prefs": true,
            "oauth_scaffold": true,
            "embedded_agent_chat": true,
            "chat_sessions": true,
            "session_transcripts": true,
            "tool_loop": "via local grok/claude/codex CLIs",
        }
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(BackendState {
            child: Mutex::new(None),
        })
        .setup(|app| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.maximize();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            list_peers,
            list_agent_clis,
            launch_peer,
            launch_agent_in_project,
            run_agent_local,
            start_agent_local,
            list_claude_sessions,
            list_projects,
            pin_project,
            archive_project,
            reorder_projects,
            set_project_sort,
            get_project_prefs,
            add_project,
            touch_project,
            remove_manual_project,
            list_chat_sessions,
            create_chat_session,
            get_chat_session,
            append_chat_message,
            set_chat_session_status,
            rename_chat_session,
            delete_chat_session,
            reorder_chat_sessions,
            start_backend,
            backend_url,
            app_info,
            process_note,
            get_profile,
            save_profile,
            openrouter_key_status,
            save_openrouter_key,
            clear_openrouter_key,
            list_openrouter_models,
            openrouter_chat,
            begin_oauth,
            sign_out,
            set_fullscreen,
            maximize_window
        ])
        .run(tauri::generate_context!())
        .expect("error while running waterfall");
}
