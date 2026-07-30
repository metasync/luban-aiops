const gatewayInput = document.querySelector("#gateway-url");
const userInput = document.querySelector("#user-id");
const promptInput = document.querySelector("#prompt-input");
const sessionIdOutput = document.querySelector("#session-id");
const requestIdOutput = document.querySelector("#request-id");
const identityOutput = document.querySelector("#identity-output");
const responseOutput = document.querySelector("#response-output");
const AUTH_SESSION_KEY = "luban.portal.authSession";
const AUTH_REQUEST_KEY = "luban.portal.authRequest";
let authCallbackNavigationPending = false;
let refreshTimerId = null;
const REFRESH_MARGIN_SECONDS = 60;

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
    return;
  }
  userInput.removeAttribute("disabled");
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
  target.textContent = error instanceof Error ? error.message : String(error);
}

function shouldAppendStreamDelta(payload) {
  const event = String(payload.event || "").toLowerCase();
  return Boolean(payload.delta) && ["message_delta", "text_block_start", "text_block_delta"].includes(event);
}

function isStreamComplete(payload) {
  const event = String(payload.event || "").toLowerCase();
  return event === "message_end" || event === "reply_end";
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
  responseOutput.textContent = "Signed in.";
  return true;
}

async function logout() {
  const session = loadAuthSession();
  clearAuthSession();
  clearPendingAuthRequest();
  sessionIdOutput.textContent = "Not created";
  responseOutput.textContent = "Signed out.";

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
  responseOutput.textContent = JSON.stringify(payload, null, 2);
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
  responseOutput.textContent = payload.response;
}

async function streamPrompt() {
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;
  responseOutput.textContent = "";

  const params = new URLSearchParams({
    message: promptInput.value,
    user_id: currentAuthenticatedUser() || userInput.value
  });

  if (sessionIdOutput.textContent !== "Not created") {
    params.set("session_id", sessionIdOutput.textContent);
  }

  let streamCompleted = false;
  try {
    const response = await fetch(`${currentGateway()}/api/v1/chat/stream?${params.toString()}`, {
      headers: {
        "x-request-id": requestId,
        ...authHeaders()
      }
    });
    if (!response.ok || !response.body) {
      throw new Error("Stream request failed.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const event of events) {
        if (!event.startsWith("data: ")) {
          continue;
        }
        const payloadText = event.slice(6);
        const payload = JSON.parse(payloadText);
        sessionIdOutput.textContent = payload.session_id || sessionIdOutput.textContent;
        if (shouldAppendStreamDelta(payload)) {
          responseOutput.textContent += payload.delta;
        }
        if (!streamCompleted && isStreamComplete(payload)) {
          streamCompleted = true;
          responseOutput.textContent += "\n\n[stream complete]";
        }
      }
    }
    if (!streamCompleted && !responseOutput.textContent.trim()) {
      responseOutput.textContent = "[stream completed with no visible text]";
    }
  } catch (error) {
    throw error;
  }
}

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
    renderError(responseOutput, error);
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

completeLoginFromCallback()
  .catch((error) => {
    renderError(responseOutput, error);
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
