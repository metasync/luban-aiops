const gatewayInput = document.querySelector("#gateway-url");
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

// Evidence panel state (SPEC-011 R-4).
const evidencePanel = document.querySelector("#evidence-panel");
const evidenceCards = document.querySelector("#evidence-cards");
const evidenceCardMap = new Map();

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

function syncResolvedUser() {
  const authenticatedUser = currentAuthenticatedUser();
  if (authenticatedUser) {
    userInput.value = authenticatedUser;
    userInput.setAttribute("disabled", "disabled");
    identityBadge.textContent = authenticatedUser;
    document.querySelector("#login-button").hidden = true;
    document.querySelector("#logout-button").hidden = false;
    return;
  }
  userInput.removeAttribute("disabled");
  identityBadge.textContent = "Not signed in";
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

function clearEvidencePanel() {
  evidenceCardMap.clear();
  evidenceCards.innerHTML = "";
  evidencePanel.hidden = true;
}

function renderToolCall(payload) {
  evidencePanel.hidden = false;
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
  evidenceCards.appendChild(card);
  evidenceCardMap.set(payload.call_id, card);
}

function renderToolResult(payload) {
  let card = evidenceCardMap.get(payload.call_id);
  if (!card) {
    evidencePanel.hidden = false;
    card = document.createElement("div");
    card.className = "evidence-card";
    card.dataset.callId = payload.call_id;
    evidenceCards.appendChild(card);
    evidenceCardMap.set(payload.call_id, card);
  }
  const status = payload.status || "error";
  const evidence = payload.evidence || {};
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
}

function scrollToBottom() {
  const chatMain = responseOutput.closest(".chat-main");
  if (chatMain) {
    chatMain.scrollTop = chatMain.scrollHeight;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

async function streamPrompt() {
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;
  clearEvidencePanel();

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

  promptInput.value = "";
  scrollToBottom();
  const params = new URLSearchParams({
    message: userMsg,
    user_id: currentAuthenticatedUser() || userInput.value
  });

  if (sessionIdOutput.textContent !== "Not created") {
    params.set("session_id", sessionIdOutput.textContent);
  }

  let streamCompleted = false;
  let accumulatedText = "";

  try {
    const response = await fetch(`${currentGateway()}/api/v1/chat/stream?${params.toString()}`, {
      headers: {
        "x-request-id": requestId,
        ...authHeaders()
      }
    });
    if (!response.ok || !response.body) {
      if (response.status === 401) {
        throw new Error("Not authenticated. Please click Login in the top bar to sign in first.");
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
  } catch (error) {
    agentDiv.innerHTML = `<p style="color: var(--error)">${escapeHtml(error.message)}</p>`;
  }
}

// --- Event listeners ---
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
