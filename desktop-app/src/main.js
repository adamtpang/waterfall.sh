/**
 * waterfall desktop: Claude Desktop layout
 * Left: projects + chat sessions (status filter, nested under project).
 * Transcripts persist under ~/.waterfall/sessions.
 * Grok (and other local agents) run in-app via headless CLI — no terminal.
 */
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const PORT = 8765;
let apiBase = `http://127.0.0.1:${PORT}`;
let profile = null;
/** Full list from backend (before client filter) */
let projectsAll = [];
/** Visible list after filter (render + select indices) */
let projects = [];
let selected = null;
/** Active waterfall chat session (persisted) */
let activeSession = null;
/** Session rows for currently selected project (and status filter) */
let projectSessions = [];
/** Global session status filter: all | running | idle | error */
let sessStatusFilter = "all";
let showArchived = false;
let fullscreenOn = false;
let sortMode = "activity";
let scopeFilter = "all";
let filterQuery = "";
let dragPath = null;
/** project_path -> true after first successful in-app turn (use --continue) */
const sessionTouched = new Map();
let chatBusy = false;
let streamUnlisten = null;
/** Live assistant bubble while streaming */
let liveAssistantEl = null;
let liveThoughtEl = null;
let liveBodyEl = null;
let liveLogEl = null;
/** Batched stream paint (keeps UI smooth under token flood) */
let pendingText = "";
let pendingThought = "";
let paintScheduled = false;
let runStartedAt = 0;
let tickTimer = null;
/** Active detached agent run (UI must stay free while Grok works) */
let activeRunId = null;
let activeRunResolve = null;

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");

function fmtMoney(n) {
  if (n == null || Number.isNaN(n)) return "$0";
  const v = Number(n);
  return v >= 1 ? "$" + v.toFixed(2) : "$" + v.toFixed(4);
}

function agentLabel(id) {
  return (
    { auto: "Auto", claude: "Claude Code", codex: "Codex", grok: "Grok", opencode: "OpenCode" }[
      id
    ] || id
  );
}

async function resolveAgent(id) {
  const want = id || profile?.default_agent || "auto";
  if (want !== "auto") return want;
  try {
    const clis = await invoke("list_agent_clis");
    return clis.find((c) => c.available)?.id || "codex";
  } catch {
    return "codex";
  }
}

async function api(path, opts) {
  const res = await fetch(apiBase + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function applyAesthetic(a) {
  if (!a) return;
  document.body.dataset.theme = a.theme || "deep";
  document.documentElement.style.setProperty("--accent", a.accent || "#5ec6ff");
}

function show(mode) {
  $("empty-state").classList.toggle("hidden", mode !== "empty");
  $("workspace").classList.toggle("hidden", mode !== "work");
  $("settings").classList.toggle("hidden", mode !== "settings");
  $("add-panel").classList.toggle("hidden", mode !== "add");
  $("cascade").classList.toggle("hidden", mode !== "cascade");
}

function relativeActivity(mtime) {
  const sec = parseInt(mtime, 10);
  if (!sec) return "";
  const ago = Math.max(0, Math.floor(Date.now() / 1000) - sec);
  if (ago < 60) return "just now";
  if (ago < 3600) return Math.floor(ago / 60) + "m";
  if (ago < 86400) return Math.floor(ago / 3600) + "h";
  if (ago < 86400 * 14) return Math.floor(ago / 86400) + "d";
  return Math.floor(ago / (86400 * 7)) + "w";
}

function applyClientFilterSort() {
  const q = filterQuery.trim().toLowerCase();
  let list = projectsAll.slice();

  if (scopeFilter === "pinned") list = list.filter((p) => p.pinned);
  else if (scopeFilter === "discovered") list = list.filter((p) => p.source === "discovered");
  else if (scopeFilter === "manual") list = list.filter((p) => p.source === "manual");

  if (q) {
    list = list.filter(
      (p) =>
        (p.project || "").toLowerCase().includes(q) ||
        (p.project_path || "").toLowerCase().includes(q)
    );
  }

  // Client-side sort mirrors backend so filter changes feel instant
  if (sortMode === "name") {
    list.sort((a, b) =>
      (a.project || "").localeCompare(b.project || "", undefined, { sensitivity: "base" })
    );
  } else if (sortMode === "sessions") {
    list.sort(
      (a, b) =>
        (b.session_count || 0) - (a.session_count || 0) ||
        String(b.mtime).localeCompare(String(a.mtime))
    );
  } else if (sortMode === "path") {
    list.sort((a, b) =>
      (a.project_path || "").localeCompare(b.project_path || "", undefined, {
        sensitivity: "base",
      })
    );
  } else if (sortMode === "manual") {
    // Keep backend/manual order already in projectsAll; only filter
  } else {
    // activity: pinned first, then mtime desc
    list.sort((a, b) => {
      if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
      return String(b.mtime).localeCompare(String(a.mtime));
    });
  }

  projects = list;
  const hint = $("proj-hint");
  if (hint) {
    const n = projects.length;
    const total = projectsAll.length;
    hint.textContent =
      n === total
        ? `Drag chats or projects · ${n} · ${sortMode}`
        : `${n} of ${total} · ${sortMode}`;
  }
}

function statusDotClass(status) {
  const s = (status || "idle").toLowerCase();
  if (s === "running") return "running";
  if (s === "error") return "error";
  return "idle";
}

function renderSessionRowsHtml(projPath) {
  if (!selected || selected.project_path !== projPath) return "";
  if (!projectSessions.length) {
    return '<div class="sess-empty">No chats yet. New chat.</div>';
  }
  return projectSessions
    .map((s) => {
      const active = activeSession && activeSession.id === s.id ? "active" : "";
      const when = relativeActivity(s.updated_at);
      const n = s.message_count || 0;
      const sub = [s.status || "idle", when, n ? n + " msg" : ""]
        .filter(Boolean)
        .join(" · ");
      return `<div class="sess-row ${active}" data-sid="${esc(s.id)}" draggable="true">
        <span class="drag-handle sess-handle" title="Drag to reorder" aria-hidden="true">⋮⋮</span>
        <span class="sess-dot ${statusDotClass(s.status)}" title="${esc(s.status || "idle")}"></span>
        <button type="button" class="sess" data-sid="${esc(s.id)}">
          <span class="name">${esc(s.title || "New chat")}</span>
          <span class="sub">${esc(sub)}</span>
        </button>
        <button type="button" class="sess-del" data-del="${esc(s.id)}" title="Delete chat">×</button>
      </div>`;
    })
    .join("");
}

let dragSessId = null;

async function reorderSessionsByDrag(fromId, toId) {
  if (!selected?.project_path || !fromId || !toId || fromId === toId) return;
  const list = projectSessions.slice();
  const fi = list.findIndex((s) => s.id === fromId);
  const ti = list.findIndex((s) => s.id === toId);
  if (fi < 0 || ti < 0) return;
  const [item] = list.splice(fi, 1);
  list.splice(ti, 0, item);
  projectSessions = list;
  renderSidebar();
  try {
    await invoke("reorder_chat_sessions", {
      projectPath: selected.project_path,
      ids: list.map((s) => s.id),
    });
  } catch (err) {
    console.warn(err);
    await loadProjectSessions();
    renderSidebar();
  }
}

function bindSessionDrag(host) {
  host.querySelectorAll(".sess-row").forEach((row) => {
    row.addEventListener("dragstart", (e) => {
      dragSessId = row.dataset.sid || null;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", dragSessId || "");
      // Stop project-row drag from fighting session drag
      e.stopPropagation();
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      host.querySelectorAll(".sess-row").forEach((r) => r.classList.remove("drag-over"));
      dragSessId = null;
    });
    row.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "move";
      row.classList.add("drag-over");
    });
    row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
    row.addEventListener("drop", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      row.classList.remove("drag-over");
      const from =
        dragSessId || e.dataTransfer.getData("text/plain") || null;
      const to = row.dataset.sid;
      if (!from || !to) return;
      await reorderSessionsByDrag(from, to);
    });
  });
}

