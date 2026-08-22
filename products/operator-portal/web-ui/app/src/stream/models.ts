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
}

export interface PendingCall {
  callId?: string;
  toolName?: string;
  parameters?: Record<string, unknown>;
  riskLevel?: string;
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
