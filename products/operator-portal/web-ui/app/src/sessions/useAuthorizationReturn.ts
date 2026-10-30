import { useEffect, useState } from "react";
import { authorizationSession, authorizationStatus } from "../api/authorizations";

interface ReturnOptions {
  booting: boolean;
  username: string | null;
  studioAllowed: boolean;
  selectOperation: (id: string) => void;
  selectDevelopment: (id: string) => void;
  navigate: (view: "chat" | "studio") => void;
}

// Only an opaque ID enters the portal. No code/state parsing, automatic Continue,
// confirmation resume, provider navigation, or credential persistence happens here.
export function useAuthorizationReturn({ booting, username, studioAllowed,
  selectOperation, selectDevelopment, navigate }: ReturnOptions): string | null {
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    const path = window.location.pathname;
    if (!path.startsWith("/authorizations/return/")) return;
    const match = /^\/authorizations\/return\/([0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})$/.exec(path);
    const clean = () => window.history.replaceState({}, "", "/");
    if (!match || window.location.search || window.location.hash) {
      clean();
      setNotice("Target authorization unavailable. Open the originating conversation.");
      return;
    }
    if (booting) return;
    if (!username) {
      setNotice("Sign in to check target authorization in the originating conversation.");
      return;
    }
    const controller = new AbortController();
    setNotice("Checking target authorization…");
    void (async () => {
      try {
        const status = await authorizationStatus(match[1], controller.signal);
        if (controller.signal.aborted) return;
        const detail = await authorizationSession(status.session_id, controller.signal);
        if (controller.signal.aborted) return;
        if (detail.session_id !== status.session_id || detail.user_id !== username
            || !detail.evidence_turns?.some((turn) => turn.frames.some((frame) =>
              frame.type === "authorization_required" && frame.auth_challenge_id === match[1]
              && frame.target === status.target))
            || !["operation", "development"].includes(detail.session_type ?? "")
            || (detail.session_type === "development" && !studioAllowed)) throw new Error();
        // ChatView's normal active-session load reconstructs the durable transcript.
        if (detail.session_type === "development") {
          selectDevelopment(detail.session_id);
          navigate("studio");
        } else {
          selectOperation(detail.session_id);
          navigate("chat");
        }
        setNotice(`Target authorization: ${status.status}. No operation was resumed.`);
      } catch {
        if (!controller.signal.aborted) {
          setNotice("Target authorization unavailable. Open the originating conversation to check again.");
        }
      } finally {
        if (!controller.signal.aborted) clean();
      }
    })();
    return () => controller.abort();
  }, [booting, username, studioAllowed, selectOperation, selectDevelopment, navigate]);
  return notice;
}