function renderSidebar() {
  const host = $("project-list");
  $("btn-toggle-archived").classList.toggle("on", showArchived);
  $("btn-toggle-archived").textContent = showArchived ? "Active" : "Archived";
  applyClientFilterSort();

  if (!projects.length) {
    host.innerHTML = showArchived
      ? '<div class="side-empty">No archived projects</div>'
      : filterQuery || scopeFilter !== "all"
        ? '<div class="side-empty">No matches</div>'
        : '<div class="side-empty">No projects. Add one.</div>';
    return;
  }

  host.innerHTML = projects
    .map((p, i) => {
      const active =
        selected && selected.project_path === p.project_path ? "active" : "";
      const arch = p.archived ? "· archived" : "";
      const when = relativeActivity(p.mtime);
      const pinTitle = p.pinned ? "Unpin" : "Pin";
      const pinCls = p.pinned ? "pin on" : "pin";
      const wfCount = selected && selected.project_path === p.project_path
        ? projectSessions.length
        : null;
      const sessions =
        wfCount != null
          ? `${wfCount} chat${wfCount === 1 ? "" : "s"}`
          : p.session_count > 0
            ? `${p.session_count}s`
            : p.source === "manual"
              ? "added"
              : "";
      const sub = [when, sessions, arch].filter(Boolean).join(" ");
      return `<div class="proj-row ${active}" data-i="${i}" draggable="true">
        <span class="drag-handle" title="Drag to reorder" aria-hidden="true">⋮⋮</span>
        <button type="button" class="proj" data-i="${i}">
          <span class="name">${esc(p.project)}${p.pinned ? " ★" : ""}</span>
          <span class="sub">${esc(sub)}</span>
        </button>
        <button type="button" class="${pinCls}" data-pin="${i}" title="${pinTitle}" aria-label="${pinTitle}">${p.pinned ? "★" : "☆"}</button>
      </div>${renderSessionRowsHtml(p.project_path)}`;
    })
    .join("");

  host.querySelectorAll(".proj").forEach((btn) => {
    btn.addEventListener("click", () => selectProject(projects[+btn.dataset.i]));
  });
  host.querySelectorAll(".sess").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      selectSessionById(btn.dataset.sid);
    });
  });
  bindSessionDrag(host);
  host.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = btn.dataset.del;
      if (!id || !confirm("Delete this chat transcript?")) return;
      try {
        await invoke("delete_chat_session", { id });
        if (activeSession?.id === id) {
          activeSession = null;
          clearChat();
          updateSessionHeader();
        }
        await loadProjectSessions();
        renderSidebar();
      } catch (err) {
        alert("Delete failed: " + err);
      }
    });
  });
  host.querySelectorAll("[data-pin]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const p = projects[+btn.dataset.pin];
      if (!p) return;
      try {
        await invoke("pin_project", {
          path: p.project_path,
          pinned: !p.pinned,
        });
        const keepPath = selected?.project_path;
        const keepSess = activeSession?.id;
        await loadProjects({ keepSelection: true });
        if (keepPath) {
          const again = projects.find((x) => x.project_path === keepPath);
          if (again) {
            again._chatKeep = true;
            await selectProject(again, { keepSessionId: keepSess });
          }
        }
      } catch (err) {
        alert("Pin failed: " + err);
      }
    });
  });

  // Drag reorder (index-based; paths with special chars are fine)
  host.querySelectorAll(".proj-row").forEach((row) => {
    row.addEventListener("dragstart", (e) => {
      const p = projects[+row.dataset.i];
      dragPath = p?.project_path || null;
      row.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", String(row.dataset.i));
    });
    row.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      host.querySelectorAll(".proj-row").forEach((r) => r.classList.remove("drag-over"));
      dragPath = null;
    });
    row.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      row.classList.add("drag-over");
    });
    row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
    row.addEventListener("drop", async (e) => {
      e.preventDefault();
      row.classList.remove("drag-over");
      const from = dragPath || projects[+e.dataTransfer.getData("text/plain")]?.project_path;
      const to = projects[+row.dataset.i]?.project_path;
      if (!from || !to || from === to) return;
      await reorderByDrag(from, to);
    });
  });
}

