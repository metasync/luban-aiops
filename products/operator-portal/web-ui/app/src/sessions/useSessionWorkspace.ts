// Session workspace state (SPEC-023 R-3, consuming SPEC-022 Appendix A):
// panel list with 30s polling, per-tab active-session persistence, create,
// delete with parked/not-found mapping, and pinned incident deep-link
// entries.
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/client";
import {
  createSession,
  deleteSession,
  listSessions,
  renameSession,
  type SessionSummary,
} from "../api/sessions";

// SPEC-056 R-2: the active-session pointer is namespaced per mode so Chat
// (operation) and Studio (development) never fight over one key — each entry
// restores its own last-open session on reload.
const ACTIVE_SESSION_KEY_PREFIX = "luban.portal.activeSessionId";
const POLL_INTERVAL_MS = 30_000;

// SPEC-056 R-2: which entry a workspace instance serves. `operation` is Chat
// (and Incidents/Documents/Settings, which all deal in operation sessions);
// `development` is Studio. The mode fixes exactly three things — the birth
// `session_type`, the list scope, and the active-session key namespace — and
// nothing in the trust path (R-5).
export type SessionMode = "operation" | "development";

function activeSessionKey(mode: SessionMode): string {
  return `${ACTIVE_SESSION_KEY_PREFIX}.${mode}`;
}

export interface DeleteOutcome {
  ok: boolean;
  message?: string;
}

// SPEC-039 R-7: owner rename outcome; the neutral 404 wording matches
// the delete anti-enumeration message by design.
export interface RenameOutcome {
  ok: boolean;
  message?: string;
}

// SPEC-055 R-4: create outcome. The develop-as-you-go opener needs a
// per-call message because a refused target is the operator's to fix inline
// (the panel error banner is shared with list failures and would not say
// which field was wrong); the one-click path keeps using `sessionId`.
export interface CreateOutcome {
  ok: boolean;
  sessionId: string | null;
  message?: string;
}

export interface SessionWorkspace {
  sessions: SessionSummary[];
  loading: boolean;
  error: string | null;
  activeSessionId: string | null;
  setActiveSessionId: (sessionId: string | null) => void;
  refresh: () => Promise<void>;
  createAndOpen: () => Promise<string | null>;
  // SPEC-055 R-4: the develop-as-you-go opener — `createAndOpen` with a
  // target declared at birth, and an outcome the dialog can report inline.
  createDevelopmentSession: (skillTarget?: string) => Promise<CreateOutcome>;
  remove: (sessionId: string) => Promise<DeleteOutcome>;
  rename: (sessionId: string, title: string) => Promise<RenameOutcome>;
  // SPEC-023 R-3 deep links: incident sessions appear as extra panel
  // entries even before the server list catches up.
  pinned: SessionSummary[];
  pinIncidentSession: (incidentId: string, sessionId?: string) => string;
}

function loadActiveSessionId(mode: SessionMode): string | null {
  return window.sessionStorage.getItem(activeSessionKey(mode));
}

function saveActiveSessionId(
  mode: SessionMode,
  sessionId: string | null,
): void {
  const key = activeSessionKey(mode);
  if (sessionId) {
    window.sessionStorage.setItem(key, sessionId);
  } else {
    window.sessionStorage.removeItem(key);
  }
}

