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
//
// SPEC-035 R-3: the settle window is time-based (five minutes) instead of
// a tick budget. A resumed turn that runs tools before summarizing can
// outlast the old 60-second budget, and background tabs throttle
// setInterval — so the window is a deadline, every applied change resets
// it, and a visibility/focus kick ticks immediately when the tab returns
// to the foreground.
//
// Returns `{ settling }` — true from the moment a decision is applied
// (card transitions out of pending) until the agent's resumed response
// arrives (transcript grows). ChatView uses this to show an "Agent is
// working..." indicator during the gap.
import { useEffect, useRef, useState } from "react";
import { getSession } from "../api/sessions";
import type { SessionDetail } from "../api/sessions";
import type { ChatTurn } from "../stream/useChatStream";

export const PENDING_SYNC_INTERVAL_MS = 5_000;

// How long to keep polling after the last pending card resolves: the
// resumed turn's transcript content lands when the resume stream ends,
// which trails the claim-time record write by the tool run plus the
// summary generation — comfortably inside five minutes, and every change
// that lands resets the deadline.
export const SETTLE_WINDOW_MS = 300_000;

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

// Isolate the transcript portion so we can detect "records changed but
// transcript stayed the same" (decision applied, agent still working)
// versus "transcript grew" (agent response arrived).
function transcriptFingerprint(detail: SessionDetail): string {
  const transcript = detail.transcript ?? [];
  const chars = transcript.reduce(
    (sum, turn) => sum + turn.content.length,
    0,
  );
  return `${transcript.length}#${chars}`;
}

export interface PendingDecisionPollOptions {
  sessionId: string | null;
  turns: ChatTurn[];
  streaming: boolean;
  // Re-seeds the timeline from the authoritative detail; ChatView routes
  // this through the same transcriptToTurns path the initial load uses.
  applyDetail: (detail: SessionDetail) => void;
}

export interface PendingDecisionPollResult {
  // True from the moment a decision is applied until the agent's resumed
  // response arrives (transcript grows). Drives the "Agent is working..."
  // activity indicator in ChatView.
  settling: boolean;
}

export function usePendingDecisionPoll({
  sessionId,
  turns,
  streaming,
  applyDetail,
}: PendingDecisionPollOptions): PendingDecisionPollResult {
  const pending = hasPendingCard(turns);
  const [settling, setSettling] = useState(false);
  // Latest-value refs: a fetch started under one render must see the
  // current stream/session state before it applies anything.
  const streamingRef = useRef(streaming);
  streamingRef.current = streaming;
  const sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;
  const applyRef = useRef(applyDetail);
  applyRef.current = applyDetail;
  // Deadline (epoch ms) of the settle window, 0 when inactive. Applying a
  // decision re-seeds the turns (pending → false) and restarts this
  // effect, so the window must survive that rerun — but it must never
  // leak into another session, hence the session-scoped companion ref.
  const settleUntilRef = useRef(0);
  const settleSessionRef = useRef<string | null>(null);
  // Track the transcript fingerprint at the moment the decision was
  // applied so we can detect when new content arrives.
  const transcriptAtDecisionRef = useRef<string | null>(null);

  useEffect(() => {
    if (!sessionId || streaming) return;
    const settling_ =
      settleUntilRef.current > Date.now() &&
      settleSessionRef.current === sessionId;
    if (!pending && !settling_) return;
    const capturedSession = sessionId;
    let stopped = false;
    // Baseline capture: the first tick records the current state without
    // applying, so only a genuine move re-seeds the timeline.
    let baseline: string | null = null;
    let timer: number | undefined;
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
          // Nothing moved. While settling (no card pending anymore), a
          // lapsed window ends the poll on its own.
          if (
            !pending &&
            settleUntilRef.current > 0 &&
            Date.now() >= settleUntilRef.current
          ) {
            settleUntilRef.current = 0;
            setSettling(false);
            transcriptAtDecisionRef.current = null;
            stopped = true;
            if (timer !== undefined) window.clearInterval(timer);
          }
          return;
        }
        baseline = fingerprint;

        // Detect whether the transcript grew (agent response arrived) or
        // only the records changed (decision applied, agent still working).
        const currentTranscript = transcriptFingerprint(detail);
        const transcriptGrew =
          transcriptAtDecisionRef.current !== null &&
          currentTranscript !== transcriptAtDecisionRef.current;
        if (transcriptGrew) {
          // Transcript grew — the agent's resumed response has arrived.
          setSettling(false);
          transcriptAtDecisionRef.current = null;
        }

        applyRef.current(detail);
        const stillPending = (detail.confirmations ?? []).some(
          (record) => record.status === "pending",
        );
        if (stillPending) {
          settleUntilRef.current = 0;
        } else {
          // The resumed turn's content lands when the resume stream ends,
          // which trails the claim-time record write; keep polling until
          // the deadline. Every applied change resets it, so a slow tool
          // run followed by a late summary still surfaces.
          settleUntilRef.current = Date.now() + SETTLE_WINDOW_MS;
          settleSessionRef.current = capturedSession;
          // Only activate settling when this tick is the decision moment
          // (records changed, transcript did NOT grow). If the transcript
          // grew in this same tick the response already arrived — don't
          // re-enter settling.
          if (!transcriptGrew && transcriptAtDecisionRef.current === null) {
            transcriptAtDecisionRef.current = currentTranscript;
            setSettling(true);
          }
        }
      } catch {
        // Transient failures keep the last-good view; the next tick
        // retries. A transport error never means "no decision happened".
      }
    };
    timer = window.setInterval(
      () => void tick(),
      PENDING_SYNC_INTERVAL_MS,
    );
    // Background tabs throttle setInterval (and freeze it after a while),
    // which could starve the settle window while the operator watches the
    // approver window; tick immediately whenever this tab comes back.
    const kick = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", kick);
    window.addEventListener("focus", kick);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", kick);
      window.removeEventListener("focus", kick);
      // A new effect run starts from a fresh baseline; the settle window
      // deliberately survives (it continues on the pending → settled
      // rerun) and is scoped to its session via settleSessionRef.
    };
  }, [sessionId, streaming, pending]);

  // Clear settling when the session changes or streaming starts (the
  // operator's own decide() flow handles the indicator via stream state).
  useEffect(() => {
    if (streaming) {
      setSettling(false);
      transcriptAtDecisionRef.current = null;
    }
  }, [streaming]);

  // Reset all settle state on session change so the indicator never leaks
  // into a newly selected session.
  useEffect(() => {
    setSettling(false);
    transcriptAtDecisionRef.current = null;
    settleUntilRef.current = 0;
    settleSessionRef.current = null;
  }, [sessionId]);

  return { settling };
}