async function reorderByDrag(fromPath, toPath) {
  // Work on full unfiltered list when possible so order is stable
  const base =
    sortMode === "manual" || !filterQuery
      ? projectsAll.slice()
      : projects.slice();
  const fi = base.findIndex((p) => p.project_path === fromPath);
  const ti = base.findIndex((p) => p.project_path === toPath);
  if (fi < 0 || ti < 0) return;
  const [item] = base.splice(fi, 1);
  base.splice(ti, 0, item);
  const paths = base.map((p) => p.project_path);
  // If we only reordered the filtered view, merge into full list order
  let savePaths = paths;
  if (base !== projectsAll && projectsAll.length) {
    const rest = projectsAll
      .map((p) => p.project_path)
      .filter((p) => !paths.includes(p));
    savePaths = paths.concat(rest);
  }
  try {
    await invoke("reorder_projects", { paths: savePaths });
    sortMode = "manual";
    if ($("proj-sort")) $("proj-sort").value = "manual";
    await loadProjects({ keepSelection: true });
  } catch (err) {
    alert("Reorder failed: " + err);
  }
}

function clearChat() {
  const log = $("chat-log");
  if (!log) return;
  log.innerHTML =
    '<div class="chat-empty" id="chat-empty"><p class="chat-empty-title">Start a message</p><p class="chat-empty-sub">Grok runs locally. Transcripts stay on this machine.</p></div>';
  liveAssistantEl = null;
  liveThoughtEl = null;
  liveBodyEl = null;
  liveLogEl = null;
}

function hideChatEmpty() {
  const empty = $("chat-empty");
  if (empty) empty.remove();
}

function appendMsg(role, text, opts = {}) {
  hideChatEmpty();
  const log = $("chat-log");
  const el = document.createElement("div");
  el.className = "msg " + role + (opts.pending ? " pending" : "") + (opts.error ? " error" : "");
  const meta = document.createElement("span");
  meta.className = "msg-meta";
  meta.textContent = opts.meta || (role === "user" ? "You" : "Agent");
  el.appendChild(meta);
  if (opts.thought) {
    const th = document.createElement("span");
    th.className = "msg-thought";
    th.textContent = opts.thought;
    el.appendChild(th);
  }
  const body = document.createElement("div");
  body.className = "msg-body";
  body.textContent = text || "";
  el.appendChild(body);
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
  return { el, body, meta };
}

function updateSessionHeader() {
  const el = $("ws-session");
  if (!el) return;
  if (!activeSession) {
    el.textContent = "";
    return;
  }
  const st = activeSession.status || "idle";
  el.textContent =
    (activeSession.title || "New chat") +
    " · " +
    st +
    (activeSession.agent ? " · " + agentLabel(activeSession.agent) : "");
}

async function loadProjectSessions() {
  if (!selected?.project_path) {
    projectSessions = [];
    return;
  }
  try {
    projectSessions = await invoke("list_chat_sessions", {
      projectPath: selected.project_path,
      status: sessStatusFilter === "all" ? null : sessStatusFilter,
      limit: 80,
    });
  } catch (e) {
    console.warn("list_chat_sessions", e);
    projectSessions = [];
  }
}

function renderTranscript(messages) {
  clearChat();
  if (!messages || !messages.length) return;
  for (const m of messages) {
    appendMsg(m.role === "user" ? "user" : "assistant", m.text || "", {
      meta: m.meta || (m.role === "user" ? "You" : "Agent"),
      thought: m.thought || "",
      error: !!m.error,
    });
  }
}

async function selectSessionById(id) {
  if (!id) return;
  try {
    const sess = await invoke("get_chat_session", { id });
    activeSession = sess;
    renderTranscript(sess.messages || []);
    updateSessionHeader();
    renderSidebar();
  } catch (e) {
    console.warn(e);
    appendMsg("assistant", "Could not load chat: " + e, {
      error: true,
      meta: "waterfall",
    });
  }
}

async function ensureActiveSession() {
  if (activeSession?.id && selected?.project_path) {
    if (
      normPathJs(activeSession.project_path) ===
      normPathJs(selected.project_path)
    ) {
      return activeSession;
    }
  }
  return createNewSession();
}

