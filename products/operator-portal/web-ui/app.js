const gatewayInput = document.querySelector("#gateway-url");

// Platform version shown in the sidebar footer; bump in step with the
// CHANGELOG milestones. A gateway-served /api/v1/version endpoint is the
// intended long-term source of truth.
const PLATFORM_VERSION = "v0.1.0";
document.querySelector("#version-output").textContent = PLATFORM_VERSION;
const userInput = document.querySelector("#user-id");
const promptInput = document.querySelector("#prompt-input");
const sessionIdOutput = document.querySelector("#session-id");
const requestIdOutput = document.querySelector("#request-id");
const identityOutput = document.querySelector("#identity-output");
const identityBadge = document.querySelector("#identity-badge");
const responseOutput = document.querySelector("#response-output");
const AUTH_SESSION_KEY = "luban.portal.authSession";
const AUTH_REQUEST_KEY = "luban.portal.authRequest";
let authCallbackNavigationPending = false;
let refreshTimerId = null;
const REFRESH_MARGIN_SECONDS = 60;

// Evidence state (SPEC-011 R-4). Evidence and audit are supportive detail:
// each chat turn gets its own collapsed group rendered inline directly
// after the agent reply it grounds, so provenance follows its answer.
let currentTurn = null;
const chatMain = document.querySelector(".chat-main");

// Durable audit trail view (SPEC-013 R-5): role-gated function view that
// queries the gateway's audit proxy. Client-side gating is a convenience
// only — the gateway re-enforces ``audit:read`` on every request.
const auditOutput = document.querySelector("#audit-output");
const auditMoreButton = document.querySelector("#audit-more-button");
const auditStatus = document.querySelector("#audit-status");
const AUDIT_ROLES = new Set(["auditor", "platform-admin"]);
let auditCursor = null;
let auditTableBody = null;
let auditLoadedCount = 0;
// Guards against double-clicked Refresh / Load more issuing the same cursor
// twice and appending duplicate rows.
let auditLoadInFlight = false;

// --- View navigation (sidebar → main area) ---
// Views are hidden, never destroyed, so chat history, session state, and
// loaded audit rows survive navigation.
const VIEWS = {
  chat: { nav: document.querySelector("#nav-chat"), section: document.querySelector("#chat-view") },
  settings: { nav: document.querySelector("#nav-settings"), section: document.querySelector("#settings-view") },
  audit: { nav: document.querySelector("#nav-audit"), section: document.querySelector("#audit-view") }
};
let activeViewId = "chat";

// Visible pulse on the Chat nav item while a stream is running, so switching
// to another function never hides that the agent is still working.
const chatStreamDot = document.querySelector("#chat-stream-dot");

function showView(viewId) {
  if (!VIEWS[viewId] || VIEWS[viewId].nav.hidden) return;
  activeViewId = viewId;
  for (const [id, view] of Object.entries(VIEWS)) {
    const isActive = id === viewId;
    view.section.hidden = !isActive;
    view.nav.classList.toggle("active", isActive);
    if (isActive) {
      view.nav.setAttribute("aria-current", "page");
    } else {
      view.nav.removeAttribute("aria-current");
    }
  }
  // Load the trail lazily on every activation of the audit view.
  if (viewId === "audit") {
    loadAuditEvents(false).catch((error) => {
      renderError(auditOutput, error);
    });
  }
}

for (const [viewId, view] of Object.entries(VIEWS)) {
  view.nav.addEventListener("click", () => {
    showView(viewId);
    closeSidebarDrawer();
  });
}

// --- Mobile drawer (≤800px): the hamburger opens the sidebar as an
// off-canvas drawer; backdrop tap, Escape, or picking a view closes it.
// Above 800px the drawer classes/styles simply have no effect. ---
const sidebar = document.querySelector("#sidebar");
const menuButton = document.querySelector("#menu-button");
const sidebarBackdrop = document.querySelector("#sidebar-backdrop");

function setSidebarDrawerOpen(open) {
  sidebar.classList.toggle("open", open);
  sidebarBackdrop.hidden = !open;
  menuButton.setAttribute("aria-expanded", String(open));
}

function closeSidebarDrawer() {
  setSidebarDrawerOpen(false);
}

menuButton.addEventListener("click", () => {
  setSidebarDrawerOpen(!sidebar.classList.contains("open"));
});
sidebarBackdrop.addEventListener("click", closeSidebarDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeSidebarDrawer();
    setUserMenuOpen(false);
  }
});

