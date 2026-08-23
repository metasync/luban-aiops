---
kind: frontend_style
name: Operator Portal Dark-Theme UI (Ant Design + CSS Custom Properties)
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

The only frontend in this repository is the **operator portal** (`products/operator-portal/web-ui/app`), a React 18 application built with **Vite** and styled with **Ant Design 6** (`antd`, `@ant-design/icons`, `@ant-design/x`). There is no Tailwind, Sass, or CSS-in-JS library beyond Ant's built-in theme engine. The app uses TypeScript, Vitest for tests, and JSDOM as the test environment.

## Key files and packages

- `package.json` — declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `dayjs`; dev deps include `vite`, `typescript`, `vitest`, `@vitejs/plugin-react`.
- `vite.config.ts` — builds to `../dist`, injects `__PLATFORM_VERSION__` from the repo root `VERSION` file, proxies `/api` to `http://localhost:8080` in dev, and sets `test.environment = "jsdom"`.
- `src/main.tsx` — renders `<ConfigProvider theme={portalTheme}>` wrapping the whole tree; imports `./theme/global.css`.
- `src/theme/tokens.ts` — single source of truth for design tokens: a `palette` object (bg/surface/border/text/accent/success/error/warning/codeBg/radius) plus an `antd ThemeConfig` using `darkAlgorithm` that maps those tokens to Ant tokens (`colorPrimary`, `colorBgBase`, `colorText`, `fontFamily`, `fontFamilyCode`, etc.).
- `src/theme/global.css` — defines matching CSS custom properties on `:root` (`--bg`, `--surface`, `--accent`, …) so bespoke styles and Ant components share one vocabulary; also contains all view-level layout and component styles (app shell, sidebar, chat transcript, evidence cards, sticky request banner, HITL confirmation cards, responsive rules).
- `src/App.tsx` — top-level layout using Ant `Layout.Sider` (inline sidebar with 230px width, 64px collapsed rail, `breakpoint="lg"`) plus an off-canvas `Drawer` for narrow viewports; navigation items are grouped into “Control” and “Workspace” sections and gated by roles.

## Architecture and conventions

- **Design-token duality**: `tokens.ts` holds the canonical palette; `global.css` mirrors it as CSS variables. Comments explicitly state they are “ported verbatim from the legacy portal’s :root design tokens” and reference SPEC-023 R-1 dark-theme requirements. New colors must be added to both places.
- **Ant Design as the component layer**: All UI primitives (`Button`, `Menu`, `Layout`, `Tag`, `Avatar`, `Alert`, `Spin`, `Typography`, `Drawer`) come from `antd`. The app never writes raw HTML elements for chrome; styling is done via Ant props (`theme="dark"`, `type="text"`, `size="small"`) plus the global `ConfigProvider` theme.
- **Dark-only theme**: `color-scheme: dark` is set on `:root`, the Ant theme uses `darkAlgorithm`, and the entire portal is designed around a slate/indigo dark palette. No light-mode toggle exists.
- **CSS methodology**: Scoped BEM-style class names under `.app-shell`, `.view-container`, `.chat-view`, `.session-panel`, `.evidence-*`, `.confirm-card`, `.turn-request-banner`, etc. No CSS modules, no CSS-in-JS per-component stylesheets — everything lives in `global.css`.
- **Responsive strategy**: Relies on Ant’s `breakpoint="lg"` (992px) for the sidebar collapse, plus a `@media (max-width: 860px)` rule that narrows the session panel. A fixed-position `.mobile-menu-button` toggles either the sider collapse or an off-canvas drawer depending on viewport width.
- **View composition**: `App.tsx` switches between views (`chat`, `incidents`, `audit`, `permissions`, `tools`, `skills`, `settings`) rendered from `src/views/*` and `src/chat/*`. Each view is a full-page component mounted inside a shared `Layout.Content` container.
- **Build-time versioning**: `vite.config.ts` reads the repo root `VERSION` file and exposes it as `__PLATFORM_VERSION__`, which flows through `src/version.ts` into the sidebar brand tag — part of the SPEC-023 build contract.

## Conventions and constraints

- **Token discipline**: Palette values live in `src/theme/tokens.ts` and are mirrored as CSS custom properties in `src/theme/global.css`; comments document that bespoke styles consume the CSS variables while Ant consumes the `ThemeConfig` (SPEC-023 R-1 dark theme).
- **Dark mode is enforced**: The root `:root` sets `color-scheme: dark`; the Ant theme is configured with `darkAlgorithm`; there is no light-mode path in the codebase.
- **Sidebar behavior**: The `Layout.Sider` uses `breakpoint="lg"`, `collapsedWidth={64}`, and `trigger={null}`; navigation below the lg breakpoint moves to a left-placed `Drawer`. A pinned `.mobile-menu-button` sits at `top: 12px; left: 12px; z-index: 100` to open/close the drawer or collapse the rail.
- **Chat transcript layout**: Chat-specific classes (`.chat-view`, `.session-panel`, `.chat-messages`, `.turn-group`, `.md-content`, `.evidence-turn`, `.evidence-card`, `.tool-name`, `.evidence-meta`, `.evidence-pre`) define a two-column layout where the session list is 260px wide and the transcript area scrolls independently.
- **Evidence panels**: Tool evidence groups are collapsed by default with a summary line carrying the trust signal; expanded content uses a bounded `max-height: 280px` pre block so large tool results do not push the transcript out of view (SPEC-011 R-4 parity).
- **Sticky request banner**: A `.turn-request-banner` appears when a user bubble scrolls out of view, pinned at `top: 0` with a gradient background and accent-colored left border to restate context during long replies.
- **HITL confirmation cards**: `.confirm-card` variants use warning borders for pending confirmations; call details are shown in nested `.confirm-call` blocks (SPEC-020 R-4).
- **No inline style abuse outside small overrides**: Most visual decisions go through Ant props or `global.css`; only minor positioning/padding adjustments appear inline (e.g., sidebar brand padding).
- **Testing**: Frontend tests run under Vitest with `environment: "jsdom"`; no snapshot or visual regression tests are present.