function normPathJs(p) {
  return String(p || "")
    .trim()
    .replace(/\//g, "\\")
    .replace(/\\+$/, "")
    .toLowerCase();
}

async function createNewSession() {
  if (!selected?.project_path) {
    throw new Error("Pick a project first");
  }
  const agent = $("agent-select")?.value || profile?.default_agent || "auto";
  const sess = await invoke("create_chat_session", {
    projectPath: selected.project_path,
    projectLabel: selected.project,
    agent,
  });
  activeSession = sess;
  clearChat();
  updateSessionHeader();
  await loadProjectSessions();
  renderSidebar();
  return sess;
}

async function persistMessage(role, text, opts = {}) {
  if (!activeSession?.id) return;
  try {
    const sess = await invoke("append_chat_message", {
      id: activeSession.id,
      role,
      text: text || "",
      meta: opts.meta || null,
      thought: opts.thought || null,
      error: !!opts.error,
    });
    activeSession = sess;
    updateSessionHeader();
    // Refresh sidebar titles without blocking UI
    loadProjectSessions().then(() => renderSidebar());
  } catch (e) {
    console.warn("persist message", e);
  }
}

async function setSessionStatus(status) {
  if (!activeSession?.id) return;
  try {
    activeSession = await invoke("set_chat_session_status", {
      id: activeSession.id,
      status,
    });
    updateSessionHeader();
    loadProjectSessions().then(() => renderSidebar());
  } catch (e) {
    console.warn("set status", e);
  }
}

async function selectProject(p, opts = {}) {
  const same =
    selected && selected.project_path === p.project_path;
  selected = p;
  show("work");
  $("ws-title").textContent = (p.pinned ? "📌 " : "") + p.project;
  $("ws-path").textContent = p.project_path;
  $("btn-pin").textContent = p.pinned ? "Unpin" : "Pin";
  $("btn-archive").textContent = p.archived ? "Unarchive" : "Archive";
  $("out").classList.add("hidden");
  $("out").textContent = "";

  if (!same && !p._chatKeep && !opts.keepSessionId) {
    activeSession = null;
    clearChat();
  }

  await loadProjectSessions();
  const n = projectSessions.length;
  const parts = [];
  if (n) parts.push(n + (n === 1 ? " chat" : " chats"));
  if (p.session_count) parts.push(p.session_count + " Claude");
  if (p.source === "manual") parts.push("added");
  if (p.archived) parts.push("archived");
  $("ws-meta").textContent = parts.join(" · ");

  const keepId = opts.keepSessionId || (same || p._chatKeep ? activeSession?.id : null);
  if (keepId && projectSessions.some((s) => s.id === keepId)) {
    await selectSessionById(keepId);
  } else if (projectSessions.length) {
    await selectSessionById(projectSessions[0].id);
  } else {
    activeSession = null;
    clearChat();
    updateSessionHeader();
    renderSidebar();
  }
  p._chatKeep = false;
}

async function loadProjects(opts = {}) {
  const keepSelection = !!opts.keepSelection;
  const keepSess = activeSession?.id;
  try {
    projectsAll = await invoke("list_projects", {
      limit: 200,
      includeArchived: showArchived || false,
    });
  } catch (e) {
    projectsAll = [];
    projects = [];
    $("project-list").innerHTML =
      '<div class="side-empty">Could not load projects</div>';
    console.warn(e);
    return;
  }
  if (showArchived) {
    projectsAll = projectsAll.filter((p) => p.archived);
  }
  applyClientFilterSort();
  if (selected) {
    const still =
      projects.find((p) => p.project_path === selected.project_path) ||
      projectsAll.find((p) => p.project_path === selected.project_path);
    if (still) {
      if (keepSelection) {
        selected = still;
        await loadProjectSessions();
        renderSidebar();
        updateSessionHeader();
      } else {
        await selectProject(still, { keepSessionId: keepSess });
      }
    } else if (!keepSelection) {
      selected = null;
      activeSession = null;
      projectSessions = [];
      show("empty");
      renderSidebar();
    } else {
      renderSidebar();
    }
  } else if (!keepSelection) {
    show("empty");
    renderSidebar();
  } else {
    renderSidebar();
  }
}

async function fillAgents() {
  const mods = ["auto", ...(profile?.agent_modules || ["claude", "codex", "grok", "opencode"])];
  const preferred = profile?.default_agent || "auto";
  const fill = (sel) => {
    if (!sel) return;
    sel.innerHTML = mods
      .map(
        (id) =>
          `<option value="${esc(id)}" ${id === preferred ? "selected" : ""}>${esc(agentLabel(id))}</option>`
      )
      .join("");
  };
  fill($("agent-select"));
  fill($("default-agent"));
}

async function loadSavings() {
  try {
    const stats = await api("/api/stats?since_days=90");
    $("sm-saved").textContent = fmtMoney(stats.estimated_cost_saved);
  } catch {
    $("sm-saved").textContent = "$0";
  }
}

async function loadPeers() {
  try {
    const peers = await invoke("list_peers");
    $("peers-row").innerHTML = peers
      .filter((p) => p.available)
      .map(
        (p) =>
          `<button type="button" class="btn" data-peer="${esc(p.id)}">${esc(p.label)}</button>`
      )
      .join("");
    $("peers-row").querySelectorAll("[data-peer]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await invoke("launch_peer", { id: btn.dataset.peer });
        } catch (e) {
          alert(String(e));
        }
      });
    });
  } catch (e) {
    console.warn(e);
  }
}

async function persistAgentChoice(id) {
  if (!profile || !id) return;
  if (profile.default_agent === id) return;
  profile.default_agent = id;
  try {
    profile = await invoke("save_profile", { profile });
  } catch (e) {
    console.warn("save agent choice failed", e);
    return;
  }
  const def = $("default-agent");
  if (def && def.value !== id) def.value = id;
}

/** External interactive TUI (opens a console). Prefer sendInApp for chat. */
async function openAgentTui() {
  if (!selected?.project_path) {
    appendMsg("assistant", "Pick a project first.", { error: true, meta: "waterfall" });
    return;
  }
  const prompt = $("prompt").value.trim();
  const agentId = $("agent-select").value;
  await persistAgentChoice(agentId);
  const agent = await resolveAgent(agentId);
  try {
    const msg = await invoke("launch_agent_in_project", {
      agent,
      cwd: selected.project_path,
      prompt: prompt || null,
    });
    appendMsg("assistant", msg, { meta: agentLabel(agent) + " TUI" });
  } catch (e) {
    appendMsg("assistant", String(e), { error: true, meta: "error" });
  }
}

function ensureLiveAssistant(agentName) {
  if (liveAssistantEl) return;
  hideChatEmpty();
  const log = $("chat-log");
  const el = document.createElement("div");
  el.className = "msg assistant pending";
  const meta = document.createElement("span");
  meta.className = "msg-meta";
  meta.textContent = agentName || "Agent";
  const status = document.createElement("span");
  status.className = "msg-status";
  status.textContent = "starting…";
  // Collapsible activity (hidden until there is something useful)
  const logBox = document.createElement("details");
  logBox.className = "msg-log";
  const logSum = document.createElement("summary");
  logSum.textContent = "Activity";
  logSum.className = "msg-log-sum";
  const logBody = document.createElement("div");
  logBody.className = "msg-log-body";
  logBox.appendChild(logSum);
  logBox.appendChild(logBody);
  const thought = document.createElement("span");
  thought.className = "msg-thought";
  thought.style.display = "none";
  const body = document.createElement("div");
  body.className = "msg-body";
  body.textContent = "";
  el.appendChild(meta);
  el.appendChild(status);
  el.appendChild(logBox);
  el.appendChild(thought);
  el.appendChild(body);
  log.appendChild(el);
  liveAssistantEl = el;
  liveThoughtEl = thought;
  liveBodyEl = body;
  liveLogEl = logBody;
  liveAssistantEl._status = status;
  liveAssistantEl._meta = meta;
  liveAssistantEl._logBox = logBox;
  log.scrollTop = log.scrollHeight;
}

