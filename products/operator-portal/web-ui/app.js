const gatewayInput = document.querySelector("#gateway-url");

// Platform version shown as a chip in the sidebar logo row (SPEC-019 R-1);
// must match the root VERSION file (enforced by make validate-version). A
// gateway-served /api/v1/version endpoint is the intended long-term source
// of truth.
const PLATFORM_VERSION = "v0.6.0";
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

// Incident triage view (SPEC-015 R-6): list/detail surfaces over the
// gateway's incident proxy plus the manual intake form. Client-side gating
// is a convenience only — the gateway re-enforces incident:* policy on
// every request.
const incidentsOutput = document.querySelector("#incidents-output");
const incidentsStatus = document.querySelector("#incidents-status");
const incidentsReportToggle = document.querySelector("#incidents-report-toggle");
const incidentsReportForm = document.querySelector("#incidents-report-form");
const INCIDENT_VIEW_ROLES = new Set([
  "platform-admin", "approver", "operator", "developer", "read-only-observer"
]);
const INCIDENT_ACT_ROLES = new Set([
  "platform-admin", "approver", "operator", "developer"
]);
const INCIDENTS_AUTO_REFRESH_SECONDS = 15;
let incidentsMode = "list"; // "list" | "detail"
let incidentsDetailId = null;
let incidentsAutoRefreshId = null;
// Guards Refresh racing the auto-refresh tick into duplicate renders.
let incidentsLoadInFlight = false;

// Permissions view (SPEC-019 R-3): renders the live role x action matrix
// from the gateway's /api/v1/policy/matrix endpoint. Rows arrive scoped
// server-side; the view displays them verbatim. Sign-in-gated: every signed
// role holds policy:read, so the entry hides only when signed out. The
// gateway re-enforces policy:read on every request regardless.
const permissionsOutput = document.querySelector("#permissions-output");
const permissionsStatus = document.querySelector("#permissions-status");

// Workspace resource views (SPEC-019 R-4): read-only Tools and Skills
// inventories over gateway proxies. Same gating posture as Permissions:
// sign-in-gated entries, server re-enforcement on tools:list / skills:read.
const toolsOutput = document.querySelector("#tools-output");
const toolsStatus = document.querySelector("#tools-status");
const skillsOutput = document.querySelector("#skills-output");
const skillsStatus = document.querySelector("#skills-status");

// --- View navigation (sidebar → main area) ---
// Views are hidden, never destroyed, so chat history, session state, and
// loaded audit rows survive navigation.
const VIEWS = {
  chat: { nav: document.querySelector("#nav-chat"), section: document.querySelector("#chat-view") },
  settings: { nav: document.querySelector("#nav-settings"), section: document.querySelector("#settings-view") },
  incidents: { nav: document.querySelector("#nav-incidents"), section: document.querySelector("#incidents-view") },
  audit: { nav: document.querySelector("#nav-audit"), section: document.querySelector("#audit-view") },
  permissions: { nav: document.querySelector("#nav-permissions"), section: document.querySelector("#permissions-view") },
  tools: { nav: document.querySelector("#nav-tools"), section: document.querySelector("#tools-view") },
  skills: { nav: document.querySelector("#nav-skills"), section: document.querySelector("#skills-view") }
};
let activeViewId = "chat";

// Section wrappers (SPEC-019 R-1): a header hides automatically when every
// entry in its section is hidden.
const NAV_SECTIONS = {
  control: {
    container: document.querySelector("#nav-section-control"),
    entries: ["incidents", "audit", "permissions"]
  },
  workspace: {
    container: document.querySelector("#nav-section-workspace"),
    entries: ["tools", "skills", "settings"]
  }
};