// --- Markdown renderer ---
function renderMarkdown(text) {
  if (!text) return "";
  let html = text;

  // Escape HTML first
  html = html.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Headers
  html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");

  // Horizontal rules
  html = html.replace(/^---+$/gm, "<hr>");

  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");
  html = html.replace(/_(.+?)_/g, "<em>$1</em>");

  // Strikethrough
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Blockquotes
  html = html.replace(/^&gt;\s+(.+)$/gm, "<blockquote>$1</blockquote>");

  // Unordered lists
  html = html.replace(/^[\*\-]\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Ordered lists
  html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");

  // Tables
  html = html.replace(/^\|(.+)\|$/gm, (match, content) => {
    const cells = content.split("|").map(c => c.trim());
    if (cells.every(c => /^[-:]+$/.test(c))) return ""; // separator row
    const tag = "td";
    return "<tr>" + cells.map(c => `<${tag}>${c}</${tag}>`).join("") + "</tr>";
  });
  html = html.replace(/((?:<tr>.*<\/tr>\n?)+)/g, "<table>$1</table>");

  // Paragraphs: wrap remaining lines that aren't already in block elements
  html = html.replace(/^(?!<[hupoltbd]|<\/|<hr|<blockquote|<pre|<code)(.+)$/gm, "<p>$1</p>");

  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, "");

  return html;
}

function defaultGateway() {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return window.location.origin;
  }
  return "http://localhost:8080";
}

function buildRequestId() {
  return `req-${crypto.randomUUID()}`;
}

function currentGateway() {
  const explicitValue = gatewayInput.value.trim().replace(/\/$/, "");
  return explicitValue || defaultGateway();
}

gatewayInput.value = defaultGateway();

function loadAuthSession() {
  const raw = window.sessionStorage.getItem(AUTH_SESSION_KEY);
  return raw ? JSON.parse(raw) : null;
}