function schedulePaint() {
  if (paintScheduled) return;
  paintScheduled = true;
  requestAnimationFrame(() => {
    paintScheduled = false;
    if (pendingThought && liveThoughtEl) {
      liveThoughtEl.style.display = "block";
      let t = (liveThoughtEl.textContent || "") + pendingThought;
      if (t.length > 2400) t = "…" + t.slice(-2400);
      liveThoughtEl.textContent = t;
      pendingThought = "";
    }
    if (pendingText && liveBodyEl) {
      liveBodyEl.textContent += pendingText;
      pendingText = "";
    }
    const log = $("chat-log");
    if (log) log.scrollTop = log.scrollHeight;
  });
}

function setLiveStatus(text) {
  if (!liveAssistantEl?._status) return;
  liveAssistantEl._status.style.display = "block";
  const elapsed = runStartedAt
    ? Math.floor((Date.now() - runStartedAt) / 1000) + "s · "
    : "";
  liveAssistantEl._status.textContent = elapsed + text;
}

function appendLiveLog(line) {
  if (!liveLogEl || !line) return;
  const row = document.createElement("div");
  row.className = "msg-log-line";
  row.textContent = line;
  liveLogEl.appendChild(row);
  // Keep last ~30 log lines for perf; do not auto-scroll whole chat on every log
  while (liveLogEl.childNodes.length > 30) {
    liveLogEl.removeChild(liveLogEl.firstChild);
  }
  if (liveAssistantEl?._logBox) {
    const n = liveLogEl.childNodes.length;
    const sum = liveAssistantEl._logBox.querySelector("summary");
    if (sum) sum.textContent = n ? `Activity (${n})` : "Activity";
  }
}

function onAgentStream(ev) {
  const p = ev.payload || {};
  // Ignore events from a previous run if a new one is active
  if (activeRunId && p.run_id && p.run_id !== activeRunId) return;

  const kind = p.kind || "";
  let text = p.text || "";
  const agent = p.agent || "agent";
  const label = agentLabel(agent);
  ensureLiveAssistant(label);
  if (liveAssistantEl?._meta) {
    const ms = p.ms != null ? ` · ${Math.round(p.ms / 1000)}s` : "";
    liveAssistantEl._meta.textContent = label + (kind === "done" ? "" : ms);
  }

  if (kind === "start" || kind === "status" || kind === "tick") {
    // tick = status only (do not spam activity log — that freezes WebView)
    setLiveStatus(text || "running…");
    if (kind === "status" && text) appendLiveLog(text);
  } else if (kind === "tool") {
    setLiveStatus(text);
    appendLiveLog(text);
  } else if (kind === "log") {
    appendLiveLog(text);
  } else if (kind === "usage") {
    appendLiveLog(text);
    setLiveStatus(text);
  } else if (kind === "thought") {
    pendingThought += text;
    schedulePaint();
  } else if (kind === "text") {
    pendingText += text;
    schedulePaint();
  } else if (kind === "error") {
    schedulePaint(); // flush buffers first
    if (liveBodyEl) {
      const cur = liveBodyEl.textContent || "";
      liveBodyEl.textContent = cur + (cur ? "\n" : "") + text;
    }
    if (liveAssistantEl) liveAssistantEl.classList.add("error");
    appendLiveLog("error: " + text);
  } else if (kind === "done") {
    // done payload may be "status\n\x1efulltext" for recovery if stream was missed
    let fullRecover = "";
    const sep = text.indexOf("\n\x1e");
    if (sep >= 0) {
      fullRecover = text.slice(sep + 2);
      text = text.slice(0, sep);
    }
    // flush pending paint
    if (pendingThought && liveThoughtEl) {
      liveThoughtEl.style.display = "block";
      liveThoughtEl.textContent =
        (liveThoughtEl.textContent || "") + pendingThought;
      pendingThought = "";
    }
    if (pendingText && liveBodyEl) {
      liveBodyEl.textContent += pendingText;
      pendingText = "";
    }
    if (
      liveBodyEl &&
      !(liveBodyEl.textContent || "").trim() &&
      fullRecover
    ) {
      liveBodyEl.textContent = fullRecover;
    }
    if (liveAssistantEl) liveAssistantEl.classList.remove("pending");
    setLiveStatus(text || "done");
    appendLiveLog(text || "done");
    if (activeRunResolve) {
      const resolve = activeRunResolve;
      activeRunResolve = null;
      resolve({
        ok: p.ok !== false,
        agent,
        text: (liveBodyEl?.textContent || fullRecover || "").trim(),
        exit_code: p.exit_code != null ? p.exit_code : p.ok === false ? 1 : 0,
        elapsed_ms: p.ms,
        run_id: p.run_id || activeRunId,
      });
    }
  }
}

async function ensureStreamListen() {
  if (streamUnlisten) return;
  try {
    streamUnlisten = await listen("agent-stream", onAgentStream);
  } catch (e) {
    console.warn("listen agent-stream", e);
  }
}

