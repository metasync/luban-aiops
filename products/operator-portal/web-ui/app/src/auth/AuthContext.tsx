import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  completeLoginFromCallback,
  logout as oidcLogout,
  refreshAuthenticatedIdentity,
  scheduleTokenRefresh,
  startLogin,
} from "./oidc";
import { loadAuthSession, type AuthSession } from "./storage";

export interface AuthContextValue {
  session: AuthSession | null;
  booting: boolean;
  authError: string | null;
  username: string | null;
  roles: string[];
  login: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [booting, setBooting] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const handleRefresh = useCallback((refreshed: AuthSession | null) => {
    setSession(refreshed ?? loadAuthSession());
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const fromCallback = await completeLoginFromCallback();
        if (cancelled) return;
        if (fromCallback) {
          setSession(fromCallback);
          scheduleTokenRefresh(fromCallback, handleRefresh);
          setBooting(false);
          return;
        }
        const existing = loadAuthSession();
        if (existing?.access_token) {
          scheduleTokenRefresh(existing, handleRefresh);
        }
        const refreshed = await refreshAuthenticatedIdentity();
        if (!cancelled) {
          setSession(refreshed);
        }
      } catch (error) {
        if (!cancelled) {
          setAuthError(error instanceof Error ? error.message : String(error));
        }
      } finally {
        if (!cancelled) setBooting(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [handleRefresh]);

  const login = useCallback(async () => {
    setAuthError(null);
    try {
      await startLogin();
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  const logout = useCallback(async () => {
    setSession(null);
    await oidcLogout();
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      session,
      booting,
      authError,
      username: session?.identity?.username ?? null,
      roles: session?.identity?.roles ?? [],
      login,
      logout,
    }),
    [session, booting, authError, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return value;
}
