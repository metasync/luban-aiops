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
  type SessionSummary,
} from "../api/sessions";

const ACTIVE_SESSION_KEY = "luban.portal.activeSessionId";
const POLL_INTERVAL_MS = 30_000;

export interface DeleteOutcome {
  ok: boolean;
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
  remove: (sessionId: string) => Promise<DeleteOutcome>;
  // SPEC-023 R-3 deep links: incident sessions appear as extra panel
  // entries even before the server list catches up.
  pinned: SessionSummary[];
  pinIncidentSession: (incidentId: string) => string;
}

function loadActiveSessionId(): string | null {
  return window.sessionStorage.getItem(ACTIVE_SESSION_KEY);
}

function saveActiveSessionId(sessionId: string | null): void {
  if (sessionId) {
    window.sessionStorage.setItem(ACTIVE_SESSION_KEY, sessionId);
  } else {
    window.sessionStorage.removeItem(ACTIVE_SESSION_KEY);
  }
}

export function useSessionWorkspace(authenticated: boolean): SessionWorkspace {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [pinned, setPinned] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionIdState] = useState<string | null>(
    loadActiveSessionId(),
  );
  const aliveRef = useRef(true);

  const refresh = useCallback(async () => {
    if (!authenticated) {
      setSessions([]);
      return;
    }
    try {
      const result = await listSessions();
      if (!aliveRef.current) return;
      setSessions(result);
      setError(null);
    } catch (err) {
      if (!aliveRef.current) return;
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [authenticated]);

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

  const setActiveSessionId = useCallback((sessionId: string | null) => {
    setActiveSessionIdState(sessionId);
    saveActiveSessionId(sessionId);
  }, []);

  const createAndOpen = useCallback(async (): Promise<string | null> => {
    try {
      const detail = await createSession();
      setActiveSessionId(detail.session_id);
      await refresh();
      return detail.session_id;
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return null;
    }
  }, [refresh, setActiveSessionId]);

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

  const pinIncidentSession = useCallback(
    (incidentId: string): string => {
      const sessionId = `incident-${incidentId}`;
      setPinned((current) =>
        current.some((entry) => entry.session_id === sessionId)
          ? current
          : [
              ...current,
              {
                session_id: sessionId,
                title: `Incident ${incidentId}`,
                created_at: new Date().toISOString(),
                last_active_at: null,
                pending_confirmation: false,
              },
            ],
      );
      setActiveSessionId(sessionId);
      return sessionId;
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
    remove,
    pinned,
    pinIncidentSession,
  };
}
