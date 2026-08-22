import { theme as antdTheme, type ThemeConfig } from "antd";

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
