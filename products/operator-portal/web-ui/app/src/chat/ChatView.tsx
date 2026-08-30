// ChatView — the operator chat workspace (SPEC-023 R-3). Composes the
// session panel (SPEC-022 R-1 surface), the SSE stream adapter (R-2), and
// transcript seeding so a resumed session renders like a live one.
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
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
  AudioOutlined,
  CheckOutlined,
  CloseOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  FileTextOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Bubble, Sender } from "@ant-design/x";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { ApiError } from "../api/client";
import { getModelCatalog, type ModelCatalogResponse } from "../api/models";
import {
  createSkillDraft,
  getSession,
  type SessionSummary,
  type SkillDraftResponse,
} from "../api/sessions";
import { useAuth } from "../auth/AuthContext";
import {
  CHAT_CONFIRM_ROLES,
  APPROVAL_DECIDER_ROLES,
  SKILL_DRAFT_ROLES,
  hasAnyRole,
} from "../roles";
import type { SessionWorkspace } from "../sessions/useSessionWorkspace";
import type { ExecutionReceipt, ToolResultFrame } from "../stream/models";
import {
  useChatStream,
  type ChatTurn,
  type ConfirmationCard,
  type ConfirmationDecision,
} from "../stream/useChatStream";
import { renderMarkdown } from "./markdown";
import { ComposerSelectionBar } from "./ComposerSelectionBar";
import { SkillDraftPreviewModal } from "./SkillDraftPreview";
import { detectArrivalSpan, transcriptToTurns, type ArrivalSpan } from "./transcript";
import { usePendingDecisionPoll } from "./usePendingDecisionPoll";
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
          <pre className="evidence-pre">
            {JSON.stringify(result.data, null, 2)}
          </pre>
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

export function ConfirmationCardView({
  card,
  canDecide,
  busy,
  onDecide,
}: {
  card: ConfirmationCard;
  canDecide: boolean;
  busy: boolean;
  onDecide: (confirmId: string, decision: ConfirmationDecision) => void;
}) {
  const status = CARD_STATUS[card.status] ?? CARD_STATUS.error;
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
      {card.message ? <div>{card.message}</div> : null}
      {card.pendingCalls.map((call, index) => (
        <div className="confirm-call" key={call.callId ?? index}>
          <div
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
            <strong>{call.toolName ?? call.callId ?? "tool"}</strong>
            <Tag color={call.riskLevel === "read" ? "default" : "warning"}>
              {call.riskLevel ?? "unknown"}
            </Tag>
          </div>
          <pre className="evidence-pre">
            {JSON.stringify(call.parameters ?? {}, null, 2)}
          </pre>
        </div>
      ))}
      {card.executions && card.executions.length > 0 ? (
        <div className="confirm-executions">
          {card.executions.map((execution) => {
            const status =
              EXECUTION_STATUS[execution.status] ?? EXECUTION_STATUS.requested;
            const note = executionDigestNote(execution);
            return (
              <div className="confirm-execution" key={execution.executionId}>
                <Tag color={status.color}>{status.label}</Tag>
                <strong>{execution.toolName || execution.callId}</strong>
                {note ? (
                  <span className="confirm-execution-note">{note}</span>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
      {card.status === "pending" ? (
        effectiveCanDecide ? (
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <Button
              type="primary"
              icon={<CheckOutlined />}
              disabled={busy}
              onClick={() => onDecide(card.confirmId, "approve")}
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

function TurnGroup({
  turn,
  canDecide,
  busy,
  onDecide,
  justArrived,
  revealFromChars,
}: {
  turn: ChatTurn;
  canDecide: boolean;
  busy: boolean;
  onDecide: (confirmId: string, decision: ConfirmationDecision) => void;
  justArrived?: boolean;
  // SPEC-035 R-4: when set, the reply bubble re-types itself from this
  // char offset so the operator watches the new content land instead of
  // meeting a silent wall of text. Evidence and cards render at once.
  revealFromChars?: number;
}) {
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
        loading={loading}
        content={displayReply}
        contentRender={(content) => (
          // Safe by construction: renderMarkdown escapes every source
          // character (including quotes) before introducing markup and
          // only renders http(s) links.
          <div
            className="md-content"
            dangerouslySetInnerHTML={{
              __html: renderMarkdown(String(content ?? "")),
            }}
          />
        )}
      />
      {turn.error ? (
        <Alert type="error" showIcon title={turn.error} />
      ) : null}
      {/* Evidence panel renders whenever a turn carries tool frames —
          live streams and replayed (SPEC-025) evidence share this path. */}
      {turn.toolCalls.length > 0 || turn.toolResults.length > 0 ? (
        <EvidencePanel turn={turn} />
      ) : null}
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

function SessionPanel({
  sessions,
  activeSessionId,
  loading,
  error,
  authenticated,
  onSelect,
  onCreate,
  onDelete,
  onRename,
}: {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;
  error: string | null;
  authenticated: boolean;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
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
                  {dayjs(session.last_active_at ?? session.created_at).fromNow()}
                </span>
                {/* SPEC-039 R-8: truncated id with full value on hover. */}
                <span className="session-item-id">
                  <code title={session.session_id}>{session.session_id}</code>
                  <CopyIdButton id={session.session_id} />
                </span>
              </div>
              {session.pending_confirmation ? (
                <Tag color="warning">awaiting approval</Tag>
              ) : null}
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
export default function ChatView({
  workspace,
}: {
  workspace: SessionWorkspace;
}) {
  const { username, roles } = useAuth();
  const authenticated = Boolean(username);
  const chat = useChatStream();
  const [draft, setDraft] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  // Explicit empty-transcript note (SPEC-023 R-3): a resumed session whose
  // transcript_available is false tells the operator so, rather than
  // silently showing the generic placeholder.
  const [transcriptNote, setTranscriptNote] = useState<string | null>(null);
  // Sessions whose transcript was already loaded this tab; switching back
  // restores the in-memory cache without another fetch.
  const loadedRef = useRef(new Set<string>());
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

  // Session switch: load the transcript once per tab, then let the stream
  // hook's per-session cache take over on subsequent switches.
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
    if (loadedRef.current.has(activeSessionId)) {
      setSession(activeSessionId);
      return;
    }
    const controller = new AbortController();
    const target = activeSessionId;
    setHistoryLoading(true);
    getSession(target, controller.signal)
      .then((detail) => {
        if (controller.signal.aborted) return;
        loadedRef.current.add(target);
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
        // Any other failure (transient gateway blip, expired token) must
        // not be cached as "empty": leave the miss out of loadedRef so
        // switching away and back retries the fetch, and tell the
        // operator why the history is missing.
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
  usePendingDecisionPoll({
    sessionId: chat.sessionId,
    turns: chat.turns,
    streaming: chat.streaming,
    applyDetail: (detail) => {
      if (!chat.sessionId) return;
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
        onSelect={setActiveSessionId}
        onCreate={() => void workspace.createAndOpen()}
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
            <DraftAsSkillButton sessionId={activeSummary.session_id} />
          </div>
        ) : null}
        <div className="chat-messages" ref={scrollRef}>
          {!authenticated ? (
            <div className="chat-placeholder">
              Sign in from the sidebar to start chatting with the operations
              agent.
            </div>
          ) : historyLoading ? (
            <div className="chat-placeholder">
              <Spin tip="Loading session transcript…" />
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
                busy={chat.streaming}
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
                onDecide={(confirmId, decision) =>
                  void chat.decide(confirmId, decision)
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
    </div>
  );
}
