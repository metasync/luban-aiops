// Gateway API client (ported from legacy app.js). Every request carries
// an x-request-id and the bearer token when signed in; the gateway
// re-enforces policy on every request regardless of client-side gating.
import { loadAuthSession } from "../auth/storage";

const GATEWAY_OVERRIDE_KEY = "luban.portal.gatewayUrl";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    // The server's own explanation, when it sent one. SPEC-055 R-4 makes this
    // load-bearing: a graduation refusal names every blast-radius guard the
    // trace failed and the steps responsible, which *is* the operator's remedy
    // — reducing it to a status code would answer "not graduable" and send
    // them hunting. Absent when the body carried no string detail (a proxy's
    // HTML 502, or the policy engine's structured 403 object).
    public readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function defaultGateway(): string {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return window.location.origin;
  }
  return "http://localhost:8080";
}

export function currentGateway(): string {
  const override = window.localStorage.getItem(GATEWAY_OVERRIDE_KEY)?.trim();
  return (override || defaultGateway()).replace(/\/$/, "");
}

export function setGatewayOverride(url: string): void {
  if (url.trim()) {
    window.localStorage.setItem(GATEWAY_OVERRIDE_KEY, url.trim());
  } else {
    window.localStorage.removeItem(GATEWAY_OVERRIDE_KEY);
  }
}

export function buildRequestId(): string {
  return `req-${crypto.randomUUID()}`;
}

// SPEC-030 R-6: the Settings panel surfaces the most recent request id
// for issue correlation. Read-only exposure — nothing outside this
// module can rewrite the id a request actually carried.
let lastRequestId: string | null = null;

export function lastApiRequestId(): string | null {
  return lastRequestId;
}

export function authHeaders(): Record<string, string> {
  const session = loadAuthSession();
  if (!session?.access_token) {
    return {};
  }
  return { authorization: `Bearer ${session.access_token}` };
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

export async function requestJson<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "x-request-id": buildRequestId(),
    ...authHeaders(),
  };
  lastRequestId = headers["x-request-id"];
  if (options.body !== undefined) {
    headers["content-type"] = "application/json";
  }

  const response = await fetch(`${currentGateway()}${path}`, {
    method: options.method || "GET",
    headers,
    signal: options.signal,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    throw new ApiError(
      response.status,
      `Request failed: ${response.status} ${response.statusText}`,
      await errorDetail(response),
    );
  }
  return (await response.json()) as T;
}

// Best-effort read of an error body's `detail` string. Never throws: an
// unreadable or non-JSON body must not replace the status a caller was about
// to receive with a parse failure, so the detail is simply absent.
async function errorDetail(response: Response): Promise<string | undefined> {
  try {
    const payload = (await response.json()) as { detail?: unknown } | null;
    return typeof payload?.detail === "string" ? payload.detail : undefined;
  } catch {
    return undefined;
  }
}

// Only spent-handle metadata survives reload; never the delivered value.
const DELIVERY_ATTEMPT_KEY = "luban.portal.secretDeliveryAttempt.";
export function secretDeliveryAttempted(deliveryId: string): boolean {
  try {
    return sessionStorage.getItem(DELIVERY_ATTEMPT_KEY + deliveryId) === "spent";
  } catch {
    return false;
  }
}

// A one-time value stays inside this callback; never React state, storage, or errors.
export async function copyDeliveredSecret(deliveryId: string): Promise<void> {
  if (!navigator.clipboard?.writeText || !authHeaders().authorization) {
    throw new Error("Sign in and enable clipboard access before copying.");
  }
  if (secretDeliveryAttempted(deliveryId)) {
    throw new Error("Password unavailable. Generate a new password.");
  }
  try {
    sessionStorage.setItem(DELIVERY_ATTEMPT_KEY + deliveryId, "spent");
  } catch {
    // Storage can be disabled; the server still enforces single-use redemption.
  }
  let payload: { value?: unknown } | null = null;
  try {
    const response = await fetch(`${currentGateway()}/api/v1/secrets/delivery/${encodeURIComponent(deliveryId)}`, {
      headers: { ...authHeaders(), "x-request-id": buildRequestId() },
      cache: "no-store",
      redirect: "error",
    });
    if (!response.ok) throw new Error();
    payload = await response.json();
    if (typeof payload?.value !== "string" || !payload.value) throw new Error();
    await navigator.clipboard.writeText(payload.value);
  } catch {
    throw new Error("Could not copy the password. Generate a new password.");
  } finally {
    if (payload) payload.value = undefined;
  }
}

export function currentAuthenticatedUser(): string | null {
  return loadAuthSession()?.identity?.username || null;
}

export function currentRoles(): string[] {
  return loadAuthSession()?.identity?.roles || [];
}