function saveAuthSession(session) {
  window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

function clearAuthSession() {
  window.sessionStorage.removeItem(AUTH_SESSION_KEY);
  cancelRefreshTimer();
}

function loadPendingAuthRequest() {
  const raw = window.sessionStorage.getItem(AUTH_REQUEST_KEY);
  return raw ? JSON.parse(raw) : null;
}

function savePendingAuthRequest(payload) {
  window.sessionStorage.setItem(AUTH_REQUEST_KEY, JSON.stringify(payload));
}

function clearPendingAuthRequest() {
  window.sessionStorage.removeItem(AUTH_REQUEST_KEY);
}

function currentAuthenticatedUser() {
  return loadAuthSession()?.identity?.username || null;
}

function currentRoles() {
  return loadAuthSession()?.identity?.roles || [];
}

function canViewAudit() {
  return currentRoles().some((role) => AUDIT_ROLES.has(role));
}

// Initials for the user-card avatar: up to two letters from the username,
// split on non-alphanumerics ("luban-admin" -> "LA").
function userInitials(username) {
  const parts = username.split(/[^a-zA-Z0-9]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2);
  return parts[0][0] + parts[1][0];
}

// --- User popup menu (sidebar footer) ---
// Home for user-related info and actions: granted roles today; future
// items (session expiry, token state, profile) belong here, not elsewhere.
const userMenu = document.querySelector("#user-menu");
const userMenuButton = document.querySelector("#user-menu-button");

function setUserMenuOpen(open) {
  userMenu.hidden = !open;
  userMenuButton.setAttribute("aria-expanded", String(open));
}

userMenuButton.addEventListener("click", () => {
  setUserMenuOpen(userMenu.hidden);
});
document.addEventListener("click", (event) => {
  if (!userMenu.hidden && !event.target.closest(".user-card")) {
    setUserMenuOpen(false);
  }
});

function syncResolvedUser() {
  const authenticatedUser = currentAuthenticatedUser();
  const roles = currentRoles();
  const auditAllowed = canViewAudit();
  VIEWS.audit.nav.hidden = !auditAllowed;
  if (!auditAllowed && activeViewId === "audit") {
    showView("chat");
  }
  const roleBadge = document.querySelector("#identity-role");
  const avatar = document.querySelector("#user-avatar");
  if (authenticatedUser) {
    userInput.value = authenticatedUser;
    userInput.setAttribute("disabled", "disabled");
    identityBadge.textContent = authenticatedUser;
    avatar.textContent = userInitials(authenticatedUser);
    roleBadge.textContent = roles.join(", ") || "no role";
    document.querySelector("#login-button").hidden = true;
    document.querySelector("#logout-button").hidden = false;
    return;
  }
  userInput.removeAttribute("disabled");
  identityBadge.textContent = "Not signed in";
  avatar.textContent = "?";
  roleBadge.textContent = "no role";
  setUserMenuOpen(false);
  document.querySelector("#login-button").hidden = false;
  document.querySelector("#logout-button").hidden = true;
}

function renderIdentity(payload) {
  identityOutput.textContent = JSON.stringify(payload, null, 2);
  syncResolvedUser();
}

function authHeaders() {
  const session = loadAuthSession();
  if (!session?.access_token) {
    return {};
  }
  return {
    authorization: `Bearer ${session.access_token}`
  };
}

function tokenExpiresInSeconds(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (!payload.exp) return null;
    return payload.exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

function scheduleTokenRefresh(session) {
  cancelRefreshTimer();
  if (!session?.access_token || !session?.refresh_token) return;
  const remaining = tokenExpiresInSeconds(session.access_token);
  if (remaining === null) return;
  const delayMs = Math.max((remaining - REFRESH_MARGIN_SECONDS) * 1000, 5000);
  refreshTimerId = setTimeout(() => silentRefresh(), delayMs);
}

function cancelRefreshTimer() {
  if (refreshTimerId !== null) {
    clearTimeout(refreshTimerId);
    refreshTimerId = null;
  }
}

async function silentRefresh() {
  const session = loadAuthSession();
  if (!session?.refresh_token) {
    clearAuthSession();
    renderIdentity({ authenticated: false, reason: "session expired — please sign in again" });
    return;
  }
  try {
    const refreshed = await requestJson("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: session.refresh_token })
    });
    saveAuthSession(refreshed);
    scheduleTokenRefresh(refreshed);
    renderIdentity({ authenticated: true, identity: refreshed.identity });
  } catch {
    clearAuthSession();
    renderIdentity({ authenticated: false, reason: "session expired — please sign in again" });
  }
}

async function requestJson(path, options = {}) {
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;
  const headers = {
    "x-request-id": requestId,
    ...authHeaders(),
    ...(options.headers || {})
  };

  if (options.body) {
    headers["content-type"] = "application/json";
  }

  const response = await fetch(`${currentGateway()}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

function clearAuthCallbackQuery() {
  const url = new URL(window.location.href);
  for (const key of ["code", "state", "session_state", "iss", "error", "error_description"]) {
    url.searchParams.delete(key);
  }
  if (url.pathname === "/callback") {
    authCallbackNavigationPending = true;
    window.location.replace(`${url.origin}/`);
    return;
  }
  window.history.replaceState({}, document.title, url.pathname + url.search + url.hash);
}

function renderError(target, error) {
  const msg = error instanceof Error ? error.message : String(error);
  const p = document.createElement("p");
  p.style.color = "var(--error)";
  p.textContent = msg;
  target.innerHTML = "";
  target.appendChild(p);
}

// --- Durable audit trail view (SPEC-013 R-5) ---
function buildAuditQueryParams(cursor) {
  const params = new URLSearchParams({ limit: "50" });
  const username = document.querySelector("#audit-filter-username").value.trim();
  const eventType = document.querySelector("#audit-filter-type").value;
  const service = document.querySelector("#audit-filter-service").value;
  const since = document.querySelector("#audit-filter-since").value;
  const until = document.querySelector("#audit-filter-until").value;
  if (username) params.set("username", username);
  if (eventType) params.set("event_type", eventType);
  if (service) params.set("service", service);
  if (since) params.set("since", new Date(since).toISOString());
  if (until) params.set("until", new Date(until).toISOString());
  if (cursor) params.set("cursor", cursor);
  return params;
}

async function loadAuditEvents(append) {
  if (!canViewAudit() || auditLoadInFlight) return;
  auditLoadInFlight = true;
  auditMoreButton.disabled = true;
  try {
    const cursor = append ? auditCursor : null;
    const query = buildAuditQueryParams(cursor).toString();
    const payload = await requestJson(`/api/v1/audit/events?${query}`, { method: "GET" });
    auditCursor = payload.next_cursor || null;
    if (!append) auditLoadedCount = 0;
    renderAuditEvents(payload.events || [], append);
    auditLoadedCount += (payload.events || []).length;
    auditMoreButton.hidden = !auditCursor;
    auditStatus.textContent = auditCursor
      ? `${auditLoadedCount} events shown \u00b7 more available`
      : `${auditLoadedCount} event${auditLoadedCount === 1 ? "" : "s"} shown \u00b7 end of trail`;
  } finally {
    auditLoadInFlight = false;
    auditMoreButton.disabled = false;
  }
}

function renderAuditEvents(events, append) {
  if (!append) {
    auditOutput.innerHTML = "";
    auditTableBody = null;
  }
  if (!auditTableBody) {
    if (events.length === 0) {
      auditOutput.innerHTML = '<p class="chat-placeholder">No audit events match these filters.</p>';
      return;
    }
    const table = document.createElement("table");
    table.className = "audit-table";
    const headers = ["occurred at", "type", "service", "outcome", "actor", "request"];
    table.innerHTML = `<thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>`;
    auditTableBody = document.createElement("tbody");
    table.appendChild(auditTableBody);
    auditOutput.appendChild(table);
  }
  for (const event of events) {
    auditTableBody.appendChild(auditEventRows(event));
  }
}

// One event renders as a summary row plus a hidden detail row carrying the
// verbatim event envelope; clicking the summary toggles the envelope.
function auditEventRows(event) {
  const fragment = document.createDocumentFragment();
  const row = document.createElement("tr");
  row.className = "audit-row";
  const cells = [
    formatAuditTimestamp(event.occurred_at),
    event.event_type,
    event.service,
    event.outcome,
    event.username || event.actor || event.subject || "\u2014",
    event.request_id
  ];
  for (const [index, value] of cells.entries()) {
    const td = document.createElement("td");
    td.textContent = value;
    if (index === 3 && (event.outcome === "deny" || event.outcome === "error")) {
      td.className = "audit-outcome-negative";
    }
    row.appendChild(td);
  }
  const detailRow = document.createElement("tr");
  detailRow.className = "audit-detail-row";
  detailRow.hidden = true;
  const detailCell = document.createElement("td");
  detailCell.colSpan = 6;
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(event, null, 2);
  detailCell.appendChild(pre);
  detailRow.appendChild(detailCell);
  row.addEventListener("click", () => {
    detailRow.hidden = !detailRow.hidden;
  });
  fragment.append(row, detailRow);
  return fragment;
}

function formatAuditTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

// Stream events carry their kind in `type` per the gateway/agent contract.
function streamEventType(payload) {
  return String(payload.type || payload.event || "").toLowerCase();
}

function shouldAppendStreamDelta(payload) {
  return Boolean(payload.delta) && ["message_delta", "text_block_start", "text_block_delta"].includes(streamEventType(payload));
}

function isStreamComplete(payload) {
  return ["message_end", "reply_end"].includes(streamEventType(payload));
}

async function refreshAuthenticatedIdentity() {
  const session = loadAuthSession();
  if (!session?.access_token) {
    renderIdentity({ authenticated: false });
    return;
  }

  try {
    const payload = await requestJson("/api/v1/auth/me", { method: "GET" });
    if (!payload.authenticated) {
      clearAuthSession();
      renderIdentity({ authenticated: false });
      return;
    }
    const refreshedSession = {
      ...session,
      identity: payload.identity
    };
    saveAuthSession(refreshedSession);
    renderIdentity({ authenticated: true, identity: payload.identity });
  } catch (error) {
    if (session.identity) {
      renderIdentity({
        authenticated: true,
        identity: session.identity,
        warning: "Using cached identity until session refresh succeeds again."
      });
      return;
    }
    clearAuthSession();
    renderIdentity({ authenticated: false, error: error.message });
  }
}

async function startLogin() {
  const payload = await requestJson("/api/v1/auth/login", { method: "GET" });
  savePendingAuthRequest({
    state: payload.state,
    code_verifier: payload.code_verifier,
    redirect_uri: payload.redirect_uri
  });
  renderIdentity({
    authenticated: false,
    login_start: payload
  });
  window.location.assign(payload.authorization_url);
}

async function completeLoginFromCallback() {
  const url = new URL(window.location.href);
  const onCallbackPath = url.pathname === "/callback";
  const authError = url.searchParams.get("error");
  if (authError) {
    clearAuthSession();
    clearPendingAuthRequest();
    renderIdentity({
      authenticated: false,
      error: authError,
      error_description: url.searchParams.get("error_description")
    });
    clearAuthCallbackQuery();
    return false;
  }
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code || !state) {
    if (onCallbackPath) {
      clearAuthCallbackQuery();
    }
    return false;
  }

  const pendingRequest = loadPendingAuthRequest();
  if (!pendingRequest || pendingRequest.state !== state) {
    clearAuthSession();
    clearPendingAuthRequest();
    clearAuthCallbackQuery();
    throw new Error("OIDC state validation failed.");
  }

  const session = await requestJson("/api/v1/auth/callback", {
    method: "POST",
    body: JSON.stringify({
      code,
      code_verifier: pendingRequest.code_verifier,
      redirect_uri: pendingRequest.redirect_uri
    })
  });
  saveAuthSession(session);
  scheduleTokenRefresh(session);
  clearPendingAuthRequest();
  clearAuthCallbackQuery();
  renderIdentity({ authenticated: true, identity: session.identity });
  return true;
}

async function logout() {
  const session = loadAuthSession();
  clearAuthSession();
  clearPendingAuthRequest();
  sessionIdOutput.textContent = "Not created";
  syncResolvedUser();

  if (!session) {
    renderIdentity({ authenticated: false });
    return;
  }

  try {
    const payload = await requestJson("/api/v1/auth/logout-url", {
      method: "POST",
      body: JSON.stringify({
        id_token_hint: session.id_token,
        post_logout_redirect_uri: `${currentGateway()}/`
      })
    });
    renderIdentity({ authenticated: false });
    window.location.assign(payload.logout_url);
  } catch (error) {
    renderIdentity({ authenticated: false, error: error.message });
  }
}

async function normalizeIdentity() {
  const payload = await requestJson("/api/v1/identity/normalize", {
    method: "POST",
    body: JSON.stringify({
      sub: "user-123",
      preferred_username: currentAuthenticatedUser() || userInput.value,
      email: `${(currentAuthenticatedUser() || userInput.value)}@example.com`,
      groups: ["ops-operators"]
    })
  });
  renderIdentity({
    authenticated: Boolean(currentAuthenticatedUser()),
    normalized_identity: payload
  });
}

async function createSession() {
  const payload = await requestJson("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ user_id: currentAuthenticatedUser() || userInput.value })
  });
  sessionIdOutput.textContent = payload.session_id;
}

async function sendPrompt() {
  const payload = await requestJson("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionIdOutput.textContent === "Not created" ? null : sessionIdOutput.textContent,
      user_id: currentAuthenticatedUser() || userInput.value,
      message: promptInput.value
    })
  });
  sessionIdOutput.textContent = payload.session_id;
  responseOutput.innerHTML = `<div class="md-content">${renderMarkdown(payload.response)}</div>`;
}

function formatCounts(counts) {
  if (counts.calls === 0) return "no tool calls";
  const parts = [`${counts.calls} call${counts.calls === 1 ? "" : "s"}`];
  if (counts.pending > 0) parts.push(`${counts.pending} running`);
  if (counts.success > 0) parts.push(`${counts.success} ok`);
  if (counts.error > 0) parts.push(`${counts.error} failed`);
  if (counts.denied > 0) parts.push(`${counts.denied} denied`);
  return parts.join(" · ");
}

// The turn group is created lazily on the first tool frame, so purely
// conversational turns leave no empty group in the chat history. It is
// inserted directly after the agent reply it grounds and stays collapsed:
// the summary line carries the trust signal without crowding the answer.
function ensureCurrentTurn() {
  if (!currentTurn || currentTurn.group) return currentTurn;
  const group = document.createElement("details");
  group.className = "evidence-turn";
  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.className = "evidence-turn-title";
  title.textContent = "Tool evidence";
  const summaryLine = document.createElement("span");
  summaryLine.className = "evidence-summary";
  summaryLine.textContent = formatCounts(currentTurn.counts);
  summary.append(title, summaryLine);
  const body = document.createElement("div");
  body.className = "evidence-turn-body";
  group.append(summary, body);
  currentTurn.anchor.after(group);
  currentTurn.group = group;
  currentTurn.body = body;
  currentTurn.summaryLine = summaryLine;
  return currentTurn;
}

function renderToolCall(payload) {
  const turn = ensureCurrentTurn();
  if (!turn) return;
  turn.counts.calls += 1;
  turn.counts.pending += 1;
  turn.entries.push({
    call_id: payload.call_id,
    tool: payload.tool_name || payload.call_id,
    status: "pending",
    executed_at: null,
    duration_ms: null,
    risk_level: null,
    source_system: null
  });
  turn.summaryLine.textContent = formatCounts(turn.counts);
  const card = document.createElement("div");
  card.className = "evidence-card";
  card.dataset.callId = payload.call_id;
  card.innerHTML = `
    <div class="card-header">
      <span class="tool-name">${escapeHtml(payload.tool_name)}</span>
      <span class="status-badge pending">pending</span>
      <span class="spinner"></span>
    </div>
    <details>
      <summary>Parameters</summary>
      <pre>${escapeHtml(JSON.stringify(payload.parameters || {}, null, 2))}</pre>
    </details>
  `;
  turn.body.appendChild(card);
  turn.cardMap.set(payload.call_id, card);
}

// Cited guidance: when a skills.* tool succeeds, the streamed data_summary
// carries the matched skills; surface them as citation chips under the
// evidence card. A truncated summary (_truncated marker) yields no chips
// rather than partial ones.
function citedSkills(payload) {
  if (payload.status !== "success") return [];
  const data = payload.data_summary;
  if (!data || typeof data !== "object" || data._truncated) return [];
  const entries =
    payload.tool_name === "skills.search" ? data.matches
    : payload.tool_name === "skills.list" ? data.skills
    : payload.tool_name === "skills.get" ? [data]
    : [];
  return (Array.isArray(entries) ? entries : [])
    .filter((item) => item && item.skill_id)
    .map((item) => ({
      skillId: String(item.skill_id),
      title: String(item.title || item.skill_id)
    }));
}

function renderCitedGuidance(card, payload) {
  if (!String(payload.tool_name || "").startsWith("skills.")) return;
  if (card.querySelector(".cited-guidance")) return;
  const citations = citedSkills(payload);
  if (citations.length === 0) return;
  const section = document.createElement("div");
  section.className = "cited-guidance";
  const label = document.createElement("div");
  label.className = "cited-guidance-label";
  label.textContent = "Cited guidance";
  section.appendChild(label);
  const chips = document.createElement("div");
  chips.className = "cited-chips";
  for (const citation of citations) {
    const chip = document.createElement("span");
    chip.className = "cited-chip";
    chip.title = citation.skillId;
    const titleSpan = document.createElement("span");
    titleSpan.className = "cited-chip-title";
    titleSpan.textContent = citation.title;
    const idSpan = document.createElement("span");
    idSpan.className = "cited-chip-id";
    idSpan.textContent = citation.skillId;
    chip.append(titleSpan, idSpan);
    chips.appendChild(chip);
  }
  section.appendChild(chips);
  card.appendChild(section);
}

function renderToolResult(payload) {
  const turn = ensureCurrentTurn();
  if (!turn) return;
  let card = turn.cardMap.get(payload.call_id);
  if (!card) {
    turn.counts.calls += 1;
    card = document.createElement("div");
    card.className = "evidence-card";
    card.dataset.callId = payload.call_id;
    turn.body.appendChild(card);
    turn.cardMap.set(payload.call_id, card);
  } else if (turn.counts.pending > 0) {
    turn.counts.pending -= 1;
  }
  const status = payload.status || "error";
  if (Object.prototype.hasOwnProperty.call(turn.counts, status)) {
    turn.counts[status] += 1;
  }
  const evidence = payload.evidence || {};
  let entry = turn.entries.find((item) => item.call_id === payload.call_id);
  if (!entry) {
    entry = {
      call_id: payload.call_id,
      tool: payload.tool_name || payload.call_id,
      status,
      executed_at: null,
      duration_ms: null,
      risk_level: null,
      source_system: null
    };
    turn.entries.push(entry);
  }
  entry.tool = payload.tool_name || entry.tool;
  entry.status = status;
  entry.executed_at = evidence.executed_at || null;
  entry.duration_ms = evidence.duration_ms ?? null;
  entry.risk_level = evidence.risk_level || null;
  entry.source_system = evidence.source_system || null;
  turn.summaryLine.textContent = formatCounts(turn.counts);
  const spinner = card.querySelector(".spinner");
  if (spinner) spinner.remove();
  const badge = card.querySelector(".status-badge");
  if (badge) {
    badge.className = `status-badge ${status}`;
    badge.textContent = status;
  } else {
    const header = card.querySelector(".card-header") || card;
    const newBadge = document.createElement("span");
    newBadge.className = `status-badge ${status}`;
    newBadge.textContent = status;
    header.prepend(newBadge);
  }
  if (!card.querySelector(".tool-name")) {
    const header = card.querySelector(".card-header");
    if (header) {
      const nameSpan = document.createElement("span");
      nameSpan.className = "tool-name";
      nameSpan.textContent = payload.tool_name || payload.call_id;
      header.insertBefore(nameSpan, header.firstChild);
    }
  }
  let metaDiv = card.querySelector(".evidence-meta");
  if (!metaDiv) {
    metaDiv = document.createElement("div");
    metaDiv.className = "evidence-meta";
    card.appendChild(metaDiv);
  }
  const metaParts = [];
  if (evidence.source_system) metaParts.push(`<span>${escapeHtml(evidence.source_system)}</span>`);
  if (evidence.duration_ms != null) metaParts.push(`<span>${evidence.duration_ms}ms</span>`);
  if (evidence.risk_level) metaParts.push(`<span>risk: ${escapeHtml(evidence.risk_level)}</span>`);
  if (evidence.executed_at) metaParts.push(`<span>${escapeHtml(evidence.executed_at)}</span>`);
  metaDiv.innerHTML = metaParts.join("");
  if (payload.error) {
    const errorDiv = document.createElement("div");
    errorDiv.className = "evidence-meta";
    errorDiv.style.color = status === "denied" ? "var(--error)" : "var(--warning)";
    errorDiv.textContent = `${payload.error.code}: ${payload.error.message}`;
    card.appendChild(errorDiv);
  }
  if (payload.data_summary != null) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Data summary";
    details.appendChild(summary);
    const pre = document.createElement("pre");
    pre.textContent = typeof payload.data_summary === "string"
      ? payload.data_summary
      : JSON.stringify(payload.data_summary, null, 2);
    details.appendChild(pre);
    card.appendChild(details);
  }
  renderCitedGuidance(card, payload);
}

// Tool execution card: aggregates what the stream delivered for ONE turn
// only — self-service inspection of one's own session. It is a rendition of
// streamed evidence, not the authoritative backend audit trail. The card is
// rendered inside its turn group, inline after the reply it grounds.
function renderAuditCard(requestId) {
  if (!currentTurn || !currentTurn.group || currentTurn.entries.length === 0) return;
  const turn = currentTurn;
  const card = document.createElement("details");
  card.className = "evidence-card tool-execution-card";
  const summary = document.createElement("summary");
  summary.textContent = `Tool execution · this turn (${turn.entries.length} call${turn.entries.length === 1 ? "" : "s"})`;
  card.appendChild(summary);

  const ids = document.createElement("div");
  ids.className = "evidence-meta";
  const sessionId = sessionIdOutput.textContent;
  ids.innerHTML = `<span>request: ${escapeHtml(requestId)}</span>`
    + (sessionId !== "Not created" ? `<span>session: ${escapeHtml(sessionId)}</span>` : "");
  card.appendChild(ids);

  const table = document.createElement("table");
  const headerCells = ["tool", "status", "executed at", "duration", "risk", "source"];
  table.innerHTML = `<thead><tr>${headerCells.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  for (const entry of turn.entries) {
    const row = document.createElement("tr");
    const cells = [
      entry.tool,
      entry.status,
      entry.executed_at || "—",
      entry.duration_ms != null ? `${entry.duration_ms}ms` : "—",
      entry.risk_level || "—",
      entry.source_system || "—"
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      row.appendChild(td);
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  card.appendChild(table);
  turn.body.prepend(card);
}

function isNearBottom(threshold = 80) {
  if (!chatMain) return true;
  return chatMain.scrollHeight - chatMain.scrollTop - chatMain.clientHeight < threshold;
}

// Sticky smart-scroll: only follow the stream when the reader is already at
// (or near) the bottom. Growing evidence or late deltas must not yank the
// viewport away from text the user is reading.
function scrollToBottom(force = false) {
  if (!chatMain) return;
  if (force || isNearBottom()) {
    chatMain.scrollTop = chatMain.scrollHeight;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

// "Thinking…" placeholder shown while the agent is working before the first
// content event arrives (first-token latency + tool runs can exceed 15s).
function thinkingIndicator() {
  const div = document.createElement("div");
  div.className = "thinking";
  div.innerHTML = '<span class="thinking-dots"><span></span><span></span><span></span></span>'
    + '<span class="thinking-label">Thinking…</span>';
  return div;
}

function removeThinking(thinking) {
  if (thinking && thinking.parentNode) thinking.remove();
}

async function streamPrompt() {
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;

  // Remove placeholder on first message
  const placeholder = responseOutput.querySelector(".chat-placeholder");
  if (placeholder) placeholder.remove();

  // Append user message to chat history
  const userMsg = promptInput.value;
  const userDiv = document.createElement("div");
  userDiv.className = "chat-msg user-msg";
  const userLabel = document.createElement("strong");
  userLabel.textContent = "You: ";
  const userText = document.createElement("span");
  userText.textContent = userMsg;
  userDiv.appendChild(userLabel);
  userDiv.appendChild(userText);
  responseOutput.appendChild(userDiv);

  // Append agent response container
  const agentDiv = document.createElement("div");
  agentDiv.className = "chat-msg agent-msg md-content";
  responseOutput.appendChild(agentDiv);

  // Animated placeholder until the first content event arrives.
  const thinking = thinkingIndicator();
  responseOutput.appendChild(thinking);

  // Turn-scoped evidence/audit state: the group is created lazily on the
  // first tool frame and inserted directly after this reply.
  currentTurn = {
    anchor: agentDiv,
    group: null,
    body: null,
    summaryLine: null,
    counts: { calls: 0, pending: 0, success: 0, error: 0, denied: 0 },
    entries: [],
    cardMap: new Map()
  };

  promptInput.value = "";
  scrollToBottom(true);
  const params = new URLSearchParams({
    message: userMsg,
    user_id: currentAuthenticatedUser() || userInput.value
  });

  if (sessionIdOutput.textContent !== "Not created") {
    params.set("session_id", sessionIdOutput.textContent);
  }

  let streamCompleted = false;
  let accumulatedText = "";
  // Sidebar pulse so other views stay aware the agent is still working.
  chatStreamDot.hidden = false;

  try {
    const response = await fetch(`${currentGateway()}/api/v1/chat/stream?${params.toString()}`, {
      headers: {
        "x-request-id": requestId,
        ...authHeaders()
      }
    });
    if (!response.ok || !response.body) {
      if (response.status === 401) {
        throw new Error("Not authenticated. Please click Login in the sidebar to sign in first.");
      }
      throw new Error(`Stream request failed (${response.status}).`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        if (!event.startsWith("data: ")) continue;
        const payloadText = event.slice(6);
        const payload = JSON.parse(payloadText);
        sessionIdOutput.textContent = payload.session_id || sessionIdOutput.textContent;

        const eventType = streamEventType(payload);
        if (eventType === "tool_call") {
          renderToolCall(payload);
          continue;
        }
        if (eventType === "tool_result") {
          renderToolResult(payload);
          continue;
        }

        if (shouldAppendStreamDelta(payload)) {
          removeThinking(thinking);
          accumulatedText += payload.delta;
          agentDiv.innerHTML = renderMarkdown(accumulatedText);
          scrollToBottom();
        }
        if (!streamCompleted && isStreamComplete(payload)) {
          streamCompleted = true;
        }
      }
    }

    if (!accumulatedText.trim()) {
      agentDiv.innerHTML = '<p style="color: var(--text-muted)"><em>No response received.</em></p>';
    }
    removeThinking(thinking);
    renderAuditCard(requestId);
    currentTurn = null;
  } catch (error) {
    removeThinking(thinking);
    agentDiv.innerHTML = `<p style="color: var(--error)">${escapeHtml(error.message)}</p>`;
    renderAuditCard(requestId);
    currentTurn = null;
  } finally {
    chatStreamDot.hidden = true;
  }
}

// --- Event listeners ---
document.querySelector("#audit-refresh-button").addEventListener("click", () => {
  loadAuditEvents(false).catch((error) => {
    renderError(auditOutput, error);
  });
});

auditMoreButton.addEventListener("click", () => {
  loadAuditEvents(true).catch((error) => {
    renderError(auditOutput, error);
  });
});

document.querySelector("#login-button").addEventListener("click", () => {
  startLogin().catch((error) => {
    renderError(identityOutput, error);
  });
});

document.querySelector("#logout-button").addEventListener("click", () => {
  logout().catch((error) => {
    renderError(identityOutput, error);
  });
});

document.querySelector("#normalize-button").addEventListener("click", () => {
  normalizeIdentity().catch((error) => {
    renderError(identityOutput, error);
  });
});

document.querySelector("#session-button").addEventListener("click", () => {
  createSession().catch((error) => {
    renderError(identityOutput, error);
  });
});

document.querySelector("#send-button").addEventListener("click", () => {
  sendPrompt().catch((error) => {
    renderError(responseOutput, error);
  });
});

document.querySelector("#stream-button").addEventListener("click", () => {
  streamPrompt().catch((error) => {
    renderError(responseOutput, error);
  });
});

// Enter sends the prompt (Shift+Enter inserts a newline).
promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    streamPrompt().catch((error) => {
      renderError(responseOutput, error);
    });
  }
});

completeLoginFromCallback()
  .catch((error) => {
    renderError(identityOutput, error);
  })
  .finally(() => {
    if (authCallbackNavigationPending) {
      return;
    }
    const existingSession = loadAuthSession();
    if (existingSession?.access_token) {
      scheduleTokenRefresh(existingSession);
    }
    refreshAuthenticatedIdentity().catch((error) => {
      renderError(identityOutput, error);
    });
  });
