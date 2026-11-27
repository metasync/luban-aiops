// SSE frame decoder (SPEC-023 R-2). Ports the legacy app.js dispatch 1:1:
// events are separated by "\n\n", only lines starting with "data: " carry
// payloads, and the frame kind rides in `type` (or `event`), lowercased.
import type {
  ChangeRequest,
  ChangeRequestField,
  ClarificationAnswer,
  ClarificationOption,
  ClarificationQuestion,
  DecodedEvent,
  FlowSummary,
  PendingCall,
  StreamFrame,
} from "./models";

type RawPayload = Record<string, unknown>;

const DELTA_EVENT_TYPES = new Set([
  "message_delta",
  "text_block_start",
  "text_block_delta",
]);
const TERMINAL_EVENT_TYPES = new Set(["message_end", "reply_end"]);

// SPEC-030 R-5: parked-call policy actions the card understands; anything
// else is dropped so unknown future actions degrade to tier_1 rendering.
const PENDING_CALL_ACTIONS = new Set(["tools:invoke", "tools:mutate"]);

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

// SPEC-051 R-6: parse the card-level browser-flow headline. Returns
// undefined for a non-browser card (no flow_summary on the wire) so the
// card falls back to plain tool-action rendering.
function toFlowSummary(value: unknown): FlowSummary | undefined {
  const record = asRecord(value);
  if (!record) {
    return undefined;
  }
  return {
    skillId: asString(record.skill_id),
    origin: asString(record.origin),
    title: asString(record.title),
    description: asString(record.description),
    flowIntent: asString(record.flow_intent),
    riskClass: asString(record.risk_class),
  };
}

// SPEC-054 R-3: parse one pending call's change-request projection. Returns
// undefined unless the payload is an object carrying a string `summary`
// (mirrors the kernel/routes coercion), so a malformed or absent projection
// degrades to today's tool-level rendering rather than an empty node. Field
// rows without a usable label are dropped; a masked row's value already
// arrives as the mask token from the kernel (the portal never unmasks).
function toChangeRequest(value: unknown): ChangeRequest | undefined {
  const record = asRecord(value);
  const summary = asString(record?.summary);
  if (!record || summary === undefined) {
    return undefined;
  }
  const fields: ChangeRequestField[] | undefined = Array.isArray(record.fields)
    ? record.fields
        .map((row): ChangeRequestField | undefined => {
          const field = asRecord(row);
          const label = asString(field?.label);
          if (!field || label === undefined) {
            return undefined;
          }
          return {
            label,
            value: typeof field.value === "string" ? field.value : "",
            masked: field.masked === true,
          };
        })
        .filter((field): field is ChangeRequestField => field !== undefined)
    : undefined;
  return {
    summary,
    ...(fields && fields.length > 0 ? { fields } : {}),
    ...(asString(record.warning) ? { warning: asString(record.warning) } : {}),
    ...(record.requires_acknowledgment === true ? { requiresAcknowledgment: true } : {}),
  };
}

export function toSecretDeliveryFrame(payload: {
  delivery_id?: unknown; channel?: unknown; expires_at?: unknown;
}): import("./models").SecretDeliveryFrame | null {
  const deliveryId = asString(payload.delivery_id);
  const expiresAt = asString(payload.expires_at);
  if (
    !deliveryId || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(deliveryId) ||
    payload.channel !== "portal_copy" || !expiresAt ||
    !/(Z|[+-]\d{2}:\d{2})$/.test(expiresAt) || !Number.isFinite(Date.parse(expiresAt))
  ) return null;
  return { kind: "secret_delivery", deliveryId, expiresAt, channel: "portal_copy" };
}

export function toAuthorizationRequiredFrame(payload: {
  auth_challenge_id?: unknown; target?: unknown; expires_at?: unknown;
}): import("./models").AuthorizationRequiredFrame | null {
  const authChallengeId = asString(payload.auth_challenge_id);
  const target = asString(payload.target);
  const expiresAt = asString(payload.expires_at);
  if (!authChallengeId || !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(authChallengeId) ||
    !target?.trim()) return null;
  if (payload.expires_at !== undefined && (!expiresAt ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(expiresAt) ||
    !Number.isFinite(Date.parse(expiresAt)))) return null;
  return { kind: "authorization_required", authChallengeId, target,
    ...(expiresAt ? { expiresAt } : {}) };
}

