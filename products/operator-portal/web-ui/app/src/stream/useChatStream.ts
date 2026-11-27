// useChatStream — the single view-facing surface of the stream adapter
// (SPEC-023 R-2). Owns one conversation's turn state: delta accumulation,
// tool evidence frames, and HITL confirmation cards including the resume
// flow (POST /api/v1/chat/confirm returns the resumed SSE stream).
import { useCallback, useReducer, useRef, useState } from "react";
import { currentAuthenticatedUser } from "../api/client";
import type {
  AuthorizationRequiredFrame,
  ClarificationAnswer,
  ClarificationQuestion,
  ClarificationStatus,
  ConfirmationStatus,
  DecodedEvent,
  ExecutionReceipt,
  FlowSummary,
  PendingCall,
  SecretDeliveryFrame,
  ToolCallFrame,
  ToolResultFrame,
} from "./models";
import {
  StreamOpenError,
  alreadyResolvedDetail,
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
  // SPEC-031 R-5 attribution on durable cards (replayed from the record
  // store or flipped by a race 409): who decided and when. Undefined on
  // live undecided cards.
  deciderUserId?: string;
  decidedAt?: string;
  // SPEC-037 R-6: receipts closing the approved calls, seeded from the
  // session-detail execution rows; undefined on live cards, legacy
  // decided rows, and inbox records (decision-metadata-only surface).
  executions?: ExecutionReceipt[];
  // SPEC-051 R-6: the browser-flow headline (workflow intent + origin),
  // live from the confirmation_request frame or replayed from the durable
  // record; undefined for non-browser cards.
  flowSummary?: FlowSummary;
  // SPEC-054 R-1: the parked batch's declared kind, live from the frame or
  // replayed from the durable record; undefined for cards predating v11.
  approvalKind?: "flow" | "action";
}

// SPEC-080 R-7: a parked read-only clarification the session OWNER answers
// in-line (never routed to an approver). Mirrors ConfirmationCard's anchoring
// and lifecycle but carries the projected questions instead of pending calls,
// and resolves to "answered" rather than approved/denied.
export interface ClarificationCard {
  clarificationId: string;
  questions: ClarificationQuestion[];
  status: ClarificationStatus;
  note?: string;
  // The card stays bound to the session that parked it (SPEC-023 R-3 parity),
  // so answering resumes that session even after the operator switches away.
  sessionId: string | null;
  // The owner's answers, echoed from clarification_result or replayed from the
  // durable record on re-login; undefined on a live pending card.
  answers?: ClarificationAnswer[];
}

