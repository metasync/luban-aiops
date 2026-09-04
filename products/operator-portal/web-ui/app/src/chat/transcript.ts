// Transcript seeding (SPEC-023 R-3): map the SPEC-022 transcript shape
// into the chat turn model so a resumed session renders like a live one.
// SPEC-025 R-3: persisted tool evidence groups attach to the matching
// assistant turn by turn_index, so replay renders the same evidence card
// the live stream showed.
// SPEC-031 R-2: durable confirmation records merge into the turn timeline
// so cards survive re-login; decided records render read-only with
// decider attribution.
import type {
  ConfirmationRecord,
  EvidenceFrame,
  EvidenceTurn,
  TranscriptTurn,
} from "../api/sessions";
import type {
  ExecutionReceipt,
  FlowSummary,
  PendingCall,
  ToolCallFrame,
  ToolResultFrame,
} from "../stream/models";
import type { ChatTurn, ConfirmationCard } from "../stream/useChatStream";

// Frame mapping mirrors the live decoder's tool_call/tool_result handling
// field-for-field so a replayed card is prop-identical to its live twin.
function toToolCallFrame(frame: EvidenceFrame): ToolCallFrame {
  return {
    kind: "tool_call",
    callId: frame.call_id,
    toolName: frame.tool_name,
    parameters: frame.parameters,
  };
}

function toToolResultFrame(frame: EvidenceFrame): ToolResultFrame {
  const evidence = frame.evidence;
  return {
    kind: "tool_result",
    callId: frame.call_id,
    toolName: frame.tool_name,
    status: frame.status || "success",
    evidence: evidence
      ? {
          executedAt: evidence.executed_at,
          durationMs:
            typeof evidence.duration_ms === "number"
              ? evidence.duration_ms
              : undefined,
          riskLevel: evidence.risk_level,
          sourceSystem: evidence.source_system,
        }
      : undefined,
    data: frame.data === undefined ? undefined : frame.data,
    dataSummary:
      frame.data_summary === undefined ? undefined : frame.data_summary,
    error: frame.error
      ? { code: frame.error.code, message: frame.error.message }
      : undefined,
    // Store-added size marker (SPEC-025 R-1): visible in the replay card.
    truncated: frame.truncated
      ? {
          reason: frame.truncated.reason,
          originalChars: frame.truncated.original_chars,
        }
      : undefined,
  };
}

function attachEvidence(turns: ChatTurn[], groups: EvidenceTurn[]): void {
  // The backend turn_index is the exchange ordinal: it equals the count of
  // user messages that preceded this exchange (0 for the first, 1 for the
  // second, etc.).  Both the original stream and the confirmation/resumed
  // stream produce the same turn_index for a given exchange (the backend
  // uses max(0, count_user_turns - 1) for the resumed stream), and the
  // evidence store merges all frames for the same turn_index into one
  // group.
  //
  // Frontend ChatTurn layout mirrors this exactly:
  //   ChatTurn 0 = user msg 1 + assistant reply 1
  //   ChatTurn 1 = user msg 2 + assistant reply 2
  //
  // Mapping: backend turn_index k → ChatTurn k (direct index).
  for (const group of groups ?? []) {
    const target = turns[group.turn_index];
    // Out-of-range groups (evidence outliving a truncated transcript) are
    // dropped, never crash the seeding path.
    if (!target) continue;
    target.requestId = group.request_id;
    for (const frame of group.frames ?? []) {
      if (frame.type === "tool_call") {
        target.toolCalls.push(toToolCallFrame(frame));
      } else if (frame.type === "tool_result") {
        target.toolResults.push(toToolResultFrame(frame));
      }
    }
  }
}

// Attribution note for replayed decided cards (SPEC-031 R-2): the card
// shows who decided and when, mirroring the live FINAL_NOTES wording.
function attributionNote(record: ConfirmationRecord): string {
  if (record.status === "expired") {
    return "This confirmation expired before a decision was applied.";
  }
  const who = record.decider_user_id ? ` by ${record.decider_user_id}` : "";
  const when = record.decided_at ? ` at ${record.decided_at}` : "";
  const verb =
    record.status === "approved"
      ? "Approved"
      : record.status === "denied"
        ? "Denied"
        : `Resolved (${record.status})`;
  return `${verb}${who}${when}.`;
}

// SPEC-051 R-6: map the durable record's browser-flow headline (wire
// snake_case) to the card's view-model (camelCase). Returns undefined for
// a non-browser card or a record that predates the field, so the card
// falls back to plain tool-action rendering.
function toFlowSummary(
  summary: ConfirmationRecord["flow_summary"],
): FlowSummary | undefined {
  if (!summary) {
    return undefined;
  }
  return {
    skillId: summary.skill_id,
    origin: summary.origin,
    title: summary.title,
    description: summary.description,
    riskClass: summary.risk_class,
  };
}

