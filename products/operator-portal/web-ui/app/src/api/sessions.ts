// Session workspace API client (SPEC-022 R-1 surface, consumed per
// SPEC-023 R-3). All shapes mirror the gateway/agent contracts.
import { requestJson } from "./client";

export interface TranscriptTurn {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

export interface SessionSummary {
  session_id: string;
  title: string | null;
  created_at: string;
  last_active_at: string | null;
  pending_confirmation: boolean;
}

export interface SessionDetail extends SessionSummary {
  user_id: string;
  status: "active" | "expired";
  transcript_available: boolean;
  transcript: TranscriptTurn[];
}

export interface SessionListResponse {
  sessions: SessionSummary[];
}

export async function listSessions(signal?: AbortSignal): Promise<SessionSummary[]> {
  const response = await requestJson<SessionListResponse>("/api/v1/sessions", {
    signal,
  });
  return response.sessions ?? [];
}

export async function getSession(
  sessionId: string,
  signal?: AbortSignal,
): Promise<SessionDetail> {
  return requestJson<SessionDetail>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}`,
    { signal },
  );
}

// Omitting sessionId keeps the server-generated id; named sessions are
// reserved for dedicated workflows (incident triage, SPEC-015 R-3).
export async function createSession(
  sessionId?: string,
): Promise<SessionDetail> {
  return requestJson<SessionDetail>("/api/v1/sessions", {
    method: "POST",
    body: sessionId ? { session_id: sessionId } : {},
  });
}

// Throws ApiError with status 409 (parked) or 404 (unknown/foreign);
// callers map those to the SPEC-022 R-1 workspace messages.
export async function deleteSession(sessionId: string): Promise<void> {
  await requestJson(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
  });
}
