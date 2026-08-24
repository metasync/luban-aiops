---
kind: frontend_style
name: 'Operator Portal Frontend Style: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui/app`) is a React 18 + TypeScript SPA built with Vite. Styling is centered on **Ant Design v6** using its `darkAlgorithm` theme, and a parallel set of **CSS custom properties (design tokens)** in `src/theme/global.css` that mirror the Ant Design token values. This dual-token approach lets Ant components consume the typed `ThemeConfig` while bespoke component styles reference the same palette via `var(--accent)`, `var(--surface)`, etc., keeping Ant and hand-written CSS on one vocabulary.

There is no Tailwind, Sass, or CSS-in-JS library — plain CSS files are imported directly by the app entry point. The build outputs to `../dist` and is served by nginx from the sibling directory.

## Key files and packages

- `package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, plus React 18, Vite, Vitest, and TypeScript.
- `vite.config.ts` — injects `__PLATFORM_VERSION__` at build time; configures dev proxy `/api → http://localhost:8080`; builds to `../dist` for nginx.
- `src/theme/tokens.ts` — single source of truth for colors, radius, fonts, and the `antd` `ThemeConfig` (`portalTheme`).
- `src/theme/global.css` — root-level `:root` CSS variables mirroring `tokens.ts`, global resets, app shell layout, chat transcript styling, evidence cards, HITL confirmation cards, view toolbar/report form chrome, and an `@media (max-width: 860px)` breakpoint.
- `nginx.conf` (in `operator-portal/`) serves the built `dist/` as the site root.

## Architecture and conventions

### Design tokens
All visual tokens live in `src/theme/tokens.ts` as a `const` palette object and an `antd` `ThemeConfig`. The comment explicitly states that `global.css` mirrors these values so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1 dark theme). Changes should be made in `tokens.ts` and reflected in `global.css`.

### Ant Design theme
The portal uses `antd`'s `darkAlgorithm` with overridden tokens (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBgElevated`, `colorBorder`, `colorText`, `colorSuccess/Error/Warning`, `borderRadius`, `fontFamily`, `fontFamilyCode`). Components are styled through Ant's built-in theming rather than custom CSS classes wherever possible.

### Global CSS scope
`global.css` defines:
- A dark color scheme (`color-scheme: dark`) and a `--bg` / `--surface` / `--accent` / `--text` / `--border` / `--radius` palette.
- A full-height app shell (`app-shell`) composed of an `ant-layout-sider` sidebar and a main content area.
- Chat-specific layout (`.chat-view`, `.session-panel`, `.chat-messages`, `.chat-composer`) with a fixed-width session list and a flex-1 transcript column.
- Markdown rendering rules under `.md-content` (headings, code blocks, blockquotes, tables).
- Evidence groups (`.evidence-turn`, `.evidence-card`, `.evidence-pre`) collapsed by default per SPEC-011 parity.
- A sticky request banner (`.turn-request-banner`) that appears when the user bubble scrolls out of view.
- HITL confirmation cards (`.confirm-card`) with pending/warning state variants.
- Shared view chrome (`.view-toolbar`, `.report-form`, `.incident-section`).
- A narrow viewport rule at `860px` that shrinks the session panel width.

### Component styling convention
Components use Ant Design primitives (`Layout`, `Menu`, `Drawer`, `Card`, `Table`, `Form`, etc.) and rely on the injected `portalTheme` for consistent appearance. Custom layout concerns (sidebar collapse behavior, mobile drawer toggle, view containers) are expressed as small BEM-style class names in `global.css` rather than per-component CSS modules. There are no inline style objects or CSS-in-JS libraries in the codebase.

### Responsive strategy
Responsive behavior is minimal and CSS-driven:
- Ant Design's `Sider` auto-collapses below its `lg` breakpoint (992px), and a pinned `.mobile-menu-button` opens an off-canvas drawer instead of the inline sidebar.
- A single `@media (max-width: 860px)` rule narrows the session panel.
No responsive breakpoints are defined per component; the layout adapts via Ant's built-in responsive grid/sider behavior.

### Build-time versioning
The platform version string is read from the repo root `VERSION` file and injected as `__PLATFORM_VERSION__` at build time, then asserted by `make validate-version`. This is a build-time constant, not a runtime fetch.

## Conventions and constraints

- **Single token source**: Colors, radius, and fonts must be defined in `src/theme/tokens.ts` and mirrored in `src/theme/global.css` so Ant and custom CSS share the same palette (documented in both files' comments referencing SPEC-023 R-1).
- **Dark theme only**: `color-scheme: dark` is set globally; no light-mode toggle exists in the current codebase.
- **Ant Design first**: Prefer Ant components and their `ThemeConfig` overrides over writing new CSS classes. Custom CSS is reserved for layout shells, chat transcript structure, and feature-specific cards (evidence, HITL confirmations).
- **BEM-like class naming**: Custom CSS uses descriptive class names (`.session-item.active`, `.evidence-card`, `.turn-request-banner.visible`) scoped to semantic regions rather than utility classes.
- **Scoped scroll zones**: Transcript and evidence panels use explicit `overflow-y: auto` with bounded heights (e.g., `.evidence-pre` capped at `280px`) so expanding content does not push the whole page.
- **Accessibility baseline**: `:focus-visible` gets a 2px accent-colored outline with offset; keyboard focus is intentionally preserved on custom controls.
- **Build output contract**: Vite builds to `../dist` which nginx serves at `/`; content-hashed assets are immutable-cacheable while `index.html` is no-store (per `vite.config.ts` comments referencing SPEC-023 R-1).
- **Dev proxy**: During development, `/api` requests are proxied to `http://localhost:8080` (the platform gateway); production deployments do not use this proxy.