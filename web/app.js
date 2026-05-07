const chatEl = document.getElementById("chat");
const toolEventsEl = document.getElementById("tool-events");
const runtimeOverviewEl = document.getElementById("runtime-overview");
const approvalBarEl = document.getElementById("approval-bar");
const formEl = document.getElementById("composer-form");
const inputEl = document.getElementById("composer-input");
const sendButtonEl = document.getElementById("send-button");
const newChatButtonEl = document.getElementById("new-chat-button");
const sidebarToggleButtonEl = document.getElementById("sidebar-toggle-button");
const sessionsSidebarEl = document.getElementById("sessions-sidebar");
const sessionsListEl = document.getElementById("sessions-list");
const collapsedHistoryListEl = document.getElementById("collapsed-history-list");
const statusPillEl = document.getElementById("status-pill");
const appErrorEl = document.getElementById("app-error");

const appState = {
  lastStateKey: "",
  autoFollow: true,
  openRawEventKeys: new Set(),
  sidebarCollapsed: false,
  isGenerating: false,
  pendingApproval: null,
  approvalSelection: 0,
  sessions: [
    { id: "s1", title: "Current chat", preview: "Active conversation", active: true },
  ],
};

// returns role formatted for frontend
function roleLabel(role) {
  if (role === "user") return "USER";
  if (role === "assistant") return "WALLACE";
  if (role === "tool") return "TOOL";
  if (role === "system") return "SYSTEM";
  return String(role || "").toUpperCase();
}

// return HTML escaped transformation of a string
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// return parsed markdown with raw HTML disabled before it reaches innerHTML
function renderMarkdown(content) {
  const source = String(content || "");
  const escapedSource = escapeHtml(source);

  if (typeof marked === "undefined") {
    return renderBasicMarkdown(escapedSource);
  }

  const html = marked.parse(escapedSource, {
    breaks: true,
    gfm: true,
  });

  if (typeof DOMPurify !== "undefined") {
    return DOMPurify.sanitize(html);
  }

  return html;
}

function renderInlineMarkdown(source) {
  const codeSpans = [];
  let text = source.replace(/`([^`\n]+)`/g, (_match, code) => {
    const token = `\u0000CODE${codeSpans.length}\u0000`;
    codeSpans.push(`<code>${code}</code>`);
    return token;
  });

  text = text
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\b__([^_]+)__\b/g, "<strong>$1</strong>")
    .replace(/\*([^*\n]+)\*/g, "<em>$1</em>")
    .replace(/\b_([^_\n]+)_\b/g, "<em>$1</em>");

  codeSpans.forEach((html, index) => {
    text = text.replaceAll(`\u0000CODE${index}\u0000`, html);
  });

  return text;
}

function renderBasicMarkdown(escapedSource) {
  const lines = escapedSource.replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let listType = "";
  let inCodeBlock = false;
  let codeLines = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(`<p>${renderInlineMarkdown(paragraph.join("<br>"))}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!listItems.length) return;
    const tag = listType === "ol" ? "ol" : "ul";
    blocks.push(`<${tag}>${listItems.map((item) => `<li>${renderInlineMarkdown(item)}</li>`).join("")}</${tag}>`);
    listItems = [];
    listType = "";
  }

  function flushCodeBlock() {
    blocks.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
    codeLines = [];
  }

  for (const line of lines) {
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      flushParagraph();
      flushList();
      if (inCodeBlock) {
        flushCodeBlock();
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const unordered = /^[-*+]\s+(.+)$/.exec(trimmed);
    if (unordered) {
      flushParagraph();
      if (listType && listType !== "ul") flushList();
      listType = "ul";
      listItems.push(unordered[1]);
      continue;
    }

    const ordered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
    if (ordered) {
      flushParagraph();
      if (listType && listType !== "ol") flushList();
      listType = "ol";
      listItems.push(ordered[1]);
      continue;
    }

    const quote = /^&gt;\s?(.+)$/.exec(trimmed);
    if (quote) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }

    flushList();
    paragraph.push(trimmed);
  }

  if (inCodeBlock) flushCodeBlock();
  flushParagraph();
  flushList();

  return blocks.join("");
}

