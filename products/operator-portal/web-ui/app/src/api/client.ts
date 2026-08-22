// Gateway API client (ported from legacy app.js). Every request carries
// an x-request-id and the bearer token when signed in; the gateway
// re-enforces policy on every request regardless of client-side gating.
import { loadAuthSession } from "../auth/storage";

const GATEWAY_OVERRIDE_KEY = "luban.portal.gatewayUrl";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
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
    );
  }
  return (await response.json()) as T;
}

export function currentAuthenticatedUser(): string | null {
  return loadAuthSession()?.identity?.username || null;
}

export function currentRoles(): string[] {
  return loadAuthSession()?.identity?.roles || [];
}
