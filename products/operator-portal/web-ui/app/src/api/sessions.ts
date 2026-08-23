// Session workspace API client (SPEC-022 R-1 surface, consumed per
// SPEC-023 R-3). All shapes mirror the gateway/agent contracts.
import { requestJson } from "./client";

export interface TranscriptTurn {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

// Persisted tool evidence (SPEC-025 R-2): one group per assistant turn.
// Frames keep the wire shape of the stream contract's tool_call/tool_result
// frames, plus an optional store-added truncation marker (SPEC-025 R-1).
export interface EvidenceTruncated {
  reason: "entry_cap" | "session_budget" | (string & {});
  original_chars?: number;
}

export interface EvidenceFrame {
  type: "tool_call" | "tool_result" | (string & {});
  call_id?: string;
  tool_name?: string;
  parameters?: Record<string, unknown>;
  status?: string;
  evidence?: {
    executed_at?: string;
    duration_ms?: number;
    risk_level?: string;
    source_system?: string;
  };
  data?: unknown;
  data_summary?: unknown;
  error?: { code?: string; message?: string } | null;
  truncated?: EvidenceTruncated;
}

export interface EvidenceTurn {
  turn_index: number;
  request_id: string;
  created_at?: string;
  frames: EvidenceFrame[];
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
  // SPEC-025 R-2: empty array when the session stored no evidence,
  // null when the evidence store is unreadable (degraded, never a failure).
  evidence_turns?: EvidenceTurn[] | null;
  // SPEC-024 R-3: model id pinned by the session's most recent turn; the
  // composer seeds its selector from it on session switch.
  model?: string | null;
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
