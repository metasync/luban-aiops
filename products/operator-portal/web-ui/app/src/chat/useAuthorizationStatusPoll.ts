// SPEC-070 (plan line 148): bounded, visibility-aware status polling for one
// target-authorization challenge. While the inline Authorize/status/Cancel
// control is mounted and its challenge is still pending, refresh the owner-scoped
// status every two seconds; stop the moment it reaches a terminal state
// (authorized/canceled/expired/failed) or its expiry lapses, and refresh
// immediately when the tab returns to the foreground.
//
// Safety boundaries (mirroring useRecoveryPoll / usePendingDecisionPoll):
//   • it only ever names the challenge id it was given — there is no way to poll
//     another owner's challenge, and the status surface is owner-scoped
//     server-side (api/authorizations.authorizationStatus);
//   • a transient transport error keeps the last-good status and retries on the
//     next tick — an error never means "resolved" and never flips the control;
//   • stale reads are dropped when the challenge changes or the card unmounts
//     (AbortController + a captured-id guard), so a late response for a previous
//     challenge can never overwrite the current one;
//   • it owns no navigation and no mutation: Authorize/Cancel/Continue are the
//     card's explicit user actions, never a side effect of a poll.
import { useCallback, useEffect, useRef, useState } from "react";
import { authorizationStatus } from "../api/authorizations";
import type { AuthorizationStatus } from "../api/authorizations";

// Refresh cadence while a challenge is pending and visible (plan line 148).
export const AUTHORIZATION_POLL_INTERVAL_MS = 2_000;

// A challenge is settled once it leaves "pending". These four are the terminal
// vocabulary the status surface guarantees; anything else keeps polling.
const TERMINAL_STATES = new Set(["authorized", "canceled", "expired", "failed"]);

// Terminal covers both an explicit terminal state and a lapsed expiry: a
// still-"pending" row whose expires_at is in the past can never complete, so the
// control stops polling and shows it as expired rather than spinning forever.
function isSettled(status: AuthorizationStatus | null): boolean {
  // Defensive: a null/undefined/malformed read is never "settled" — it keeps the
  // last-good pending posture rather than crashing the poll loop.
  if (!status) return false;
  if (TERMINAL_STATES.has(status.status)) return true;
  const expiry = Date.parse(status.expires_at);
  return Number.isFinite(expiry) && Date.now() >= expiry;
}

export interface AuthorizationStatusPollOptions {
  // Gates the recurring poll (and the focus kick). The initial read still runs
  // so a mounted card always shows a current status; a disabled card simply does
  // not keep polling. Defaults to enabled.
  enabled?: boolean;
}

export interface AuthorizationStatusPollResult {
  // The latest owner-scoped status, or null before the first read resolves.
  status: AuthorizationStatus | null;
  // True while a recurring poll is actively running (pending + enabled + visible).
  polling: boolean;
  // Imperative re-read for the card's own actions (after Authorize/Cancel) so the
  // control updates without waiting for the next interval tick.
  refresh: () => void;
}

export function useAuthorizationStatusPoll(
  challengeId: string | null,
  options: AuthorizationStatusPollOptions = {},
): AuthorizationStatusPollResult {
  const enabled = options.enabled !== false;
  const [status, setStatus] = useState<AuthorizationStatus | null>(null);
  const [polling, setPolling] = useState(false);
  // Imperative refresh: bumping the nonce re-runs the effect (one clean read).
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  // Latest-value refs: a fetch or kick started under one render must see the
  // current status/enabled/challenge before it applies anything.
  const statusRef = useRef(status);
  statusRef.current = status;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const challengeRef = useRef(challengeId);
  challengeRef.current = challengeId;

  useEffect(() => {
    if (!challengeId) {
      setStatus(null);
      setPolling(false);
      return;
    }
    const captured = challengeId;
    const controller = new AbortController();
    let disposed = false;
    let inFlight = false;
    let timer: number | undefined;

    const active = (current: AuthorizationStatus | null) =>
      enabledRef.current &&
      !disposed &&
      document.visibilityState === "visible" &&
      !isSettled(current);

    const read = async () => {
      if (disposed || inFlight || challengeRef.current !== captured) return;
      inFlight = true;
      try {
        const next = await authorizationStatus(captured, controller.signal);
        if (disposed || challengeRef.current !== captured || controller.signal.aborted) {
          return;
        }
        setStatus(next);
        setPolling(active(next));
      } catch {
        // Transient failure keeps the last-good view; the next tick retries.
        if (!disposed && challengeRef.current === captured) {
          setPolling(active(statusRef.current));
        }
      } finally {
        inFlight = false;
      }
    };

    // A new challenge (or an imperative refresh) starts from a clean slate so a
    // stale terminal state from a previous challenge never gates this one.
    setStatus(null);
    setPolling(active(null));
    void read();
    timer = window.setInterval(() => {
      // Self-clear once settled or disabled: the interval never outlives the
      // pending window and never fetches a settled challenge again.
      if (isSettled(statusRef.current) || !enabledRef.current) {
        if (timer !== undefined) window.clearInterval(timer);
        setPolling(false);
        return;
      }
      if (document.visibilityState !== "visible") return;
      void read();
    }, AUTHORIZATION_POLL_INTERVAL_MS);

    // Background tabs throttle setInterval (and freeze it after a while); tick
    // immediately whenever the tab returns so a challenge that settled while the
    // operator was on the provider page surfaces at once.
    const kick = () => {
      if (disposed) return;
      if (document.visibilityState !== "visible") {
        setPolling(false);
        return;
      }
      setPolling(active(statusRef.current));
      if (!isSettled(statusRef.current) && enabledRef.current) void read();
    };
    document.addEventListener("visibilitychange", kick);
    window.addEventListener("focus", kick);
    return () => {
      disposed = true;
      controller.abort();
      if (timer !== undefined) window.clearInterval(timer);
      document.removeEventListener("visibilitychange", kick);
      window.removeEventListener("focus", kick);
    };
  }, [challengeId, enabled, nonce]);

  return { status, polling, refresh };
}