/** In-app local agent (Grok default): no terminal window. */
async function sendInApp() {
  if (chatBusy) return;
  if (!selected?.project_path) {
    appendMsg("assistant", "Pick a project first.", { error: true, meta: "waterfall" });
    return;
  }
  const prompt = $("prompt").value.trim();
  if (!prompt) {
    appendMsg("assistant", "Enter a message first.", { error: true, meta: "waterfall" });
    return;
  }

  // Ensure a persisted session before we write anything
  try {
    await ensureActiveSession();
  } catch (e) {
    appendMsg("assistant", "Could not create chat session: " + e, {
      error: true,
      meta: "waterfall",
    });
    return;
  }

  // Paint user message immediately (before any async work)
  const agentId = $("agent-select").value;
  appendMsg("user", prompt, { meta: "You" });
  $("prompt").value = "";
  // Persist user turn (fire-and-forget after paint)
  persistMessage("user", prompt, { meta: "You" });
  liveAssistantEl = null;
  liveThoughtEl = null;
  liveBodyEl = null;
  liveLogEl = null;
  pendingText = "";
  pendingThought = "";
  runStartedAt = Date.now();
  chatBusy = true;
  $("btn-send").disabled = true;
  setSessionStatus("running");
  // Keep prompt enabled so UI feels alive; just block double-send via chatBusy
  ensureLiveAssistant(agentLabel(agentId === "auto" ? "grok" : agentId));
  setLiveStatus("queued…");
  appendLiveLog("send · " + agentId);

  // Yield a frame so the user bubble paints before heavy work
  await new Promise((r) => requestAnimationFrame(() => r()));

  await ensureStreamListen();
  // Fire-and-forget profile save — never block the send path
  persistAgentChoice(agentId);

  let agent = agentId;
  if (agent === "auto") {
    setLiveStatus("resolving agent…");
    agent = await resolveAgent("auto");
  }

  const localOk = ["grok", "claude", "codex"].includes(agent);
  if (!localOk) {
    const msg =
      agentLabel(agent) + " is not wired for in-app yet. Use Open TUI, or switch to Grok.";
    appendMsg("assistant", msg, { meta: "waterfall", error: true });
    await persistMessage("assistant", msg, { meta: "waterfall", error: true });
    await setSessionStatus("error");
    chatBusy = false;
    $("btn-send").disabled = false;
    return;
  }

  if (liveAssistantEl?._meta) {
    liveAssistantEl._meta.textContent = agentLabel(agent);
  }
  setLiveStatus("starting " + agent + "…");

  // Resume CLI only within the same waterfall session after first success
  const resumeKey = (activeSession?.id || selected.project_path) + ":" + agent;
  const resume = !!sessionTouched.get(resumeKey);
  const cwd = selected.project_path;

  // Client-side elapsed ticker (independent of stream events)
  if (tickTimer) clearInterval(tickTimer);
  tickTimer = setInterval(() => {
    if (!chatBusy || !liveAssistantEl?._status) return;
    const s = Math.floor((Date.now() - runStartedAt) / 1000);
    const cur = liveAssistantEl._status.textContent || "";
    // Only rewrite the timer prefix if status exists
    const rest = cur.replace(/^\d+s · /, "");
    liveAssistantEl._status.textContent = s + "s · " + rest;
  }, 500);

  let finalText = "";
  let failed = false;
  try {
    // Detached start: invoke returns in milliseconds. Window stays interactive.
    // Completion arrives via agent-stream "done" (see onAgentStart + wait below).
    setLiveStatus("starting " + agent + " (window stays live)…");
    const started = await invoke("start_agent_local", {
      agent,
      cwd,
      prompt,
      resume,
    });
    activeRunId = started?.run_id || null;
    appendLiveLog("run " + (activeRunId || "?").slice(0, 18) + " · detached");

    const result = await new Promise((resolve, reject) => {
      // Safety timeout (30 min) so we never leak chatBusy forever
      const timer = setTimeout(() => {
        if (activeRunResolve) {
          activeRunResolve = null;
          reject(new Error("agent run timed out after 30 minutes"));
        }
      }, 30 * 60 * 1000);
      activeRunResolve = (r) => {
        clearTimeout(timer);
        resolve(r);
      };
    });

    if (result?.ok) sessionTouched.set(resumeKey, true);
    // Flush any leftover batches
    if (pendingText && liveBodyEl) {
      liveBodyEl.textContent += pendingText;
      pendingText = "";
    }
    if (liveBodyEl && !(liveBodyEl.textContent || "").trim() && result?.text) {
      liveBodyEl.textContent = result.text;
    }
    finalText = (liveBodyEl?.textContent || result?.text || "").trim();
    if (liveAssistantEl) liveAssistantEl.classList.remove("pending");
    if (result?.elapsed_ms != null) {
      appendLiveLog(`finished · ${result.elapsed_ms}ms · exit ${result.exit_code}`);
    }
    if (!result?.ok) failed = true;
    // Lightweight touch only — skip full list_projects (expensive, froze UI)
    invoke("touch_project", { path: cwd }).catch(() => {});
  } catch (e) {
    failed = true;
    const msg = String(e?.message || e);
    if (liveBodyEl && !(liveBodyEl.textContent || "").trim()) {
      liveBodyEl.textContent = msg;
      finalText = msg;
    } else {
      appendMsg("assistant", msg, { error: true, meta: "error" });
      finalText = msg;
    }
    if (liveAssistantEl) {
      liveAssistantEl.classList.add("error");
      liveAssistantEl.classList.remove("pending");
    }
    appendLiveLog("failed: " + msg);
  } finally {
    activeRunId = null;
    activeRunResolve = null;
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
    // Persist assistant reply (or error body) to disk
    if (finalText) {
      await persistMessage("assistant", finalText, {
        meta: agentLabel(agent),
        error: failed,
      });
    }
    await setSessionStatus(failed ? "error" : "idle");
    chatBusy = false;
    $("btn-send").disabled = false;
    $("prompt").focus();
    liveAssistantEl = null;
    liveThoughtEl = null;
    liveBodyEl = null;
    liveLogEl = null;
  }
}

async function cascade(mode) {
  const prompt = $("prompt").value.trim();
  if (!prompt) {
    $("out").classList.remove("hidden");
    $("out").textContent = "Enter a message first.";
    return;
  }
  $("out").classList.remove("hidden");
  $("out").textContent = "…";
  try {
    let data;
    if (mode === "classify") {
      data = await api("/api/classify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
    } else {
      data = await api("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, dry_run: mode === "dry" }),
      });
    }
    $("out").textContent = JSON.stringify(data, null, 2);
    if (selected?.project_path) {
      await invoke("touch_project", { path: selected.project_path });
      await loadProjects();
    }
    if (mode === "live") loadSavings();
  } catch (e) {
    $("out").textContent = "Error: " + (e.message || e);
  }
}

