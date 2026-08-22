// Auth session storage (ported from legacy app.js). sessionStorage keeps
// the session per-tab, matching the legacy behavior and the SPEC-023 R-3
// per-tab active-session persistence posture.

export const AUTH_SESSION_KEY = "luban.portal.authSession";
export const AUTH_REQUEST_KEY = "luban.portal.authRequest";

export interface AuthIdentity {
  username: string;
  subject?: string;
  roles: string[];
  groups?: string[];
}

export interface AuthSession {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
  identity?: AuthIdentity;
}

export interface PendingAuthRequest {
  state: string;
  code_verifier: string;
  redirect_uri: string;
}

// Guarded parse: a corrupt or hand-edited stored value must degrade to
// "absent", never throw mid-render or mid-login.
function parseStored<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function loadAuthSession(): AuthSession | null {
  return parseStored<AuthSession>(window.sessionStorage.getItem(AUTH_SESSION_KEY));
}

export function saveAuthSession(session: AuthSession): void {
  window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session));
}

export function clearAuthSession(): void {
  window.sessionStorage.removeItem(AUTH_SESSION_KEY);
}

export function loadPendingAuthRequest(): PendingAuthRequest | null {
  return parseStored<PendingAuthRequest>(
    window.sessionStorage.getItem(AUTH_REQUEST_KEY),
  );
}

export function savePendingAuthRequest(payload: PendingAuthRequest): void {
  window.sessionStorage.setItem(AUTH_REQUEST_KEY, JSON.stringify(payload));
}

export function clearPendingAuthRequest(): void {
  window.sessionStorage.removeItem(AUTH_REQUEST_KEY);
}
