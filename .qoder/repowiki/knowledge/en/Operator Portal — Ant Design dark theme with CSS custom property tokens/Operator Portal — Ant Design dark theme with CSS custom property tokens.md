---
kind: frontend_style
name: Operator Portal — Ant Design dark theme with CSS custom property tokens
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

The only frontend in this repository is the **operator-portal web UI** (`products/operator-portal/web-ui/app`), a React 18 + TypeScript application built with **Vite**. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via Antd's `ConfigProvider` with a single `ThemeConfig` object. There is no Tailwind, SCSS, CSS-in-JS library, or component library of its own — bespoke visual rules live in one global stylesheet and are consumed through CSS custom properties.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd` ^6, `@ant-design/icons` ^6, `@ant-design/x` ^2, plus Vite/Vitest tooling.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the palette (`bg`, `surface`, `accent`, `success`, `error`, `warning`, `border`, `text`, `radius`, …) and builds an `antd` `ThemeConfig` using `darkAlgorithm` that maps those tokens to Antd's design tokens (colorPrimary, colorBgBase, colorBorder, borderRadius, fontFamily, fontFamilyCode).
- `products/operator-portal/web-ui/app/src/theme/global.css` — declares the same values as `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, …) so non-Antd components and legacy-migrated styles share one vocabulary; also contains all bespoke layout/typography rules for the app shell, chat transcript, evidence cards, HITL confirmation cards, sticky request banner, markdown rendering, and view chrome.
- `products/operator-portal/web-ui/app/src/main.tsx` — bootstraps the root with `<ConfigProvider theme={portalTheme}>`, importing both `tokens.ts` and `global.css` once at the entry point.
- `products/operator-portal/web-ui/app/vite.config.ts` — build config; outputs to `../dist`, injects `__PLATFORM_VERSION__` from the repo root `VERSION` file, and proxies `/api` to the platform gateway during dev.
- `products/operator-portal/web-ui/app/src/App.tsx` — top-level layout consuming Antd `Layout.Sider` (dark mode, breakpoint-driven collapse to a drawer at ≤991px), `Menu`, `Badge`, `Avatar`, `Tag`, `Alert`, `Spin`; applies utility class names like `app-shell`, `view-container`, `mobile-menu-button` defined in `global.css`.

## Architecture and conventions

1. **Single source of truth for colors/shapes.** The palette lives in `src/theme/tokens.ts`. That file both drives the Antd theme and is mirrored verbatim into `:root` CSS variables in `global.css` (the comment explicitly says they mirror each other so bespoke styles and Antd stay on one vocabulary). Adding a new semantic color means editing `tokens.ts` and keeping the matching `--var` in sync.

2. **Dark-only theme.** `color-scheme: dark` is set on `:root`, the Antd theme uses `darkAlgorithm`, and the menu/layout are forced to `theme="dark"`. No light-mode toggle exists.

3. **Component styling split:**
   - Antd primitives (`Button`, `Layout`, `Menu`, `Tag`, `Alert`, `Drawer`, `Typography`, `Avatar`, `Badge`, `Spin`) are styled purely through the injected `ThemeConfig` and their built-in props — no className overrides on these elements.
   - Application-specific chrome (sidebar, session panel, chat transcript, evidence groups, HITL cards, markdown content, sticky banners, view containers) is implemented as plain CSS classes in `global.css` and applied via `className` on JSX elements.

4. **Responsive strategy.** Uses Antd's built-in `breakpoint="lg"` on `Layout.Sider` (992px) to auto-collapse to a 64px icon rail, plus a `useNarrowViewport()` hook watching `(max-width: 991px)` to switch between inline sidebar and an off-canvas `Drawer`. A `@media (max-width: 860px)` rule narrows the session panel. There is no mobile-first grid framework — layout is flexbox-based with a few narrow breakpoints.

5. **Build-time version injection.** `vite.config.ts` reads the repo root `VERSION` file and exposes it as `__PLATFORM_VERSION__`, which the app renders as a tag next to the "Luban AIOps" brand in the sidebar. This is enforced by the `make validate-version` step referenced in the config comments.

6. **No CSS modules / no per-component stylesheets.** All custom CSS is centralized in `global.css`; components reference shared class names rather than scoped stylesheets.

## Conventions and constraints

- **Use Antd for all primitive UI controls**; do not roll your own buttons, menus, alerts, or drawers — style them via the shared `portalTheme` instead of overriding CSS.
- **Do not hard-code colors or radii in components.** Pull values from the `palette` tokens (for JS logic) or the `--*` CSS variables (in CSS); the two sources must stay in sync.
- **Bespoke layout classes follow the naming patterns already in `global.css`**: `app-shell`, `view-container` / `view-container-flush`, `session-panel`, `chat-view`, `evidence-card`, `confirm-card`, `turn-request-banner`, `view-toolbar`, `report-form`, `incident-section`, `mobile-menu-button`, `sidebar-brand(-spacer)`, `sidebar-footer(-collapsed)`, `md-content`, `composer-selection-bar`, `turn-group`, `evidence-turn`, `tool-name`, `evidence-meta`, `evidence-pre`, `confirm-call`, `confirm-note`, `confirm-card-title`, `sidebar-footer`, `view-toolbar`, `report-form`, `incident-section`.
- **Keyboard accessibility is preserved** — `:focus-visible` gets a 2px accent-colored outline with offset, and interactive elements use `aria-label` attributes (e.g. login/logout/menu buttons).
- **Markdown and code blocks** rendered inside transcripts must be wrapped in the `.md-content` class so headings, code, pre, blockquote, tables, links, hr, strong, and em inherit the portal's dark palette.
- **Chat transcript evidence and HITL confirmation cards** must use the established `.evidence-*` and `.confirm-*` class families so they align with the existing transcript column width and collapsed-by-default behavior.
- **Responsive behavior** should respect the existing breakpoints (992px for sider collapse, 860px for session panel narrowing) and prefer folding content (drawer, collapsible panels) over squashing layouts.
- **Version display** must read from the injected `__PLATFORM_VERSION__` constant (via `./version`) rather than reading the filesystem directly.

These conventions are documented inline in the source files themselves (comments referencing SPEC-019, SPEC-020, SPEC-023, SPEC-024, SPEC-031) and are enforced by the fact that every view component imports and composes the same `portalTheme` and shares the same `global.css`.