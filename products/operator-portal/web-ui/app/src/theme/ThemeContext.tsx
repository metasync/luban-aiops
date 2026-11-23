import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ConfigProvider } from "antd";
import { themeForMode } from "./tokens";
import {
  DEFAULT_THEME_MODE,
  loadThemeMode,
  saveThemeMode,
  type ThemeMode,
} from "./mode";

interface ThemeModeContextValue {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

// Safe default so components that read the mode still render when no provider
// is mounted (e.g. unit tests rendering a bare <App/>). The no-op setters keep
// the UI inert rather than throwing.
const ThemeModeContext = createContext<ThemeModeContextValue>({
  mode: DEFAULT_THEME_MODE,
  setMode: () => {},
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  // Lazy init: resolve the persisted choice (or the OS preference) once, on
  // first render, so the very first paint already matches.
  const [mode, setModeState] = useState<ThemeMode>(() => loadThemeMode());

  // Paint the data-theme attribute before the browser paints to avoid a flash
  // of the wrong palette. Also persist the choice.
  useLayoutEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.dataset.theme = mode;
    }
    saveThemeMode(mode);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setModeState((current) => (current === "light" ? "dark" : "light"));
  }, []);

  const value = useMemo<ThemeModeContextValue>(
    () => ({ mode, setMode, toggleTheme }),
    [mode, setMode, toggleTheme],
  );

  return (
    <ThemeModeContext.Provider value={value}>
      <ConfigProvider theme={themeForMode(mode)}>{children}</ConfigProvider>
    </ThemeModeContext.Provider>
  );
}

export function useThemeMode(): ThemeModeContextValue {
  return useContext(ThemeModeContext);
}
