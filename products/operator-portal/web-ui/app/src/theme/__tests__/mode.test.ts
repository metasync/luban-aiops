// Theme-mode resolution tests: OS-preference default, injected preference,
// localStorage persistence, and rejection of invalid stored values. Mirrors
// src/voice/__tests__/languages.test.ts.
import { describe, expect, it } from "vitest";
import {
  DEFAULT_THEME_MODE,
  isThemeMode,
  loadThemeMode,
  resolveDefaultThemeMode,
  saveThemeMode,
} from "../mode";

function fakeStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => {
      data.set(key, value);
    },
    data,
  };
}

describe("isThemeMode", () => {
  it("accepts exactly the two supported modes", () => {
    expect(isThemeMode("dark")).toBe(true);
    expect(isThemeMode("light")).toBe(true);
  });

  it("rejects anything else", () => {
    expect(isThemeMode("solarized")).toBe(false);
    expect(isThemeMode("")).toBe(false);
    expect(isThemeMode(null)).toBe(false);
    expect(isThemeMode(undefined)).toBe(false);
  });
});

describe("resolveDefaultThemeMode", () => {
  it("honours an injected OS preference", () => {
    expect(resolveDefaultThemeMode(true)).toBe("dark");
    expect(resolveDefaultThemeMode(false)).toBe("light");
  });

  it("falls back to a valid mode from the environment when not injected", () => {
    // The jsdom matchMedia stub reports matches:false (setup.ts), so the
    // resolved default is light; assert it is at least a supported mode.
    expect(isThemeMode(resolveDefaultThemeMode())).toBe(true);
    expect(resolveDefaultThemeMode()).toBe("light");
  });

  it("ships dark as the no-matchMedia fallback", () => {
    expect(DEFAULT_THEME_MODE).toBe("dark");
  });
});

describe("loadThemeMode / saveThemeMode", () => {
  it("prefers a persisted supported selection over the default", () => {
    const storage = fakeStorage({ "luban.portal.themeMode": "light" });
    expect(loadThemeMode(true, storage)).toBe("light");
  });

  it("ignores a persisted invalid value and resolves the default", () => {
    const storage = fakeStorage({ "luban.portal.themeMode": "solarized" });
    expect(loadThemeMode(true, storage)).toBe("dark");
    expect(loadThemeMode(false, storage)).toBe("light");
  });

  it("persists only supported modes", () => {
    const storage = fakeStorage();
    saveThemeMode("light", storage);
    expect(storage.data.get("luban.portal.themeMode")).toBe("light");
    saveThemeMode("dark", storage);
    expect(storage.data.get("luban.portal.themeMode")).toBe("dark");
    // An invalid value must not overwrite the last good one.
    saveThemeMode("solarized" as never, storage);
    expect(storage.data.get("luban.portal.themeMode")).toBe("dark");
  });
});
