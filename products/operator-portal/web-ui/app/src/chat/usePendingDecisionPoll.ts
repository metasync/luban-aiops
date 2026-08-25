// usePendingDecisionPoll — owner-side live decision sync (SPEC-032).
// While the active session renders a pending confirmation card, decisions
// can land from elsewhere (the approver inbox, a second browser session);
// the confirmation_result frame only rides the answering stream, so this
// hook polls the session-detail surface on a short interval and re-seeds
// the turn timeline when the state moves. Polling is bounded: it exists
// only while a card is pending (plus a settle window — the durable outcome
// lands at claim time, ahead of the resumed transcript content, SPEC-031
// review fix) and never while a stream is active, so a poll can neither
// abort nor interleave with a live stream.
import { useEffect, useRef } from "react";
import { getSession } from "../api/sessions";
import type { SessionDetail } from "../api/sessions";
import type { ChatTurn } from "../stream/useChatStream";

export const PENDING_SYNC_INTERVAL_MS = 5_000;

// Ticks to keep polling after the last pending card resolves: the resumed
// turn's transcript content lands when the resume stream ends, which can
// trail the claim-time record write by a few seconds.
export const SETTLE_TICKS = 12;

function hasPendingCard(turns: ChatTurn[]): boolean {
  return turns.some((turn) => turn.confirmationPending);
}

// Cheap change gate: identical responses never rebuild the timeline (no
// scroll disturbance, no flicker). Covers every observable move — card
// status transitions and transcript growth from the resumed turn.
function detailFingerprint(detail: SessionDetail): string {
  const records = (detail.confirmations ?? [])
    .map((record) => `${record.confirm_id}:${record.status}`)
    .join("|");
  const transcript = detail.transcript ?? [];
  const chars = transcript.reduce(
    (sum, turn) => sum + turn.content.length,
    0,
  );
  return `${transcript.length}#${chars}#${records}`;
}

export interface PendingDecisionPollOptions {
  sessionId: string | null;
  turns: ChatTurn[];
  streaming: boolean;
  // Re-seeds the timeline from the authoritative detail; ChatView routes
  // this through the same transcriptToTurns path the initial load uses.
  applyDetail: (detail: SessionDetail) => void;
}

export function usePendingDecisionPoll({
  sessionId,
  turns,
  streaming,
  applyDetail,
}: PendingDecisionPollOptions): void {
  const pending = hasPendingCard(turns);
  // Latest-value refs: a fetch started under one render must see the
  // current stream/session state before it applies anything.
  const streamingRef = useRef(streaming);
  streamingRef.current = streaming;
  const sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;
  const applyRef = useRef(applyDetail);
  applyRef.current = applyDetail;
  const settleRef = useRef(0);
  // The session the settle window belongs to: applying a decision re-seeds
  // the turns (pending → false) and restarts this effect, so the window
  // must survive that rerun — but it must never leak into another session.
  const settleSessionRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId || streaming) return;
    const settling =
      settleRef.current > 0 && settleSessionRef.current === sessionId;
    if (!pending && !settling) return;
    const capturedSession = sessionId;
    let stopped = false;
    // Baseline capture: the first tick records the current state without
    // applying, so only a genuine move re-seeds the timeline.
    let baseline: string | null = null;
    const tick = async () => {
      if (stopped) return;
      if (streamingRef.current || sessionRef.current !== capturedSession) {
        return;
      }
      try {
        const detail = await getSession(capturedSession);
        if (
          stopped ||
          streamingRef.current ||
          sessionRef.current !== capturedSession
        ) {
          return;
        }
        const fingerprint = detailFingerprint(detail);
        if (baseline === null) {
          baseline = fingerprint;
          return;
        }
        if (fingerprint === baseline) {
          // Nothing moved. While settling (no card pending anymore), the
          // window counts down and the poll stops on its own.
          if (!pending && settleRef.current > 0) {
            settleRef.current -= 1;
            if (settleRef.current === 0) {
              stopped = true;
              window.clearInterval(timer);
            }
          }
          return;
        }
        baseline = fingerprint;
        applyRef.current(detail);
        const stillPending = (detail.confirmations ?? []).some(
          (record) => record.status === "pending",
        );
        if (stillPending) {
          settleRef.current = 0;
        } else {
          // The resumed turn's content lands when the resume stream ends,
          // which trails the claim-time record write; keep polling through
          // the settle window so it surfaces without a refresh.
          settleRef.current = SETTLE_TICKS;
          settleSessionRef.current = capturedSession;
        }
      } catch {
        // Transient failures keep the last-good view; the next tick
        // retries. A transport error never means "no decision happened".
      }
    };
    const timer = window.setInterval(
      () => void tick(),
      PENDING_SYNC_INTERVAL_MS,
    );
    return () => {
      stopped = true;
      window.clearInterval(timer);
      // A new effect run starts from a fresh baseline; the settle window
      // deliberately survives (it continues on the pending → settled
      // rerun) and is scoped to its session via settleSessionRef.
    };
  }, [sessionId, streaming, pending]);
}
