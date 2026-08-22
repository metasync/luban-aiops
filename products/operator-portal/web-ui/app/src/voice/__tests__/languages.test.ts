// Recognition language resolution tests (SPEC-023 R-4): browser-locale
// default, primary-subtag mapping, en-US fallback, localStorage persistence.
import { describe, expect, it } from "vitest";
import {
  DEFAULT_VOICE_LANGUAGE,
  loadVoiceLanguage,
  resolveDefaultVoiceLanguage,
  saveVoiceLanguage,
} from "../languages";

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

describe("resolveDefaultVoiceLanguage", () => {
  it("matches an exact supported code case-insensitively", () => {
    expect(resolveDefaultVoiceLanguage("zh-CN")).toBe("zh-CN");
    expect(resolveDefaultVoiceLanguage("en-us")).toBe("en-US");
  });

  it("maps a primary subtag to the supported variant", () => {
    expect(resolveDefaultVoiceLanguage("zh-Hans-CN")).toBe("zh-CN");
    expect(resolveDefaultVoiceLanguage("en-GB")).toBe("en-US");
  });

  it("falls back to en-US for unsupported locales", () => {
    expect(resolveDefaultVoiceLanguage("fr-FR")).toBe(DEFAULT_VOICE_LANGUAGE);
    expect(resolveDefaultVoiceLanguage("ja")).toBe(DEFAULT_VOICE_LANGUAGE);
  });

  it("falls back to en-US when the browser locale is missing", () => {
    expect(resolveDefaultVoiceLanguage(undefined)).toBe(DEFAULT_VOICE_LANGUAGE);
    expect(resolveDefaultVoiceLanguage("")).toBe(DEFAULT_VOICE_LANGUAGE);
  });
});

describe("loadVoiceLanguage / saveVoiceLanguage", () => {
  it("prefers a persisted supported selection", () => {
    const storage = fakeStorage({ "luban.portal.voiceLanguage": "zh-CN" });
    expect(loadVoiceLanguage("en-US", storage)).toBe("zh-CN");
  });

  it("ignores a persisted unsupported value and resolves the default", () => {
    const storage = fakeStorage({ "luban.portal.voiceLanguage": "fr-FR" });
    expect(loadVoiceLanguage("en-GB", storage)).toBe("en-US");
  });

  it("persists only supported codes", () => {
    const storage = fakeStorage();
    saveVoiceLanguage("zh-CN", storage);
    expect(storage.data.get("luban.portal.voiceLanguage")).toBe("zh-CN");
    saveVoiceLanguage("fr-FR", storage);
    expect(storage.data.get("luban.portal.voiceLanguage")).toBe("zh-CN");
  });
});