// change inputEl height
function resizeComposer() {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 180)}px`;
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error || "Unknown error");
}

function showAppError(error) {
  appErrorEl.textContent = errorMessage(error);
  appErrorEl.hidden = false;
}

function clearAppError() {
  appErrorEl.textContent = "";
  appErrorEl.hidden = true;
}

// return if same message as last processed message
// create html bit for each message
// set lastStateKey to current key and autoscroll if necessary
function renderMessages(messages) {
  const nextKey = JSON.stringify(messages);
  if (nextKey === appState.lastStateKey) return;

  const nearBottom =
    Math.abs(chatEl.scrollHeight - chatEl.clientHeight - chatEl.scrollTop) < 8;

  chatEl.innerHTML = messages
    .map((message) => {
      const role = message.role || "assistant";
      const content = message.content || " ";

      return `
        <article class="message ${escapeHtml(role)}">
          <div class="label">${escapeHtml(roleLabel(role))}</div>
          <div class="body">${renderMarkdown(content)}</div>
        </article>
      `;
    })
    .join("");

  appState.lastStateKey = nextKey;

  if (appState.autoFollow || nearBottom) {
    chatEl.scrollTop = chatEl.scrollHeight;
  }
}

// process each keys and return first one that is a valid key of object else return ""
function firstPresent(object, keys) {
  for (const key of keys) {
    const value = object?.[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      return value;
    }
  }

  return "";
}


// return JSON string sliced according to maxLength
function compactValue(value, maxLength = 120) {
  if (value === undefined || value === null) return "";

  const text =
    typeof value === "string" ? value : JSON.stringify(value);

  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

// return event title according to event kind or tool or name or defaults to event
function eventTitle(event) {
  const kind = event?.kind || "tool";
  return event?.[kind] || event?.tool || event?.name || "event";
}

// return event status according to event result status or event status or defaults to unknown
function eventStatus(event) {
  return event?.result?.status || event?.status || "unknown";
}


// return compact versions of common argument fields
function summarizeArgs(args = {}) {
  const parts = [];

  for (const key of ["path", "symbol", "skill_name", "index_name"]) {
    if (args[key]) parts.push(`${key}=${compactValue(args[key], 70)}`);
  }

  if (args.command) parts.push(`cmd=${compactValue(args.command, 90)}`);
  if (args.intent) parts.push(`intent=${compactValue(args.intent, 90)}`);
  if (args.query) parts.push(`query=${compactValue(args.query, 90)}`);
  if (args.url) parts.push(`url=${compactValue(args.url, 90)}`);

  return parts.join(" · ");
}


// return compacted version of returncode, selectedSkill, path or metadata_path or procedure_path, error message, message or content or stdout as a list of JSON objects
function summarizeResult(result = {}) {
  const parts = [];

  if (result.returncode !== undefined) {
    parts.push(`returncode=${result.returncode}`);
  }

  const selectedSkill = firstPresent(result, ["skill_name", "selection"]);
  if (selectedSkill) {
    parts.push(`skill=${compactValue(selectedSkill, 80)}`);
  }

  const path = firstPresent(result, ["path", "metadata_path", "procedure_path"]);
  if (path) {
    parts.push(`path=${compactValue(path, 80)}`);
  }

  const message = firstPresent(result, ["error", "message"]);
  if (message) {
    parts.push(compactValue(message, 140));
  } else if (result.content !== undefined) {
    parts.push(`content=${compactValue(result.content, 140)}`);
  } else if (result.stdout) {
    parts.push(`stdout=${compactValue(result.stdout, 140)}`);
  } else if (result.stderr) {
    parts.push(`stderr=${compactValue(result.stderr, 140)}`);
  }

  return parts.join(" · ");
}

function policyCountLabel(label, count) {
  return `
    <span class="policy-count">
      <span class="policy-count-value">${escapeHtml(formatCount(count))}</span>
      <span>${escapeHtml(label)}</span>
    </span>
  `;
}

function renderRuntimeOverview(state = {}) {
  if (!runtimeOverviewEl) return;

  const policy = state.active_skill_policy || {};
  const activeSkill = state.active_skill_name || "none";
  const allowedTools = policy.allowed_tools || [];
  const recommendedTools = policy.recommended_tool_calls || [];
  const forbiddenTools = policy.forbidden_tool_calls || [];

  runtimeOverviewEl.innerHTML = `
    <section class="runtime-overview-card">
      <div class="overview-label">Selected skill</div>
      <div class="overview-value">${escapeHtml(activeSkill)}</div>
    </section>
    <section class="runtime-overview-card">
      <div class="overview-label">Policy</div>
      <div class="policy-counts">
        ${policyCountLabel("allowed", allowedTools.length)}
        ${policyCountLabel("ordered", recommendedTools.length)}
        ${policyCountLabel("blocked", forbiddenTools.length)}
      </div>
    </section>
  `;
}

function approvalOptionsMarkup() {
  return ["Yes", "No"].map((label, index) => {
    const action = index === 0 ? "approve" : "deny";
    const selected = appState.approvalSelection === index;
    return `
      <button
        class="approval-option ${selected ? "selected" : ""}"
        type="button"
        data-curl-approval-action="${action}"
        data-approval-option-index="${index}"
        aria-selected="${selected ? "true" : "false"}"
      >
        <span class="approval-option-index">${index + 1}.</span>
        <span>${label}</span>
      </button>
    `;
  }).join("");
}

function renderChatApprovalPrompt(approval) {
  if (!approval) return "";
  const domain = compactValue(approval.domain, 90);
  const requestedUrl = compactValue(approval.url, 160);

  return `
    <section class="chat-approval-prompt" role="listbox" aria-label="Curl whitelist approval">
      <div class="chat-approval-title">
        Add domain ${escapeHtml(domain)} to the curl whitelist?
      </div>
      <div class="chat-approval-url">
        Requested page: ${escapeHtml(requestedUrl)}
      </div>
      <div class="chat-approval-options">
        ${approvalOptionsMarkup()}
      </div>
    </section>
  `;
}

function renderApprovalBar(approval) {
  if (!approval) {
    approvalBarEl.hidden = true;
    approvalBarEl.innerHTML = "";
    return;
  }

  approvalBarEl.hidden = false;
  approvalBarEl.innerHTML = renderChatApprovalPrompt(approval);
}

// return compacted version of runtime state and approval cards
function renderRuntimePane(toolEvents, lastError) {
  const items = [];
  const previouslyOpen = new Set(appState.openRawEventKeys);
  const nextEventKeys = new Set();

  if (lastError) {
    items.push(`
      <section class="runtime-error">
        <div class="runtime-event-header">
          <span class="runtime-event-name">Error</span>
          <span class="runtime-status error">active</span>
        </div>
        <div class="runtime-event-detail">${escapeHtml(lastError)}</div>
      </section>
    `);
  }

  if (!toolEvents.length && !lastError) {
    toolEventsEl.innerHTML = '<div class="runtime-empty">No runtime events yet.</div>';
    return;
  }

  toolEvents.forEach((event, index) => {
    const name = eventTitle(event);
    const status = eventStatus(event);
    const argsSummary = summarizeArgs(event.args || {});
    const resultSummary = summarizeResult(event.result || {});
    const rawJson = JSON.stringify(event, null, 2);
    const eventKey = event.id || `${index}:${name}`;
    const isOpen = previouslyOpen.has(eventKey);

    nextEventKeys.add(eventKey);

    const duration = event.duration_ms ?? event.result?.duration_ms ?? event.elapsed_ms;
    const eventKind = event.kind || "tool";

    items.push(`
      <section class="runtime-event timeline-event">
        <div class="timeline-index">${index + 1}</div>
        <div class="timeline-body">
        <div class="runtime-event-header">
          <span class="runtime-event-name">${escapeHtml(name)}</span>
          <span class="runtime-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
        </div>
        <div class="runtime-event-meta">
          <span>${escapeHtml(eventKind)}</span>
          <span>${escapeHtml(formatDuration(duration))}</span>
        </div>
        ${argsSummary ? `<div class="runtime-event-detail">${escapeHtml(argsSummary)}</div>` : ""}
        ${resultSummary ? `<div class="runtime-event-result">${escapeHtml(resultSummary)}</div>` : ""}
        <details class="runtime-raw" data-event-key="${escapeHtml(eventKey)}" ${isOpen ? "open" : ""}>
          <summary>Raw</summary>
          <pre>${escapeHtml(rawJson)}</pre>
        </details>
        </div>
      </section>
    `);
  });

  appState.openRawEventKeys = new Set(
    [...appState.openRawEventKeys].filter((eventKey) => nextEventKeys.has(eventKey)),
  );

  toolEventsEl.innerHTML = items.join("");
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("#measure-baseline-button");
  if (!button) return;
  measureBaselineMetrics();
});

function submitApprovalAction(action) {
  if (!appState.pendingApproval || !action) return Promise.resolve();
  return fetch("/api/curl-approvals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      approval_id: appState.pendingApproval.approval_id,
    }),
  }).then(async (response) => {
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || `Approval failed: ${response.status}`);
    }
    await refreshState();
  });
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-curl-approval-action]");
  if (!button || !appState.pendingApproval) return;

  const action = button.getAttribute("data-curl-approval-action");
  try {
    await submitApprovalAction(action);
  } catch (error) {
    console.error(error);
    showAppError(error);
  }
});

toolEventsEl.addEventListener("toggle", (event) => {
  const details = event.target;
  if (!(details instanceof HTMLDetailsElement)) return;
  if (!details.classList.contains("runtime-raw")) return;

  const eventKey = details.getAttribute("data-event-key");
  if (!eventKey) return;

  if (details.open) {
    appState.openRawEventKeys.add(eventKey);
  } else {
    appState.openRawEventKeys.delete(eventKey);
  }
}, true);

// selected icon on the current session
function sessionButtonMarkup(session) {
  const activeClass = session.active ? "active" : "";
  return `
    <div
      class="session-item ${activeClass}"
      data-session-id="${escapeHtml(session.id)}"
      title="${escapeHtml(session.title)}"
    >
      <span class="session-item-icon">💬</span>
      <span class="session-item-text">
        <div class="session-item-title">${escapeHtml(session.title)}</div>
        <div class="session-item-meta">${escapeHtml(session.preview || "")}</div>
      </span>
      <button
        class="session-rename-button"
        type="button"
        data-rename-session-id="${escapeHtml(session.id)}"
        aria-label="Rename conversation"
        title="Rename conversation"
      >
        Rename
      </button>
    </div>
  `;
}


// render sessions list
function renderSessions() {
  sessionsListEl.innerHTML = appState.sessions.map(sessionButtonMarkup).join("");

  const recentSessions = appState.sessions.slice(0, 8);
  collapsedHistoryListEl.innerHTML = recentSessions.map(sessionButtonMarkup).join("");
}

// button to rename a session. calls rerender on change
function renameSession(sessionId) {
  const session = appState.sessions.find((item) => item.id === sessionId);
  if (!session) return;

  const title = window.prompt("Rename conversation", session.title);
  if (title === null) return;

  const cleaned = title.trim();
  if (!cleaned) return;

  appState.sessions = appState.sessions.map((item) => (
    item.id === sessionId ? { ...item, title: cleaned } : item
  ));
  renderSessions();
}

// change the state of sidebar (collapse / expanded)
function applySidebarState() {
  sessionsSidebarEl.classList.toggle("collapsed", appState.sidebarCollapsed);
  sessionsSidebarEl.classList.toggle("expanded", !appState.sidebarCollapsed);
}

// block inputs if generating and prints generating state
function setGenerating(isGenerating) {
  appState.isGenerating = Boolean(isGenerating);
  const waitingForApproval = Boolean(appState.pendingApproval);
  inputEl.disabled = isGenerating || waitingForApproval;
  sendButtonEl.disabled = isGenerating || waitingForApproval;

  inputEl.placeholder = waitingForApproval
    ? "Select an approval option to continue"
    : isGenerating
    ? "Generation in progress..."
    : "Type a message. Enter sends, Shift+Enter adds a new line";

  statusPillEl.textContent = waitingForApproval ? "Approval" : isGenerating ? "Running" : "Idle";
  statusPillEl.className = `status ${isGenerating || waitingForApproval ? "running" : "idle"}`;
}

// call /api/state then call renderMessages, renderRuntimePane, setGenerating
async function refreshState() {
  const response = await fetch("/api/state", {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new Error(`State refresh failed: ${response.status}`);
  }

  const state = await response.json();
  renderMessages(state.messages || []);
  renderRuntimeMetrics(state.runtime_metrics || {});
  renderRuntimeOverview(state);
  appState.pendingApproval = state.pending_approval || null;
  if (!appState.pendingApproval) appState.approvalSelection = 0;
  renderApprovalBar(appState.pendingApproval);
  renderRuntimePane(state.tool_events || [], state.last_error || "");
  setGenerating(Boolean(state.is_generating));
  clearAppError();
}

// POST submitted input to /api/messages
async function submitMessage(content) {
  const response = await fetch("/api/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Submit failed: ${response.status}`);
  }
}


