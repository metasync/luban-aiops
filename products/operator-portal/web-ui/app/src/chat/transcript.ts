// Transcript seeding (SPEC-023 R-3): map the SPEC-022 transcript shape
// into the chat turn model so a resumed session renders like a live one.
// SPEC-025 R-3: persisted tool evidence groups attach to the matching
// assistant turn by turn_index, so replay renders the same evidence card
// the live stream showed.
import type { EvidenceFrame, EvidenceTurn, TranscriptTurn } from "../api/sessions";
import type { ToolCallFrame, ToolResultFrame } from "../stream/models";
import type { ChatTurn } from "../stream/useChatStream";

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

export function transcriptToTurns(
  transcript: TranscriptTurn[],
  evidenceTurns?: EvidenceTurn[] | null,
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
  return turns;
}
