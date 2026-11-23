import { theme as antdTheme, type ThemeConfig } from "antd";
import type { ThemeMode } from "./mode";

// Palette ported verbatim from the legacy portal's :root design tokens
// (styles.css). The CSS custom properties in global.css mirror these so
// bespoke styles and antd components stay on one vocabulary (SPEC-023
// R-1 dark theme).
export const palette = {
  bg: "#0f172a",
  surface: "#1e293b",
  surfaceAlt: "#334155",
  border: "#475569",
  text: "#e2e8f0",
  textMuted: "#94a3b8",
  accent: "#38bdf8",
  accentHover: "#7dd3fc",
  success: "#4ade80",
  error: "#f87171",
  warning: "#fbbf24",
  codeBg: "#1a2332",
  radius: 8,
} as const;

// Light palette: a daylight counterpart of the shipped dark tokens, keeping
// the same slate/sky family so the two modes read as one product. global.css
// mirrors these under [data-theme="light"].
export const lightPalette = {
  bg: "#f8fafc",
  surface: "#ffffff",
  surfaceAlt: "#e2e8f0",
  border: "#cbd5e1",
  text: "#0f172a",
  textMuted: "#64748b",
  accent: "#0284c7",
  accentHover: "#0369a1",
  success: "#16a34a",
  error: "#dc2626",
  warning: "#d97706",
  codeBg: "#f1f5f9",
  radius: 8,
} as const;

export const portalTheme: ThemeConfig = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    colorPrimary: palette.accent,
    colorBgBase: palette.bg,
    colorBgContainer: palette.surface,
    colorBgElevated: palette.surfaceAlt,
    colorBorder: palette.border,
    colorBorderSecondary: palette.border,
    colorText: palette.text,
    colorTextSecondary: palette.textMuted,
    colorSuccess: palette.success,
    colorError: palette.error,
    colorWarning: palette.warning,
    borderRadius: palette.radius,
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif',
    fontFamilyCode: '"JetBrains Mono", "Fira Code", monospace',
  },
};

export const lightTheme: ThemeConfig = {
  algorithm: antdTheme.defaultAlgorithm,
  token: {
    colorPrimary: lightPalette.accent,
    colorBgBase: lightPalette.bg,
    colorBgContainer: lightPalette.surface,
    colorBgElevated: lightPalette.surfaceAlt,
    colorBorder: lightPalette.border,
    colorBorderSecondary: lightPalette.border,
    colorText: lightPalette.text,
    colorTextSecondary: lightPalette.textMuted,
    colorSuccess: lightPalette.success,
    colorError: lightPalette.error,
    colorWarning: lightPalette.warning,
    borderRadius: lightPalette.radius,
    fontFamily:
      'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif',
    fontFamilyCode: '"JetBrains Mono", "Fira Code", monospace',
  },
};

// The antd ThemeConfig for a given mode. Computed synchronously so the first
// paint already matches the persisted choice (no flash of the wrong theme).
export function themeForMode(mode: ThemeMode): ThemeConfig {
  return mode === "light" ? lightTheme : portalTheme;
}