// Shared by transcript seeding and the approvals inbox (SPEC-031 R-5):
// both surfaces render the same durable record through one card mapping.
export function confirmationRecordToCard(
  record: ConfirmationRecord,
): ConfirmationCard {
  const pendingCalls: PendingCall[] = (record.pending_calls ?? []).map(
    (call) => ({
      callId: call.call_id,
      toolName: call.tool_name,
      parameters: call.parameters,
      riskLevel: call.risk_level,
      // Per-call action wins; the record-level action is the parked
      // batch's highest action and keeps the tier badge alive when the
      // payload predates per-call actions.
      action: call.action ?? record.action ?? undefined,
      // SPEC-050 follow-up: pass through the element description for
      // browser interaction tools.
      displayHint: call.display_hint,
    }),
  );
  const card: ConfirmationCard = {
    confirmId: record.confirm_id,
    pendingCalls,
    // SPEC-021 R-3 parity: any non-read pending call makes the batch
    // mutating.
    mutating: pendingCalls.some(
      (call) => Boolean(call.riskLevel) && call.riskLevel !== "read",
    ),
    status: record.status,
    sessionId: record.session_id,
    deciderUserId: record.decider_user_id ?? undefined,
    decidedAt: record.decided_at ?? undefined,
    // SPEC-051 R-6: replay the browser-flow headline so a re-login renders
    // the same workflow framing the live card showed; absent for
    // non-browser cards and records that predate the field.
    flowSummary: toFlowSummary(record.flow_summary),
  };
  if (record.status !== "pending") {
    card.note = attributionNote(record);
    // SPEC-037 R-6: receipts ride decided cards only; legacy rows and
    // inbox records (no executions field) keep the card unchanged.
    const executions: ExecutionReceipt[] = (record.executions ?? []).map(
      (row) => ({
        executionId: row.execution_id,
        callId: row.call_id,
        toolName: row.tool_name,
        status: row.status,
        digestMatch: row.digest_match ?? null,
        rejectReason: row.reject_reason ?? undefined,
      }),
    );
    if (executions.length > 0) {
      card.executions = executions;
    }
  }
  return card;
}

function attachConfirmations(
  turns: ChatTurn[],
  records: ConfirmationRecord[],
  makeTurn: (userMessage: string) => ChatTurn,
): void {
  for (const record of records ?? []) {
    const card = confirmationRecordToCard(record);
    // SPEC-033 R-3: records parked after the anchoring spec carry the
    // parking turn ordinal and land under the exchange that created them.
    // Records without a usable ordinal (predating the field, or pointing
    // past a truncated transcript) keep the legacy anchor — the most
    // recent turn — and a session without any transcript turns (empty or
    // unrecoverable) gets a synthetic turn so parked requests stay
    // visible.
    const anchored =
      typeof record.turn_index === "number"
        ? turns[record.turn_index]
        : undefined;
    const target = anchored ?? turns[turns.length - 1] ?? (() => {
      const synthetic = makeTurn("");
      turns.push(synthetic);
      return synthetic;
    })();
    target.confirmations.push(card);
    if (card.status === "pending") {
      target.confirmationPending = true;
    }
  }
}

export function transcriptToTurns(
  transcript: TranscriptTurn[],
  evidenceTurns?: EvidenceTurn[] | null,
  confirmations?: ConfirmationRecord[] | null,
): ChatTurn[] {
  const turns: ChatTurn[] = [];
  const makeTurn = (userMessage: string): ChatTurn => ({
    id: `history-${crypto.randomUUID()}`,
    userMessage,
    replyText: "",
    completed: true,
    confirmationPending: false,
    toolCalls: [],
    toolResults: [],
    confirmations: [],
    history: true,
  });

  for (const turn of transcript) {
    if (turn.role === "user") {
      turns.push(makeTurn(turn.content));
      continue;
    }
    const current = turns[turns.length - 1];
    if (current) {
      current.replyText += (current.replyText ? "\n\n" : "") + turn.content;
    } else {
      // Assistant turn without a preceding user turn — keep it visible.
      const orphan = makeTurn("");
      orphan.replyText = turn.content;
      turns.push(orphan);
    }
  }
  attachEvidence(turns, evidenceTurns ?? []);
  attachConfirmations(turns, confirmations ?? [], makeTurn);
  return turns;
}

// SPEC-034 R-1 / SPEC-035 R-4: compares the timeline on screen with a
// poll re-seed and reports where new content arrived. Returns null when
// the reseed added nothing (e.g. a deny/expiry card flip with no resumed
// reply) so no highlight fires; otherwise returns the first turn that
// gained content plus how many reply chars were already on screen — the
// caller reveals everything past that offset so the operator watches the
// new words land instead of seeing a silent wall of text.
export interface ArrivalSpan {
  from: number;
  prevReplyChars: number;
}

export function detectArrivalSpan(
  previous: ChatTurn[],
  next: ChatTurn[],
): ArrivalSpan | null {
  for (let i = 0; i < next.length; i += 1) {
    const before = previous[i];
    if (!before) return { from: i, prevReplyChars: 0 };
    if (next[i].replyText.length > before.replyText.length) {
      return { from: i, prevReplyChars: before.replyText.length };
    }
  }
  return null;
}