export interface ChatTurn {
  id: string;
  userMessage: string;
  replyText: string;
  completed: boolean;
  // A parked confirmation ends the stream without message_end; views use
  // this to suppress the "no response received" placeholder (legacy parity).
  confirmationPending: boolean;
  // SPEC-080 R-7: a parked clarification ends the stream the same way (no
  // message_end); views suppress the placeholder/spinner exactly as they do
  // for confirmationPending. Distinct flag so the two card kinds stay
  // independently inspectable (mirrors the backend park_kind discriminator).
  clarificationPending: boolean;
  error?: string;
  toolCalls: ToolCallFrame[];
  toolResults: ToolResultFrame[];
  secretDeliveries?: SecretDeliveryFrame[];
  authorizations?: AuthorizationRequiredFrame[];
  confirmations: ConfirmationCard[];
  clarifications: ClarificationCard[];
  // Transcript-seeded turns carry chat text only unless persisted tool
  // evidence is attached (SPEC-025 R-3); the request id correlates the
  // replayed evidence with the audit trail.
  history?: boolean;
  requestId?: string;
  // SPEC-035 R-2: a tool frame sets this flag so the next delta starts a
  // new paragraph — each text segment between tool calls is one reasoning
  // step, and without the break a segment-start heading glues onto the
  // previous segment's last sentence (live parity with the transcript
  // block join).
  segmentBreak?: boolean;
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

// SPEC-080 R-7: the clarification card's lifecycle mirrors ConfirmationCard's
// but resolves to "answered" (the read-only analogue of approved/denied) — a
// clarification is owner-answered in-line, never routed to an approver, so
// there is no denied state.
const CLARIFICATION_FINAL_NOTES: Partial<Record<ClarificationStatus, string>> = {
  answered: "Answered — the parked reply resumed.",
  expired: "This clarification expired before an answer was applied.",
};

function lockClarificationCard(
  card: ClarificationCard,
  status: ClarificationStatus,
  note?: string,
): void {
  if (card.status !== "pending") return;
  card.status = status;
  card.note =
    note || CLARIFICATION_FINAL_NOTES[status] || `Clarification ${status}.`;
}

function clarificationResultStatus(raw: string): ClarificationStatus {
  // v14 clarification_result status enum: "answered" | "expired" |
  // "interrupted". The portal collapses both non-answer terminal states to
  // "expired"; anything unrecognized degrades to "error" exactly as
  // resultStatus does for a confirmation.
  if (raw === "answered") return "answered";
  if (raw === "expired" || raw === "interrupted") return "expired";
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
  // SPEC-024 R-3: the composer's model selection for this turn; omitted
  // when no catalog is available so the runtime resolves its default.
  model?: string | null;
}

export interface ChatStreamApi {
  turns: ChatTurn[];
  sessionId: string | null;
  streaming: boolean;
  lastRequestId: string | null;
  send: (message: string, options?: SendOptions) => Promise<void>;
  decide: (confirmId: string, decision: ConfirmationDecision, recipientWarningAcknowledged?: boolean) => Promise<void>;
  // SPEC-080 R-7: answer a parked read-only clarification; the response is
  // the resumed SAME-turn stream (the decide() sibling for clarifications).
  answer: (clarificationId: string, answers: ClarificationAnswer[]) => Promise<void>;
  // Session-switch support (SPEC-023 R-3): aborts any in-flight stream,
  // stashes the current session's turns, and restores the target session's
  // cached turns — or seeds them from `history` (the loaded transcript).
  setSession: (sessionId: string | null, history?: ChatTurn[]) => void;
  // Authoritative re-seed of the CURRENT session's timeline (SPEC-032):
  // replaces both the live turns and the cache entry, so the per-tab
  // cache can never shadow the fresh state. Never moves the session
  // pointer and never aborts a stream.
  reseedTurns: (sessionId: string, turns: ChatTurn[]) => void;
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
  // `fallbackClarification` is the SPEC-080 R-7 sibling for an answer-resume
  // stream — the clarification card being answered when a frame carries no
  // matching clarification_id.
  const handleEvent = useCallback(
    (
      turn: ChatTurn,
      event: DecodedEvent,
      fallbackCard?: ConfirmationCard,
      fallbackClarification?: ClarificationCard,
    ) => {
      if (event.sessionId) {
        sessionIdRef.current = event.sessionId;
      }
      const frame = event.frame;
      if (!frame) return;
      switch (frame.kind) {
        case "delta":
          // SPEC-035 R-2: the first delta after a tool frame opens a new
          // paragraph so block markdown at a segment start still renders.
          if (turn.segmentBreak && turn.replyText) {
            turn.replyText += "\n\n";
          }
          turn.segmentBreak = false;
          turn.replyText += frame.text;
          break;
        case "tool_call":
          turn.segmentBreak = true;
          turn.toolCalls.push(frame);
          break;
        case "tool_result":
          turn.segmentBreak = true;
          turn.toolResults.push(frame);
          break;
        case "authorization_required":
          // SPEC-070: attach the decoded challenge so a live turn matches its
          // replayed twin (transcript.ts). The decoder already reduced it to
          // routing metadata — {kind, authChallengeId, target, expiresAt?} —
          // dropping provider_url/code/state/confirm_id, so nothing sensitive
          // rides into portal state. Deliberately inert: this neither
          // navigates nor issues a follow-up request. The Authorize/status/
          // Cancel control that acts on it is a separate consumer, enabled
          // only with trusted custody/routes.
          turn.authorizations ??= [];
          if (!turn.authorizations.some((item) => item.authChallengeId === frame.authChallengeId)) {
            turn.authorizations.push(frame);
          }
          break;
        case "secret_delivery":
          turn.secretDeliveries ??= [];
          if (!turn.secretDeliveries.some((item) => item.deliveryId === frame.deliveryId)) {
            turn.secretDeliveries.push(frame);
          }
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
            flowSummary: frame.flowSummary,
            approvalKind: frame.approvalKind,
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
        case "clarification_request":
          // SPEC-080 R-7: the agent parked a read-only AskUser clarification
          // the session OWNER answers in-line (never routed to an approver).
          // The card anchors to the parking session; the stream ends without
          // message_end, so mark the turn clarification-pending — the sibling
          // of confirmationPending, kept a distinct flag so the two park kinds
          // stay independently inspectable.
          turn.clarifications.push({
            clarificationId: frame.clarificationId,
            questions: frame.questions,
            status: "pending",
            sessionId: sessionIdRef.current,
          });
          turn.clarificationPending = true;
          break;
        case "clarification_result": {
          // The resumed stream opens with the answered clarification_result
          // (kernel parity), echoing the owner's answers; match the parked
          // card by id, else lock the card being answered during the resume.
          const target = frame.clarificationId
            ? turn.clarifications.find(
                (c) => c.clarificationId === frame.clarificationId,
              )
            : undefined;
          const card = target ?? fallbackClarification;
          if (card) {
            lockClarificationCard(
              card,
              clarificationResultStatus(frame.status),
              undefined,
            );
            if (frame.answers) {
              card.answers = frame.answers;
            }
          }
          break;
        }
        case "error":
          // Mid-stream guard (e.g. owner mismatch): the confirm stream
          // ends without a confirmation_result, so lock the pending card
          // explicitly instead of leaving it on "Approving…/Denying…". The
          // clarification resume gets the same treatment for its card.
          if (fallbackCard && fallbackCard.status === "pending") {
            lockCard(fallbackCard, "error", frame.message);
          }
          if (
            fallbackClarification &&
            fallbackClarification.status === "pending"
          ) {
            lockClarificationCard(fallbackClarification, "error", frame.message);
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
        clarificationPending: false,
        toolCalls: [],
        toolResults: [],
        confirmations: [],
        clarifications: [],
      };
      turnsRef.current.push(turn);
      beginStream();
      bump();
      const userId =
        options.userId || currentAuthenticatedUser() || "operator";
      const attempt = async (sessionId: string | null) => {
        const path = chatStreamPath({
          message,
          userId,
          sessionId,
          inputModality: options.inputModality,
          model: options.model,
        });
        const opened = await openStream(path, { signal: controller.signal });
        requestIdRef.current = opened.requestId;
        await consumeStream(opened.chunks, (event) =>
          handleEvent(turn, event),
        );
      };
      const settle = () => {
        // Natural stream end completes the turn even when no terminal
        // frame arrives (legacy parity: the kernel may close the stream
        // after its last delta without a message_end). Parked
        // confirmations and clarifications keep their pending marker instead.
        if (!turn.confirmationPending && !turn.clarificationPending) {
          turn.completed = true;
        }
      };
      try {
        await attempt(sessionIdRef.current);
        settle();
      } catch (error) {
        if (isAbortError(error)) {
          // A session switch closed this stream: keep the partial reply
          // visible instead of leaving the bubble loading forever.
          settle();
        } else if (
          error instanceof StreamOpenError &&
          error.status === 404 &&
          sessionIdRef.current
        ) {
          // Stale session pointer (deleted elsewhere, expired, or a
          // never-created pinned id): the gateway now answers 404 before
          // the SSE stream opens. Drop the pointer and retry once with
          // server-side auto-creation — the legacy first-message flow.
          sessionIdRef.current = null;
          bump();
          try {
            await attempt(null);
            settle();
          } catch (retryError) {
            if (isAbortError(retryError)) {
              settle();
            } else {
              turn.error =
                retryError instanceof Error
                  ? retryError.message
                  : String(retryError);
            }
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
    async (confirmId: string, decision: ConfirmationDecision, recipientWarningAcknowledged = false) => {
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
            ...(decision === "approve" && recipientWarningAcknowledged
              ? { recipient_warning_acknowledged: true } : {}),
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
        turn.confirmationPending = false;
      } catch (error) {
        if (error instanceof StreamOpenError && error.status === 410) {
          lockCard(
            decided,
            "expired",
            "This confirmation expired before a decision was applied.",
          );
          // Terminal: this card can never be answered again, so settle the
          // turn. Clearing confirmationPending WITHOUT completed left
          // ChatView's `loading` true forever
          // (!completed && !confirmationPending && !error), so the assistant
          // bubble spun with no reply and no error — an expired card looked
          // exactly like a hung agent even though the backend had already
          // resolved the park and the composer still worked.
          turn.completed = true;
          turn.confirmationPending = false;
        } else if (error instanceof StreamOpenError && error.status === 409) {
          // SPEC-031 R-4 race: another approver decided first. The card
          // flips to the winner's outcome with attribution instead of
          // staying pending (which would invite a doomed retry).
          const race = alreadyResolvedDetail(error.detail);
          if (race) {
            lockCard(
              decided,
              resultStatus(race.status ?? ""),
              `Already resolved${
                race.decider_user_id ? ` by ${race.decider_user_id}` : ""
              }${race.decided_at ? ` at ${race.decided_at}` : ""}.`,
            );
            decided.deciderUserId = race.decider_user_id ?? undefined;
            decided.decidedAt = race.decided_at ?? undefined;
            // Terminal for this operator, so settle the turn exactly as the
            // 410 branch does — the same spinner otherwise outlives the race.
            turn.completed = true;
            turn.confirmationPending = false;
          } else {
            // Retryable: the card stays pending, so the turn stays parked.
            // Clearing confirmationPending here spun the bubble forever and
            // dropped the session panel's "awaiting approval" tag from a card
            // the operator could still answer.
            decided.note = `Confirm request failed (409).`;
          }
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

  // SPEC-080 R-7: submit the owner's answers to a parked read-only
  // clarification. The response IS the resumed SAME-turn SSE stream, exactly
  // as decide() is for a confirmation — deltas and tool frames re-attach to
  // the parked turn and the card flips to "answered" from the echoed
  // clarification_result. Mirrors decide()'s 410/409/abort handling.
  const answer = useCallback(
    async (clarificationId: string, answers: ClarificationAnswer[]) => {
      if (streamingRef.current) return;
      let owner: ChatTurn | undefined;
      let card: ClarificationCard | undefined;
      for (const turn of turnsRef.current) {
        const match = turn.clarifications.find(
          (c) => c.clarificationId === clarificationId && c.status === "pending",
        );
        if (match) {
          owner = turn;
          card = match;
          break;
        }
      }
      // Locked-card guard: answers only act on pending cards.
      if (!owner || !card) return;

      const sessionId = card.sessionId ?? sessionIdRef.current;
      if (!sessionId) {
        card.note = "No active session for this clarification.";
        bump();
        return;
      }

      const decided = card;
      const turn = owner;
      decided.note = "Submitting…";
      bump();

      const controller = new AbortController();
      controllerRef.current = controller;
      beginStream();
      try {
        const opened = await openStream(
          `/api/v1/sessions/${encodeURIComponent(sessionId)}/clarification/answer`,
          {
            method: "POST",
            body: { clarification_id: clarificationId, answers },
            signal: controller.signal,
          },
        );
        requestIdRef.current = opened.requestId;
        // The response IS the resumed SAME-turn stream; it drives the parked
        // turn so tool frames and deltas attach to the same turn group.
        await consumeStream(opened.chunks, (event) =>
          handleEvent(turn, event, undefined, decided),
        );
        // Guarantee a final card state even when the stream ends without a
        // clarification_result (truncated stream, upstream outage).
        if (decided.status === "pending") {
          lockClarificationCard(
            decided,
            "error",
            "The clarification stream ended unexpectedly.",
          );
        }
        // A resumed stream that closes without a terminal frame still
        // completes the parked turn (legacy parity).
        turn.completed = true;
        turn.clarificationPending = false;
      } catch (error) {
        if (error instanceof StreamOpenError && error.status === 410) {
          lockClarificationCard(
            decided,
            "expired",
            "This clarification expired before an answer was applied.",
          );
          // Terminal: this card can never be answered again, so settle the
          // turn exactly as the confirmation 410 branch does.
          turn.completed = true;
          turn.clarificationPending = false;
        } else if (error instanceof StreamOpenError && error.status === 409) {
          // SPEC-080 R-4 / SPEC-031 R-4 posture: a racing second answer (or a
          // mis-routed confirmation park) flips the card to the winner's
          // outcome with attribution instead of inviting a doomed retry.
          const race = alreadyResolvedDetail(error.detail);
          if (race) {
            lockClarificationCard(
              decided,
              clarificationResultStatus(race.status ?? ""),
              `Already resolved${
                race.decider_user_id ? ` by ${race.decider_user_id}` : ""
              }${race.decided_at ? ` at ${race.decided_at}` : ""}.`,
            );
            turn.completed = true;
            turn.clarificationPending = false;
          } else {
            // Retryable: the card stays pending, so the turn stays parked.
            decided.note = `Clarification answer failed (409).`;
          }
        } else if (error instanceof StreamOpenError) {
          // Legacy parity: the card stays pending so the owner can retry.
          decided.note = `Clarification answer failed (${error.status}).`;
        } else if (!isAbortError(error)) {
          decided.note =
            error instanceof Error ? error.message : String(error);
        } else {
          // Aborted by a session switch: settle the parked turn and drop the
          // transient "Submitting…" note so the card renders as plain pending
          // (retryable) when the session comes back.
          decided.note = undefined;
          if (!turn.clarificationPending) {
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

  // SPEC-032: setSession called for the session already on screen stashes
  // the current turns into the cache and then restores that same entry —
  // a passed-in `history` never applies (the cache hit wins). The pending-
  // decision poll therefore re-seeds through this dedicated path, which
  // replaces the live turns AND the cache entry so a later switch away
  // and back restores the fresh timeline, not the shadowed stale one.
  const reseedTurns = useCallback((sessionId: string, turns: ChatTurn[]) => {
    if (sessionIdRef.current !== sessionId) return;
    turnsRef.current = turns;
    turnsCacheRef.current.set(sessionId, turns);
    bump();
  }, []);

  return {
    turns: turnsRef.current,
    sessionId: sessionIdRef.current,
    streaming,
    lastRequestId: requestIdRef.current,
    send,
    decide,
    answer,
    setSession,
    reseedTurns,
  };
}
