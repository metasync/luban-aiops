// SPEC-063 R-5a: bounded, visibility-aware recovery polling for unsettled
// executions on a *decided* card. A dispatch that was claimed but whose tool
// result has not durably landed (or whose outcome is unknown) can still
// settle — a late worker report may be recorded after the card first
// rendered. While the owner watches the session, refresh the detail every
// two seconds for at most 120 seconds per observation window; when the
// window lapses with the outcome still unsettled, stop and surface refresh
// guidance instead of polling forever.
//
// Safety boundaries (all mirror usePendingDecisionPoll):
//   • never races a live stream — it only runs while `!streaming`;
//   • never crosses sessions — the window is session-scoped and every
//     in-flight read is dropped when the session changes;
//   • never polls another owner's session — the detail surface is
//     owner-scoped server-side and the hook only ever names the active
//     sessionId (it has no way to name anyone else's);
//   • a late durable result that lands after the window stays readable — a
//     visibility/reload kick or the next manual refresh still fetches and
//     applies it, so polling ending never hides a recorded outcome.
import { useEffect, useRef, useState } from "react";
import { getSession } from "../api/sessions";
import type { ExecutionRecovery, SessionDetail } from "../api/sessions";
import type { ChatTurn } from "../stream/useChatStream";

// Refresh cadence while an observation window is open.
export const RECOVERY_POLL_INTERVAL_MS = 2_000;

// Hard wall-clock bound on one observation window. Past it the hook stops
// and shows refresh guidance rather than polling indefinitely.
export const RECOVERY_WINDOW_MS = 120_000;

// An execution is "unsettled" while its recovery read is available but has
// not durably recorded a result. `result_recorded` is terminal; everything
// else (claimed, unknown, registered/not-dispatched) may still move, so it
// keeps the window open. An unavailable/not_found read is not pollable —
// there is nothing to refresh until the ledger is readable again.
export function hasUnsettledExecution(turns: ChatTurn[]): boolean {
  return turns.some((turn) =>
    turn.confirmations.some((card) =>
      card.status !== "pending" && (card.executions ?? []).some((execution) => {
        const recovery = execution.recovery;
        return (
          recovery !== undefined &&
          recovery.availability === "available" &&
          recovery.state !== "result_recorded"
        );
      }),
    ),
  );
}

// Cheap change gate over the recovery projections only: identical reads
// never rebuild the timeline. Covers every observable move — a state
// transition, a receipt landing, an observation being appended, or a
// continuation cursor appearing.
function recoveryFingerprint(
  rows: { id: string; recovery?: ExecutionRecovery | null }[],
): string {
  // Ignore the moving read clock, but not equal-sized changed history,
  // stop flags, receipt identities, or any other durable recovery fact.
  return JSON.stringify(
    rows.map(({ id, recovery }) => {
      const facts = recovery
        ? Object.fromEntries(Object.entries(recovery).filter(([key]) => key !== "as_of"))
        : null;
      return [id, facts];
    }).sort(([a], [b]) => String(a).localeCompare(String(b))),
    (_key, value) => value && typeof value === "object" && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)))
      : value,
  );
}

export interface RecoveryPollOptions {
  sessionId: string | null;
  turns: ChatTurn[];
  streaming: boolean;
  executionCursor?: string;
  // Re-seeds the timeline from the authoritative detail; ChatView routes
  // this through the same transcriptToTurns path the initial load uses.
  applyDetail: (detail: SessionDetail) => void;
}

export interface RecoveryPollResult {
  // True while a bounded observation window is actively polling.
  recoveryPolling: boolean;
  // True once a window lapsed with the outcome still unsettled — ChatView
  // shows refresh guidance rather than polling forever. Cleared on session
  // change and when a fresh window opens.
  recoveryGuidance: boolean;
}

