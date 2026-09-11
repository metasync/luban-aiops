---
kind: frontend_style
name: Operator Portal Frontend Style System (Ant Design + CSS Tokens)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The only frontend in this repository is the **operator-portal web UI** (`products/operator-portal/web-ui/app`), a React 19 / TypeScript application built with **Vite**. Styling is centered on **Ant Design v6** as the component library, with a custom dark theme applied via Antd's `ConfigProvider` and `ThemeConfig`. A single global stylesheet (`app/src/theme/global.css`) defines CSS custom properties that mirror the Antd token values, so bespoke styles and Antd components share one vocabulary. There is no Tailwind, Sass, or CSS-in-JS beyond what Antd provides.

## Key files and packages

- `app/package.json` — declares dependencies: `antd`, `@ant-design/icons`, `@ant-design/x`, `react`, `react-dom`; dev deps include `vite`, `vitest`, `@testing-library/react`, `jsdom`.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving; proxies `/api` to `localhost:8080` in dev.
- `app/src/main.tsx` — root entry wrapping the app in `<ConfigProvider theme={portalTheme}>` and `<AuthProvider>`.
- `app/src/theme/tokens.ts` — central design tokens: `palette` object (bg, surface, border, text, accent, success, error, warning, codeBg, radius) and `portalTheme: ThemeConfig` mapping those tokens into Antd's dark algorithm, including font families (`Inter` + JetBrains Mono/Fira Code).
- `app/src/theme/global.css` — single source of truth for CSS variables under `:root` (`--bg`, `--surface`, `--accent`, etc.), base resets, layout shell (`.app-shell`, `.view-container`, `.sidebar-*`), chat workspace panels (`.session-panel`, `.chat-view`, `.turn-group`, `.evidence-*`, `.confirm-card`, `.turn-request-banner`), markdown rendering rules (`.md-content *`), and responsive breakpoints (`max-width: 860px`).
- `app/src/App.tsx` — antd `Layout.Sider`/`Menu`/`Drawer` shell; uses `breakpoint="lg"` (992px) to switch between inline sidebar and off-canvas drawer; applies `theme="dark"` to sider/menu.

## Architecture and conventions

1. **Single-token source of truth.** `tokens.ts` defines the palette once; `global.css` mirrors it as CSS custom properties so both Antd components and hand-written CSS consume the same colors/radius/font. The comment in `tokens.ts` explicitly states the two sources must stay in sync (SPEC-023 R-1 dark theme).
2. **Dark-only theme.** `color-scheme: dark` is set on `:root`; Antd's `darkAlgorithm` is selected; all views render against the dark palette. No light-mode toggle exists.
3. **CSS Modules-style class naming.** Custom classes use BEM-like names scoped to feature areas (`.session-panel`, `.chat-messages`, `.approvals-entry`, `.evidence-card`, `.confirm-card`, `.turn-request-banner`) rather than CSS modules or styled-components. They live in one file rather than per-component stylesheets.
4. **Responsive strategy via CSS media queries + Antd breakpoints.** The sidebar uses antd's built-in `breakpoint="lg"` (992px) to collapse into an icon rail; below 860px the session panel narrows; a fixed `.mobile-menu-button` toggles a Drawer for navigation on small screens. Reduced-motion is respected via `@media (prefers-reduced-motion: reduce)`.
5. **Design-system-driven by specs.** Many style decisions are tied to spec requirements referenced in comments (SPEC-019, SPEC-020, SPEC-023, SPEC-024, SPEC-031, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041), e.g. turn arrival flash animation, approval inbox cards, bounded panes with `--bounded-pane-max-height`, sticky request banner.
6. **Build-time versioning.** Platform and dependency versions are injected as constants (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) and displayed in the Settings view; the build hashes asset filenames for immutable caching while `index.html` stays no-store.

## Conventions and constraints

- **Use Antd `ConfigProvider` theme for all component-level styling**; do not override Antd defaults with ad-hoc CSS when a token can be expressed via `ThemeConfig`.
- **All visual tokens flow through `src/theme/tokens.ts`**; any new color, radius, or font must be added there and mirrored in `global.css` `:root` variables.
- **Custom CSS lives exclusively in `src/theme/global.css`**; components should not define their own stylesheets but instead compose Antd components and apply the shared class names defined there.
- **Dark mode is enforced globally** — new components inherit the dark palette automatically via Antd's algorithm and CSS variables.
- **Responsive behavior uses Antd's `lg` breakpoint (992px)** for sidebar collapse and CSS `@media` queries for finer-grained adjustments; avoid hardcoding widths inside components.
- **Accessibility baseline**: `:focus-visible` outline uses `var(--accent)` with 2px offset; reduced-motion animations are disabled when `prefers-reduced-motion: reduce` is set.
- **Bounded scrolling**: long content areas (code blocks, evidence panels, digest/prose panes) use `max-height` with internal overflow rather than expanding the page, keeping chrome pinned above scrollable content.