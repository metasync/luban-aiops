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
  delivery_id?: string;
  channel?: string;
  expires_at?: string;
}

export interface EvidenceTurn {
  turn_index: number;
  request_id: string;
  created_at?: string;
  frames: EvidenceFrame[];
}

// SPEC-054 R-3: the display-only change-request projection on a durable
// record's parked call (wire shape mirrors the live frame's projection).
export interface ConfirmationChangeRequestField {
  label: string;
  value: string;
  masked?: boolean;
}

export interface ConfirmationChangeRequest {
  summary: string;
  fields?: ConfirmationChangeRequestField[];
  warning?: string;
  requires_acknowledgment?: boolean;
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
  // SPEC-054 R-3: the per-call change-request projection persisted at park
  // time (action cards); absent for flow cards and legacy records.
  change_request?: ConfirmationChangeRequest;
}

// SPEC-051 R-6: the card-level browser-flow headline on the durable
// record (wire shape mirrors the kernel's FlowContext.summary()).
export interface ConfirmationFlowSummary {
  skill_id?: string;
  origin?: string;
  title?: string;
  description?: string;
  // SPEC-053 R-3: skill-authored gated-step intent (the card's lead line).
  flow_intent?: string;
  risk_class?: string;
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
  // SPEC-051 R-6: card-level browser-flow headline captured at park time;
  // absent/null for non-browser cards and records parked before the field
  // existed. Both the session-detail and inbox surfaces carry it so the
  // approvals inbox replays the same workflow framing.
  flow_summary?: ConfirmationFlowSummary | null;
  // SPEC-054 R-1: the parked batch's declared kind captured at park time;
  // absent/null for records parked before the field existed.
  approval_kind?: "flow" | "action" | null;
  // SPEC-054 R-4: the card's top-line message, computed once at park time and
  // persisted so a re-login and the approver inbox render the same lead line
  // the live card showed; absent/null for legacy records.
  message?: string | null;
  status: "pending" | "approved" | "denied" | "expired";
  parked_at?: string | null;
  decider_user_id?: string | null;
  decision?: string | null;
  decided_at?: string | null;
  // SPEC-037 R-6: signed-execution rows closing the approved calls; only
  // the session-detail surface carries them (the inbox stays
  // decision-metadata-only), and legacy records render an empty list.
  executions?: ExecutionRecord[] | null;
  recovery_only?: boolean;
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
  // SPEC-063 R-5a: the owner-scoped recovery projection for this execution,
  // fetched from the durable ledger independently of the legacy presentation
  // rows above. Absent/null when recovery is unavailable or the row predates
  // the field; it is a *read*, never an original response, and confers no
  // dispatch, continuation, or secret-release right.
  recovery?: ExecutionRecovery | null;
}

// SPEC-063 R-5a: one bounded observation in an owner recovery projection.
// Read-only wire shape (snake_case, straight from the ledger); the portal
// renders a representative subset and never reconstructs authority from it.
export interface RecoveryObservation {
  observation_id: string;
  source: "agent" | "worker" | (string & {});
  kind:
    | "claim_committed"
    | "wait_expired"
    | "transport_uncertain"
    | "pre_dispatch_refused"
    | "worker_result"
    | "result_persistence_unconfirmed"
    | "response_accepted"
    | "run_stopped"
    | "duplicate_seen"
    | (string & {});
  observed_at: string;
  request_id?: string;
  reason_code?: string;
  tool_status?: "success" | "error" | "denied" | (string & {});
}

// SPEC-063 R-5a: the durable receipt embedded in a `result_recorded`
// recovery projection — a subset of execution-receipt.schema.json. The
// portal shows outcome, completion time, and the correlating request id;
// the digest and signature are audit detail and are not rendered.
export interface RecoveryReceipt {
  status: "succeeded" | "failed" | "timeout" | (string & {});
  completed_at?: string | null;
  request_id?: string | null;
}

