// ChatView — the operator chat workspace (SPEC-023 R-3). Composes the
// session panel (SPEC-022 R-1 surface), the SSE stream adapter (R-2), and
// transcript seeding so a resumed session renders like a live one.
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Collapse,
  Input,
  Modal,
  Select,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  AimOutlined,
  AudioOutlined,
  CheckOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Bubble, Sender } from "@ant-design/x";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { ApiError, copyDeliveredSecret, secretDeliveryAttempted } from "../api/client";
import { getModelCatalog, type ModelCatalogResponse } from "../api/models";
import {
  createSkillDraft,
  declareSkillTarget,
  getSession,
  graduateSessionSkill,
  type ExecutionRecovery,
  type SessionDetail,
  type SessionSummary,
  type SkillDraftResponse,
  type SkillGraduationResponse,
} from "../api/sessions";
import { useAuth } from "../auth/AuthContext";
import {
  CHAT_CONFIRM_ROLES,
  APPROVAL_DECIDER_ROLES,
  SKILL_DRAFT_ROLES,
  SKILL_GRADUATE_ROLES,
  hasAnyRole,
} from "../roles";
import type {
  SessionMode,
  SessionWorkspace,
} from "../sessions/useSessionWorkspace";
import type { ExecutionReceipt, ToolResultFrame } from "../stream/models";
import {
  useChatStream,
  type ChatTurn,
  type ConfirmationCard,
  type ConfirmationDecision,
} from "../stream/useChatStream";
import { renderMarkdown } from "./markdown";
import { displayToolNames } from "./toolNames";
import { useToolNameMap } from "./useToolNames";
import { ComposerSelectionBar } from "./ComposerSelectionBar";
import { SkillDraftPreviewModal } from "./SkillDraftPreview";
import { detectArrivalSpan, transcriptToTurns, type ArrivalSpan } from "./transcript";
import { usePendingDecisionPoll } from "./usePendingDecisionPoll";
import { useRecoveryPoll } from "./useRecoveryPoll";
import {
  VOICE_LANGUAGES,
  loadVoiceLanguage,
  saveVoiceLanguage,
} from "../voice/languages";
import { useSpeechRecognition } from "../voice/useSpeechRecognition";

dayjs.extend(relativeTime);

// --- Tool evidence (legacy parity) --------------------------------------

interface EvidenceEntry {
  callId: string;
  tool: string;
  parameters?: Record<string, unknown>;
  result?: ToolResultFrame;
}

interface EvidenceCounts {
  calls: number;
  pending: number;
  success: number;
  error: number;
  denied: number;
}

function buildEvidenceEntries(turn: ChatTurn): EvidenceEntry[] {
  const entries: EvidenceEntry[] = [];
  const byId = new Map<string, EvidenceEntry>();
  for (const call of turn.toolCalls) {
    const callId = call.callId ?? `call-${entries.length}`;
    const entry: EvidenceEntry = {
      callId,
      tool: call.toolName ?? callId,
      parameters: call.parameters,
    };
    entries.push(entry);
    byId.set(callId, entry);
  }
  for (const result of turn.toolResults) {
    const callId = result.callId ?? `result-${entries.length}`;
    const existing = byId.get(callId);
    if (existing) {
      existing.result = result;
    } else {
      const entry: EvidenceEntry = {
        callId,
        tool: result.toolName ?? callId,
        result,
      };
      entries.push(entry);
      byId.set(callId, entry);
    }
  }
  return entries;
}

function countEvidence(entries: EvidenceEntry[]): EvidenceCounts {
  const counts: EvidenceCounts = {
    calls: entries.length,
    pending: 0,
    success: 0,
    error: 0,
    denied: 0,
  };
  for (const entry of entries) {
    const status = entry.result?.status;
    if (!status) counts.pending += 1;
    else if (status === "success") counts.success += 1;
    else if (status === "error") counts.error += 1;
    else if (status === "denied") counts.denied += 1;
  }
  return counts;
}

function formatCounts(counts: EvidenceCounts): string {
  if (counts.calls === 0) return "no tool calls";
  const parts = [`${counts.calls} call${counts.calls === 1 ? "" : "s"}`];
  if (counts.pending > 0) parts.push(`${counts.pending} running`);
  if (counts.success > 0) parts.push(`${counts.success} ok`);
  if (counts.error > 0) parts.push(`${counts.error} failed`);
  if (counts.denied > 0) parts.push(`${counts.denied} denied`);
  return parts.join(" · ");
}

const RESULT_STATUS_COLOR: Record<string, string> = {
  success: "green",
  error: "red",
  denied: "orange",
};

// The evidence group stays collapsed by default: the summary line carries
// the trust signal without crowding the answer (legacy parity).
function EvidencePanel({ turn }: { turn: ChatTurn }) {
  const entries = buildEvidenceEntries(turn);
  const counts = countEvidence(entries);
  return (
    <Collapse
      size="small"
      className="evidence-turn"
      items={[
        {
          key: "evidence",
          label: (
            <span>
              Tool evidence{" "}
              <span className="evidence-summary">{formatCounts(counts)}</span>
            </span>
          ),
          children: (
            <div>
              {entries.map((entry) => (
                <EvidenceCard
                  key={entry.callId}
                  entry={entry}
                  requestId={turn.requestId}
                />
              ))}
            </div>
          ),
        },
      ]}
    />
  );
}

function EvidenceCard({
  entry,
  requestId,
}: {
  entry: EvidenceEntry;
  requestId?: string;
}) {
  const result = entry.result;
  const status = result?.status ?? "pending";
  const evidence = result?.evidence;
  return (
    <div className="evidence-card">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="tool-name">{entry.tool}</span>
        <Tag color={RESULT_STATUS_COLOR[status] ?? "blue"}>{status}</Tag>
      </div>
      {entry.parameters !== undefined ? (
        <details>
          <summary>Parameters</summary>
          <pre className="evidence-pre">
            {JSON.stringify(entry.parameters, null, 2)}
          </pre>
        </details>
      ) : null}
      {evidence || requestId ? (
        <div className="evidence-meta">
          {requestId ? <span>request: {requestId}</span> : null}
          {evidence?.executedAt ? <span>{evidence.executedAt}</span> : null}
          {typeof evidence?.durationMs === "number" ? (
            <span>{evidence.durationMs} ms</span>
          ) : null}
          {evidence?.riskLevel ? <span>risk: {evidence.riskLevel}</span> : null}
          {evidence?.sourceSystem ? <span>{evidence.sourceSystem}</span> : null}
        </div>
      ) : null}
      {/* Store-added size marker (SPEC-025 R-1): always visible, never a
          silently dropped payload. */}
      {result?.truncated ? (
        <div className="confirm-note">
          {result.truncated.reason === "entry_cap"
            ? `Payload truncated at the entry cap${
                typeof result.truncated.originalChars === "number"
                  ? ` (original ${result.truncated.originalChars} chars)`
                  : ""
              }; the preview below is partial.`
            : "Payload evicted by the session evidence budget; metadata is preserved."}
        </div>
      ) : null}
      {/* Presence of `data` (even null) drives the expander; data_summary
          renders only when data is absent (legacy parity). Budget-evicted
          payloads (data=null + marker) show the note above instead. */}
      {result &&
      result.data !== undefined &&
      !(result.data === null && result.truncated) ? (
        <details>
          <summary>Result data</summary>
          {/* SPEC-050 follow-up: render web.screenshot base64 as an
              actual image so operators can see the capture. */}
          {entry.tool === "web.screenshot" &&
           typeof result.data === "object" &&
           result.data !== null &&
           "screenshot" in result.data &&
           typeof (result.data as Record<string, unknown>).screenshot === "string" ? (
            <div style={{ marginTop: 8 }}>
              {(() => {
                const d = result.data as Record<string, unknown>;
                const fmt = typeof d.format === "string" ? d.format : "jpeg";
                const b64 = d.screenshot as string;
                const title = typeof d.title === "string" ? d.title : undefined;
                const url = typeof d.url === "string" ? d.url : undefined;
                const bytes = typeof d.bytes === "number" ? d.bytes : undefined;
                return (
                  <>
                    {title || url ? (
                      <div className="evidence-meta" style={{ marginBottom: 4 }}>
                        {title ? <span>{title}</span> : null}
                        {url ? <span>{url}</span> : null}
                        {bytes !== undefined ? <span>{bytes} bytes</span> : null}
                      </div>
                    ) : null}
                    <img
                      src={`data:image/${fmt};base64,${b64}`}
                      alt={title ?? "Screenshot"}
                      style={{
                        maxWidth: "100%",
                        maxHeight: 400,
                        border: "1px solid var(--border)",
                        borderRadius: "var(--radius)",
                      }}
                    />
                  </>
                );
              })()}
            </div>
          ) : (
            <pre className="evidence-pre">
              {JSON.stringify(result.data, null, 2)}
            </pre>
          )}
        </details>
      ) : result && result.dataSummary !== undefined ? (
        <details>
          <summary>Result summary</summary>
          <pre className="evidence-pre">
            {JSON.stringify(result.dataSummary, null, 2)}
          </pre>
        </details>
      ) : null}
      {result?.error ? (
        <div className="confirm-note">
          {result.error.code ? `${result.error.code}: ` : ""}
          {result.error.message ?? "tool execution failed"}
        </div>
      ) : null}
    </div>
  );
}

// --- Confirmation cards (SPEC-020 R-4 / SPEC-021) ------------------------

