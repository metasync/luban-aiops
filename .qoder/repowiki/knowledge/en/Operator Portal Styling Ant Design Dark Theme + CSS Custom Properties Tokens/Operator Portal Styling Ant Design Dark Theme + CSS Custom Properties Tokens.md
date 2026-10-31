---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme + CSS Custom Properties Tokens'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
---

## System

The operator portal (`products/operator-portal/web-ui/app`) is a React 19 / Vite application styled with **Ant Design v6** (`antd` + `@ant-design/icons` + `@ant-design/x`). There is no Tailwind, SCSS, or CSS-in-JS library beyond Antd's built-in theme engine. Custom styling lives in a single global stylesheet and a TypeScript token module; there are no per-component style files.

## Key files

- `app/package.json` — declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `dayjs`; build via `vite build`, test via `vitest` (jsdom).
- `app/src/theme/tokens.ts` — central design-token source: the `palette` object (bg/surface/border/text/accent/success/error/warning/codeBg/radius) and the `portalTheme: ThemeConfig` that maps them onto Antd's dark algorithm (`antdTheme.darkAlgorithm`).
- `app/src/theme/global.css` — all bespoke CSS for the portal shell, chat workspace, markdown rendering, HITL confirmation cards, evidence groups, sticky request banners, bounded panes, and responsive breakpoints.
- `app/src/main.tsx` — root entry that wraps `<App>` in Antd's `<ConfigProvider theme={portalTheme}>`, making tokens available to every component.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx consumption.

## Architecture and conventions

1. **Single source of truth for colors.** The comment in `tokens.ts` states the palette was "ported verbatim from the legacy portal's :root design tokens" so that bespoke styles and Antd components share one vocabulary. `global.css` mirrors the same values as CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) under `:root`, while `portalTheme` maps the same values into Antd's `token` config.

2. **Dark-only theme.** `color-scheme: dark` is set on `:root`, and Antd is configured with `algorithm: antdTheme.darkAlgorithm`. No light-mode toggle exists.

3. **Component library usage.** All UI primitives come from `antd`: `Layout`, `Menu`, `Button`, `Modal`, `Table`, `Tabs`, `Tag`, `Typography`, `Alert`, `Spin`, `Pagination`, `Statistic`, `Collapse`, `Segmented`, `Select`, plus icons from `@ant-design/icons`. Components are imported directly rather than through a local wrapper layer.

4. **Bespoke CSS class naming.** Custom classes use BEM-like dot selectors scoped to semantic regions (`.app-shell`, `.sidebar-footer`, `.session-panel`, `.chat-view`, `.turn-group`, `.confirm-card`, `.evidence-card`, `.turn-request-banner`, `.digest-bounded`, `.prose-bounded`). They reference CSS variables from `global.css` rather than hard-coded hex values.

5. **Responsive strategy.** A single `@media (max-width: 860px)` breakpoint narrows the session panel; the sidebar uses Antd's built-in `lg` breakpoint (992px) where the `Sider` auto-collapses, and a pinned `.mobile-menu-button` opens an off-canvas drawer below that threshold. No mobile-first framework is used.

6. **Accessibility hooks.** `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion: reduce` disables the turn-arrival animation; keyboard focusability is called out in comments.

7. **Spec-driven style gates.** Style decisions are cross-referenced to specs inline (e.g. `SPEC-023 R-1 dark theme`, `SPEC-019 R-1`, `SPEC-023 R-3`, `SPEC-034 R-1`, `SPEC-035 R-4`, `SPEC-037 R-6`, `SPEC-039 R-8`, `SPEC-041 R-3`, `SPEC-063 R-5a`). This is the repository's documented enforcement mechanism for visual consistency.

## Conventions and constraints

- Colors, radii, and fonts are defined once in `src/theme/tokens.ts` and mirrored as CSS custom properties in `src/theme/global.css`; bespoke CSS should consume the CSS variables, not redeclare colors.
- Antd components receive their theme exclusively through the top-level `<ConfigProvider theme={portalTheme}>` in `main.tsx`; individual components do not pass a `theme` prop.
- The font stack is fixed: sans-serif falls back to `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`; monospace code text uses `"JetBrains Mono", "Fira Code", monospace`.
- All bespoke layout classes live in `global.css`; there are no component-scoped CSS modules, CSS-in-JS, or Tailwind utility classes.
- Build-time constants `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` are injected by `vite.config.ts` so the Settings view can display the exact shipped dependency versions.
- The output directory is `../dist` (consumed by the parent product's nginx), and content-hash filenames are used for immutable caching while `index.html` stays no-store (per SPEC-023 R-1).