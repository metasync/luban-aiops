// useChatStream — the single view-facing surface of the stream adapter
// (SPEC-023 R-2). Owns one conversation's turn state: delta accumulation,
// tool evidence frames, and HITL confirmation cards including the resume
// flow (POST /api/v1/chat/confirm returns the resumed SSE stream).
import { useCallback, useReducer, useRef, useState } from "react";
import { currentAuthenticatedUser } from "../api/client";
import type {
  ConfirmationStatus,
  DecodedEvent,
  PendingCall,
  ToolCallFrame,
  ToolResultFrame,
} from "./models";
import {
  StreamOpenError,
  chatStreamPath,
  consumeStream,
  openStream,
} from "./transport";

export interface ConfirmationCard {
  confirmId: string;
  message?: string;
  pendingCalls: PendingCall[];
  mutating: boolean;
  status: ConfirmationStatus;
  note?: string;
  // SPEC-023 R-3 anchoring: the card stays bound to the session that
  // parked it, so approve/deny resumes that session even after the
  // operator switches away and back.
  sessionId: string | null;
}

export interface ChatTurn {
  id: string;
  userMessage: string;
  replyText: string;
  completed: boolean;
  // A parked confirmation ends the stream without message_end; views use
  // this to suppress the "no response received" placeholder (legacy parity).
  confirmationPending: boolean;
  error?: string;
  toolCalls: ToolCallFrame[];
  toolResults: ToolResultFrame[];
  confirmations: ConfirmationCard[];
  // Transcript-seeded turns carry chat text only (SPEC-022 R-1 keeps tool
  // frames out of v1 transcripts); views skip the evidence panel for them.
  history?: boolean;
}

export type ConfirmationDecision = "approve" | "deny";

const FINAL_NOTES: Partial<Record<ConfirmationStatus, string>> = {
  approved: "Approved — the parked reply resumed.",
  denied: "Denied — the refusal was reported to the agent.",
  expired: "This confirmation expired before a decision was applied.",
};

function lockCard(
  card: ConfirmationCard,
  status: ConfirmationStatus,
  note?: string,
): void {
  if (card.status !== "pending") return;
  card.status = status;
  card.note = note || FINAL_NOTES[status] || `Confirmation ${status}.`;
}