// call /api/reset 
async function resetSession() {
    const response = await fetch("/api/reset", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
    });

    if(!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Reset failed: ${response.status}`);
    }
}

// reset input, composer height, call submitMessage, refreshState
formEl.addEventListener("submit", async (event) => {
  event.preventDefault();

  const content = inputEl.value.trim();
  if (!content || inputEl.disabled) return;

  inputEl.value = "";
  resizeComposer();
  appState.autoFollow = true;

  try {
    await submitMessage(content);
    await refreshState();
  } catch (error) {
    console.error(error);
    showAppError(error);
  }
});

newChatButtonEl.addEventListener("click", async () => {
  try {
    await resetSession();
    appState.lastStateKey = "";
    appState.openRawEventKeys = new Set();
    await refreshState();
  } catch (error) {
    console.error(error);
    showAppError(error);
  }

  inputEl.focus();
});

sidebarToggleButtonEl.addEventListener("click", () => {
  appState.sidebarCollapsed = !appState.sidebarCollapsed;
  applySidebarState();
});

function handleSessionClick(event) {
  const renameButton = event.target.closest("[data-rename-session-id]");
  if (renameButton) {
    const sessionId = renameButton.getAttribute("data-rename-session-id");
    if (sessionId) renameSession(sessionId);
    return;
  }

  const button = event.target.closest("[data-session-id]");
  if (!button) return;
}

sessionsListEl.addEventListener("click", handleSessionClick);
collapsedHistoryListEl.addEventListener("click", handleSessionClick);

inputEl.addEventListener("input", () => {
  resizeComposer();
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

document.addEventListener("keydown", async (event) => {
  if (!appState.pendingApproval) return;
  if (event.key === "ArrowUp" || event.key === "ArrowDown") {
    event.preventDefault();
    appState.approvalSelection = appState.approvalSelection === 0 ? 1 : 0;
    renderApprovalBar(appState.pendingApproval);
    return;
  }
  if (event.key === "1" || event.key === "2") {
    event.preventDefault();
    appState.approvalSelection = event.key === "1" ? 0 : 1;
    renderApprovalBar(appState.pendingApproval);
    try {
      await submitApprovalAction(appState.approvalSelection === 0 ? "approve" : "deny");
    } catch (error) {
      console.error(error);
      showAppError(error);
    }
    return;
  }
  if (event.key === "Enter") {
    event.preventDefault();
    try {
      await submitApprovalAction(appState.approvalSelection === 0 ? "approve" : "deny");
    } catch (error) {
      console.error(error);
      showAppError(error);
    }
  }
});

chatEl.addEventListener("scroll", () => {
  appState.autoFollow =
    Math.abs(chatEl.scrollHeight - chatEl.clientHeight - chatEl.scrollTop) < 8;
});

async function tick() {
  try {
    await refreshState();
  } catch (error) {
    console.error(error);
    showAppError(error);
  }
}

function scheduleNextTick() {
  const delay = appState.isGenerating ? 300 : 1500;
  window.setTimeout(async () => {
    await tick();
    scheduleNextTick();
  }, delay);
}

window.addEventListener("load", async () => {
  applySidebarState();
  renderSessions();
  resizeComposer();
  await tick();
  scheduleNextTick();
});
