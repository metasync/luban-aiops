// ChatView — the operator chat workspace (SPEC-023 R-3). Composes the
// session panel (SPEC-022 R-1 surface), the SSE stream adapter (R-2), and
// transcript seeding so a resumed session renders like a live one.
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Collapse,
  Modal,
  Select,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  AudioOutlined,
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Bubble, Sender } from "@ant-design/x";
import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";
import { getSession, type SessionSummary } from "../api/sessions";
import { useAuth } from "../auth/AuthContext";
import { CHAT_CONFIRM_ROLES, hasAnyRole } from "../roles";
import { useSessionWorkspace } from "../sessions/useSessionWorkspace";
import type { ToolResultFrame } from "../stream/models";
import {
  useChatStream,
  type ChatTurn,
  type ConfirmationCard,
  type ConfirmationDecision,
} from "../stream/useChatStream";
import { renderMarkdown } from "./markdown";
import { transcriptToTurns } from "./transcript";
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
                <EvidenceCard key={entry.callId} entry={entry} />
              ))}
            </div>
          ),
        },
      ]}
    />
  );
}

function EvidenceCard({ entry }: { entry: EvidenceEntry }) {
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
      {evidence ? (
        <div className="evidence-meta">
          {evidence.executedAt ? <span>{evidence.executedAt}</span> : null}
          {typeof evidence.durationMs === "number" ? (
            <span>{evidence.durationMs} ms</span>
          ) : null}
          {evidence.riskLevel ? <span>risk: {evidence.riskLevel}</span> : null}
          {evidence.sourceSystem ? <span>{evidence.sourceSystem}</span> : null}
        </div>
      ) : null}
      {/* Presence of `data` (even null) drives the expander; data_summary
          renders only when data is absent (legacy parity). */}
      {result && result.data !== undefined ? (
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

function ConfirmationCardView({
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
      {card.status === "pending" ? (
        canDecide ? (
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
            Your current role cannot approve or deny this request.
          </div>
        )
      ) : null}
      {card.note ? <div className="confirm-note">{card.note}</div> : null}
    </div>
  );
}

// --- Turn rendering -------------------------------------------------------

function TurnGroup({
  turn,
  canDecide,
  busy,
  onDecide,
}: {
  turn: ChatTurn;
  canDecide: boolean;
  busy: boolean;
  onDecide: (confirmId: string, decision: ConfirmationDecision) => void;
}) {
  // Legacy parity: a finished turn with no text and no parked confirmation
  // shows the "(no response received)" placeholder.
  const reply =
    turn.replyText ||
    (turn.completed && !turn.confirmationPending
      ? "(no response received)"
      : "");
  const loading = !turn.completed && !turn.confirmationPending && !turn.error;
  return (
    <div className="turn-group">
      {turn.userMessage ? (
        <Bubble placement="end" variant="filled" content={turn.userMessage} />
      ) : null}
      <Bubble
        placement="start"
        variant="outlined"
        loading={loading}
        content={reply}
        contentRender={(content) => (
          // Safe by construction: renderMarkdown escapes every source
          // character before introducing markup (legacy parity).
          <div
            className="md-content"
            dangerouslySetInnerHTML={{
              __html: renderMarkdown(String(content ?? "")),
            }}
          />
        )}
      />
      {turn.error ? (
        <Alert type="error" showIcon message={turn.error} />
      ) : null}
      {/* Transcript-seeded turns carry chat text only — no evidence panel. */}
      {!turn.history &&
      (turn.toolCalls.length > 0 || turn.toolResults.length > 0) ? (
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

function SessionPanel({
  sessions,
  activeSessionId,
  loading,
  error,
  onSelect,
  onCreate,
  onDelete,
}: {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  loading: boolean;
  error: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onDelete: (session: SessionSummary) => void;
}) {
  return (
    <aside className="session-panel">
      <div className="session-panel-header">
        <Typography.Text strong>Sessions</Typography.Text>
        <Button
          size="small"
          icon={<PlusOutlined />}
          onClick={onCreate}
          aria-label="New session"
        >
          New
        </Button>
      </div>
      {error ? (
        <Alert
          type="warning"
          showIcon
          message={error}
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
              </div>
              {session.pending_confirmation ? (
                <Tag color="warning">awaiting approval</Tag>
              ) : null}
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

export default function ChatView() {
  const { username, roles } = useAuth();
  const authenticated = Boolean(username);
  const workspace = useSessionWorkspace(authenticated);
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
  // Set while the workspace pointer is catching up to a session id learned
  // from the stream; prevents the switch effect from treating the pointer
  // move as a user-initiated session change.
  const catchingUpRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);

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
        setSession(target, transcriptToTurns(detail.transcript ?? []));
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        // Unknown/expired session (e.g. a pinned incident session that the
        // server has not created yet): open it empty — the first message
        // creates the server-side state.
        loadedRef.current.add(target);
        setSession(target, []);
      })
      .finally(() => {
        if (!controller.signal.aborted) setHistoryLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId, setSession]);

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

  // Keep the newest turn visible while streaming.
  const lastTurn = chat.turns[chat.turns.length - 1];
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat.turns.length, lastTurn?.replyText, historyLoading]);

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

  const submitMessage = (message: string) => {
    const text = message.trim();
    if (!text || !authenticated || chat.streaming) return;
    speech.stop();
    setDraft("");
    const inputModality = voiceUsedRef.current ? "voice" : undefined;
    voiceUsedRef.current = false;
    void chat.send(text, { userId: username ?? undefined, inputModality });
  };

  return (
    <div className="chat-view">
      <SessionPanel
        sessions={mergedSessions}
        activeSessionId={workspace.activeSessionId}
        loading={workspace.loading}
        error={workspace.error}
        onSelect={setActiveSessionId}
        onCreate={() => void workspace.createAndOpen()}
        onDelete={confirmDelete}
      />
      <div className="chat-column">
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
            chat.turns.map((turn) => (
              <TurnGroup
                key={turn.id}
                turn={turn}
                canDecide={canDecide}
                busy={chat.streaming}
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
              message={speech.error}
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
              speech.supported ? (
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
              )
            }
          />
        </div>
      </div>
    </div>
  );
}