function openSettings() {
  if (!profile) return;
  const a = profile.aesthetic || {};
  $("theme-pick").value = a.theme || "deep";
  $("accent-pick").value = a.accent || "#5ec6ff";
  $("default-agent").value = profile.default_agent || "auto";
  const o = profile.oauth || {};
  $("account-line").textContent =
    o.status === "connected"
      ? "Connected as " + (o.email || o.display_name || "user")
      : "Local profile on this device";
  $("email").value = o.email || "";
  show("settings");
  refreshKeyStatus();
}

// ── Events ──
$("btn-add").addEventListener("click", () => {
  $("add-path").value = "";
  $("add-label").value = "";
  $("add-err").textContent = "";
  show("add");
});
$("btn-add-cancel").addEventListener("click", () => show(selected ? "work" : "empty"));
$("btn-add-confirm").addEventListener("click", async () => {
  const path = $("add-path").value.trim();
  const label = $("add-label").value.trim() || null;
  $("add-err").textContent = "";
  try {
    const row = await invoke("add_project", { path, label });
    showArchived = false;
    await loadProjects();
    await selectProject(row);
  } catch (e) {
    $("add-err").textContent = String(e);
  }
});

async function onNewChat() {
  if (!selected?.project_path) {
    alert("Pick a project first.");
    return;
  }
  if (chatBusy) {
    alert("Wait for the current run to finish.");
    return;
  }
  try {
    await createNewSession();
    $("prompt")?.focus();
  } catch (e) {
    alert("New chat failed: " + e);
  }
}
$("btn-new-chat")?.addEventListener("click", () => onNewChat());
$("btn-new-chat-ws")?.addEventListener("click", () => onNewChat());

$("btn-toggle-archived").addEventListener("click", async () => {
  showArchived = !showArchived;
  selected = null;
  activeSession = null;
  projectSessions = [];
  await loadProjects();
});

// Filter / sort (instant client filter; sort mode persisted)
let filterTimer = null;
$("proj-filter").addEventListener("input", () => {
  filterQuery = $("proj-filter").value || "";
  clearTimeout(filterTimer);
  filterTimer = setTimeout(() => renderSidebar(), 60);
});
$("proj-sort").addEventListener("change", async () => {
  sortMode = $("proj-sort").value || "activity";
  try {
    await invoke("set_project_sort", { mode: sortMode });
  } catch (e) {
    console.warn(e);
  }
  await loadProjects({ keepSelection: true });
});
$("proj-scope").addEventListener("change", () => {
  scopeFilter = $("proj-scope").value || "all";
  renderSidebar();
});
$("sess-status")?.addEventListener("change", async () => {
  sessStatusFilter = $("sess-status").value || "all";
  if (selected) {
    await loadProjectSessions();
    renderSidebar();
  }
});

$("btn-pin").addEventListener("click", async () => {
  if (!selected) return;
  try {
    await invoke("pin_project", {
      path: selected.project_path,
      pinned: !selected.pinned,
    });
    const keepPath = selected.project_path;
    const keepSess = activeSession?.id;
    await loadProjects();
    const again = projects.find((x) => x.project_path === keepPath);
    if (again) await selectProject(again, { keepSessionId: keepSess });
  } catch (err) {
    alert("Pin failed: " + err);
  }
});

$("btn-archive").addEventListener("click", async () => {
  if (!selected) return;
  const next = !selected.archived;
  await invoke("archive_project", {
    path: selected.project_path,
    archived: next,
  });
  selected = null;
  activeSession = null;
  projectSessions = [];
  if (next) showArchived = false;
  await loadProjects();
  show("empty");
});

$("btn-settings").addEventListener("click", openSettings);
$("btn-back").addEventListener("click", async () => {
  if (selected) await selectProject(selected, { keepSessionId: activeSession?.id });
  else show("empty");
});
$("btn-send").addEventListener("click", () => sendInApp());
$("btn-open").addEventListener("click", () => openAgentTui());
$("btn-classify").addEventListener("click", () => cascade("classify"));
$("btn-dry").addEventListener("click", () => cascade("dry"));
$("btn-route").addEventListener("click", () => cascade("live"));

// Enter sends in-app; Shift+Enter inserts a newline
$("prompt").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  if (e.shiftKey) return;
  if (e.isComposing) return;
  e.preventDefault();
  sendInApp();
});

// Persist model choice as soon as the user changes it
$("agent-select").addEventListener("change", () => {
  persistAgentChoice($("agent-select").value);
});

$("btn-save").addEventListener("click", async () => {
  if (!profile) return;
  profile.aesthetic = {
    ...(profile.aesthetic || {}),
    theme: $("theme-pick").value,
    accent: $("accent-pick").value,
    density: "comfortable",
    scale: 1,
    rail: "left",
    savings_hero: true,
  };
  profile.default_agent = $("default-agent").value;
  profile = await invoke("save_profile", { profile });
  applyAesthetic(profile.aesthetic);
  await fillAgents();
  if (selected) await selectProject(selected, { keepSessionId: activeSession?.id });
  else show("empty");
});
$("btn-connect").addEventListener("click", async () => {
  profile = await invoke("begin_oauth", { email: $("email").value.trim() || null });
  openSettings();
});
$("btn-out").addEventListener("click", async () => {
  profile = await invoke("sign_out");
  openSettings();
});
$("accent-pick").addEventListener("input", () => {
  document.documentElement.style.setProperty("--accent", $("accent-pick").value);
});
$("btn-settings").addEventListener("contextmenu", async (e) => {
  e.preventDefault();
  fullscreenOn = !fullscreenOn;
  try {
    await invoke("set_fullscreen", { on: fullscreenOn });
  } catch {
    try {
      await invoke("maximize_window");
    } catch (_) {}
  }
});

