---
kind: frontend_style
name: Operator Portal Frontend Style System (Ant Design + CSS Custom Properties)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 18 + TypeScript application built with Vite. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library, with a custom dark theme applied via Ant Design's `ThemeConfig`. Global base styles and bespoke UI chrome are written in plain CSS under `src/theme/global.css`, using CSS custom properties (CSS variables) to share a single design token vocabulary between Ant Design components and hand-written styles.

There is no CSS-in-JS library, Sass/Less preprocessor, or utility-first framework (e.g., Tailwind). The build pipeline is Vite with the `@vitejs/plugin-react` plugin; tests run under Vitest with a jsdom environment.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, plus Vite/Vitest tooling.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — centralizes the palette and maps it to an Ant Design `ThemeConfig` named `portalTheme`; uses `antd.theme.darkAlgorithm` for the dark mode algorithm.
- `products/operator-portal/web-ui/app/src/theme/global.css` — defines `:root` CSS custom properties mirroring the same palette, plus global resets, layout shell classes (`app-shell`, `view-container`, `chat-view`, `session-panel`, `md-content`, evidence cards, HITL confirm cards), and a narrow-viewport media query at `max-width: 860px`.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__` at build time from the repo root `VERSION` file; outputs to `../dist` for nginx serving; proxies `/api` to `http://localhost:8080` in dev.
- `products/operator-portal/web-ui/app/src/App.tsx` — top-level shell using Ant Design `Layout.Sider`/`Layout.Content`, `Menu`, `Drawer`, `Button`, `Avatar`, `Tag`, `Typography`; implements responsive behavior via `breakpoint="lg"` (992px) and a custom `useNarrowViewport` hook that switches between inline sidebar and off-canvas drawer below 991px.
- `nginx.conf` (at `products/operator-portal/`) serves the built `web-ui/dist` at `/`.

## Architecture and conventions

### Single source of truth for tokens
`tokens.ts` defines a `palette` object (bg, surface, surfaceAlt, border, text, textMuted, accent, success, error, warning, codeBg, radius) and a `portalTheme` `ThemeConfig` that maps those values into Ant Design's token space (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBorder`, `borderRadius`, `fontFamily`, etc.). `global.css` mirrors the same palette as CSS custom properties (`--bg`, `--surface`, `--accent`, …) so bespoke CSS and Ant Design components consume one vocabulary. Comments explicitly state this dual mapping is required by SPEC-023 R-1 for dark-theme parity.

### Dark-only theme
The app sets `color-scheme: dark` globally and applies `darkAlgorithm` to the Ant Design theme. All views, menus, sider, and content areas use Ant Design's dark tokens; there is no light-mode toggle.

### Layout shell
The root `App.tsx` composes a fixed-height `Layout` with a collapsible `Layout.Sider` (width 230, collapsed width 64) and a `Layout.Content` area. A pinned `.mobile-menu-button` (fixed top-left) toggles either the sider collapse state (desktop) or opens an off-canvas `Drawer` (below 991px). Sidebar menu items are grouped into "Control" and "Workspace" sections, with visibility gated by roles (`hasAnyRole`).

### View composition
Each feature lives under `src/views/<area>/` (audit, control, incidents) and `src/chat/`, `src/stream/`, `src/voice/`, `src/auth/`, `src/sessions/`. Views are rendered conditionally inside the main `Layout.Content` based on an active `ViewId` state. Shared view chrome classes live in `global.css`: `.view-container`, `.view-container-flush` (for chat's full-bleed scrolling), `.view-toolbar`, `.report-form`, `.incident-section`.

### Chat workspace styling
A dedicated `.chat-view` flex layout splits a fixed-width `.session-panel` (260px, shrinks to 200px at ≤860px) and a fluid `.chat-column`. Message rendering uses `.md-content` rules ported from the legacy `styles.css`, including headings, lists, code blocks, blockquotes, links, tables, and horizontal rules. Evidence groups and HITL confirmation cards have their own scoped classes (`.evidence-turn`, `.evidence-card`, `.confirm-card`, `.confirm-call`, `.turn-request-banner`).

### Responsive strategy
Responsive behavior is breakpoint-driven rather than fluid:
- Ant Design Sider uses `breakpoint="lg"` (992px) to auto-collapse to a 64px icon rail.
- A custom `useNarrowViewport` hook listens to `(max-width: 991px)` to switch between inline sidebar and a left-placed Drawer.
- A `@media (max-width: 860px)` rule narrows the session panel from 260px to 200px.
- The mobile menu button is always visible and repositions itself relative to the collapsed sider.

### Build-time version injection
`vite.config.ts` reads the repository root `VERSION` file and exposes it as `__PLATFORM_VERSION__`, which is consumed via `./version.ts` and displayed next to the "Luban AIOps" brand in the sidebar. This is enforced by `make validate-version` (referenced in comments).

## Conventions and constraints

- **Use Ant Design tokens, not raw colors**: new visual values should be added to `tokens.ts` palette and mapped into `portalTheme`, then referenced via CSS custom properties in `global.css`. Ad-hoc hex literals in components are discouraged where a token exists.
- **Dark theme only**: all new UI must work within the dark algorithm; avoid assuming light-mode defaults.
- **BEM-like class naming for bespoke CSS**: classes in `global.css` follow a flat, descriptive naming scheme (e.g., `session-item`, `session-item.active`, `composer-selection-bar`, `turn-request-banner.visible`) scoped to the portal; they are not namespaced per-component but rely on specificity and consistent prefixes.
- **Responsive breakpoints are centralized**: the sider breakpoint (992px) and the narrow viewport threshold (991px) are defined in `App.tsx`; new responsive behavior should reference these constants rather than inventing new magic numbers.
- **Markdown content styling is shared**: any rendered markdown should wrap content in `.md-content` to inherit the established heading, code, table, and link styles.
- **Evidence and HITL UI reuse existing classes**: new transcript elements should extend `.evidence-*` and `.confirm-*` families to maintain alignment with the transcript column width and trust signals.
- **Build artifact location**: the Vite build writes to `../dist` (relative to `web-ui/app`), which is served by the portal's nginx configuration; do not change `outDir` without updating deployment.