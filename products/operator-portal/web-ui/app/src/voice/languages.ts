// Recognition language selection (SPEC-023 R-4): an explicit operator
// choice, constant-driven list, browser-locale default with en-US
// fallback, localStorage persistence. The selection drives the browser
// recognizer's `lang` only — it is never sent to the backend.
export interface VoiceLanguage {
  code: string;
  label: string;
}

export const VOICE_LANGUAGES: VoiceLanguage[] = [
  { code: "en-US", label: "English (US)" },
  { code: "zh-CN", label: "中文（普通话）" },
];

export const DEFAULT_VOICE_LANGUAGE = "en-US";

const STORAGE_KEY = "luban.portal.voiceLanguage";

function isSupportedCode(code: string): boolean {
  return VOICE_LANGUAGES.some((lang) => lang.code === code);
}

// Default resolution: an exact match wins ("zh-CN" -> zh-CN), otherwise
// the primary subtag maps to the first supported variant ("zh-Hans" ->
// zh-CN, "en-GB" -> en-US); anything else falls back to en-US.
export function resolveDefaultVoiceLanguage(
  browserLanguage: string | undefined,
): string {
  if (!browserLanguage) return DEFAULT_VOICE_LANGUAGE;
  const normalized = browserLanguage.trim().toLowerCase();
  if (!normalized) return DEFAULT_VOICE_LANGUAGE;
  const exact = VOICE_LANGUAGES.find(
    (lang) => lang.code.toLowerCase() === normalized,
  );
  if (exact) return exact.code;
  const primary = normalized.split("-")[0];
  const partial = VOICE_LANGUAGES.find((lang) =>
    lang.code.toLowerCase().startsWith(primary),
  );
  return partial ? partial.code : DEFAULT_VOICE_LANGUAGE;
}

export function loadVoiceLanguage(
  browserLanguage?: string,
  storage: Pick<Storage, "getItem"> = window.localStorage,
): string {
  const stored = storage.getItem(STORAGE_KEY);
  if (stored && isSupportedCode(stored)) return stored;
  return resolveDefaultVoiceLanguage(
    browserLanguage ?? window.navigator?.language,
  );
}

export function saveVoiceLanguage(
  code: string,
  storage: Pick<Storage, "setItem"> = window.localStorage,
): void {
  if (isSupportedCode(code)) storage.setItem(STORAGE_KEY, code);
}
