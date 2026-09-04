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

// Durable confirmation lifecycle record (SPEC-031 R-1/R-2): the owner's
// transcript cards and the approver inbox share this wire shape.
// pending_calls follows the parked confirmation_request payload.
export interface ConfirmationCallPayload {
  call_id?: string;
  tool_name?: string;
  parameters?: Record<string, unknown>;
  risk_level?: string;
  action?: string;
  // SPEC-050 follow-up: human-readable element description for browser
  // interaction tools (web.click, web.type, etc.).
  display_hint?: string;
}

export interface ConfirmationRecord {
  confirm_id: string;
  session_id: string;
  owner_user_id: string;
  // Inbox-only enrichment (session title at list time); absent on the
  // session-detail surface where the caller already knows the session.
  session_title?: string | null;
  pending_calls: ConfirmationCallPayload[];
  action?: string | null;
  // SPEC-033 R-2: ordinal of the user turn that parked the record (same
  // convention as evidence_turns.turn_index); absent/null for records
  // parked before the field existed.
  turn_index?: number | null;
  status: "pending" | "approved" | "denied" | "expired";
  parked_at?: string | null;
  decider_user_id?: string | null;
  decision?: string | null;
  decided_at?: string | null;
  // SPEC-037 R-6: signed-execution rows closing the approved calls; only
  // the session-detail surface carries them (the inbox stays
  // decision-metadata-only), and legacy records render an empty list.
  executions?: ExecutionRecord[] | null;
}

export interface ExecutionRecord {
  execution_id: string;
  call_id: string;
  confirm_id: string;
  session_id: string;
  tool_name: string;
  status: "requested" | "succeeded" | "failed" | "timeout" | "rejected";
  requested_at?: string | null;
  completed_at?: string | null;
  digest_match?: boolean | null;
  reject_reason?: string | null;
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
  // SPEC-031 R-2: durable confirmation lifecycle cards for the owner
  // transcript; empty list when the session parked none, null when the
  // record store is unreadable (degraded, never a failure).
  confirmations?: ConfirmationRecord[] | null;
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

// Owner rename (SPEC-039 R-7): supersedes the server-minted set-once
// title. Throws ApiError 400 (blank/overlong after trim) or 404
// (unknown/foreign — anti-enumeration). Renames are unaudited by design.
export async function renameSession(
  sessionId: string,
  title: string,
): Promise<SessionDetail> {
  return requestJson<SessionDetail>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/title`,
    { method: "PATCH", body: { title } },
  );
}

// Skill-draft export (SPEC-044 R-1): the agent layer generates the
// draft from the session's durable facts and validates it against
// skills-hub before returning it — an unvalidated draft never reaches
// the caller. Throws ApiError 404 (unknown/foreign — anti-enumeration),
// 503 (validation not configured), or 502 (validation unreachable).
export interface SkillDraftResponse {
  markdown: string;
  mode: "generated" | "skeleton" | (string & {});
  validation: "passed" | (string & {});
  suggested_filename: string;
}

export async function createSkillDraft(
  sessionId: string,
): Promise<SkillDraftResponse> {
  return requestJson<SkillDraftResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/skill-draft`,
    { method: "POST" },
  );
}