function syncNavSectionVisibility() {
  for (const section of Object.values(NAV_SECTIONS)) {
    section.container.hidden = section.entries.every((id) => VIEWS[id].nav.hidden);
  }
}

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
  // Incidents: every activation returns to the list and lazy-loads it; the
  // auto-refresh keeps statuses fresh while the view stays open (triage
  // flips them asynchronously) and stops as soon as another view opens.
  if (viewId === "incidents") {
    incidentsMode = "list";
    incidentsDetailId = null;
    loadIncidentsList().catch((error) => {
      renderError(incidentsOutput, error);
    });
    startIncidentsAutoRefresh();
  } else {
    stopIncidentsAutoRefresh();
  }
  // Transparency and inventory views lazy-load on every activation so the
  // rendered state tracks the live policy bundle and workspace resources.
  if (viewId === "permissions") {
    loadPolicyMatrix().catch((error) => {
      renderError(permissionsOutput, error);
    });
  }
  if (viewId === "tools") {
    loadToolsCatalog().catch((error) => {
      renderError(toolsOutput, error);
    });
  }
  if (viewId === "skills") {
    loadSkillsInventory().catch((error) => {
      renderError(skillsOutput, error);
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

function canViewIncidents() {
  return currentRoles().some((role) => INCIDENT_VIEW_ROLES.has(role));
}

// Reporting and triage need the write vocabulary (incident:create /
// incident:triage); read-only-observer can look but not act.
function canActOnIncidents() {
  return currentRoles().some((role) => INCIDENT_ACT_ROLES.has(role));
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
  const incidentsAllowed = canViewIncidents();
  VIEWS.incidents.nav.hidden = !incidentsAllowed;
  incidentsReportToggle.hidden = !canActOnIncidents();
  if (!incidentsAllowed && activeViewId === "incidents") {
    showView("chat");
  }
  // Permissions/Tools/Skills are granted to all five roles, so the signed-in
  // session itself is the gate (SPEC-019 R-1); the server re-enforces
  // policy:read / tools:list / skills:read on every request regardless.
  const signedIn = Boolean(authenticatedUser);
  for (const viewId of ["permissions", "tools", "skills"]) {
    VIEWS[viewId].nav.hidden = !signedIn;
    if (!signedIn && activeViewId === viewId) {
      showView("chat");
    }
  }
  syncNavSectionVisibility();
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

// --- Permissions view (SPEC-019 R-3) ---
async function loadPolicyMatrix() {
  if (!currentAuthenticatedUser()) return;
  const payload = await requestJson("/api/v1/policy/matrix", { method: "GET" });
  renderPolicyMatrix(payload);
}

function renderPolicyMatrix(payload) {
  permissionsOutput.innerHTML = "";
  const meta = document.createElement("p");
  meta.className = "permissions-meta";
  meta.textContent =
    `Policy bundle v${payload.version} \u00b7 ${payload.source} \u00b7 scope: ${payload.scope}`;
  permissionsOutput.appendChild(meta);

  const actions = payload.actions || [];
  const table = document.createElement("table");
  table.className = "audit-table policy-matrix-table";
  const headRow = document.createElement("tr");
  const roleHeader = document.createElement("th");
  roleHeader.textContent = "role";
  headRow.appendChild(roleHeader);
  for (const action of actions) {
    const th = document.createElement("th");
    th.textContent = action;
    headRow.appendChild(th);
  }
  const thead = document.createElement("thead");
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (const role of payload.roles || []) {
    const row = document.createElement("tr");
    const roleCell = document.createElement("td");
    roleCell.textContent = role;
    row.appendChild(roleCell);
    for (const action of actions) {
      const cell = document.createElement("td");
      const allowed = Boolean(payload.matrix?.[role]?.[action]);
      const badge = document.createElement("span");
      badge.className = `status-badge ${allowed ? "success" : "denied"}`;
      badge.textContent = allowed ? "allow" : "deny";
      cell.appendChild(badge);
      row.appendChild(cell);
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  permissionsOutput.appendChild(table);
  const rows = (payload.roles || []).length;
  permissionsStatus.textContent =
    `${rows} role${rows === 1 ? "" : "s"} \u00d7 ${actions.length} actions \u00b7 evaluated from the enforced bundle`;
}

// --- Tools catalog view (SPEC-019 R-4) ---
async function loadToolsCatalog() {
  if (!currentAuthenticatedUser()) return;
  const payload = await requestJson("/api/v1/tools", { method: "GET" });
  renderToolsCatalog(Array.isArray(payload) ? payload : []);
}

function renderToolsCatalog(tools) {
  toolsOutput.innerHTML = "";
  if (tools.length === 0) {
    toolsOutput.innerHTML = '<p class="chat-placeholder">No tools are registered in this workspace.</p>';
    toolsStatus.textContent = "";
    return;
  }
  const table = document.createElement("table");
  table.className = "audit-table tools-table";
  const headers = ["name", "description", "category", "risk"];
  table.innerHTML = `<thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  for (const tool of tools) {
    const row = document.createElement("tr");
    for (const value of [tool.name, tool.description, tool.category, tool.risk_level]) {
      const td = document.createElement("td");
      td.textContent = value ?? "\u2014";
      row.appendChild(td);
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  toolsOutput.appendChild(table);
  toolsStatus.textContent =
    `${tools.length} tool${tools.length === 1 ? "" : "s"} registered \u00b7 read-only catalog`;
}

// --- Skills inventory view (SPEC-019 R-4) ---
function buildSkillsQuery() {
  const params = new URLSearchParams({ limit: "100" });
  const source = document.querySelector("#skills-filter-source").value.trim();
  const tag = document.querySelector("#skills-filter-tag").value.trim();
  if (source) params.set("source", source);
  if (tag) params.set("tag", tag);
  return params.toString();
}

async function loadSkillsInventory() {
  if (!currentAuthenticatedUser()) return;
  const payload = await requestJson(`/api/v1/skills?${buildSkillsQuery()}`, { method: "GET" });
  renderSkillsInventory(payload.skills || [], payload.total || 0);
}

function renderSkillsInventory(skills, total) {
  skillsOutput.innerHTML = "";
  if (skills.length === 0) {
    skillsOutput.innerHTML = '<p class="chat-placeholder">No skills match these filters.</p>';
    skillsStatus.textContent = "";
    return;
  }
  const table = document.createElement("table");
  table.className = "audit-table";
  const headers = ["title", "source", "tags", "version", "updated"];
  table.innerHTML = `<thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  for (const skill of skills) {
    const row = document.createElement("tr");
    const cells = [
      skill.title || skill.skill_id,
      skill.source_id || "\u2014",
      (skill.tags || []).join(", ") || "\u2014",
      skill.version || "\u2014",
      formatAuditTimestamp(skill.updated_at)
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      row.appendChild(td);
    }
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  skillsOutput.appendChild(table);
  skillsStatus.textContent =
    `${skills.length} skill${skills.length === 1 ? "" : "s"} shown \u00b7 ${total} total`;
}

// --- Incident triage view (SPEC-015 R-6) ---
function setIncidentsStatus(text, isError = false) {
  incidentsStatus.textContent = text;
  incidentsStatus.style.color = isError ? "var(--error)" : "";
}

function startIncidentsAutoRefresh() {
  stopIncidentsAutoRefresh();
  incidentsAutoRefreshId = setInterval(() => {
    if (activeViewId !== "incidents" || incidentsMode !== "list") return;
    loadIncidentsList().catch((error) => setIncidentsStatus(error.message, true));
  }, INCIDENTS_AUTO_REFRESH_SECONDS * 1000);
}

function stopIncidentsAutoRefresh() {
  if (incidentsAutoRefreshId !== null) {
    clearInterval(incidentsAutoRefreshId);
    incidentsAutoRefreshId = null;
  }
}

function buildIncidentsQuery() {
  const params = new URLSearchParams({ limit: "50" });
  const status = document.querySelector("#incidents-filter-status").value;
  const severity = document.querySelector("#incidents-filter-severity").value;
  const source = document.querySelector("#incidents-filter-source").value;
  if (status) params.set("status", status);
  if (severity) params.set("severity", severity);
  if (source) params.set("source", source);
  return params.toString();
}

async function loadIncidentsList() {
  if (!canViewIncidents() || incidentsLoadInFlight) return;
  incidentsLoadInFlight = true;
  try {
    const payload = await requestJson(`/api/v1/incidents?${buildIncidentsQuery()}`, { method: "GET" });
    incidentsMode = "list";
    incidentsDetailId = null;
    renderIncidentsList(payload.incidents || []);
    const shown = (payload.incidents || []).length;
    setIncidentsStatus(`${shown} incident${shown === 1 ? "" : "s"} shown \u00b7 ${payload.total} total`);
  } finally {
    incidentsLoadInFlight = false;
  }
}

// Shared badge builder: .status-badge carries the shape, the kind prefix
// (sev/st/src/dsp/prio) picks the semantic color in styles.css.
function incidentBadge(value, kind) {
  const span = document.createElement("span");
  span.className = `status-badge ${kind}-${value}`;
  span.textContent = value;
  return span;
}

function renderIncidentsList(incidents) {
  incidentsOutput.innerHTML = "";
  if (incidents.length === 0) {
    incidentsOutput.innerHTML = '<p class="chat-placeholder">No incidents match these filters.</p>';
    return;
  }
  const table = document.createElement("table");
  table.className = "audit-table";
  const headers = ["opened", "title", "severity", "status", "source", "id"];
  table.innerHTML = `<thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>`;
  const tbody = document.createElement("tbody");
  for (const incident of incidents) {
    const row = document.createElement("tr");
    row.className = "incident-row";
    const cells = [
      formatAuditTimestamp(incident.created_at),
      incident.title,
      incidentBadge(incident.severity, "sev"),
      incidentBadge(incident.status, "st"),
      incident.source,
      incident.incident_id
    ];
    for (const value of cells) {
      const td = document.createElement("td");
      if (typeof value === "string") td.textContent = value;
      else td.appendChild(value);
      row.appendChild(td);
    }
    row.addEventListener("click", () => {
      openIncidentDetail(incident.incident_id).catch((error) => {
        setIncidentsStatus(error.message, true);
      });
    });
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  incidentsOutput.appendChild(table);
}

async function openIncidentDetail(incidentId) {
  const payload = await requestJson(`/api/v1/incidents/${incidentId}`, { method: "GET" });
  incidentsMode = "detail";
  incidentsDetailId = incidentId;
  renderIncidentDetail(payload);
  setIncidentsStatus(`incident ${incidentId}`);
}

function renderIncidentDetail(payload) {
  const { incident, report, dispatches } = payload;
  incidentsOutput.innerHTML = "";
  const detail = document.createElement("div");
  detail.className = "incident-detail";

  const back = document.createElement("button");
  back.type = "button";
  back.className = "btn-sm";
  back.textContent = "\u2190 All incidents";
  back.addEventListener("click", () => {
    loadIncidentsList().catch((error) => renderError(incidentsOutput, error));
    startIncidentsAutoRefresh();
  });
  detail.appendChild(back);

  const header = document.createElement("div");
  header.className = "incident-detail-header";
  const title = document.createElement("h3");
  title.textContent = incident.title;
  const badges = document.createElement("div");
  badges.className = "incident-badges";
  badges.append(
    incidentBadge(incident.severity, "sev"),
    incidentBadge(incident.status, "st"),
    incidentBadge(incident.source, "src")
  );
  header.append(title, badges);
  detail.appendChild(header);

  const meta = document.createElement("div");
  meta.className = "evidence-meta incident-meta";
  const metaParts = [
    `id: ${incident.incident_id}`,
    `fingerprint: ${incident.fingerprint}`,
    `opened: ${formatAuditTimestamp(incident.created_at)}`,
    `updated: ${formatAuditTimestamp(incident.updated_at)}`
  ];
  if (incident.reported_by) metaParts.push(`reported by: ${incident.reported_by}`);
  if (incident.resolved_at) metaParts.push(`resolved: ${formatAuditTimestamp(incident.resolved_at)}`);
  meta.innerHTML = metaParts.map((part) => `<span>${escapeHtml(part)}</span>`).join("");
  detail.appendChild(meta);

  if (incident.labels && Object.keys(incident.labels).length > 0) {
    const chips = document.createElement("div");
    chips.className = "cited-chips incident-labels";
    for (const [key, value] of Object.entries(incident.labels)) {
      const chip = document.createElement("span");
      chip.className = "cited-chip";
      chip.textContent = `${key}=${value}`;
      chips.appendChild(chip);
    }
    detail.appendChild(chips);
  }

  if (incident.summary) {
    const summary = document.createElement("p");
    summary.className = "incident-summary";
    summary.textContent = incident.summary;
    detail.appendChild(summary);
  }

  // Actions: triage is operator-initiated and gated to write roles; the
  // chat deep-link opens the chat view on the incident's triage session.
  const actions = document.createElement("div");
  actions.className = "incident-actions";
  if (canActOnIncidents()) {
    const triageButton = document.createElement("button");
    triageButton.type = "button";
    triageButton.className = "btn-sm";
    triageButton.textContent = report ? "Re-run triage" : "Run triage";
    triageButton.disabled = incident.status === "triaging";
    triageButton.addEventListener("click", () => {
      runIncidentTriage(incident.incident_id, triageButton);
    });
    actions.appendChild(triageButton);
  }
  const chatButton = document.createElement("button");
  chatButton.type = "button";
  chatButton.className = "btn-sm";
  chatButton.textContent = "Continue in chat";
  chatButton.addEventListener("click", () => {
    sessionIdOutput.textContent = incident.session_id || `incident-${incident.incident_id}`;
    showView("chat");
  });
  actions.appendChild(chatButton);
  detail.appendChild(actions);

  if (report) {
    detail.appendChild(renderTriageReport(report));
  } else if (incident.status === "triage_failed" && incident.triage_raw) {
    // Failed triage keeps the raw agent output for inspection.
    const raw = document.createElement("details");
    raw.className = "incident-raw";
    const rawSummary = document.createElement("summary");
    rawSummary.textContent = "Raw triage output (validation failed)";
    const pre = document.createElement("pre");
    pre.textContent = incident.triage_raw;
    raw.append(rawSummary, pre);
    detail.appendChild(raw);
  } else if (incident.status === "new") {
    const hint = document.createElement("p");
    hint.className = "chat-placeholder";
    hint.textContent = "No triage report yet \u2014 run triage to let the agent gather evidence.";
    detail.appendChild(hint);
  }

  detail.appendChild(renderDispatches(dispatches || []));
  incidentsOutput.appendChild(detail);
}

function incidentListSection(headingText, items) {
  const block = document.createElement("div");
  const heading = document.createElement("h4");
  heading.textContent = headingText;
  block.appendChild(heading);
  const list = document.createElement("ul");
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  }
  block.appendChild(list);
  return block;
}

function renderTriageReport(report) {
  const section = document.createElement("div");
  section.className = "incident-section";
  const heading = document.createElement("h3");
  heading.textContent = "Triage report";
  section.appendChild(heading);

  const reportHead = document.createElement("div");
  reportHead.className = "incident-report-head";
  reportHead.appendChild(incidentBadge(report.severity_assessment, "sev"));
  const byLine = document.createElement("span");
  byLine.className = "audit-status";
  byLine.textContent = `${report.generated_by} \u00b7 ${formatAuditTimestamp(report.generated_at)} \u00b7 session ${report.session_id}`;
  reportHead.appendChild(byLine);
  section.appendChild(reportHead);

  const summary = document.createElement("div");
  summary.className = "md-content";
  summary.innerHTML = renderMarkdown(report.summary);
  section.appendChild(summary);

  if ((report.evidence || []).length > 0) {
    section.appendChild(incidentListSection(
      "Evidence",
      report.evidence.map((ref) => `${ref.source}: ${ref.description}`)
    ));
  }
  if ((report.hypotheses || []).length > 0) {
    section.appendChild(incidentListSection("Hypotheses", report.hypotheses));
  }
  if ((report.next_steps || []).length > 0) {
    const steps = document.createElement("div");
    const label = document.createElement("h4");
    label.textContent = "Next steps (advisory)";
    steps.appendChild(label);
    const list = document.createElement("ol");
    for (const step of report.next_steps) {
      const item = document.createElement("li");
      const titleSpan = document.createElement("strong");
      titleSpan.textContent = step.title;
      item.append(titleSpan, " ", incidentBadge(step.priority, "prio"));
      const rationale = document.createElement("p");
      rationale.textContent = step.rationale;
      item.appendChild(rationale);
      list.appendChild(item);
    }
    steps.appendChild(list);
    section.appendChild(steps);
  }
  if ((report.skills_cited || []).length > 0) {
    const cited = document.createElement("div");
    const label = document.createElement("h4");
    label.textContent = "Cited guidance";
    cited.appendChild(label);
    const chips = document.createElement("div");
    chips.className = "cited-chips";
    for (const skillId of report.skills_cited) {
      const chip = document.createElement("span");
      chip.className = "cited-chip";
      chip.textContent = skillId;
      chips.appendChild(chip);
    }
    cited.appendChild(chips);
    section.appendChild(cited);
  }
  return section;
}

function renderDispatches(dispatches) {
  const section = document.createElement("div");
  section.className = "incident-section";
  const heading = document.createElement("h3");
  heading.textContent = "Connector dispatch";
  section.appendChild(heading);
  if (dispatches.length === 0) {
    const empty = document.createElement("p");
    empty.className = "audit-status";
    empty.textContent = "No connector dispatches yet.";
    section.appendChild(empty);
    return section;
  }
  const table = document.createElement("table");
  table.className = "audit-table";
  table.innerHTML = "<thead><tr><th>connector</th><th>status</th><th>reference</th><th>dispatched</th></tr></thead>";
  const tbody = document.createElement("tbody");
  for (const dispatch of dispatches) {
    const row = document.createElement("tr");
    const connector = document.createElement("td");
    connector.textContent = dispatch.connector;
    const status = document.createElement("td");
    status.appendChild(incidentBadge(dispatch.status, "dsp"));
    if (dispatch.status === "failed" && dispatch.error) status.title = dispatch.error;
    const reference = document.createElement("td");
    reference.textContent = dispatch.reference || "\u2014";
    const at = document.createElement("td");
    at.textContent = formatAuditTimestamp(dispatch.created_at);
    row.append(connector, status, reference, at);
    tbody.appendChild(row);
  }
  table.appendChild(tbody);
  section.appendChild(table);
  return section;
}

// Triage runs the full delegated chain through the gateway (operator
// identity + delegated bearer); the call blocks until the agent turn and
// connector dispatches complete, so the button stays disabled in flight.
async function runIncidentTriage(incidentId, button) {
  button.disabled = true;
  const originalLabel = button.textContent;
  button.textContent = "Triaging\u2026";
  setIncidentsStatus(`running triage for ${incidentId}\u2026`);
  try {
    const payload = await requestJson(`/api/v1/incidents/${incidentId}/triage`, { method: "POST" });
    renderIncidentDetail(payload);
    setIncidentsStatus(`incident ${incidentId} \u00b7 triage ${payload.incident.status}`);
  } catch (error) {
    button.disabled = false;
    button.textContent = originalLabel;
    setIncidentsStatus(error.message, true);
  }
}

// Labels input is "key=value, key2=value2"; empty entries are skipped and
// anything without a non-empty key is a client-side rejection.
function parseLabelsInput(raw) {
  const labels = {};
  for (const part of raw.split(",")) {
    const entry = part.trim();
    if (!entry) continue;
    const separator = entry.indexOf("=");
    if (separator <= 0) throw new Error("Labels must be key=value pairs.");
    labels[entry.slice(0, separator).trim()] = entry.slice(separator + 1).trim();
  }
  return labels;
}

async function submitIncidentReport(event) {
  event.preventDefault();
  const statusLine = document.querySelector("#incidents-report-status");
  const submitButton = document.querySelector("#incidents-report-submit");
  try {
    const labels = parseLabelsInput(document.querySelector("#incidents-report-labels").value);
    submitButton.disabled = true;
    statusLine.textContent = "Reporting\u2026";
    const created = await requestJson("/api/v1/incidents", {
      method: "POST",
      body: JSON.stringify({
        title: document.querySelector("#incidents-report-title").value.trim(),
        summary: document.querySelector("#incidents-report-summary").value.trim(),
        severity: document.querySelector("#incidents-report-severity").value,
        labels
      })
    });
    incidentsReportForm.hidden = true;
    incidentsReportForm.reset();
    statusLine.textContent = "";
    await openIncidentDetail(created.incident_id);
  } catch (error) {
    statusLine.textContent = error.message;
  } finally {
    submitButton.disabled = false;
  }
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
  if (payload.data != null) {
    // Stream schema v5: the frame carries the full tool payload within
    // the size cap — surface it verbatim so operators can inspect the
    // complete output (e.g. full log lines) regardless of how the model
    // phrases its reply.
    const details = document.createElement("details");
    details.className = "evidence-full-output";
    const summary = document.createElement("summary");
    summary.textContent = "Show full output";
    details.appendChild(summary);
    appendFullOutputBody(details, payload.data);
    card.appendChild(details);
  } else if (payload.data_summary != null) {
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

// Readable full-output rendition: multi-line text fields (e.g. the
// `logs` blob from k8s.get_pod_logs) are lifted out of the JSON envelope
// and shown as raw text blocks; the remaining fields surface as a compact
// meta line, with any structured leftovers pretty-printed afterwards.
function appendFullOutputBody(container, data) {
  if (typeof data === "string") {
    const pre = document.createElement("pre");
    pre.textContent = data;
    container.appendChild(pre);
    return;
  }
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const textFields = [];
    const rest = {};
    for (const [key, value] of Object.entries(data)) {
      if (typeof value === "string" && value.includes("\n")) {
        textFields.push([key, value]);
      } else {
        rest[key] = value;
      }
    }
    if (textFields.length > 0) {
      for (const [key, value] of textFields) {
        const label = document.createElement("div");
        label.className = "evidence-output-label";
        label.textContent = key;
        container.appendChild(label);
        const pre = document.createElement("pre");
        pre.textContent = value;
        container.appendChild(pre);
      }
      const restEntries = Object.entries(rest);
      if (restEntries.length > 0) {
        const scalars = restEntries.filter(
          ([, value]) => typeof value !== "object" || value === null
        );
        const structured = restEntries.filter(
          ([, value]) => typeof value === "object" && value !== null
        );
        if (scalars.length > 0) {
          const meta = document.createElement("div");
          meta.className = "evidence-meta";
          meta.innerHTML = scalars
            .map(([key, value]) => `<span>${escapeHtml(key)}: ${escapeHtml(String(value))}</span>`)
            .join("");
          container.appendChild(meta);
        }
        for (const [key, value] of structured) {
          const label = document.createElement("div");
          label.className = "evidence-output-label";
          label.textContent = key;
          container.appendChild(label);
          const pre = document.createElement("pre");
          pre.textContent = JSON.stringify(value, null, 2);
          container.appendChild(pre);
        }
      }
      return;
    }
  }
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(data, null, 2);
  container.appendChild(pre);
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

// --- HITL confirmation card (SPEC-020 R-4) ---
// The kernel parks an ASK-gated tool batch and the stream surfaces a
// confirmation_request frame; this renders the inline approval card and
// resumes the reply from the confirm response. Button visibility is a
// client convenience only — the gateway re-enforces chat:confirm.
const CHAT_CONFIRM_ROLES = new Set([
  "platform-admin", "approver", "operator", "developer"
]);

function canConfirmTools() {
  return currentRoles().some((role) => CHAT_CONFIRM_ROLES.has(role));
}

function findConfirmationCard(confirmId) {
  if (!confirmId) return null;
  return document.querySelector(`.confirm-card[data-confirm-id="${CSS.escape(confirmId)}"]`);
}

function renderConfirmationRequest(payload, agentDiv, parkedTurn, textSink) {
  const card = document.createElement("div");
  card.className = "confirm-card";
  card.dataset.confirmId = payload.confirm_id || "";

  const header = document.createElement("div");
  header.className = "confirm-card-header";
  header.innerHTML = '<span class="confirm-card-title">Tool confirmation required</span>'
    + '<span class="status-badge pending">awaiting decision</span>';
  card.appendChild(header);

  const message = document.createElement("p");
  message.className = "confirm-card-message";
  message.textContent = payload.message || "Tool execution requires your confirmation.";
  card.appendChild(message);

  for (const call of payload.pending_calls || []) {
    const callDetails = document.createElement("details");
    callDetails.className = "confirm-call";
    callDetails.innerHTML =
      `<summary><span class="tool-name">${escapeHtml(call.tool_name || call.call_id || "tool")}</span></summary>`
      + `<pre>${escapeHtml(JSON.stringify(call.parameters || {}, null, 2))}</pre>`;
    card.appendChild(callDetails);
  }

  const actions = document.createElement("div");
  actions.className = "confirm-card-actions";
  const statusLine = document.createElement("div");
  statusLine.className = "confirm-card-status";
  if (canConfirmTools()) {
    const approveButton = document.createElement("button");
    approveButton.className = "confirm-approve";
    approveButton.textContent = "Approve";
    const denyButton = document.createElement("button");
    denyButton.className = "confirm-deny";
    denyButton.textContent = "Deny";
    const decide = (decision) => {
      sendConfirmation(card, payload.confirm_id, decision, parkedTurn, textSink)
        .catch((error) => {
          statusLine.textContent = error.message;
        });
    };
    approveButton.addEventListener("click", () => decide("approve"));
    denyButton.addEventListener("click", () => decide("deny"));
    actions.append(approveButton, denyButton);
  } else {
    statusLine.textContent = "Your role cannot approve or deny tool confirmations.";
  }
  card.append(actions, statusLine);
  agentDiv.after(card);
  return card;
}

function lockConfirmationCard(card, status, note) {
  if (!card || card.dataset.locked === "true") return;
  card.dataset.locked = "true";
  const badge = card.querySelector(".status-badge");
  if (badge) {
    const badgeClass = status === "approved" ? "success"
      : status === "denied" ? "denied" : "error";
    badge.className = `status-badge ${badgeClass}`;
    badge.textContent = status || "resolved";
  }
  for (const button of card.querySelectorAll("button")) button.disabled = true;
  // The in-progress line ("Approving…"/"Denying…") must always be
  // replaced once the decision is applied; callers only pass a note for
  // out-of-band outcomes (expiry, transport errors).
  const statusLine = card.querySelector(".confirm-card-status");
  if (statusLine) {
    const finalNotes = {
      approved: "Approved — the parked reply resumed.",
      denied: "Denied — the refusal was reported to the agent.",
      expired: "This confirmation expired before a decision was applied."
    };
    statusLine.textContent = note || finalNotes[status] || `Confirmation ${status || "resolved"}.`;
  }
}

async function sendConfirmation(card, confirmId, decision, parkedTurn, textSink) {
  const sessionId = sessionIdOutput.textContent;
  if (sessionId === "Not created") {
    throw new Error("No active session for this confirmation.");
  }
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;
  for (const button of card.querySelectorAll("button")) button.disabled = true;
  const statusLine = card.querySelector(".confirm-card-status");
  statusLine.textContent = decision === "approve" ? "Approving…" : "Denying…";

  const response = await fetch(`${currentGateway()}/api/v1/chat/confirm`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-request-id": requestId,
      ...authHeaders()
    },
    body: JSON.stringify({ session_id: sessionId, confirm_id: confirmId, decision })
  });
  if (response.status === 410) {
    lockConfirmationCard(
      card, "expired", "This confirmation expired before a decision was applied."
    );
    return;
  }
  if (!response.ok || !response.body) {
    statusLine.textContent = `Confirm request failed (${response.status}).`;
    for (const button of card.querySelectorAll("button")) button.disabled = false;
    return;
  }

  // The response IS the resumed SSE stream. Restore the parked turn's
  // evidence context so tool frames from the resumed reply attach to the
  // same turn group, then drive it through the chat frame parser.
  currentTurn = parkedTurn;
  chatStreamDot.hidden = false;
  try {
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
        const payload = JSON.parse(event.slice(6));
        sessionIdOutput.textContent = payload.session_id || sessionIdOutput.textContent;
        const eventType = streamEventType(payload);
        if (eventType === "confirmation_result") {
          lockConfirmationCard(card, payload.status);
          continue;
        }
        if (eventType === "error") {
          // Mid-stream guard (e.g. owner mismatch) — the stream ends
          // without a confirmation_result, so lock the card explicitly
          // instead of leaving it on "Approving…/Denying…".
          lockConfirmationCard(
            card, "error",
            (payload.error && payload.error.message) || payload.message
              || "The confirmation failed."
          );
          continue;
        }
        // A resumed turn can park again on another ASK-gated tool.
        if (eventType === "confirmation_request") {
          renderConfirmationRequest(payload, card, parkedTurn, textSink);
          continue;
        }
        if (eventType === "tool_call") {
          renderToolCall(payload);
          continue;
        }
        if (eventType === "tool_result") {
          renderToolResult(payload);
          continue;
        }
        if (shouldAppendStreamDelta(payload)) {
          textSink.append(payload.delta);
        }
      }
    }
    // Guarantee a final card state even when the stream ends without a
    // confirmation_result (truncated stream, upstream outage).
    if (card.dataset.locked !== "true") {
      lockConfirmationCard(
        card, "error", "The confirmation stream ended unexpectedly."
      );
    }
    renderAuditCard(requestId);
  } finally {
    chatStreamDot.hidden = true;
    currentTurn = null;
  }
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
  // A parked confirmation ends the stream without message_end; suppress the
  // "No response received" placeholder so the approval card speaks instead.
  let confirmationPending = false;
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
        if (eventType === "confirmation_request") {
          // SPEC-020 R-4: the kernel parked an ASK-gated tool call. Render
          // the inline approval card and end this stream without the
          // no-response placeholder; the confirm response resumes the reply.
          removeThinking(thinking);
          confirmationPending = true;
          renderConfirmationRequest(payload, agentDiv, currentTurn, {
            append: (delta) => {
              removeThinking(thinking);
              accumulatedText += delta;
              agentDiv.innerHTML = renderMarkdown(accumulatedText);
              scrollToBottom();
            }
          });
          continue;
        }
        if (eventType === "confirmation_result") {
          lockConfirmationCard(
            findConfirmationCard(payload.confirm_id), payload.status
          );
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

    if (!accumulatedText.trim() && !confirmationPending) {
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

document.querySelector("#incidents-refresh-button").addEventListener("click", () => {
  if (incidentsMode === "detail" && incidentsDetailId) {
    openIncidentDetail(incidentsDetailId).catch((error) => {
      setIncidentsStatus(error.message, true);
    });
    return;
  }
  loadIncidentsList().catch((error) => {
    renderError(incidentsOutput, error);
  });
});

// Filter changes always re-query the list, whatever the current mode.
for (const filterId of ["#incidents-filter-status", "#incidents-filter-severity", "#incidents-filter-source"]) {
  document.querySelector(filterId).addEventListener("change", () => {
    loadIncidentsList().catch((error) => {
      renderError(incidentsOutput, error);
    });
  });
}

// Transparency and workspace inventory surfaces (SPEC-019 R-3/R-4).
document.querySelector("#permissions-refresh-button").addEventListener("click", () => {
  loadPolicyMatrix().catch((error) => {
    renderError(permissionsOutput, error);
  });
});

document.querySelector("#tools-refresh-button").addEventListener("click", () => {
  loadToolsCatalog().catch((error) => {
    renderError(toolsOutput, error);
  });
});

document.querySelector("#skills-refresh-button").addEventListener("click", () => {
  loadSkillsInventory().catch((error) => {
    renderError(skillsOutput, error);
  });
});

for (const filterId of ["#skills-filter-source", "#skills-filter-tag"]) {
  document.querySelector(filterId).addEventListener("change", () => {
    loadSkillsInventory().catch((error) => {
      renderError(skillsOutput, error);
    });
  });
}

incidentsReportToggle.addEventListener("click", () => {
  incidentsReportForm.hidden = !incidentsReportForm.hidden;
});

document.querySelector("#incidents-report-cancel").addEventListener("click", () => {
  incidentsReportForm.hidden = true;
});

incidentsReportForm.addEventListener("submit", (event) => {
  submitIncidentReport(event);
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