const CARD_STATUS: Record<string, { color: string; label: string }> = {
  pending: { color: "warning", label: "Pending" },
  approved: { color: "success", label: "Approved" },
  denied: { color: "error", label: "Denied" },
  expired: { color: "default", label: "Expired" },
  error: { color: "error", label: "Error" },
};

// SPEC-037 R-6: read-only receipt states on decided cards; mirrors the
// execution record store's five statuses.
const EXECUTION_STATUS: Record<string, { color: string; label: string }> = {
  requested: { color: "default", label: "requested" },
  succeeded: { color: "success", label: "succeeded" },
  failed: { color: "error", label: "failed" },
  timeout: { color: "warning", label: "timeout" },
  rejected: { color: "error", label: "rejected" },
};

function executionDigestNote(execution: ExecutionReceipt): string {
  if (execution.status === "rejected") {
    return execution.rejectReason
      ? `rejected: ${execution.rejectReason}`
      : "rejected";
  }
  if (execution.digestMatch === true) {
    return "arguments matched the signed request";
  }
  if (execution.digestMatch === false) {
    return "arguments did not match the signed request";
  }
  if (execution.status === "requested") {
    return "signed request issued";
  }
  return "";
}

// --- SPEC-063 R-5a: owner-facing recovery vocabulary ----------------------
// These labels describe only what the durable ledger can *prove* about an
// execution — never what the operator is allowed to do. A recovery read is
// not an original response, so there is deliberately no retry, reset,
// mark-success, or reveal-old-password affordance anywhere in this block:
// the only guidance offered is to verify the target system independently.

export const RECOVERY_VOCABULARY = {
  availability: ["available", "unavailable", "not_found"],
  state: [null, "not_dispatched", "dispatch_claimed", "outcome_unknown", "result_recorded"],
  source: ["agent", "worker"],
  kind: ["claim_committed", "wait_expired", "transport_uncertain", "pre_dispatch_refused",
    "worker_result", "result_persistence_unconfirmed", "response_accepted", "run_stopped", "duplicate_seen"],
  reason: ["none", "unauthorized", "bad_request", "signing_unavailable", "signature_invalid",
    "args_digest_mismatch", "request_missing", "identity_conflict", "protocol_unsupported",
    "request_expired", "request_not_yet_valid", "lifetime_invalid", "admission_disabled",
    "epoch_mismatch", "store_unavailable", "schema_invalid", "claim_commit_unconfirmed",
    "gateway_not_configured", "credential_missing", "wait_expired", "transport_error",
    "response_invalid", "receipt_unconfirmed", "run_stopped", "predecessor_unresolved",
    "send_lock_unavailable", "shutdown", "integrity_conflict", "metadata_replay"],
  receipt: ["succeeded", "failed", "timeout"],
} as const;

function recoveryId(value: unknown): string | undefined {
  return typeof value === "string" && /^[A-Za-z0-9_.:-]{1,256}$/.test(value) ? value : undefined;
}

function recoveryTime(value: unknown): string | undefined {
  return typeof value === "string" && value.length <= 40 &&
    /^\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
    Number.isFinite(Date.parse(value)) ? value : undefined;
}

// A recorded result is "late" when its durable completion lands after the
// observation deadline the card was polling against — the outcome exists and
// is readable now, but it was not visible while the window was open.
function isLateRecoveryReport(recovery: ExecutionRecovery): boolean {
  const completed = recoveryTime(recovery.receipt?.completed_at);
  const observed = recoveryTime(recovery.observe_by);
  if (!completed || !observed) return false;
  const completedAt = Date.parse(completed);
  const deadline = Date.parse(observed);
  return (
    Number.isFinite(completedAt) &&
    Number.isFinite(deadline) &&
    completedAt > deadline
  );
}

function recoveryLabel(recovery: ExecutionRecovery): {
  color: string;
  label: string;
  note: string;
} {
  if (recovery.availability === "not_found") {
    return { color: "default", label: "recovery not found",
      note: "No execution was found in this owner's session. Missing evidence does not establish whether the target changed." };
  }
  if (recovery.availability !== "available") {
    return {
      color: "default",
      label: "recovery unavailable",
      note: "The outcome ledger could not be read. This is not evidence either way — the action may or may not have run. Verify the target system independently.",
    };
  }
  if (recovery.integrity_conflict) {
    return {
      color: "error",
      label: "conflicting reports",
      note: "The ledger holds reports that could not be reconciled into one outcome, so the result is treated as unknown. Verify the target system independently before acting again.",
    };
  }
  switch (recovery.state) {
    case "result_recorded": {
      const status = recovery.receipt?.status;
      if (status !== "succeeded" && status !== "failed" && status !== "timeout") {
        return { color: "warning", label: "outcome unknown",
          note: "The recorded report is incomplete or unrecognized. Verify the target system independently." };
      }
      const late = isLateRecoveryReport(recovery);
      const verb =
        status === "failed"
          ? "tool failure recorded"
          : status === "timeout"
            ? "timeout recorded"
            : "tool report recorded";
      return {
        color: status === "succeeded" ? "success" : "warning",
        label: late ? `late ${verb}` : verb,
        note: late
          ? "A durable tool report landed after the observation window closed. It is recorded and readable now; it was not visible while the card was polling. This is the recorded report, not a live re-run."
          : "The worker's tool result was durably recorded. This is the recorded report, not a live re-run.",
      };
    }
    case "dispatch_claimed":
      return {
        color: "processing",
        label: "dispatch claimed",
        note: "A worker claimed this dispatch but no tool result has been durably recorded yet, so the outcome is still open. Verify the target system independently before acting again.",
      };
    case "outcome_unknown":
      return {
        color: "warning",
        label: "outcome unknown",
        note: "The available evidence does not establish one durable tool outcome. The action may still be running or may have completed. Verify the target system independently.",
      };
    case "not_dispatched":
      return {
        color: "default",
        label: "not dispatched",
        note: "This submission was positively refused before dispatch. That does not establish the outcome of any other attempt.",
      };
    case null:
      return {
        color: "default",
        label: "registered — dispatch not established",
        note: "The signed request was registered. Registration alone does not prove that the target did nothing; the handoff may be unresolved.",
      };
    default:
      return { color: "warning", label: "outcome unknown",
        note: "The recovery state is unrecognized. Verify the target system independently." };
  }
}

