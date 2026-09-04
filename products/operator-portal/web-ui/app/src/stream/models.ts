// Typed models for the platform SSE stream contract (stream schema v6).
// SPEC-023 R-2: these models are the only representation of the wire
// format that views consume — nothing outside src/stream/ parses frames.

export interface ToolEvidence {
  executedAt?: string;
  durationMs?: number;
  riskLevel?: string;
  sourceSystem?: string;
}

export interface ToolError {
  code?: string;
  message?: string;
}

export interface DeltaFrame {
  kind: "delta";
  text: string;
}

export interface TerminalFrame {
  kind: "terminal";
}

export interface ToolCallFrame {
  kind: "tool_call";
  callId?: string;
  toolName?: string;
  parameters?: Record<string, unknown>;
}

export type ToolResultStatus = "success" | "error" | "denied" | (string & {});

// Store-added size marker on persisted evidence (SPEC-025 R-1); never
// present on live-stream frames, always visible in the replay card.
export interface ToolTruncated {
  reason: "entry_cap" | "session_budget" | (string & {});
  originalChars?: number;
}

export interface ToolResultFrame {
  kind: "tool_result";
  callId?: string;
  toolName?: string;
  status: ToolResultStatus;
  evidence?: ToolEvidence;
  // Presence of `data` (full output) drives the expander UI; the
  // data_summary fallback renders only when data is absent (legacy parity).
  data?: unknown;
  dataSummary?: unknown;
  error?: ToolError;
  truncated?: ToolTruncated;
}

export interface PendingCall {
  callId?: string;
  toolName?: string;
  parameters?: Record<string, unknown>;
  riskLevel?: string;
  // SPEC-030 R-5: the policy action the call was parked under; drives the
  // approval-tier badge (tools:mutate => tier_2 "approver required").
  action?: string;
  // SPEC-050 follow-up: human-readable element description for browser
  // interaction tools (web.click, web.type, etc.) so the confirmation card
  // shows what element will be affected, not just the raw ref number.
  displayHint?: string;
}

export interface ConfirmationRequestFrame {
  kind: "confirmation_request";
  confirmId: string;
  message?: string;
  pendingCalls: PendingCall[];
  // SPEC-021 R-3: any non-read pending call makes the batch mutating.
  mutating: boolean;
}

export interface ConfirmationResultFrame {
  kind: "confirmation_result";
  confirmId?: string;
  status: string;
}

export interface ErrorFrame {
  kind: "error";
  message: string;
}

export type StreamFrame =
  | DeltaFrame
  | TerminalFrame
  | ToolCallFrame
  | ToolResultFrame
  | ConfirmationRequestFrame
  | ConfirmationResultFrame
  | ErrorFrame;

// One decoded SSE `data:` event. Frames the decoder does not model (unknown
// types such as message_start) yield frame=null while still surfacing the
// session id so callers can keep the active session pointer current.
export interface DecodedEvent {
  sessionId?: string;
  frame: StreamFrame | null;
}

// Confirmation card lifecycle (ported from the legacy lockConfirmationCard
// semantics): a card is pending until a confirmation_result, an error
// frame, an HTTP 410, or an unexpected stream end locks it.
export type ConfirmationStatus =
  | "pending"
  | "approved"
  | "denied"
  | "expired"
  | "error";

// SPEC-037 R-6: read-only receipt view-model for one signed execution
// closing an approved call; seeded from session-detail records, never
// produced by the live stream.
export type ExecutionReceiptStatus =
  | "requested"
  | "succeeded"
  | "failed"
  | "timeout"
  | "rejected";

export interface ExecutionReceipt {
  executionId: string;
  callId: string;
  toolName: string;
  status: ExecutionReceiptStatus;
  digestMatch?: boolean | null;
  rejectReason?: string;
}