function resultStatus(raw: string): ConfirmationStatus {
  if (raw === "approved" || raw === "denied" || raw === "expired") {
    return raw;
  }
  return "error";
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

export interface SendOptions {
  userId?: string;
  // SPEC-023 R-4: voice turns arrive as transcribed text; the modality is
  // metadata only and never changes policy or HITL outcomes.
  inputModality?: "text" | "voice";
}

export interface ChatStreamApi {
  turns: ChatTurn[];
  sessionId: string | null;
  streaming: boolean;
  lastRequestId: string | null;
  send: (message: string, options?: SendOptions) => Promise<void>;
  decide: (confirmId: string, decision: ConfirmationDecision) => Promise<void>;
  // Session-switch support (SPEC-023 R-3): aborts any in-flight stream,
  // stashes the current session's turns, and restores the target session's
  // cached turns — or seeds them from `history` (the loaded transcript).
  setSession: (sessionId: string | null, history?: ChatTurn[]) => void;
}

export function useChatStream(): ChatStreamApi {
  const turnsRef = useRef<ChatTurn[]>([]);
  // Per-tab turn cache keyed by session id (SPEC-023 R-3): switching
  // sessions stashes the current turns and restores them on the way back,
  // so parked confirmation cards stay anchored to their session instead of
  // being discarded by the switch.
  const turnsCacheRef = useRef(new Map<string, ChatTurn[]>());
  const sessionIdRef = useRef<string | null>(null);
  const streamingRef = useRef(false);
  const controllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<string | null>(null);
  const [, bump] = useReducer((count: number) => count + 1, 0);
  const [streaming, setStreaming] = useState(false);

  const beginStream = () => {
    streamingRef.current = true;
    setStreaming(true);
  };
  const endStream = (owner: AbortController) => {
    // Ownership check: setSession() may supersede this stream while its
    // rejection is still settling; a superseded cleanup must not wipe the
    // replacement stream's controller and streaming flag.
    if (controllerRef.current !== owner) return;
    streamingRef.current = false;
    controllerRef.current = null;
    setStreaming(false);
    bump();
  };

  // Frame dispatch for one turn. `fallbackCard` is the card being decided
  // during a confirm-resume stream: error frames and a bare
  // confirmation_result lock it when they carry no matching confirm_id.
  const handleEvent = useCallback(
    (
      turn: ChatTurn,
      event: DecodedEvent,
      fallbackCard?: ConfirmationCard,
    ) => {
      if (event.sessionId) {
        sessionIdRef.current = event.sessionId;
      }
      const frame = event.frame;
      if (!frame) return;
      switch (frame.kind) {
        case "delta":
          turn.replyText += frame.text;
          break;
        case "tool_call":
          turn.toolCalls.push(frame);
          break;
        case "tool_result":
          turn.toolResults.push(frame);
          break;
        case "terminal":
          turn.completed = true;
          break;
        case "confirmation_request":
          // SPEC-020 R-4: the kernel parked an ASK-gated batch. The card
          // anchors to the parking session; the stream ends without
          // message_end, so mark the turn confirmation-pending.
          turn.confirmations.push({
            confirmId: frame.confirmId,
            message: frame.message,
            pendingCalls: frame.pendingCalls,
            mutating: frame.mutating,
            status: "pending",
            sessionId: sessionIdRef.current,
          });
          turn.confirmationPending = true;
          break;
        case "confirmation_result": {
          const target = frame.confirmId
            ? turn.confirmations.find((c) => c.confirmId === frame.confirmId)
            : undefined;
          const card = target ?? fallbackCard;
          if (card) {
            lockCard(card, resultStatus(frame.status), undefined);
          }
          break;
        }
        case "error":
          // Mid-stream guard (e.g. owner mismatch): the confirm stream
          // ends without a confirmation_result, so lock the pending card
          // explicitly instead of leaving it on "Approving…/Denying…".
          if (fallbackCard && fallbackCard.status === "pending") {
            lockCard(fallbackCard, "error", frame.message);
          }
          turn.error = frame.message;
          break;
      }
      bump();
    },
    [],
  );

  const send = useCallback(
    async (message: string, options: SendOptions = {}) => {
      if (streamingRef.current || !message.trim()) return;
      const controller = new AbortController();
      controllerRef.current = controller;
      const turn: ChatTurn = {
        id: crypto.randomUUID(),
        userMessage: message,
        replyText: "",
        completed: false,
        confirmationPending: false,
        toolCalls: [],
        toolResults: [],
        confirmations: [],
      };
      turnsRef.current.push(turn);
      beginStream();
      bump();
      try {
        const path = chatStreamPath({
          message,
          userId: options.userId || currentAuthenticatedUser() || "operator",
          sessionId: sessionIdRef.current,
          inputModality: options.inputModality,
        });
        const opened = await openStream(path, { signal: controller.signal });
        requestIdRef.current = opened.requestId;
        await consumeStream(opened.chunks, (event) =>
          handleEvent(turn, event),
        );
        // Natural stream end completes the turn even when no terminal
        // frame arrives (legacy parity: the kernel may close the stream
        // after its last delta without a message_end). Parked
        // confirmations keep their pending marker instead.
        if (!turn.confirmationPending) {
          turn.completed = true;
        }
      } catch (error) {
        if (isAbortError(error)) {
          // A session switch closed this stream: keep the partial reply
          // visible instead of leaving the bubble loading forever.
          if (!turn.confirmationPending) {
            turn.completed = true;
          }
        } else {
          turn.error =
            error instanceof StreamOpenError && error.status === 401
              ? "Not authenticated. Please sign in from the sidebar first."
              : error instanceof Error
                ? error.message
                : String(error);
        }
      } finally {
        endStream(controller);
      }
    },
    [handleEvent],
  );

  const decide = useCallback(
    async (confirmId: string, decision: ConfirmationDecision) => {
      if (streamingRef.current) return;
      let owner: ChatTurn | undefined;
      let card: ConfirmationCard | undefined;
      for (const turn of turnsRef.current) {
        const match = turn.confirmations.find(
          (c) => c.confirmId === confirmId && c.status === "pending",
        );
        if (match) {
          owner = turn;
          card = match;
          break;
        }
      }
      // Locked-card guard: decisions only act on pending cards.
      if (!owner || !card) return;

      const sessionId = card.sessionId ?? sessionIdRef.current;
      if (!sessionId) {
        card.note = "No active session for this confirmation.";
        bump();
        return;
      }

      const decided = card;
      const turn = owner;
      decided.note = decision === "approve" ? "Approving…" : "Denying…";
      bump();

      const controller = new AbortController();
      controllerRef.current = controller;
      beginStream();
      try {
        const opened = await openStream("/api/v1/chat/confirm", {
          method: "POST",
          body: {
            session_id: sessionId,
            confirm_id: confirmId,
            decision,
          },
          signal: controller.signal,
        });
        requestIdRef.current = opened.requestId;
        // The response IS the resumed SSE stream; it drives the parked
        // turn so tool frames and deltas attach to the same turn group.
        await consumeStream(opened.chunks, (event) =>
          handleEvent(turn, event, decided),
        );
        // Guarantee a final card state even when the stream ends without
        // a confirmation_result (truncated stream, upstream outage).
        if (decided.status === "pending") {
          lockCard(
            decided,
            "error",
            "The confirmation stream ended unexpectedly.",
          );
        }
        // A resumed stream that closes without a terminal frame still
        // completes the parked turn (legacy parity).
        turn.completed = true;
      } catch (error) {
        if (error instanceof StreamOpenError && error.status === 410) {
          lockCard(
            decided,
            "expired",
            "This confirmation expired before a decision was applied.",
          );
        } else if (error instanceof StreamOpenError) {
          // Legacy parity: the card stays pending so the operator can retry.
          decided.note = `Confirm request failed (${error.status}).`;
        } else if (!isAbortError(error)) {
          decided.note =
            error instanceof Error ? error.message : String(error);
        } else {
          // Aborted by a session switch: settle the parked turn and drop
          // the transient "Approving…/Denying…" note so the card renders
          // as plain pending (retryable) when the session comes back.
          decided.note = undefined;
          if (!turn.confirmationPending) {
            turn.completed = true;
          }
        }
      } finally {
        endStream(controller);
      }
    },
    [handleEvent],
  );

  const setSession = useCallback(
    (sessionId: string | null, history?: ChatTurn[]) => {
      controllerRef.current?.abort();
      controllerRef.current = null;
      streamingRef.current = false;
      setStreaming(false);

      const previousId = sessionIdRef.current;
      if (previousId !== null && turnsRef.current.length > 0) {
        turnsCacheRef.current.set(previousId, turnsRef.current);
      }
      sessionIdRef.current = sessionId;
      turnsRef.current =
        (sessionId !== null ? turnsCacheRef.current.get(sessionId) : undefined) ??
        history ??
        [];
      bump();
    },
    [],
  );

  return {
    turns: turnsRef.current,
    sessionId: sessionIdRef.current,
    streaming,
    lastRequestId: requestIdRef.current,
    send,
    decide,
    setSession,
  };
}
