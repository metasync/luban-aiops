// SSE frame decoder (SPEC-023 R-2). Ports the legacy app.js dispatch 1:1:
// events are separated by "\n\n", only lines starting with "data: " carry
// payloads, and the frame kind rides in `type` (or `event`), lowercased.
import type { DecodedEvent, PendingCall, StreamFrame } from "./models";

type RawPayload = Record<string, unknown>;

const DELTA_EVENT_TYPES = new Set([
  "message_delta",
  "text_block_start",
  "text_block_delta",
]);
const TERMINAL_EVENT_TYPES = new Set(["message_end", "reply_end"]);

function streamEventType(payload: RawPayload): string {
  const raw = payload.type || payload.event || "";
  return String(raw).toLowerCase();
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function asRecord(value: unknown): RawPayload | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as RawPayload)
    : undefined;
}

function isMutating(calls: PendingCall[]): boolean {
  // SPEC-021 R-3: any non-read pending call makes this a mutating batch.
  return calls.some((call) => Boolean(call.riskLevel) && call.riskLevel !== "read");
}

function toFrame(payload: RawPayload): StreamFrame | null {
  const eventType = streamEventType(payload);

  if (eventType === "tool_call") {
    return {
      kind: "tool_call",
      callId: asString(payload.call_id),
      toolName: asString(payload.tool_name),
      parameters: asRecord(payload.parameters) as Record<string, unknown> | undefined,
    };
  }
  if (eventType === "tool_result") {
    const evidence = asRecord(payload.evidence);
    const error = asRecord(payload.error);
    return {
      kind: "tool_result",
      callId: asString(payload.call_id),
      toolName: asString(payload.tool_name),
      status: asString(payload.status) || "success",
      evidence: evidence
        ? {
            executedAt: asString(evidence.executed_at),
            durationMs:
              typeof evidence.duration_ms === "number"
                ? evidence.duration_ms
                : undefined,
            riskLevel: asString(evidence.risk_level),
            sourceSystem: asString(evidence.source_system),
          }
        : undefined,
      data: payload.data === undefined ? undefined : payload.data,
      dataSummary:
        payload.data_summary === undefined ? undefined : payload.data_summary,
      error: error
        ? { code: asString(error.code), message: asString(error.message) }
        : undefined,
    };
  }
  if (eventType === "confirmation_request") {
    const pendingCalls: PendingCall[] = (
      Array.isArray(payload.pending_calls) ? payload.pending_calls : []
    ).map((call) => {
      const record = asRecord(call) ?? {};
      return {
        callId: asString(record.call_id),
        toolName: asString(record.tool_name),
        parameters: asRecord(record.parameters) as
          | Record<string, unknown>
          | undefined,
        riskLevel: asString(record.risk_level),
      };
    });
    return {
      kind: "confirmation_request",
      confirmId: asString(payload.confirm_id) || "",
      message: asString(payload.message),
      pendingCalls,
      mutating: isMutating(pendingCalls),
    };
  }
  if (eventType === "confirmation_result") {
    return {
      kind: "confirmation_result",
      confirmId: asString(payload.confirm_id),
      status: asString(payload.status) || "resolved",
    };
  }
  if (eventType === "error") {
    const error = asRecord(payload.error);
    return {
      kind: "error",
      message:
        asString(error?.message) ||
        asString(payload.message) ||
        "The stream reported an error.",
    };
  }
  if (TERMINAL_EVENT_TYPES.has(eventType)) {
    return { kind: "terminal" };
  }
  // Delta frames gate on a truthy `delta` plus the legacy type whitelist.
  if (
    DELTA_EVENT_TYPES.has(eventType) &&
    typeof payload.delta === "string" &&
    payload.delta.length > 0
  ) {
    return { kind: "delta", text: payload.delta };
  }
  // Unknown/unmodeled types (message_start, ...) carry no view state.
  return null;
}

// Decode one complete `data:` event block. Returns null for non-data
// blocks and for malformed JSON (the legacy loop would throw; skipping
// keeps a corrupt frame from killing the whole turn).
export function decodeEventBlock(block: string): DecodedEvent | null {
  if (!block.startsWith("data: ")) {
    return null;
  }
  let payload: unknown;
  try {
    payload = JSON.parse(block.slice(6));
  } catch {
    return null;
  }
  const record = asRecord(payload);
  if (!record) {
    return null;
  }
  return {
    sessionId: asString(record.session_id),
    frame: toFrame(record),
  };
}

// Incremental SSE buffer: feed raw text chunks, receive decoded events.
// The split/remainder behavior mirrors the legacy loop exactly — events
// are only emitted once their "\n\n" separator has arrived.
export class SseLineDecoder {
  private buffer = "";

  push(chunk: string): DecodedEvent[] {
    this.buffer += chunk;
    const blocks = this.buffer.split("\n\n");
    this.buffer = blocks.pop() ?? "";
    const events: DecodedEvent[] = [];
    for (const block of blocks) {
      const decoded = decodeEventBlock(block);
      if (decoded) {
        events.push(decoded);
      }
    }
    return events;
  }

  reset(): void {
    this.buffer = "";
  }
}