(async () => {
  // Subscribe to agent stream ASAP so first-token events are never missed
  ensureStreamListen();

  try {
    await invoke("maximize_window");
  } catch (_) {}

  try {
    profile = await invoke("get_profile");
    applyAesthetic(profile.aesthetic);
  } catch (e) {
    console.warn(e);
  }

  // Agents + projects first (user-visible); backend can lag
  await fillAgents();
  try {
    const prefs = await invoke("get_project_prefs");
    if (prefs?.sort_mode) {
      sortMode = prefs.sort_mode;
      if ($("proj-sort")) $("proj-sort").value = sortMode;
    }
  } catch (_) {}
  await loadProjects();

  // Cascade backend + savings/peers in background (non-blocking boot)
  (async () => {
    try {
      apiBase = await invoke("backend_url", { port: PORT });
      await invoke("start_backend", { port: PORT });
      for (let i = 0; i < 16; i++) {
        try {
          if ((await fetch(apiBase + "/api/status")).ok) break;
        } catch (_) {}
        await new Promise((r) => setTimeout(r, 200));
      }
      await loadSavings();
    } catch (e) {
      console.warn(e);
    }
    try {
      await loadPeers();
    } catch (e) {
      console.warn(e);
    }
  })();
})();

// ── Cascade: one OpenRouter key, cheapest capable model ──
//
// Self-contained module. The key never enters this file: every call goes
// through a Tauri command and Rust holds the secret, so the webview only ever
// sees a masked preview. Catalog is fetched once per session and refiltered
// client-side so changing "min context" costs no network.

let cxCatalog = [];

function cxPrice(m) {
  if (m.free) return "free";
  // OpenRouter prices are per-token; per-million reads better at a glance.
  const perM = m.prompt_price * 1e6;
  return "$" + (perM < 1 ? perM.toFixed(3) : perM.toFixed(2)) + "/M";
}

function cxContext(m) {
  const c = m.context_length || 0;
  if (c >= 1e6) return (c / 1e6).toFixed(c % 1e6 === 0 ? 0 : 1) + "M";
  if (c >= 1000) return Math.round(c / 1000) + "K";
  return String(c);
}

function renderCascadeModels() {
  const min = parseInt($("cx-ctx").value, 10) || 0;
  const sel = $("cx-model");
  const previous = sel.value;
  const rows = cxCatalog.filter((m) => (m.context_length || 0) >= min);

  if (!rows.length) {
    sel.innerHTML = '<option value="">No model matches that context size</option>';
    $("cx-model-note").textContent = "";
    return;
  }
  sel.innerHTML = rows
    .map(
      (m) =>
        '<option value="' +
        m.id +
        '">' +
        m.id +
        "  ·  " +
        cxPrice(m) +
        "  ·  " +
        cxContext(m) +
        "</option>"
    )
    .join("");
  // Keep the user's pick across a refilter when it still qualifies.
  if (previous && rows.some((m) => m.id === previous)) sel.value = previous;

  const freeCount = rows.filter((m) => m.free).length;
  $("cx-model-note").textContent =
    rows.length +
    " capable text models, cheapest first. " +
    freeCount +
    " are free.";
}

async function loadCascadeModels(force) {
  const sel = $("cx-model");
  if (cxCatalog.length && !force) return renderCascadeModels();
  sel.innerHTML = '<option value="">Loading catalog…</option>';
  try {
    cxCatalog = await invoke("list_openrouter_models", { minContext: 0 });
    renderCascadeModels();
  } catch (e) {
    cxCatalog = [];
    sel.innerHTML = '<option value="">Could not load catalog</option>';
    $("cx-model-note").textContent = String(e);
  }
}

async function refreshKeyStatus() {
  try {
    const s = await invoke("openrouter_key_status");
    $("or-status").textContent = s.configured
      ? "Key configured (" +
        (s.source === "env" ? "from OPENROUTER_API_KEY" : "from file") +
        "): " +
        s.masked
      : "No key configured. The cascade cannot run without one.";
    $("or-path").textContent =
      "Shared with the CLI at " +
      s.path +
      (s.source === "env"
        ? ". The environment variable takes precedence over this file."
        : "");
  } catch (e) {
    $("or-status").textContent = "Could not read key status: " + e;
  }
}

async function openCascade() {
  show("cascade");
  await loadCascadeModels(false);
}

$("btn-cascade").addEventListener("click", openCascade);
$("btn-cx-back").addEventListener("click", () => {
  show(selected ? "work" : "empty");
});
$("cx-ctx").addEventListener("change", renderCascadeModels);
$("btn-cx-refresh").addEventListener("click", () => loadCascadeModels(true));

$("btn-cx-run").addEventListener("click", async () => {
  const model = $("cx-model").value;
  const prompt = $("cx-prompt").value.trim();
  if (!model) return ($("cx-meta").textContent = "Pick a model first.");
  if (!prompt) return ($("cx-meta").textContent = "Write a prompt first.");

  const btn = $("btn-cx-run");
  btn.disabled = true;
  $("cx-meta").textContent = "Running…";
  try {
    const r = await invoke("openrouter_chat", { model, prompt, maxTokens: 1024 });
    $("cx-out-card").classList.remove("hidden");
    $("cx-out").textContent = r.content || "(empty response)";
    $("cx-meta").textContent =
      r.model +
      "  ·  " +
      r.prompt_tokens +
      " in / " +
      r.completion_tokens +
      " out  ·  $" +
      r.cost +
      "  ·  " +
      (r.elapsed_ms / 1000).toFixed(2) +
      "s";
  } catch (e) {
    $("cx-meta").textContent = String(e);
  } finally {
    btn.disabled = false;
  }
});

$("btn-or-save").addEventListener("click", async () => {
  const key = $("or-key").value.trim();
  if (!key) return ($("or-status").textContent = "Paste a key first.");
  try {
    await invoke("save_openrouter_key", { key });
    $("or-key").value = "";
    cxCatalog = []; // a new key can change what the catalog returns
    await refreshKeyStatus();
  } catch (e) {
    $("or-status").textContent = "Could not save: " + e;
  }
});

$("btn-or-clear").addEventListener("click", async () => {
  try {
    await invoke("clear_openrouter_key");
    cxCatalog = [];
    await refreshKeyStatus();
  } catch (e) {
    $("or-status").textContent = "Could not clear: " + e;
  }
});