// SPEC-063 R-5a: the owner-scoped recovery projection riding an execution
// row of the session detail (wire shape mirrors execution-recovery.schema
// v1). `state` is the durable outcome the ledger can prove; `availability`
// distinguishes a readable ledger (`available`) from one that could not be
// read (`unavailable`) or an execution the owner cannot see (`not_found`).
export interface ExecutionRecovery {
  availability: "available" | "unavailable" | "not_found";
  state:
    | "not_dispatched"
    | "dispatch_claimed"
    | "outcome_unknown"
    | "result_recorded"
    | null;
  // Present only when the request was registered but never dispatched
  // (state null); it never coexists with a dispatch outcome.
  preparation_state?: "registered";
  execution_id: string | null;
  confirm_id?: string | null;
  call_id?: string | null;
  run_id?: string | null;
  attempt_request_id?: string | null;
  tool_name?: string | null;
  requested_at?: string | null;
  expires_at?: string | null;
  claimed_at?: string | null;
  observe_by?: string | null;
  as_of?: string | null;
  replay: boolean;
  run_stopped: boolean;
  integrity_conflict: boolean;
  target_verification_required: boolean;
  receipt?: RecoveryReceipt | null;
  observations: RecoveryObservation[];
  observations_truncated: boolean;
  next_observation_cursor?: string | null;
}

export interface SessionSummary {
  session_id: string;
  title: string | null;
  created_at: string;
  last_active_at: string | null;
  pending_confirmation: boolean;
  // SPEC-056 R-1: the birth discriminator, fixed once at creation and
  // immutable (never inferred, never promoted/demoted). Chat lists
  // `operation`, Studio lists `development`; the shift-summary picker is
  // scoped to `operation` (R-4). The gateway always serializes it (its
  // Pydantic mirror defaults to `operation`), so it is never absent here.
  session_type: "operation" | "development";
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
  // SPEC-063 R-5a: whether the durable recovery ledger was readable for
  // this owner detail. `unavailable` degrades the recovery rows to a
  // "could not be read" state without hiding the historical presentation
  // facts; absent on responses that predate the field.
  execution_recovery_availability?: "available" | "unavailable" | null;
  executions_truncated?: boolean;
  next_execution_cursor?: string | null;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
}

export async function listSessions(
  signal?: AbortSignal,
  sessionType?: "operation" | "development",
): Promise<SessionSummary[]> {
  // SPEC-056 R-2: an optional, ownership-preserving scope. Omitted returns
  // every session (the legacy behavior); a value scopes the list to that
  // type server-side (`?session_type=<mode>`) — how Chat and Studio each
  // list only their own kind, and how the shift-summary picker is confined
  // to operation sessions (R-4) rather than hidden client-side.
  const query = sessionType
    ? `?session_type=${encodeURIComponent(sessionType)}`
    : "";
  const response = await requestJson<SessionListResponse>(
    `/api/v1/sessions${query}`,
    { signal },
  );
  return response.sessions ?? [];
}

// SPEC-063 R-5a: optional recovery paging on the owner session detail. The
// `execution` filter selects an observation page only *after* the server-side
// owner check, so an execution id never widens the read; `executionCursor` is
// an opaque continuation cursor binding session/owner/keyset position; and
// `pageSize` bounds the executions enriched per fetch (server default 50,
// maximum 100). Omitted, the call is byte-identical to the legacy fetch.
export interface SessionRecoveryQuery {
  execution?: string;
  executionCursor?: string;
  pageSize?: number;
}