// Read-only recovery detail: the label note, the correlating times and IDs,
// the replay/missing-output explanation, history truncation, and the
// independent-verification guidance. Rendered as escaped text only.
function RecoveryDetail({
  recovery,
  label,
  busy,
  paged,
  onPage,
}: {
  recovery: ExecutionRecovery;
  label: { label: string; note: string };
  busy: boolean;
  paged: boolean;
  onPage: (cursor?: string) => void;
}) {
  const requestId = recovery.attempt_request_id ?? recovery.receipt?.request_id;
  const facts: Array<[string, string]> = [];
  for (const [name, value] of [
    ["Execution", recovery.execution_id], ["Approval", recovery.confirm_id],
    ["Run", recovery.run_id], ["Original request", requestId],
  ]) {
    const safe = recoveryId(value);
    if (name && safe) facts.push([name, safe]);
  }
  for (const [name, value] of [
    ["Requested", recovery.requested_at], ["Claimed", recovery.claimed_at],
    ["Observe by", recovery.observe_by], ["Completed", recovery.receipt?.completed_at],
    ["Read at", recovery.as_of],
  ]) {
    const safe = recoveryTime(value);
    if (name && safe) facts.push([name, safe]);
  }
  const observations = Array.isArray(recovery.observations) ? recovery.observations : [];
  const truncated = recovery.observations_truncated || observations.length > 20;
  return (
    <details className="confirm-execution-recovery">
      <summary>Recovery detail</summary>
      <div className="recovery-note">{label.note}</div>
      {facts.length > 0 ? (
        <dl className="recovery-facts">
          {facts.map(([name, value]) => (
            <div className="recovery-fact" key={name}>
              <dt>{name}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {recovery.replay ? (
        <div className="recovery-note">
          This is a replayed recovery read of the durable ledger, not the
          original live response.
        </div>
      ) : null}
      <div className="recovery-note">
        Recovery contains signed metadata only, never original tool output or a previously held secret.
        Missing output is inconclusive.
      </div>
      {recovery.run_stopped ? <div className="recovery-note">
        This run is stopped. Work already running at the target is not necessarily canceled.
      </div> : null}
      {observations.length > 0 ? <ol aria-label="Execution observations">
        {observations.slice(0, 20).map((fact, index) => {
          const kind = RECOVERY_VOCABULARY.kind.find((value) => value === fact?.kind);
          const source = RECOVERY_VOCABULARY.source.find((value) => value === fact?.source);
          const reason = RECOVERY_VOCABULARY.reason.find((value) => value === fact?.reason_code);
          const id = recoveryId(fact?.observation_id);
          const request = recoveryId(fact?.request_id);
          return <li key={`${id ?? "unrecognized"}:${index}`}>
            <strong>{kind ?? "unrecognized observation"}</strong> — {source ?? "unknown source"} at {recoveryTime(fact?.observed_at) ?? "unknown time"}
            {request ? <span> · Request: {request}</span> : null}
            {reason ? <span> · Reason: {reason}</span> : null}
            {id ? <code> · {id}</code> : null}
          </li>;
        })}
      </ol> : null}
      {truncated ? (
        <div className="recovery-note">
          Observation history is bounded to 20 entries per page in recorded order.
          {recovery.next_observation_cursor
            ? " More observations remain in the ledger."
            : " Additional observations exceeded the retention bound."}
        </div>
      ) : null}
      {recovery.next_observation_cursor ? <Button size="small" disabled={busy}
        onClick={() => onPage(recovery.next_observation_cursor!)}>Next observation page</Button> : null}
      {paged ? <Button size="small" disabled={busy} onClick={() => onPage()}>First observation page</Button> : null}
      {recovery.target_verification_required ? (
        <div className="recovery-note">
          Verify the target system independently before acting again — this
          recovery read is not proof of the current state.
        </div>
      ) : null}
    </details>
  );
}

function ExecutionRow({ execution, sessionId, busy }: {
  execution: ExecutionReceipt; sessionId?: string | null; busy: boolean;
}) {
  const [page, setPage] = useState<{ source: ExecutionRecovery | undefined; value: ExecutionRecovery; cursor?: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  useEffect(() => {
    setLoading(false);
    setError(false);
    return () => { requestRef.current?.abort(); requestRef.current = null; };
  }, [sessionId, execution.executionId, execution.recovery, busy]);
  const recovery = page?.source === execution.recovery ? page?.value : execution.recovery;
  const label = recovery ? recoveryLabel(recovery) : null;
  const loadPage = async (cursor?: string) => {
    if (!sessionId || busy || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    setError(false);
    try {
      const detail = await getSession(sessionId, controller.signal, {
        execution: execution.executionId, executionCursor: cursor, pageSize: 1,
      });
      if (controller.signal.aborted) return;
      const found = detail.session_id === sessionId ? detail.confirmations?.flatMap((card) => card.executions ?? [])
        .find((row) => row.execution_id === execution.executionId)?.recovery : null;
      if (!found || found.availability !== "available") { setError(true); return; }
      setPage({ source: execution.recovery, value: found, cursor });
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) { requestRef.current = null; setLoading(false); }
    }
  };
  const status = EXECUTION_STATUS[execution.status] ?? EXECUTION_STATUS.requested;
  const note = executionDigestNote(execution);
  return <div className="confirm-execution">
    <Tag color={status.color}>{recovery ? `Historical: ${status.label}` : status.label}</Tag>
    {label ? <Tag color={label.color} data-testid="recovery-label">{label.label}</Tag> : null}
    <strong>{execution.toolName || execution.callId}</strong>
    {note ? <span className="confirm-execution-note">{note}</span> : null}
    {recovery && label ? <RecoveryDetail recovery={recovery} label={label}
      busy={busy || loading} paged={Boolean(page?.source === execution.recovery && page?.cursor)}
      onPage={(cursor) => void loadPage(cursor)} /> : null}
    {error ? <span role="status">Recovery page could not be read. The last readable view is retained; missing evidence is inconclusive.</span> : null}
  </div>;
}

export function RecoveryPager({ sessionId, detail, cursor, busy, onPage, onBusy }: {
  sessionId: string | null; detail?: SessionDetail; cursor?: string; busy: boolean;
  onPage: (detail: SessionDetail, cursor?: string) => void; onBusy: (busy: boolean) => void;
}) {
  const requestRef = useRef<AbortController | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const onBusyRef = useRef(onBusy);
  onBusyRef.current = onBusy;
  useEffect(() => {
    setError(false);
    setLoading(false);
    return () => { requestRef.current?.abort(); requestRef.current = null; onBusyRef.current(false); };
  }, [sessionId, busy]);
  const load = async (next?: string) => {
    if (!sessionId || busy || requestRef.current) return;
    const controller = new AbortController();
    requestRef.current = controller;
    setLoading(true);
    onBusyRef.current(true);
    setError(false);
    try {
      const fresh = await getSession(sessionId, controller.signal, next ? { executionCursor: next } : undefined);
      if (controller.signal.aborted) return;
      if (fresh.session_id !== sessionId || fresh.execution_recovery_availability !== "available") {
        setError(true); return;
      }
      onPage(fresh, next);
    } catch {
      if (!controller.signal.aborted) setError(true);
    } finally {
      if (!controller.signal.aborted) {
        requestRef.current = null; setLoading(false); onBusyRef.current(false);
      }
    }
  };
  if (!sessionId || detail?.session_id !== sessionId) return null;
  return <div className="recovery-pagination">
    {detail.execution_recovery_availability === "unavailable" ? <Alert type="warning" showIcon
      title="Execution recovery is unavailable. This does not mean there were no executions; verify the target independently." /> : null}
    {detail.executions_truncated ? <span>More execution recovery records are available. </span> : null}
    {detail.next_execution_cursor ? <Button disabled={busy || loading}
      onClick={() => void load(detail.next_execution_cursor!)}>Next execution page</Button> : null}
    {cursor ? <Button disabled={busy || loading} onClick={() => void load()}>First execution page</Button> : null}
    {error ? <span role="status">Recovery page could not be read. The last readable page is retained.</span> : null}
  </div>;
}

export function ConfirmationCardView({
  card,
  canDecide,
  busy,
  onDecide,
}: {
  card: ConfirmationCard;
  canDecide: boolean;
  busy: boolean;
  onDecide: (confirmId: string, decision: ConfirmationDecision, recipientWarningAcknowledged?: boolean) => void;
}) {
  const status = CARD_STATUS[card.status] ?? CARD_STATUS.error;
  const requiresAcknowledgment = card.pendingCalls.some(
    (call) => call.changeRequest?.requiresAcknowledgment,
  );
  const [acknowledgedId, setAcknowledgedId] = useState<string | null>(null);
  const acknowledged = acknowledgedId === card.confirmId;
  // SPEC-030 R-5: a parked batch whose highest action is tools:mutate is a
  // tier_2 approval — only designated approvers may decide. Display hint
  // only; the gateway approval-tier bridge stays authoritative (403 either
  // way), so an unknown/absent action degrades to tier_1 rendering.
  const needsApprover = card.pendingCalls.some(
    (call) => call.action === "tools:mutate",
  );
  const { roles } = useAuth();
  const effectiveCanDecide =
    canDecide &&
    (!needsApprover || hasAnyRole(roles, APPROVAL_DECIDER_ROLES));
  const approving = card.status === "pending" && card.note === "Approving…";
  const denying = card.status === "pending" && card.note === "Denying…";
  return (
    <div
      className={`confirm-card${card.status === "pending" ? " pending" : ""}`}
    >
      <div className="confirm-card-title">
        <SafetyCertificateOutlined />
        <span>Confirmation requested</span>
        <Tag color={status.color}>{status.label}</Tag>
        {card.mutating ? <Tag color="orange">mutating</Tag> : null}
        {needsApprover ? (
          <Tooltip
            title={`decided by: ${Array.from(APPROVAL_DECIDER_ROLES).join(", ")}`}
          >
            <Tag color="volcano">approver required</Tag>
          </Tooltip>
        ) : (
          <Tag color="blue">operator confirmation</Tag>
        )}
      </div>
      {/* SPEC-051 R-6: a bound browser flow headlines the card with the
          workflow intent (skill title/description + origin) so the operator
          approves "reset a user's password on <origin>", not a bare
          web.click. The per-call list below stays as the tool detail. */}
      {card.flowSummary &&
      (card.flowSummary.title ||
        card.flowSummary.origin ||
        card.flowSummary.flowIntent) ? (
        <div
          className="confirm-flow"
          style={{
            margin: "6px 0 8px",
            padding: "8px 10px",
            borderRadius: 6,
            background: "rgba(127,127,127,0.08)",
            borderLeft: "3px solid var(--accent)",
          }}
        >
          {card.flowSummary.title ? (
            <div style={{ fontWeight: 600 }}>{card.flowSummary.title}</div>
          ) : null}
          {/* SPEC-053 R-3: the skill-authored gated-step intent is the lead
              decision line — the plain sentence describing what approving this
              flow actually does. Rendered as escaped JSX text (never markup),
              set apart from the bold title above and the muted description
              below. Absent for skills that declare none (renders as today). */}
          {card.flowSummary.flowIntent ? (
            <div
              className="confirm-flow-intent"
              style={{ fontSize: 13, fontWeight: 500, marginTop: 4 }}
            >
              {card.flowSummary.flowIntent}
            </div>
          ) : null}
          {card.flowSummary.description ? (
            <div style={{ opacity: 0.75, fontSize: 13, marginTop: 2 }}>
              {card.flowSummary.description}
            </div>
          ) : null}
          <div
            style={{
              display: "flex",
              gap: 6,
              alignItems: "center",
              marginTop: 6,
              flexWrap: "wrap",
            }}
          >
            {card.flowSummary.origin ? (
              <Tag color="geekblue">{card.flowSummary.origin}</Tag>
            ) : null}
            {card.flowSummary.riskClass ? (
              <Tag
                color={
                  card.flowSummary.riskClass === "read" ? "default" : "warning"
                }
              >
                {card.flowSummary.riskClass} flow
              </Tag>
            ) : null}
          </div>
        </div>
      ) : null}
      {card.message ? <div>{card.message}</div> : null}
      {card.pendingCalls.map((call, index) => call.changeRequest?.warning ? (
        <Alert key={`warning-${index}`} type="warning" showIcon title={call.changeRequest.warning} />
      ) : null)}
      {requiresAcknowledgment && card.status === "pending" && effectiveCanDecide ? (
        <Checkbox
          checked={acknowledged}
          disabled={busy}
          onChange={(event) => setAcknowledgedId(event.target.checked ? card.confirmId : null)}
        >
          I acknowledge sending a secret to a recipient outside the approved list.
        </Checkbox>
      ) : null}
      {card.pendingCalls.map((call, index) => (
        <div className="confirm-call" key={call.callId ?? index}>
          {/* SPEC-054 R-3: an action card's call leads with the change-request
              projection — the effect sentence the operator approves, then its
              decision-relevant fields — instead of a bare tool name. Secret
              values arrive pre-masked (***) from the kernel; every value
              renders as escaped JSX text, never markup. A flow or legacy call
              (no projection) keeps today's tool-level header. */}
          {call.changeRequest ? (
            <>
              <div className="confirm-call-summary" style={{ fontWeight: 600 }}>
                {call.changeRequest.summary}
              </div>
              {call.changeRequest.fields &&
              call.changeRequest.fields.length > 0 ? (
                <table
                  className="confirm-change-fields"
                  style={{
                    marginTop: 6,
                    borderCollapse: "collapse",
                    fontSize: 13,
                  }}
                >
                  <tbody>
                    {call.changeRequest.fields.map((field, fieldIndex) => (
                      <tr key={`${field.label}-${fieldIndex}`}>
                        <td
                          style={{
                            opacity: 0.75,
                            paddingRight: 10,
                            textAlign: "right",
                            verticalAlign: "top",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {field.label}
                        </td>
                        <td
                          className="confirm-change-value"
                          style={{ fontFamily: "var(--font-mono, monospace)" }}
                        >
                          {field.value}
                          {field.masked ? (
                            <Tag style={{ marginLeft: 6 }}>masked</Tag>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
            </>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <strong>{call.toolName ?? call.callId ?? "tool"}</strong>
              <Tag color={call.riskLevel === "read" ? "default" : "warning"}>
                {call.riskLevel ?? "unknown"}
              </Tag>
            </div>
          )}
          {/* SPEC-050 follow-up: the parsed element label is the one
              human-readable line for a browser interaction, so keep it
              visible as prose rather than buried in a raw code block. */}
          {call.displayHint ? (
            <div className="confirm-call-hint">{call.displayHint}</div>
          ) : null}
          {/* Post-live-test #2(c): the per-call arguments are audit detail,
              not what the operator reads to decide, so they fold behind an
              expander to keep the card readable. SPEC-055 R-7: for an action
              card these arrive pre-redacted from the kernel (secret-bearing
              values → ***, fail-closed), so the expander never shows a
              plaintext secret beside the masked change_request above; a
              flow/legacy card carries no change_request and renders as today.
              Values render as escaped JSX text, never markup. */}
          <details className="confirm-call-details">
            <summary>Technical details</summary>
            <pre className="evidence-pre">
              {JSON.stringify(call.parameters ?? {}, null, 2)}
            </pre>
          </details>
        </div>
      ))}
      {card.executions && card.executions.length > 0 ? (
        <div className="confirm-executions">
          {card.executions.map((execution) => <ExecutionRow key={execution.executionId}
            execution={execution} sessionId={card.sessionId} busy={busy} />)}
        </div>
      ) : null}
      {card.status === "pending" ? (
        effectiveCanDecide ? (
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              disabled={busy || (requiresAcknowledgment && !acknowledged)}
              onClick={() => requiresAcknowledgment
                ? onDecide(card.confirmId, "approve", acknowledged)
                : onDecide(card.confirmId, "approve")}
            >
              {approving ? "Approving…" : "Approve"}
            </Button>
            <Button
              danger
              icon={<CloseOutlined />}
              disabled={busy}
              onClick={() => onDecide(card.confirmId, "deny")}
            >
              {denying ? "Denying…" : "Deny"}
            </Button>
          </div>
        ) : (
          <div className="confirm-note">
            {needsApprover
              ? "This request needs a designated approver — your current role cannot approve or deny it."
              : "Your current role cannot approve or deny this request."}
          </div>
        )
      ) : null}
      {card.note ? <div className="confirm-note">{card.note}</div> : null}
    </div>
  );
}

// --- Turn rendering -------------------------------------------------------

// SPEC-035 R-4: the arrival window bounds both the typewriter reveal of
// freshly landed reply text and the flash highlight around it.
const ARRIVAL_WINDOW_MS = 6000;
const REVEAL_TICK_MS = 25;

// Exported for tests: the render order (reply → post-approval "working"
// indicator → tool evidence → confirmation cards) is a UX requirement
// (#3), so TurnGroup.test.tsx asserts it directly.
export function CopyPasswordControl({ delivery }: {
  delivery: import("../stream/models").SecretDeliveryFrame;
}) {
  const [state, setState] = useState<"ready" | "copying" | "copied" | "unavailable">(
    () => secretDeliveryAttempted(delivery.deliveryId) ? "unavailable" : "ready",
  );
  const [expired, setExpired] = useState(() => Date.parse(delivery.expiresAt) <= Date.now());
  const attempted = useRef(false);
  useEffect(() => {
    const remaining = Date.parse(delivery.expiresAt) - Date.now();
    if (remaining <= 0) { setExpired(true); return; }
    const timer = window.setTimeout(() => setExpired(true), Math.min(remaining, 2_147_483_647));
    return () => window.clearTimeout(timer);
  }, [delivery.expiresAt]);
  const copy = async () => {
    if (attempted.current || state !== "ready" || expired) return;
    attempted.current = true;
    setState("copying");
    try {
      await copyDeliveredSecret(delivery.deliveryId);
      setState("copied");
    } catch {
      setState("unavailable");
    }
  };
  return (
    <div className="secret-delivery" style={{ margin: "8px 0" }}>
      <Button icon={<CopyOutlined />} loading={state === "copying"}
        disabled={state !== "ready" || expired} onClick={() => void copy()}>
        {state === "copied" ? "Password copied" : expired ? "Password expired"
          : state === "unavailable" ? "Password unavailable" : "Copy password"}
      </Button>
      <div role="status" style={{ marginTop: 4, fontSize: 12 }}>
        {state === "copied" ? "Copied once. The password is not retained here."
          : expired || state === "unavailable" ? "This password cannot be copied again. Generate a new password."
          : "One-time copy. The password is never shown in this conversation."}
      </div>
    </div>
  );
}

export function TurnGroup({
  turn,
  canDecide,
  busy,
  onDecide,
  justArrived,
  revealFromChars,
  agentWorking,
}: {
  turn: ChatTurn;
  canDecide: boolean;
  busy: boolean;
  onDecide: (confirmId: string, decision: ConfirmationDecision, recipientWarningAcknowledged?: boolean) => void;
  justArrived?: boolean;
  // SPEC-035 R-4: when set, the reply bubble re-types itself from this
  // char offset so the operator watches the new content land instead of
  // meeting a silent wall of text. Evidence and cards render at once.
  revealFromChars?: number;
  // Post-approval activity indicator: the decision was applied and the
  // agent is executing the resumed stream in the background.
  agentWorking?: boolean;
}) {
  // v0.27.4 (broadened v0.27.5): every rendered surface shows the
  // registry's dotted canonical tool names (see toolNames.ts).
  const toolNames = useToolNameMap();
  // Legacy parity: a finished turn with no text and no parked confirmation
  // shows the "(no response received)" placeholder.
  const reply =
    turn.replyText ||
    (turn.completed && !turn.confirmationPending
      ? "(no response received)"
      : "");
  const [revealedChars, setRevealedChars] = useState<number | null>(null);
  useEffect(() => {
    // No active reveal: render the full reply. The guard also covers
    // reduced-motion users, who get the content instantly (the static
    // tint in global.css still marks the arrival).
    if (
      revealFromChars === undefined ||
      revealFromChars >= turn.replyText.length ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      setRevealedChars(null);
      return;
    }
    setRevealedChars(revealFromChars);
    // Chunk size scales with the landed text so a short note and a long
    // summary both finish inside the arrival window.
    const remaining = turn.replyText.length - revealFromChars;
    const chunk = Math.max(
      1,
      Math.ceil(remaining / (ARRIVAL_WINDOW_MS / REVEAL_TICK_MS)),
    );
    let shown = revealFromChars;
    const timer = window.setInterval(() => {
      shown = Math.min(turn.replyText.length, shown + chunk);
      setRevealedChars(shown >= turn.replyText.length ? null : shown);
      if (shown >= turn.replyText.length) window.clearInterval(timer);
    }, REVEAL_TICK_MS);
    return () => window.clearInterval(timer);
  }, [revealFromChars, turn.replyText]);
  const displayReply =
    revealedChars === null ? reply : turn.replyText.slice(0, revealedChars);
  const loading = !turn.completed && !turn.confirmationPending && !turn.error;
  // Sticky request banner: while this turn's user bubble has scrolled out
  // of the transcript viewport, a pinned one-liner restates the request so
  // long replies (and expanded evidence) stay correlated with it.
  const userBubbleRef = useRef<HTMLDivElement>(null);
  const [requestOutOfView, setRequestOutOfView] = useState(false);
  useEffect(() => {
    const target = userBubbleRef.current;
    if (!target || !turn.userMessage) return;
    const observer = new IntersectionObserver(
      ([entry]) => setRequestOutOfView(!entry.isIntersecting),
      { root: target.closest(".chat-messages") },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [turn.userMessage]);
  return (
    <div className={`turn-group${justArrived ? " turn-arrived" : ""}`}>
      {turn.userMessage ? (
        <div ref={userBubbleRef}>
          <Bubble placement="end" variant="filled" content={turn.userMessage} />
        </div>
      ) : null}
      {turn.userMessage ? (
        <div
          className={`turn-request-banner${requestOutOfView ? " visible" : ""}`}
          title={turn.userMessage}
        >
          <span className="turn-request-banner-label">Request</span>
          <span className="turn-request-banner-text">{turn.userMessage}</span>
        </div>
      ) : null}
      <Bubble
        placement="start"
        variant="outlined"
        loading={loading && !displayReply}
        content={displayReply}
        contentRender={(content) => (
          // Safe by construction: renderMarkdown escapes every source
          // character (including quotes) before introducing markup and
          // only renders http(s) links.
          <div
            className="md-content"
            dangerouslySetInnerHTML={{
              __html: renderMarkdown(
                displayToolNames(String(content ?? ""), toolNames),
              ),
            }}
          />
        )}
      />
      {turn.error ? (
        <Alert type="error" showIcon title={turn.error} />
      ) : null}
      {/* Post-approval activity indicator (#3): once a remote decision
          lands, show a clearly labelled "working" row directly under the
          reply and above the tool evidence so the operator sees the agent
          resumed the stream. It sits above the evidence because the new
          tool frames land below it as the resumed stream progresses. */}
      {agentWorking ? (
        <div className="agent-working" data-testid="agent-working-indicator">
          <Spin size="small" />
          <span className="agent-working-label">Agent is working…</span>
        </div>
      ) : null}
      {/* Evidence panel renders whenever a turn carries tool frames —
          live streams and replayed (SPEC-025) evidence share this path. */}
      {turn.toolCalls.length > 0 || turn.toolResults.length > 0 ? (
        <EvidencePanel turn={turn} />
      ) : null}
      {turn.secretDeliveries?.map((delivery) => (
        <CopyPasswordControl key={delivery.deliveryId} delivery={delivery} />
      ))}
      {turn.confirmations.map((card) => (
        <ConfirmationCardView
          key={card.confirmId}
          card={card}
          canDecide={canDecide}
          busy={busy}
          onDecide={onDecide}
        />
      ))}
    </div>
  );
}

// --- Session panel --------------------------------------------------------

// SPEC-039 R-8: one-click session-id copy with a visible confirmation
// state (icon flips to a check mark for a moment after copying).
export function CopyIdButton({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const copy = (event: React.MouseEvent) => {
    event.stopPropagation();
    navigator.clipboard
      .writeText(id)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {});
  };
  return (
    <Tooltip title={copied ? "Copied" : "Copy session id"}>
      <Button
        type="text"
        size="small"
        icon={copied ? <CheckOutlined /> : <CopyOutlined />}
        aria-label={`Copy session id ${id}`}
        onClick={copy}
      />
    </Tooltip>
  );
}

// SPEC-044 R-5 (rewired by SPEC-045 R-5): "Draft as skill" session
// action. Visibility mirrors the documents matrix (client-side gate;
// the gateway re-enforces session:skill_draft regardless). The
// validated draft opens in the shared read-only preview modal — the
// generated/skeleton distinction is the modal's mode badge — and only
// downloads client-side (SPEC-040 R-4 Blob pattern) on explicit
// Download .md; Discard drops the in-memory response.
export function DraftAsSkillButton({ sessionId }: { sessionId: string }) {
  const { roles } = useAuth();
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<SkillDraftResponse | null>(null);
  if (!hasAnyRole(roles, SKILL_DRAFT_ROLES)) {
    return null;
  }
  const requestDraft = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await createSkillDraft(sessionId);
      setDraft(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        message.error("Your role cannot draft skills from sessions.");
      } else if (err instanceof ApiError && err.status === 404) {
        // Safety net for the race between the incident-detail gate and
        // the click: sessions expire after an idle TTL, and foreign
        // session ids answer the same opaque 404 (anti-enumeration).
        message.error(
          "This session is no longer available to you (expired or " +
            "owned by another operator) — draft from the incident " +
            "detail instead.",
        );
      } else if (err instanceof ApiError && err.status === 503) {
        message.error("Skill validation is not configured right now.");
      } else if (err instanceof ApiError && err.status === 502) {
        message.error("Skill validation is unreachable — no draft returned.");
      } else {
        message.error(
          err instanceof Error ? err.message : "Skill draft failed.",
        );
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Tooltip title="Preview a validated Skill Format draft built from this session's record">
        <Button
          type="text"
          size="small"
          icon={<FileTextOutlined />}
          aria-label="Draft as skill"
          loading={busy}
          onClick={() => void requestDraft()}
        >
          Draft as skill
        </Button>
      </Tooltip>
      <SkillDraftPreviewModal draft={draft} onClose={() => setDraft(null)} />
    </>
  );
}

// SPEC-055 R-4: "Graduate as skill" — the develop-as-you-go counterpart of
// the draft action above it. Visibility mirrors the gateway's
// session:skill_graduate grant (client-side convenience only), but the
// artifact is a different class: the agent re-validates the session's
// captured trace against its declared blast radius and renders it
// deterministically, so the response either arrives validated or the
// operator gets a refusal naming every guard the trace failed. That refusal
// is a modal rather than a toast because it lists step positions and is the
// operator's only remedy — a toast that dismisses itself would take the
// answer with it.
export function GraduateAsSkillButton({ sessionId }: { sessionId: string }) {
  const { roles } = useAuth();
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<SkillGraduationResponse | null>(null);
  if (!hasAnyRole(roles, SKILL_GRADUATE_ROLES)) {
    return null;
  }
  const graduate = async () => {
    if (busy) return;
    setBusy(true);
    try {
      setDraft(await graduateSessionSkill(sessionId));
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        Modal.warning({
          title: "This session cannot be graduated",
          width: 640,
          content:
            err.detail ?? "Its authoring trace failed blast-radius re-validation.",
        });
      } else if (err instanceof ApiError && err.status === 403) {
        message.error("Your role cannot graduate sessions into skills.");
      } else if (err instanceof ApiError && err.status === 404) {
        // Same race as the draft action: sessions expire on an idle TTL and a
        // foreign id answers the identical opaque 404 (anti-enumeration).
        message.error(
          "This session is no longer available to you (expired or owned by " +
            "another operator).",
        );
      } else if (err instanceof ApiError && err.status === 503) {
        message.error("Skill validation is not configured right now.");
      } else if (err instanceof ApiError && err.status === 502) {
        // Covers both an unreachable validation leg and a draft ingestion
        // rejected — in neither case is anything handed over.
        message.error(
          err.detail ?? "Graduation failed validation — no draft was returned.",
        );
      } else {
        message.error(
          err instanceof Error ? err.message : "Skill graduation failed.",
        );
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Tooltip title="Render this session's approved mutations into a validated executable-flow skill draft">
        <Button
          type="text"
          size="small"
          icon={<ThunderboltOutlined />}
          aria-label="Graduate as skill"
          loading={busy}
          onClick={() => void graduate()}
        >
          Graduate as skill
        </Button>
      </Tooltip>
      <SkillDraftPreviewModal draft={draft} onClose={() => setDraft(null)} />
    </>
  );
}

// SPEC-055 R-4: declare the target a session's captured mutations are
// corroborated against. The birth path (the develop-as-you-go opener) is the
// primary one; this exists for a session that *became* a development session
// after it was opened, without which its browser steps could never graduate —
// the re-validation would have nothing to corroborate them against.
//
// The dialog reports the target actually in force rather than echoing the
// field, because the first declaration wins and cannot be widened: an
// operator who believed they had moved a scope they cannot move would trust a
// graduation that was scoped by whatever was declared first.
export function DeclareSkillTargetButton({ sessionId }: { sessionId: string }) {
  const { roles } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!hasAnyRole(roles, SKILL_GRADUATE_ROLES)) {
    return null;
  }
  const submit = async () => {
    const value = target.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      const declaration = await declareSkillTarget(sessionId, value);
      setOpen(false);
      setTarget("");
      setError(null);
      if (declaration.already_declared) {
        message.warning(
          "A different target is already in force for this session: " +
            declaration.target,
        );
      } else {
        message.success(`Target in force: ${declaration.target}`);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError(
          err.detail ??
            "Enter an absolute http(s) URL — a target with no origin can " +
              "never be corroborated.",
        );
      } else if (err instanceof ApiError && err.status === 403) {
        setError("Your role cannot declare a skill-development target.");
      } else if (err instanceof ApiError && err.status === 404) {
        setError("This session is no longer available to you.");
      } else {
        setError(err instanceof Error ? err.message : "Declaration failed.");
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Tooltip title="Declare the web target this session's mutations are corroborated against (needed to graduate a browser flow)">
        <Button
          type="text"
          size="small"
          icon={<AimOutlined />}
          aria-label="Declare skill target"
          onClick={() => {
            setError(null);
            setOpen(true);
          }}
        >
          Declare target
        </Button>
      </Tooltip>
      <Modal
        title="Declare skill-development target"
        open={open}
        okText="Declare"
        okButtonProps={{ disabled: target.trim().length === 0 }}
        confirmLoading={busy}
        onOk={() => void submit()}
        onCancel={() => setOpen(false)}
        destroyOnHidden
      >
        {error ? (
          <Alert
            type="error"
            showIcon
            title={error}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Input
          value={target}
          maxLength={2048}
          autoFocus
          placeholder="https://console.example.com/admin/users"
          aria-label="Skill target"
          onChange={(event) => setTarget(event.target.value)}
          onPressEnter={() => void submit()}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          The first declaration wins and cannot be widened. Only the origin and
          path are kept — any query, fragment or embedded credential is dropped
          — and every mutation this session captures must land inside it, or
          graduation refuses the flow.
        </Typography.Text>
      </Modal>
    </>
  );
}

function SessionPanel({
  sessions,
  activeSessionId,
  loading,
  error,
  authenticated,
  localDecisionApplied,
  mode,
  onSelect,
  onCreate,
  onCreateDevelopment,
  onDelete,
  onRename,
}: {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;
  error: string | null;
  authenticated: boolean;
  // When true, the active session's local turn state shows all cards
  // decided — suppress the stale backend pending_confirmation tag.
  localDecisionApplied: boolean;
  // SPEC-056 R-3: which create affordance the panel offers — exactly one per
  // mode, so neither entry can mint the other's session type.
  mode: SessionMode;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  // SPEC-055 R-4: opens the develop-as-you-go dialog, which collects the
  // target before the session exists to mutate anything.
  onCreateDevelopment: () => void;
  onDelete: (session: SessionSummary) => void;
  onRename: (session: SessionSummary) => void;
}) {
  return (
    <aside className="session-panel">
      <div className="session-panel-header">
        <Typography.Text strong>Sessions</Typography.Text>
        {/* Pre-login the workspace API cannot be called (401), so the
            affordance is disabled like the composer; the server-side 401
            path stays as the defence for mid-session token expiry. */}
        {/* Whichever affordance the mode selects stays inside one flex child:
            the header is space-between, so a second direct child would centre
            itself. */}
        <div style={{ display: "flex", gap: 4 }}>
          {mode === "operation" ? (
            /* Chat keeps the one-click path only. The develop-as-you-go opener
               moved to Studio (SPEC-056 R-3), so nothing in Chat can mint a
               session that could later graduate a captured flow. */
            <Tooltip title={authenticated ? "" : "Sign in to create a session"}>
              <Button
                size="small"
                icon={<PlusOutlined />}
                onClick={onCreate}
                disabled={!authenticated}
                aria-label="New session"
              >
                New
              </Button>
            </Tooltip>
          ) : (
            /* SPEC-055 R-4's opener, now Studio's only create path. It still
               collects the target before the session exists to mutate
               anything; the target is optional per SPEC-056 R-2. Not
               role-gated: the target rides session:create, which every
               authenticated role holds, because declaring a scope is inert (it
               grants nothing and only narrows what a later graduation may
               emit). Studio itself is gated on STUDIO_ROLES, and the gateway
               dual-gates minting a development session on
               session:skill_graduate regardless (R-6). */
            <Tooltip
              title={
                authenticated
                  ? "Open a skill-development session, optionally against a declared web target"
                  : "Sign in to create a session"
              }
            >
              <Button
                size="small"
                icon={<ExperimentOutlined />}
                onClick={onCreateDevelopment}
                disabled={!authenticated}
                aria-label="New skill development session"
              >
                New
              </Button>
            </Tooltip>
          )}
        </div>
      </div>
      {error ? (
        <Alert
          type="warning"
          showIcon
          title={error}
          style={{ margin: 8 }}
        />
      ) : null}
      <div className="session-list">
        {loading && sessions.length === 0 ? (
          <div style={{ padding: 16, textAlign: "center" }}>
            <Spin size="small" />
          </div>
        ) : sessions.length === 0 ? (
          <Typography.Text type="secondary" style={{ padding: 8 }}>
            No sessions yet. Create one to start.
          </Typography.Text>
        ) : (
          sessions.map((session) => (
            <div
              key={session.session_id}
              role="button"
              tabIndex={0}
              className={`session-item${
                session.session_id === activeSessionId ? " active" : ""
              }`}
              onClick={() => onSelect(session.session_id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(session.session_id);
                }
              }}
            >
              <div className="session-item-main">
                <span className="session-item-title">
                  {session.title ?? session.session_id}
                </span>
                <span className="session-item-meta">
                  <span className="session-item-time">
                    {dayjs(session.last_active_at ?? session.created_at).fromNow()}
                  </span>
                  {session.pending_confirmation &&
                  !(localDecisionApplied && session.session_id === activeSessionId) ? (
                    <Tag color="warning" className="session-pending-tag">awaiting approval</Tag>
                  ) : null}
                </span>
                {/* SPEC-039 R-8: truncated id with full value on hover. */}
                <span className="session-item-id">
                  <code title={session.session_id}>{session.session_id}</code>
                  <CopyIdButton id={session.session_id} />
                </span>
              </div>
              <Button
                type="text"
                size="small"
                icon={<EditOutlined />}
                aria-label={`Rename session ${session.title ?? session.session_id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onRename(session);
                }}
              />
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                aria-label={`Delete session ${session.title ?? session.session_id}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(session);
                }}
              />
            </div>
          ))
        )}
      </div>
    </aside>
  );
}

// --- ChatView --------------------------------------------------------------

// The session workspace is owned by App so the incidents view can pin
// incident sessions into the panel (SPEC-023 R-3 deep links).
//
// SPEC-056 R-2 / R-5: ONE ChatView serves both Chat and Studio. `mode`
// selects only three things — which authoring controls are visible, the birth
// `session_type`, and the list scope — and the last two are properties of the
// workspace instance App hands in, not of anything this component computes.
// `mode` is deliberately NOT threaded into the SSE stream adapter, the
// secret-masking renderer, or the HITL confirmation path: those are the trust
// core, and a mode that could vary them would make the two entries two
// products rather than one workspace with two scopes.
export default function ChatView({
  workspace,
  mode = "operation",
}: {
  workspace: SessionWorkspace;
  mode?: SessionMode;
}) {
  const { username, roles } = useAuth();
  const authenticated = Boolean(username);
  const chat = useChatStream();
  const [draft, setDraft] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [recoveryPage, setRecoveryPage] = useState<{ detail: SessionDetail; cursor?: string } | null>(null);
  const [recoveryPageBusy, setRecoveryPageBusy] = useState(false);
  const currentRecoveryPage = recoveryPage?.detail.session_id === chat.sessionId ? recoveryPage : null;
  // Explicit empty-transcript note (SPEC-023 R-3): a resumed session whose
  // transcript_available is false tells the operator so, rather than
  // silently showing the generic placeholder.
  const [transcriptNote, setTranscriptNote] = useState<string | null>(null);
  // Sessions the server reported as unknown (404). Their ids must never
  // prime the stream pointer: sending against them would fail, so the
  // next message auto-creates a fresh session instead (legacy flow).
  const missingRef = useRef(new Set<string>());
  // Set while the workspace pointer is catching up to a session id learned
  // from the stream; prevents the switch effect from treating the pointer
  // move as a user-initiated session change.
  const catchingUpRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // SPEC-034 R-1 / SPEC-035 R-4: after a poll reseed delivered new
  // content, the span marks where the arrival reveal and flash start;
  // cleared when the arrival window lapses.
  const [arrival, setArrival] = useState<ArrivalSpan | null>(null);
  const arrivalTimerRef = useRef<number | undefined>(undefined);

  const canDecide = hasAnyRole(roles, CHAT_CONFIRM_ROLES);
  const { setSession } = chat;
  const { activeSessionId, setActiveSessionId, refresh } = workspace;

  // Voice input (SPEC-023 R-4): browser STT only; the composed text enters
  // the draft like typing and the turn is tagged input_modality=voice.
  const speech = useSpeechRecognition();
  const [voiceLanguage, setVoiceLanguageState] = useState(() =>
    loadVoiceLanguage(),
  );
  const voiceUsedRef = useRef(false);

  const changeVoiceLanguage = (code: string) => {
    setVoiceLanguageState(code);
    saveVoiceLanguage(code);
  };

  const appendVoiceText = (text: string) => {
    voiceUsedRef.current = true;
    setDraft((current) => (current ? `${current} ${text}` : text));
  };

  const toggleVoice = () => {
    if (speech.listening) {
      speech.stop();
      return;
    }
    speech.start(voiceLanguage, appendVoiceText);
  };

  // Model catalog (SPEC-024 R-4): fetched once per sign-in; any failure
  // hides the selector and turns resolve the deploy-time default
  // server-side — chat keeps working either way.
  const [modelCatalog, setModelCatalog] =
    useState<ModelCatalogResponse | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  // Session-switch seeding runs inside a fetch callback whose closure must
  // see the latest catalog without re-running the transcript effect.
  const catalogRef = useRef<ModelCatalogResponse | null>(null);
  catalogRef.current = modelCatalog;

  useEffect(() => {
    if (!authenticated) return;
    const controller = new AbortController();
    getModelCatalog(controller.signal)
      .then((catalog) => {
        if (controller.signal.aborted) return;
        setModelCatalog(catalog);
        setSelectedModel(
          catalog.default ?? catalog.models[0]?.id ?? null,
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setModelCatalog(null);
      });
    return () => controller.abort();
  }, [authenticated]);

  // Session switch: re-read durable recovery even when a transcript is cached.
  useEffect(() => {
    if (chat.sessionId === activeSessionId) {
      catchingUpRef.current = false;
      return;
    }
    if (catchingUpRef.current) return;
    setTranscriptNote(null);
    if (!activeSessionId) {
      setSession(null);
      return;
    }
    if (missingRef.current.has(activeSessionId)) {
      // Known-missing session: show the empty transcript but leave the
      // stream pointer null so the next send auto-creates a session.
      setSession(null);
      return;
    }
    // Recovery must be re-read on return, even if a transcript is cached.
    const controller = new AbortController();
    const target = activeSessionId;
    setHistoryLoading(true);
    getSession(target, controller.signal)
      .then((detail) => {
        if (controller.signal.aborted) return;
        if (detail.session_id !== target) throw new Error("Session identity mismatch");
        setRecoveryPage({ detail });
        if (!detail.transcript_available && (detail.transcript ?? []).length === 0) {
          setTranscriptNote("This session has no recorded transcript yet.");
        }
        // SPEC-024 R-3: the selector follows the session's pinned model;
        // a session without a pin falls back to the catalog default.
        const catalog = catalogRef.current;
        if (
          detail.model &&
          catalog?.models.some((entry) => entry.id === detail.model)
        ) {
          setSelectedModel(detail.model);
        } else {
          setSelectedModel(catalog?.default ?? null);
        }
        const seeded = transcriptToTurns(
          detail.transcript ?? [],
          detail.evidence_turns,
          detail.confirmations,
        );
        setSession(
          target,
          // SPEC-031 R-2: durable confirmation cards ride the session
          // detail, so parked/decided cards survive a re-login.
          seeded,
        );
        chat.reseedTurns(target, seeded);
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) {
          // Unknown/expired session (e.g. a stale per-tab pointer or a
          // pinned incident session the server has not created yet):
          // open it empty. The id is remembered as missing so it never
          // rides along on the stream request — the first message
          // auto-creates the server-side session.
          missingRef.current.add(target);
          setSession(null);
          return;
        }
        // A transient failure must not be remembered as a missing session.
        // Returning to it performs a fresh read and can recover the history.
        setTranscriptNote(
          error instanceof ApiError && error.status === 401
            ? "Session history is unavailable because your sign-in expired. Sign in again to restore it."
            : "Session history could not be loaded right now. Switch to another session and back to retry.",
        );
        setSession(target, []);
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId, setSession]);

  // SPEC-032: owner-side live decision sync. While a confirmation card is
  // pending, a decision can land from elsewhere (the approver inbox,
  // another browser session) and the confirmation_result frame only rides
  // the answering stream; a bounded poll re-seeds the timeline through the
  // same transcriptToTurns path the initial load uses, so the decided card
  // and the resumed turn appear without a manual refresh. The re-seed
  // goes through reseedTurns (not setSession): for the session already on
  // screen, setSession's stash-then-restore would hand back the stale
  // cached turns and shadow the fresh state.
  const { settling } = usePendingDecisionPoll({
    sessionId: chat.sessionId,
    turns: chat.turns,
    streaming: chat.streaming || recoveryPageBusy || historyLoading,
    executionCursor: currentRecoveryPage?.cursor,
    applyDetail: (detail) => {
      if (!chat.sessionId) return;
      setRecoveryPage({ detail, cursor: currentRecoveryPage?.cursor });
      const reseeded = transcriptToTurns(
        detail.transcript ?? [],
        detail.evidence_turns,
        detail.confirmations,
      );
      // SPEC-034 R-1 / SPEC-035 R-4: a reseed that gained content
      // (resumed reply or new turn) reveals and flashes the arrival so
      // the operator sees that the decision actually delivered new
      // messages — the reveal starts where the old text ended.
      const arrived = detectArrivalSpan(chat.turns, reseeded);
      chat.reseedTurns(chat.sessionId, reseeded);
      if (arrived !== null) {
        setArrival(arrived);
        window.clearTimeout(arrivalTimerRef.current);
        arrivalTimerRef.current = window.setTimeout(
          () => setArrival(null),
          ARRIVAL_WINDOW_MS,
        );
      }
      // SPEC-034 R-2: the session panel learns the decision at the same
      // moment the transcript does, instead of at the next 30s poll tick.
      void refresh();
    },
  });

  // SPEC-063 R-5a: bounded recovery polling for unsettled executions on a
  // decided card. A dispatch that was claimed but not yet durably recorded
  // (or whose outcome is unknown) can still settle — a late worker report may
  // land after the card first rendered — so while the owner watches, refresh
  // every 2s for at most 120s, then show refresh guidance. Shares the
  // transcript re-seed path; a recovery-only change adds no transcript
  // content, so it triggers no arrival flash.
  const { recoveryPolling, recoveryGuidance } = useRecoveryPoll({
    sessionId: chat.sessionId,
    turns: chat.turns,
    streaming: chat.streaming || recoveryPageBusy || historyLoading,
    executionCursor: currentRecoveryPage?.cursor,
    applyDetail: (detail) => {
      if (!chat.sessionId) return;
      setRecoveryPage({ detail, cursor: currentRecoveryPage?.cursor });
      const reseeded = transcriptToTurns(
        detail.transcript ?? [],
        detail.evidence_turns,
        detail.confirmations,
      );
      chat.reseedTurns(chat.sessionId, reseeded);
      void refresh();
    },
  });

  // The stream reports server-assigned session ids; keep the workspace
  // pointer and the panel list in sync.
  useEffect(() => {
    if (chat.sessionId && chat.sessionId !== activeSessionId) {
      catchingUpRef.current = true;
      setActiveSessionId(chat.sessionId);
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chat.sessionId]);

  // SPEC-035 R-5: the panel's "awaiting approval" tag derives from the
  // session list's pending_confirmation flag. Refresh at every pending
  // transition of the live timeline (the parking moment of the owner's
  // own stream; the decision moment already refreshes via applyDetail)
  // instead of waiting for the 30s cadence — this is why the tag used
  // to appear only after the next list poll.
  const pendingCardCount = chat.turns.filter(
    (turn) => turn.confirmationPending,
  ).length;
  const prevPendingCountRef = useRef(pendingCardCount);
  useEffect(() => {
    if (prevPendingCountRef.current === pendingCardCount) return;
    prevPendingCountRef.current = pendingCardCount;
    if (authenticated) void refresh();
  }, [pendingCardCount, authenticated, refresh]);

  // The backend's pending_confirmation flag stays true until the resumed
  // stream completes (resolve() fires in the finally block). For the
  // active session, override the tag from local turn state: if all cards
  // are decided locally, suppress the stale backend flag immediately.
  const localDecisionApplied =
    pendingCardCount === 0 &&
    chat.turns.some((turn) =>
      turn.confirmations.some(
        (card) =>
          card.status === "approved" ||
          card.status === "denied" ||
          card.status === "expired",
      ),
    );

  // Keep the newest turn visible while streaming. While an arrival reveal
  // is active the scroll-into-view effect below owns positioning, so this
  // effect yields instead of fighting it.
  const lastTurn = chat.turns[chat.turns.length - 1];
  useEffect(() => {
    if (arrival) return;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.turns.length, lastTurn?.replyText, historyLoading, arrival]);

  // SPEC-035 R-4: bring the first arrived group into view so a decision
  // outcome landing off-screen still catches the operator's eye.
  useEffect(() => {
    if (!arrival) return;
    const target =
      scrollRef.current?.querySelector<HTMLElement>(".turn-group.turn-arrived");
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    target?.scrollIntoView({
      block: "nearest",
      behavior: reduced ? "auto" : "smooth",
    });
  }, [arrival]);

  // Pinned incident deep-links appear even before the server list catches
  // up (SPEC-023 R-3); the server entry replaces the pin on refresh.
  const mergedSessions: SessionSummary[] = [];
  for (const session of workspace.sessions) mergedSessions.push(session);
  for (const pin of workspace.pinned) {
    if (!workspace.sessions.some((s) => s.session_id === pin.session_id)) {
      mergedSessions.push(pin);
    }
  }

  const confirmDelete = (session: SessionSummary) => {
    Modal.confirm({
      title: "Delete this session?",
      content: `“${session.title ?? session.session_id}” and its transcript will be removed.`,
      okText: "Delete",
      okButtonProps: { danger: true },
      onOk: async () => {
        const outcome = await workspace.remove(session.session_id);
        if (!outcome.ok && outcome.message) {
          Modal.warning({
            title: "Session not deleted",
            content: outcome.message,
          });
        }
      },
    });
  };

  // SPEC-039 R-7: inline owner rename. Cosmetic and unaudited by design;
  // the server trims and bounds the title (1–80 chars).
  const [renaming, setRenaming] = useState<SessionSummary | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [renameBusy, setRenameBusy] = useState(false);

  const startRename = (session: SessionSummary) => {
    setRenaming(session);
    setRenameDraft(session.title ?? "");
    setRenameError(null);
  };

  const submitRename = async () => {
    if (!renaming) return;
    setRenameBusy(true);
    const outcome = await workspace.rename(renaming.session_id, renameDraft);
    setRenameBusy(false);
    if (!outcome.ok) {
      setRenameError(outcome.message ?? "Rename failed.");
      return;
    }
    setRenaming(null);
  };

  // SPEC-055 R-4 / SPEC-056 R-2: the develop-as-you-go opener, now Studio's
  // only create path. The target is still collected *before* the session
  // exists, which is what makes it an authorization scope rather than a claim
  // fitted to the trace afterwards — no mutation can have been captured yet,
  // so graduation can report the declaration `preceded` every step. It is now
  // OPTIONAL: an unscoped session can still capture browser mutations and be
  // scoped mid-flight with "Declare target", at which point graduation reports
  // that declaration as fitted to the trace rather than as the scope the
  // session acted under. Either way the session is minted
  // `session_type=development` — the type comes from the workspace's mode, and
  // is never inferred from whether a target happened to be named.
  const [devOpen, setDevOpen] = useState(false);
  const [devTarget, setDevTarget] = useState("");
  const [devError, setDevError] = useState<string | null>(null);
  const [devBusy, setDevBusy] = useState(false);

  const openDevelopmentDialog = () => {
    setDevTarget("");
    setDevError(null);
    setDevOpen(true);
  };

  const submitDevelopmentSession = async () => {
    const target = devTarget.trim();
    if (devBusy) return;
    setDevBusy(true);
    const outcome = await workspace.createDevelopmentSession(
      target || undefined,
    );
    setDevBusy(false);
    if (!outcome.ok) {
      setDevError(outcome.message ?? "Could not open the session.");
      return;
    }
    setDevOpen(false);
  };

  // SPEC-039 R-8: the open session header carries the id for handoff.
  const activeSummary =
    mergedSessions.find((s) => s.session_id === workspace.activeSessionId) ??
    null;

  const submitMessage = (message: string) => {
    const text = message.trim();
    if (!text || !authenticated || chat.streaming) return;
    speech.stop();
    setDraft("");
    const inputModality = voiceUsedRef.current ? "voice" : undefined;
    voiceUsedRef.current = false;
    void chat.send(text, {
      userId: username ?? undefined,
      inputModality,
      model: selectedModel ?? undefined,
    });
  };

  return (
    <div className="chat-view">
      <SessionPanel
        sessions={mergedSessions}
        activeSessionId={workspace.activeSessionId}
        loading={workspace.loading}
        error={workspace.error}
        authenticated={authenticated}
        localDecisionApplied={localDecisionApplied}
        mode={mode}
        onSelect={setActiveSessionId}
        onCreate={() => void workspace.createAndOpen()}
        onCreateDevelopment={openDevelopmentDialog}
        onDelete={confirmDelete}
        onRename={startRename}
      />
      <div className="chat-column">
        {activeSummary ? (
          <div className="chat-session-header">
            <Typography.Text
              strong
              ellipsis
              style={{ minWidth: 0, flex: "0 1 auto" }}
            >
              {activeSummary.title ?? activeSummary.session_id}
            </Typography.Text>
            <code title={activeSummary.session_id}>
              {activeSummary.session_id}
            </code>
            <CopyIdButton id={activeSummary.session_id} />
            {/* SPEC-056 R-3: the authoring controls split by mode, and neither
                mode offers a conversion — there is no "Move to Studio". An
                operation session's trace is multi-origin (its steps were
                approved as incident remediation, not as one flow), so
                graduating it would deterministically refuse; offering the
                button would only manufacture a refusal. */}
            {mode === "operation" ? (
              <DraftAsSkillButton sessionId={activeSummary.session_id} />
            ) : (
              /* Order reads as the workflow: scope the session, graduate it. */
              <>
                <DeclareSkillTargetButton
                  sessionId={activeSummary.session_id}
                />
                <GraduateAsSkillButton sessionId={activeSummary.session_id} />
              </>
            )}
          </div>
        ) : null}
        {/* SPEC-063 R-5a: recovery polling state for unsettled executions.
            While a bounded window is open, say so; once it lapses with the
            outcome still unsettled, offer refresh guidance instead of
            polling forever. Neither state exposes a retry/reset/reveal
            control — a late durable result stays readable on refresh. */}
        <RecoveryPager sessionId={chat.sessionId} detail={currentRecoveryPage?.detail}
          cursor={currentRecoveryPage?.cursor} busy={chat.streaming || historyLoading}
          onBusy={setRecoveryPageBusy} onPage={(detail, cursor) => {
            if (detail.session_id !== chat.sessionId || chat.streaming) return;
            setRecoveryPage({ detail, cursor });
            chat.reseedTurns(detail.session_id, transcriptToTurns(detail.transcript ?? [], detail.evidence_turns, detail.confirmations));
          }} />
        {recoveryPolling ? (
          <Alert
            type="info"
            showIcon
            title="Refreshing an unfinished execution outcome…"
          />
        ) : null}
        {recoveryGuidance ? (
          <Alert
            type="warning"
            showIcon
            title="An execution outcome is still unsettled. Automatic refreshing paused — reload or return to this session to check again. Verify the target system independently before acting."
          />
        ) : null}
        <div className="chat-messages" ref={scrollRef}>
          {!authenticated ? (
            <div className="chat-placeholder">
              Sign in from the sidebar to start chatting with the operations
              agent.
            </div>
          ) : historyLoading ? (
            <div className="chat-placeholder">
              <Spin description="Loading session transcript…" />
            </div>
          ) : chat.turns.length === 0 ? (
            <div className="chat-placeholder">
              {transcriptNote ??
                "Start a conversation with the operations agent. Each session keeps its own transcript and pending confirmations."}
            </div>
          ) : (
            chat.turns.map((turn, index) => (
              <TurnGroup
                key={turn.id}
                turn={turn}
                canDecide={canDecide}
                busy={chat.streaming || historyLoading || recoveryPageBusy}
                justArrived={arrival !== null && index >= arrival.from}
                // Only the span's start group re-types its reply (from
                // the already-seen offset); later groups arrive complete
                // under the flash so one reveal never buries the next.
                // Cold-seeded history renders at once — the typewriter is
                // reserved for live arrivals (0.18.1 live-check revert).
                revealFromChars={
                  arrival !== null && index === arrival.from
                    ? arrival.prevReplyChars
                    : undefined
                }
                agentWorking={
                  settling && index === chat.turns.length - 1
                }
                onDecide={(confirmId, decision, acknowledged) =>
                  void chat.decide(confirmId, decision, acknowledged)
                }
              />
            ))
          )}
        </div>
        <div className="chat-composer">
          {speech.error ? (
            <Alert
              type="warning"
              showIcon
              title={speech.error}
              style={{ marginBottom: 8 }}
            />
          ) : null}
          <Sender
            value={draft}
            onChange={setDraft}
            onSubmit={submitMessage}
            loading={chat.streaming}
            disabled={!authenticated}
            placeholder={
              speech.listening
                ? "Listening… speak now"
                : "Message the operations agent…"
            }
            autoSize={{ minRows: 1, maxRows: 6 }}
            prefix={
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {speech.supported ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <Select
                      size="small"
                      variant="borderless"
                      aria-label="Recognition language"
                      value={voiceLanguage}
                      onChange={changeVoiceLanguage}
                      options={VOICE_LANGUAGES.map((lang) => ({
                        value: lang.code,
                        label: lang.label,
                      }))}
                      popupMatchSelectWidth={false}
                    />
                    <Tooltip
                      title={
                        speech.listening
                          ? "Stop listening"
                          : "Dictate with the microphone"
                      }
                    >
                      <Button
                        type="text"
                        size="small"
                        danger={speech.listening}
                        icon={<AudioOutlined />}
                        aria-label="Voice input"
                        aria-pressed={speech.listening}
                        onClick={toggleVoice}
                      />
                    </Tooltip>
                  </div>
                ) : (
                  // Graceful degradation: affordance disabled with an
                  // explanation when the browser lacks the Web Speech API.
                  <Tooltip title="Voice input is unavailable in this browser (no Web Speech API).">
                    <Button
                      type="text"
                      size="small"
                      disabled
                      icon={<AudioOutlined />}
                      aria-label="Voice input unavailable"
                    />
                  </Tooltip>
                )}
              </div>
            }
            footer={
              // Extensible selection strip under the input: model choice
              // today (SPEC-024), further per-turn selections later.
              <ComposerSelectionBar
                catalog={modelCatalog}
                model={selectedModel}
                onModelChange={setSelectedModel}
                disabled={chat.streaming || !authenticated}
              />
            }
          />
        </div>
      </div>
      <Modal
        title="Rename session"
        open={renaming !== null}
        okText="Save"
        confirmLoading={renameBusy}
        onOk={() => void submitRename()}
        onCancel={() => setRenaming(null)}
        destroyOnHidden
      >
        {renameError ? (
          <Alert
            type="error"
            showIcon
            title={renameError}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Input
          value={renameDraft}
          maxLength={80}
          autoFocus
          placeholder="Session title (1–80 characters)"
          onChange={(event) => setRenameDraft(event.target.value)}
          onPressEnter={() => void submitRename()}
        />
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Renames apply to your own sessions only and are not audited.
        </Typography.Text>
      </Modal>
      <Modal
        title="New skill-development session"
        open={devOpen}
        okText="Open session"
        confirmLoading={devBusy}
        onOk={() => void submitDevelopmentSession()}
        onCancel={() => setDevOpen(false)}
        destroyOnHidden
      >
        {devError ? (
          <Alert
            type="error"
            showIcon
            title={devError}
            style={{ marginBottom: 12 }}
          />
        ) : null}
        <Input
          value={devTarget}
          maxLength={2048}
          autoFocus
          placeholder="https://console.example.com/admin/users"
          aria-label="Skill development target"
          onChange={(event) => setDevTarget(event.target.value)}
          onPressEnter={() => void submitDevelopmentSession()}
        />
        <Typography.Paragraph
          type="secondary"
          style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}
        >
          Optionally name the web target this session will work against.
          Declaring it here — before the first mutation — is what makes it the
          scope the session acts under: every approved change it captures is
          then corroborated against this origin at graduation, and a step that
          lands elsewhere refuses the flow. Leave it blank to open the session
          unscoped and declare a target later; graduation then reports that
          declaration as fitted to the trace rather than as the scope the
          session acted under. Only the origin and path are kept — any query,
          fragment or embedded credential is dropped. The first declaration
          wins.
        </Typography.Paragraph>
      </Modal>
    </div>
  );
}