export function useSessionWorkspace(
  authenticated: boolean,
  mode: SessionMode = "operation",
): SessionWorkspace {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [pinned, setPinned] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(
    loadActiveSessionId(mode),
  );
  const aliveRef = useRef(true);
  // SPEC-035 R-5: monotonic refresh sequence. A decision can trigger a
  // refresh while a 30s-cadence fetch is still in flight; if the older
  // response lands last it would overwrite the fresh pending-confirmation
  // flags. Only the newest sequence may apply its result.
  const refreshSeqRef = useRef(0);

  const refresh = useCallback(async () => {
    if (!authenticated) {
      setSessions([]);
      return;
    }
    refreshSeqRef.current += 1;
    const seq = refreshSeqRef.current;
    try {
      const result = await listSessions(undefined, mode);
      if (!aliveRef.current || seq !== refreshSeqRef.current) return;
      setSessions(result);
      setError(null);
    } catch (err) {
      if (!aliveRef.current || seq !== refreshSeqRef.current) return;
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [authenticated, mode]);

  useEffect(() => {
    aliveRef.current = true;
    setLoading(true);
    void refresh().finally(() => {
      if (aliveRef.current) setLoading(false);
    });
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      aliveRef.current = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  const setActiveSessionId = useCallback(
    (sessionId: string | null) => {
      setActiveSessionIdState(sessionId);
      saveActiveSessionId(mode, sessionId);
    },
    [mode],
  );

  // One implementation, two contracts: the one-click panel path wants the id
  // (or null), the develop-as-you-go dialog wants a message it can show
  // against the target field. A refused target leaves nothing behind — the
  // agent validates it before the session exists, so there is no half-created
  // session to clean up and no refresh to run.
  const createDevelopmentSession = useCallback(
    async (skillTarget?: string): Promise<CreateOutcome> => {
      try {
        const detail = await createSession(undefined, skillTarget, mode);
        setActiveSessionId(detail.session_id);
        await refresh();
        return { ok: true, sessionId: detail.session_id };
      } catch (err) {
        const text = err instanceof Error ? err.message : String(err);
        setError(text);
        if (err instanceof ApiError && err.status === 422) {
          return {
            ok: false,
            sessionId: null,
            message:
              "Enter an absolute http(s) URL. A target with no origin can " +
              "never be corroborated against the session's captured steps, " +
              "and no session was created.",
          };
        }
        return { ok: false, sessionId: null, message: text };
      }
    },
    [refresh, setActiveSessionId, mode],
  );

  const createAndOpen = useCallback(async (): Promise<string | null> => {
    const outcome = await createDevelopmentSession();
    return outcome.sessionId;
  }, [createDevelopmentSession]);

  const remove = useCallback(
    async (sessionId: string): Promise<DeleteOutcome> => {
      try {
        await deleteSession(sessionId);
        if (activeSessionId === sessionId) {
          setActiveSessionId(null);
        }
        await refresh();
        return { ok: true };
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          return {
            ok: false,
            message:
              "This session has a confirmation awaiting approval. Approve or deny it before deleting the session.",
          };
        }
        if (err instanceof ApiError && err.status === 404) {
          // Anti-enumeration: the neutral wording is deliberate.
          await refresh();
          return { ok: false, message: "Session not found." };
        }
        return {
          ok: false,
          message: err instanceof Error ? err.message : String(err),
        };
      }
    },
    [activeSessionId, refresh, setActiveSessionId],
  );

  const rename = useCallback(
    async (sessionId: string, title: string): Promise<RenameOutcome> => {
      try {
        await renameSession(sessionId, title);
        await refresh();
        return { ok: true };
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          // Anti-enumeration: the neutral wording is deliberate.
          await refresh();
          return { ok: false, message: "Session not found." };
        }
        if (err instanceof ApiError && err.status === 400) {
          return {
            ok: false,
            message: "Titles must be 1–80 characters after trimming.",
          };
        }
        return {
          ok: false,
          message: err instanceof Error ? err.message : String(err),
        };
      }
    },
    [refresh],
  );

  const pinIncidentSession = useCallback(
    (incidentId: string, sessionId?: string): string => {
      // The incident detail carries its triage session id; fall back to the
      // well-known incident-<id> naming (legacy parity).
      const resolvedId = sessionId || `incident-${incidentId}`;
      setPinned((current) =>
        current.some((entry) => entry.session_id === resolvedId)
          ? current
          : [
              ...current,
              {
                session_id: resolvedId,
                title: `Incident ${incidentId}`,
                created_at: new Date().toISOString(),
                last_active_at: null,
                pending_confirmation: false,
                // SPEC-056 R-1: an incident triage session is operational
                // work, so the synthetic pinned entry is typed `operation`.
                session_type: "operation",
              },
            ],
      );
      setActiveSessionId(resolvedId);
      return resolvedId;
    },
    [setActiveSessionId],
  );

  return {
    sessions,
    loading,
    error,
    activeSessionId,
    setActiveSessionId,
    refresh,
    createAndOpen,
    createDevelopmentSession,
    remove,
    rename,
    pinned,
    pinIncidentSession,
  };
}
