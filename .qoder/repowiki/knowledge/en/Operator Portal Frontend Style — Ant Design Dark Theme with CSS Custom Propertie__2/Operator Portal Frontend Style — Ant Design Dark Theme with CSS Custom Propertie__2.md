---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
---

## System Overview

The operator portal (`products/operator-portal/web-ui/app`) is a React 19 + TypeScript SPA built with Vite. Its styling system is centered on **Ant Design v6** (`antd` + `@ant-design/icons` + `@ant-design/x`), configured via a single dark-theme `ThemeConfig`, and extended through a shared CSS custom properties palette in `global.css`. There is no Tailwind, SCSS, or CSS-in-JS library beyond Antd's own token system.

## Key Files

- `app/package.json` — declares the UI stack: React 19, antd ^6.6.2, @ant-design/icons ^6.0.0, @ant-design/x ^2.9.0, Vite 8, Vitest, jsdom.
- `app/src/main.tsx` — root entry; wraps the app in Antd's `ConfigProvider theme={portalTheme}` so all components inherit the portal theme.
- `app/src/theme/tokens.ts` — single source of truth for colors, radii, fonts, and the `portalTheme: ThemeConfig` object (uses `antdTheme.darkAlgorithm`).
- `app/src/theme/global.css` — CSS custom properties mirroring `tokens.ts` under `:root` (`--bg`, `--surface`, `--accent`, etc.) plus bespoke component styles for chat, evidence cards, HITL confirmation cards, session panel, view chrome, and markdown rendering.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx consumption.

## Architecture and Conventions

1. **Token duality.** `tokens.ts` defines the JS-side palette and Antd `ThemeConfig`; `global.css` mirrors the same values as CSS custom properties. The comment in `tokens.ts` states they are "ported verbatim from the legacy portal's :root design tokens" and that this dual vocabulary exists so "bespoke styles and antd components stay on one vocabulary (SPEC-023 R-1 dark theme)."

2. **Dark-only theme.** `global.css` sets `color-scheme: dark` on `:root`; `tokens.ts` uses `antdTheme.darkAlgorithm`. No light-mode toggle is present.

3. **Component composition over custom CSS.** Most UI surfaces are built from Antd primitives (`Layout.Sider`, `Menu`, `Table`, `Tabs`, `Modal`, `Alert`, `Tag`, `Typography`, `Statistic`, `Collapse`, `Row/Col`, `Pagination`, `Spin`) with only layout overrides and feature-specific classes in `global.css` (e.g., `.session-panel`, `.chat-view`, `.confirm-card`, `.evidence-card`, `.turn-request-banner`, `.digest-bounded`, `.prose-bounded`).

4. **Bespoke class naming.** Custom styles use BEM-like dot-prefixed class names scoped to semantic regions (`session-panel-*`, `chat-*`, `approvals-entry-*`, `confirm-*`, `evidence-*`, `recovery-*`, `view-toolbar`, `report-form`). These live exclusively in `global.css` rather than per-component CSS modules.

5. **Responsive strategy.** A single breakpoint at `max-width: 860px` narrows the session panel width; the sidebar uses Antd's built-in Sider collapse behavior below its `lg` breakpoint (992px) and exposes a pinned `.mobile-menu-button` for off-canvas drawer mode. No mobile-first media-query cascade is used.

6. **Accessibility hooks.** `:focus-visible` gets an accent-colored outline; `prefers-reduced-motion` disables the `.turn-group.turn-arrived` flash animation.

7. **Spec-driven style evolution.** Inline comments tie visual changes to spec requirements (e.g., `SPEC-023 R-1`, `SPEC-019 R-1`, `SPEC-020 R-4`, `SPEC-034 R-1`, `SPEC-035 R-4`, `SPEC-037 R-6`, `SPEC-039 R-8`, `SPEC-041 R-3`), making the stylesheet a living implementation of those contracts.

8. **Build-time versioning.** `vite.config.ts` reads the repo root `VERSION` file and the lockfile to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants consumed by the Settings view's tech-stack table.

## Conventions and Constraints

- All Antd components receive their theme through the top-level `ConfigProvider` in `main.tsx`; individual components do not pass `theme` props.
- Color/radius/font values are never hard-coded in component JSX or bespoke CSS — they flow from `var(--*)` custom properties or Antd tokens.
- Custom CSS lives only in `src/theme/global.css`; there are no per-component `.css` files, SCSS, or CSS-in-JS style objects.
- The font stack is fixed: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif` for prose and `"JetBrains Mono", "Fira Code", monospace` for code, declared once in both `tokens.ts` and `global.css`.
- The build target is `../dist` served by the parent product's `nginx.conf`; content-hashed filenames are expected for immutable caching (per the `vite.config.ts` comment referencing SPEC-023 R-1).
- Tests run under `jsdom` via Vitest (`vite.config.ts` `test.environment = "jsdom"`), which constrains how DOM/CSS features can be exercised in unit tests.