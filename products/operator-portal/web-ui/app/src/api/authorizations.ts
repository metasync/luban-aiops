// Same-origin only: the binding cookies must never follow a gateway override.
import { ApiError, authHeaders, buildRequestId } from "./client";
import type { SessionDetail } from "./sessions";

const BASE = "/api/v1/targets/authorizations";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const unavailable = () => new ApiError(503, "Target authorization unavailable.");

export type AuthorizationState = "pending" | "authorized" | "canceled" | "expired" | "failed";
export interface AuthorizationStatus {
  challenge_id: string;
  status: AuthorizationState;
  target: string;
  session_id: string;
  updated_at: string;
  expires_at: string;
}

function validId(id: string): string {
  if (!UUID.test(id)) throw unavailable();
  return id;
}

async function request(path: string, method = "GET", signal?: AbortSignal, timeout = 10000): Promise<unknown> {
  const headers = authHeaders();
  if (!headers.authorization) throw new ApiError(401, "Sign in to view target authorization.");
  try {
    const deadline = AbortSignal.timeout(timeout);
    const response = await fetch(path, {
      method, body: undefined, headers: { ...headers, "x-request-id": buildRequestId() },
      credentials: "same-origin", cache: "no-store", redirect: "error", referrerPolicy: "no-referrer",
      signal: signal ? AbortSignal.any([signal, deadline]) : deadline,
    });
    if (!response.ok) throw new ApiError(response.status, "Target authorization unavailable.");
    if (response.status === 204) return undefined;
    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw unavailable();
  }
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw unavailable();
  return value as Record<string, unknown>;
}

function timestamp(value: unknown): value is string {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
}

export async function authorizationStatus(id: string, signal?: AbortSignal): Promise<AuthorizationStatus> {
  const value = object(await request(`${BASE}/${validId(id)}`, "GET", signal));
  if (Object.keys(value).sort().join() !== "challenge_id,expires_at,session_id,status,target,updated_at"
      || value.challenge_id !== id || typeof value.status !== "string"
      || !["pending", "authorized", "canceled", "expired", "failed"].includes(value.status)
      || typeof value.target !== "string" || !value.target.trim()
      || typeof value.session_id !== "string" || !value.session_id.trim()
      || !timestamp(value.updated_at) || !timestamp(value.expires_at)) throw unavailable();
  return value as unknown as AuthorizationStatus;
}

export async function startAuthorization(id: string): Promise<{ start_url: string; expires_at: string }> {
  const value = object(await request(`${BASE}/${validId(id)}/start`, "POST"));
  const prefix = BASE + "/start/";
  if (Object.keys(value).sort().join() !== "expires_at,start_url" || typeof value.start_url !== "string"
      || !value.start_url.startsWith(prefix) || !UUID.test(value.start_url.slice(prefix.length))
      || !timestamp(value.expires_at)) throw unavailable();
  return { start_url: value.start_url, expires_at: value.expires_at };
}

export async function cancelAuthorization(id: string): Promise<void> {
  await request(`${BASE}/${validId(id)}/cancel`, "POST");
}

export async function resetAuthorizationBrowser(): Promise<void> {
  if (!authHeaders().authorization) return;
  try {
    await request(`${BASE}/browser-reset`, "POST", undefined, 2000);
  } catch {
    // Logout must complete even with expired authentication; expiry remains the bound.
  }
}

export async function authorizationSession(id: string, signal?: AbortSignal): Promise<SessionDetail> {
  return await request(`/api/v1/sessions/${encodeURIComponent(id)}`, "GET", signal) as SessionDetail;
}