function toFrame(payload: RawPayload): StreamFrame | null {
  const eventType = streamEventType(payload);

  if (eventType === "secret_delivery") return toSecretDeliveryFrame(payload);
  if (eventType === "authorization_required") return toAuthorizationRequiredFrame(payload);
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
      const action = asString(record.action);
      return {
        callId: asString(record.call_id),
        toolName: asString(record.tool_name),
        parameters: asRecord(record.parameters) as
          | Record<string, unknown>
          | undefined,
        riskLevel: asString(record.risk_level),
        action: action && PENDING_CALL_ACTIONS.has(action) ? action : undefined,
        // SPEC-050 follow-up: pass through the element description for
        // browser interaction tools.
        displayHint: asString(record.display_hint),
        // SPEC-054 R-3: the per-call change-request projection (action cards).
        changeRequest: toChangeRequest(record.change_request),
      };
    });
    // SPEC-054 R-1: the parked batch's declared kind; only the two known
    // values survive, anything else degrades to tool-level rendering.
    const approvalKind = asString(payload.approval_kind);
    return {
      kind: "confirmation_request",
      confirmId: asString(payload.confirm_id) || "",
      message: asString(payload.message),
      pendingCalls,
      mutating: isMutating(pendingCalls),
      // SPEC-051 R-6: the browser-flow headline rides the frame when the
      // parked batch belongs to a bound web-check flow; absent otherwise.
      flowSummary: toFlowSummary(payload.flow_summary),
      approvalKind:
        approvalKind === "flow" || approvalKind === "action"
          ? approvalKind
          : undefined,
    };
  }
  if (eventType === "confirmation_result") {
    return {
      kind: "confirmation_result",
      confirmId: asString(payload.confirm_id),
      status: asString(payload.status) || "resolved",
    };
  }
  if (eventType === "clarification_request") {
    // SPEC-080 R-3/R-6: the agent parked a read-only AskUser clarification.
    // Project the wire questions to the card view-model, defensively mirroring
    // the agentscope bounds the kernel already enforced (2-4 options) and NEVER
    // reading ``preview`` — a named fast-follow that does not ride v14.
    const questions: ClarificationQuestion[] = (
      Array.isArray(payload.questions) ? payload.questions : []
    )
      .map((raw): ClarificationQuestion | undefined => {
        const record = asRecord(raw);
        const question = asString(record?.question);
        const header = asString(record?.header);
        if (!record || question === undefined || header === undefined) {
          return undefined;
        }
        const options: ClarificationOption[] = (
          Array.isArray(record.options) ? record.options : []
        )
          .map((rawOption): ClarificationOption | undefined => {
            const option = asRecord(rawOption);
            const label = asString(option?.label);
            const description = asString(option?.description);
            if (!option || label === undefined || description === undefined) {
              return undefined;
            }
            // ``preview`` is deliberately not read: it never rides v14 (R-6).
            return { label, description };
          })
          .filter((option): option is ClarificationOption => option !== undefined);
        if (options.length < 2) {
          return undefined;
        }
        const context = asString(record.context);
        return {
          question,
          header,
          multiSelect: record.multi_select === true,
          options,
          ...(context ? { context } : {}),
        };
      })
      .filter((item): item is ClarificationQuestion => item !== undefined);
    return {
      kind: "clarification_request",
      clarificationId: asString(payload.clarification_id) || "",
      questions,
    };
  }
  if (eventType === "clarification_result") {
    // SPEC-080 R-3: the owner's answers echoed back on the resumed turn.
    const answers: ClarificationAnswer[] | undefined = Array.isArray(payload.answers)
      ? payload.answers
          .map((raw): ClarificationAnswer | undefined => {
            const record = asRecord(raw);
            const question = asString(record?.question);
            if (!record || question === undefined) {
              return undefined;
            }
            const selected = Array.isArray(record.selected)
              ? record.selected.filter((item): item is string => typeof item === "string")
              : [];
            const other = asString(record.other);
            return { question, selected, ...(other ? { other } : {}) };
          })
          .filter((item): item is ClarificationAnswer => item !== undefined)
      : undefined;
    return {
      kind: "clarification_result",
      clarificationId: asString(payload.clarification_id),
      status: asString(payload.status) || "answered",
      ...(answers ? { answers } : {}),
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
