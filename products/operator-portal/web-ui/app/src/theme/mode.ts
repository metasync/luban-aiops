// Theme mode selection: an explicit operator choice, OS-preference default,
// localStorage persistence. Mirrors the voice-language convention
// (src/voice/languages.ts). The mode drives the antd ThemeConfig algorithm
// (themeForMode) and the [data-theme] attribute that swaps the global.css
// custom properties; it is a presentation-only choice and is never sent to
// the backend.
export type ThemeMode = "dark" | "light";

export const THEME_MODES: readonly ThemeMode[] = ["dark", "light"];

// Fallback when the OS preference is unavailable (no matchMedia): keep the
// portal's shipped dark appearance.
export const DEFAULT_THEME_MODE: ThemeMode = "dark";

const STORAGE_KEY = "luban.portal.themeMode";

export function isThemeMode(value: unknown): value is ThemeMode {
  return value === "dark" || value === "light";
}

// Default resolution: honour the OS/browser preference (prefers-color-scheme)
// on first visit, falling back to dark when matchMedia is unavailable. An
// explicit `prefersDark` argument wins so callers (and tests) can inject the
// preference instead of touching the global.
export function resolveDefaultThemeMode(prefersDark?: boolean): ThemeMode {
  if (typeof prefersDark === "boolean") return prefersDark ? "dark" : "light";
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return DEFAULT_THEME_MODE;
}

export function loadThemeMode(
  prefersDark?: boolean,
  storage: Pick<Storage, "getItem"> = window.localStorage,
): ThemeMode {
  const stored = storage.getItem(STORAGE_KEY);
  if (isThemeMode(stored)) return stored;
  return resolveDefaultThemeMode(prefersDark);
}

export function saveThemeMode(
  mode: ThemeMode,
  storage: Pick<Storage, "setItem"> = window.localStorage,
): void {
  if (isThemeMode(mode)) storage.setItem(STORAGE_KEY, mode);
}
