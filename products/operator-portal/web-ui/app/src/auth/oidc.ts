// OIDC auth-code flow with silent refresh (ported from legacy app.js).
// The Keycloak round-trip is unchanged: gateway /api/v1/auth/* endpoints
// own PKCE and token exchange; the portal only stores and refreshes.
import { currentGateway, requestJson } from "../api/client";
import {
  clearAuthSession,
  clearPendingAuthRequest,
  loadAuthSession,
  loadPendingAuthRequest,
  saveAuthSession,
  savePendingAuthRequest,
  type AuthSession,
} from "./storage";

const REFRESH_MARGIN_SECONDS = 60;

let refreshTimerId: number | null = null;

export function tokenExpiresInSeconds(token: string): number | null {
  try {
    const payload = JSON.parse(
      atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    if (!payload.exp) return null;
    return payload.exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

export function cancelRefreshTimer(): void {
  if (refreshTimerId !== null) {
    window.clearTimeout(refreshTimerId);
    refreshTimerId = null;
  }
}

export function scheduleTokenRefresh(
  session: AuthSession,
  onRefresh: (session: AuthSession | null) => void,
): void {
  cancelRefreshTimer();
  if (!session?.access_token || !session?.refresh_token) return;
  const remaining = tokenExpiresInSeconds(session.access_token);
  if (remaining === null) return;
  const delayMs = Math.max((remaining - REFRESH_MARGIN_SECONDS) * 1000, 5000);
  refreshTimerId = window.setTimeout(() => {
    silentRefresh(onRefresh).catch(() => onRefresh(null));
  }, delayMs);
}

export async function silentRefresh(
  onRefresh: (session: AuthSession | null) => void,
): Promise<void> {
  const session = loadAuthSession();
  if (!session?.refresh_token) {
    clearAuthSession();
    onRefresh(null);
    return;
  }
  try {
    const refreshed = await requestJson<AuthSession>("/api/v1/auth/refresh", {
      method: "POST",
      body: { refresh_token: session.refresh_token },
    });
    saveAuthSession(refreshed);
    scheduleTokenRefresh(refreshed, onRefresh);
    onRefresh(refreshed);
  } catch {
    clearAuthSession();
    onRefresh(null);
  }
}

export async function startLogin(): Promise<void> {
  const payload = await requestJson<{
    state: string;
    code_verifier: string;
    redirect_uri: string;
    authorization_url: string;
  }>("/api/v1/auth/login");
  savePendingAuthRequest({
    state: payload.state,
    code_verifier: payload.code_verifier,
    redirect_uri: payload.redirect_uri,
  });
  window.location.assign(payload.authorization_url);
}

export function clearAuthCallbackQuery(): boolean {
  const url = new URL(window.location.href);
  for (const key of [
    "code",
    "state",
    "session_state",
    "iss",
    "error",
    "error_description",
  ]) {
    url.searchParams.delete(key);
  }
  if (url.pathname === "/callback") {
    window.location.replace(`${url.origin}/`);
    return true;
  }
  window.history.replaceState(
    {},
    document.title,
    url.pathname + url.search + url.hash,
  );
  return false;
}

/** Handle an OIDC callback in the URL if present. Returns the session on
 *  success, null when no callback is present; throws on state mismatch. */
export async function completeLoginFromCallback(): Promise<AuthSession | null> {
  const url = new URL(window.location.href);
  const authError = url.searchParams.get("error");
  if (authError) {
    clearAuthSession();
    clearPendingAuthRequest();
    clearAuthCallbackQuery();
    throw new Error(
      url.searchParams.get("error_description") || authError,
    );
  }
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  if (!code || !state) {
    if (url.pathname === "/callback") {
      clearAuthCallbackQuery();
    }
    return null;
  }

  const pendingRequest = loadPendingAuthRequest();
  if (!pendingRequest || pendingRequest.state !== state) {
    clearAuthSession();
    clearPendingAuthRequest();
    clearAuthCallbackQuery();
    throw new Error("OIDC state validation failed.");
  }

  const session = await requestJson<AuthSession>("/api/v1/auth/callback", {
    method: "POST",
    body: {
      code,
      code_verifier: pendingRequest.code_verifier,
      redirect_uri: pendingRequest.redirect_uri,
    },
  });
  saveAuthSession(session);
  clearPendingAuthRequest();
  clearAuthCallbackQuery();
  return session;
}

export async function logout(): Promise<void> {
  const session = loadAuthSession();
  clearAuthSession();
  clearPendingAuthRequest();
  cancelRefreshTimer();
  if (!session) return;

  try {
    const payload = await requestJson<{ logout_url: string }>(
      "/api/v1/auth/logout-url",
      {
        method: "POST",
        body: {
          id_token_hint: session.id_token,
          post_logout_redirect_uri: `${currentGateway()}/`,
        },
      },
    );
    window.location.assign(payload.logout_url);
  } catch {
    // The local session is already cleared; a failed IdP redirect just
    // leaves the operator on the signed-out portal.
  }
}

export async function refreshAuthenticatedIdentity(): Promise<AuthSession | null> {
  const session = loadAuthSession();
  if (!session?.access_token) return null;
  try {
    const payload = await requestJson<{
      authenticated: boolean;
      identity?: AuthSession["identity"];
    }>("/api/v1/auth/me", {
      method: "GET",
    });
    if (!payload.authenticated) {
      clearAuthSession();
      return null;
    }
    const refreshed: AuthSession = { ...session, identity: payload.identity };
    saveAuthSession(refreshed);
    return refreshed;
  } catch {
    // Cached identity stays in place until the refresh succeeds again.
    return session.identity ? session : null;
  }
}