export async function getSession(
  sessionId: string,
  signal?: AbortSignal,
  recovery?: SessionRecoveryQuery,
): Promise<SessionDetail> {
  const params = new URLSearchParams();
  if (recovery?.execution) params.set("execution", recovery.execution);
  if (recovery?.executionCursor) {
    params.set("execution_cursor", recovery.executionCursor);
  }
  if (recovery?.pageSize != null) {
    params.set("page_size", String(recovery.pageSize));
  }
  const query = params.toString();
  return requestJson<SessionDetail>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}${query ? `?${query}` : ""}`,
    { signal },
  );
}

// Omitting sessionId keeps the server-generated id; named sessions are
// reserved for dedicated workflows (incident triage, SPEC-015 R-3).
//
// skillTarget (SPEC-055 R-4) opens the session as a develop-as-you-go one:
// the target is declared *at birth*, which is what makes it an authorization
// scope rather than a claim fitted to the trace afterwards — the session does
// not exist to mutate until this call returns, so no captured step can
// predate it. It rides session:create and is deliberately not gated by
// session:skill_graduate, so any authenticated role may scope their own
// session; graduating it stays gated. Throws ApiError 422 when the target is
// not a normalizable http(s) URL, and nothing is created in that case (the
// agent validates before the session exists).
export async function createSession(
  sessionId?: string,
  skillTarget?: string,
  sessionType?: "operation" | "development",
): Promise<SessionDetail> {
  const body: Record<string, string> = {};
  if (sessionId) body.session_id = sessionId;
  if (skillTarget) body.skill_target = skillTarget;
  // SPEC-056 R-1: the birth type, sent per entry (Chat → operation, Studio →
  // development) and written once at creation. Decoupled from skillTarget —
  // a development session may omit a target, and declaring one never sets
  // the type. Omitted (the historical one-click shape) defaults to
  // `operation` server-side, so an un-updated caller is unaffected.
  if (sessionType) body.session_type = sessionType;
  return requestJson<SessionDetail>("/api/v1/sessions", {
    method: "POST",
    body,
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

// Skill graduation (SPEC-055 R-4): the agent re-validates the session's
// captured authoring trace against its declared blast radius and renders it
// — deterministically, with no model involved — into an executable-flow draft
// validated against Skill v2 before it is returned. Nothing is published and
// nothing is persisted beyond the trace's lifecycle flip to `graduated`.
//
// Throws ApiError 404 (unknown/foreign — anti-enumeration), 409 (the
// deterministic blast-radius refusal; `detail` names every guard the trace
// failed and the steps responsible), 409 (the trace was already discarded),
// 503 (validation not configured) or 502 (validation unreachable, or the
// renderer and ingestion disagree — the draft is withheld rather than handed
// over unvalidated).
export interface SkillGraduationResponse extends SkillDraftResponse {
  mode: "graduated" | (string & {});
  // Replay steps in the draft, i.e. the approved mutations captured.
  step_count: number;
  // The declared scope a replay binds to; null for a flow with no browser
  // step, which needs none and gets none rather than a target it never uses.
  web_target: string | null;
  // Where the declaration sits relative to the first captured step. A report,
  // never a gate — `postdated` means the scope was fitted to a trace that had
  // already begun, and the operator is told so rather than silently trusted.
  declaration: "preceded" | "postdated" | "indeterminate" | (string & {});
}

export async function graduateSessionSkill(
  sessionId: string,
): Promise<SkillGraduationResponse> {
  return requestJson<SkillGraduationResponse>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/skill-graduate`,
    { method: "POST" },
  );
}

// Mid-session target declaration (SPEC-055 R-4): for a session that *becomes*
// a development session after it was opened, so its declaration can postdate
// the first captured step. First declaration wins and cannot be widened —
// `target` is therefore the scope actually in force, never an echo of the
// request, and `already_declared` means a *different* target is in force.
// Throws ApiError 403 (role holds no session:skill_graduate grant), 404
// (unknown/foreign) or 422 (not a normalizable http(s) URL, so it could
// never be corroborated).
export interface SkillTargetDeclaration {
  session_id: string;
  target: string;
  already_declared: boolean;
}

export async function declareSkillTarget(
  sessionId: string,
  target: string,
): Promise<SkillTargetDeclaration> {
  return requestJson<SkillTargetDeclaration>(
    `/api/v1/sessions/${encodeURIComponent(sessionId)}/skill-target`,
    { method: "POST", body: { target } },
  );
}