export function useRecoveryPoll({
  sessionId,
  turns,
  streaming,
  executionCursor,
  applyDetail,
}: RecoveryPollOptions): RecoveryPollResult {
  const unsettled = hasUnsettledExecution(turns);
  const renderedFingerprint = recoveryFingerprint(turns.flatMap((turn) =>
    turn.confirmations.flatMap((card) => (card.executions ?? []).map((row) =>
      ({ id: row.executionId, recovery: row.recovery }))),
  ));
  const renderedRef = useRef({ sessionId, executionCursor, fingerprint: renderedFingerprint });
  const baselineRef = useRef(renderedFingerprint);
  if (renderedRef.current.sessionId !== sessionId ||
      renderedRef.current.executionCursor !== executionCursor ||
      renderedRef.current.fingerprint !== renderedFingerprint) {
    renderedRef.current = { sessionId, executionCursor, fingerprint: renderedFingerprint };
    baselineRef.current = renderedFingerprint;
  }
  const [recoveryPolling, setRecoveryPolling] = useState(false);
  const [recoveryGuidance, setRecoveryGuidance] = useState(false);
  // Latest-value refs: a fetch started under one render must see the
  // current stream/session state before it applies anything.
  const streamingRef = useRef(streaming);
  streamingRef.current = streaming;
  const sessionRef = useRef(sessionId);
  sessionRef.current = sessionId;
  const cursorRef = useRef(executionCursor);
  cursorRef.current = executionCursor;
  const applyRef = useRef(applyDetail);
  applyRef.current = applyDetail;
  // Deadline (epoch ms) of the open observation window, 0 when inactive,
  // plus the session it belongs to so a window never leaks across sessions.
  const windowUntilRef = useRef(0);
  const windowSessionRef = useRef<string | null>(null);

  useEffect(() => {
    // A live stream supersedes recovery polling, and a session with nothing
    // unsettled has nothing to refresh: drop the polling indicator. A lapsed
    // window keeps `unsettled` true, so it never reaches these branches and
    // its guidance survives until the execution settles or the session
    // changes — both of which rerun this effect.
    if (windowSessionRef.current !== sessionId) {
      windowUntilRef.current = 0;
      windowSessionRef.current = sessionId;
      setRecoveryGuidance(false);
    }
    if (!sessionId || streaming) {
      setRecoveryPolling(false);
      return;
    }
    if (!unsettled) {
      // Settled, or the newly selected session has no unsettled execution:
      // close any window and clear both indicators so neither the window nor
      // a stale "refresh" hint leaks across a session change.
      windowUntilRef.current = 0;
      windowSessionRef.current = null;
      setRecoveryPolling(false);
      setRecoveryGuidance(false);
      return;
    }
    const capturedSession = sessionId;
    const controller = new AbortController();
    let disposed = false;
    let inFlight = false;
    let timer: number | undefined;
    // Retain even an expired deadline across stream pauses and renders.
    // Focus/visibility may refresh once, but never restart automatic polling.
    if (windowUntilRef.current === 0) {
      windowUntilRef.current = Date.now() + RECOVERY_WINDOW_MS;
      windowSessionRef.current = capturedSession;
      setRecoveryGuidance(false);
    }
    const updateWindow = () => {
      const expired = Date.now() >= windowUntilRef.current;
      if (expired && timer !== undefined) window.clearInterval(timer);
      setRecoveryPolling(!expired && document.visibilityState === "visible");
      setRecoveryGuidance(expired);
      return expired;
    };
    updateWindow();
    const tick = async (foregroundRefresh = false) => {
      if (disposed || streamingRef.current || sessionRef.current !== capturedSession) return;
      const expired = updateWindow();
      if (inFlight || document.visibilityState !== "visible" ||
          (expired && !foregroundRefresh)) return;
      inFlight = true;
      try {
        const detail = await getSession(capturedSession, controller.signal,
          executionCursor ? { executionCursor } : undefined);
        if (
          disposed ||
          streamingRef.current ||
          document.visibilityState !== "visible" ||
          sessionRef.current !== capturedSession ||
          cursorRef.current !== executionCursor ||
          detail.session_id !== capturedSession
        ) {
          return;
        }
        const fingerprint = recoveryFingerprint((detail.confirmations ?? [])
          .flatMap((card) => (card.executions ?? []).map((row) =>
            ({ id: row.execution_id, recovery: row.recovery }))));
        // Compare the first response to the rendered view, not to itself.
        if (fingerprint === baselineRef.current) return;
        applyRef.current(detail);
        baselineRef.current = fingerprint;
      } catch {
        // Transient failures keep the last-good view; the next tick retries.
        // A transport error never means "the outcome resolved".
      } finally {
        inFlight = false;
      }
    };
    if (Date.now() < windowUntilRef.current) {
      timer = window.setInterval(() => void tick(), RECOVERY_POLL_INTERVAL_MS);
    }
    // Background tabs throttle setInterval (and freeze it after a while),
    // which could starve the window; tick immediately whenever this tab
    // comes back to the foreground — the "resume one refresh on
    // visibility/reload" requirement.
    const kick = () => {
      updateWindow();
      if (document.visibilityState === "visible") void tick(true);
    };
    document.addEventListener("visibilitychange", kick);
    window.addEventListener("focus", kick);
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", kick);
      window.removeEventListener("focus", kick);
      // The window deliberately survives this cleanup (it continues across an
      // apply-triggered rerun) and is scoped to its session via the refs.
    };
  }, [sessionId, streaming, unsettled, executionCursor]);

  return { recoveryPolling, recoveryGuidance };
}
