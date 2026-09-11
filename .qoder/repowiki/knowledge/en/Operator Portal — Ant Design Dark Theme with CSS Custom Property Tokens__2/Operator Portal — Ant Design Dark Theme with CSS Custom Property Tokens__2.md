---
kind: frontend_style
name: Operator Portal — Ant Design Dark Theme with CSS Custom Property Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/index.html
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 + TypeScript SPA built with Vite and styled exclusively through **Ant Design v6** in its dark algorithm, augmented by a single global stylesheet. There is no Tailwind, CSS-in-JS library (other than Antd's `ConfigProvider`), or component library beyond Ant Design and `@ant-design/icons`. The app ships as static assets under `web-ui/dist/`, served by the bundled nginx configuration.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite, Vitest, jsdom.
- `app/src/theme/tokens.ts` — central design token definition: a `palette` object (bg, surface, surfaceAlt, border, text, textMuted, accent, success, error, warning, codeBg, radius) plus an `antd` `ThemeConfig` (`portalTheme`) that maps those tokens to Antd's `colorPrimary`, `colorBgBase`, `colorText`, `borderRadius`, `fontFamily`, etc., using `darkAlgorithm`.
- `app/src/theme/global.css` — root-level CSS custom properties (`--bg`, `--surface`, `--accent`, …) that mirror `tokens.ts` verbatim so bespoke styles and Antd components share one vocabulary; also contains all layout, chat transcript, evidence cards, approval cards, markdown rendering, sticky banner, and bounded-pane rules.
- `app/src/main.tsx` — bootstraps the app inside `<ConfigProvider theme={portalTheme}>` and imports `global.css` once at the top level.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time via `define`; outputs to `../dist` for nginx; proxies `/api` to `localhost:8080` in dev; runs tests under `jsdom`.
- `app/index.html` — minimal shell declaring `lang="en"`, `color-scheme: dark`, and mounting `#root`.
- `app/src/App.tsx` — uses Antd `Layout.Sider` (dark theme, breakpoint `lg` = 992px) with a collapsible 64px icon rail and an off-canvas `Drawer` on narrow viewports; composes views (chat, incidents, approvals, documents, audit, permissions, tools, skills, settings).

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` defines the palette; `global.css` re-declares the same values as CSS variables (`:root { --bg, --surface, … }`). Comments explicitly state they are "ported verbatim from the legacy portal's :root design tokens" and exist so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1). New colors must be added to both places.
2. **Ant Design dark theme is the only theme**: `portalTheme` applies `darkAlgorithm` and overrides primary/background/text/border/success/error/warning/radius/font families. All Antd components inherit this; there is no light-mode toggle.
3. **Global CSS over scoped modules**: The project does not use CSS Modules, Sass, or CSS-in-JS. All styling lives in one `global.css` file, organized into sections (app shell, chat workspace, markdown content, tool evidence groups, sticky request banner, HITL confirmation cards, shared view chrome, bounded panes). Class names follow a flat BEM-like scheme (`session-item`, `evidence-card`, `confirm-card`, `turn-group`, `view-container`, `digest-bounded`, `prose-bounded`).
4. **Responsive strategy**: Breakpoint-aware behavior is implemented in two ways — (a) CSS `@media (max-width: 860px)` for the session panel width, and (b) JS `useNarrowViewport()` hook watching `matchMedia("(max-width: 991px)")` to switch between inline `Layout.Sider` and a left `Drawer`. The Sider uses Antd's built-in `breakpoint="lg"` (992px) so the sidebar auto-collapses and the drawer takes over.
5. **Design-token-driven spacing & radii**: Spacing is ad-hoc (8px, 12px, 16px, 20px, 24px) but `borderRadius` comes from `palette.radius` (8) and is consumed via `var(--radius)` in CSS and `borderRadius` in the Antd theme config.
6. **Accessibility baseline**: `color-scheme: dark` is declared in both `index.html` and `global.css`; `:focus-visible` gets a 2px accent outline; motion-sensitive animations respect `prefers-reduced-motion: reduce` (the turn-arrive flash animation is disabled when reduced motion is preferred).
7. **Build-time versioning**: Platform and dependency versions are injected as constants (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) so the Settings view can display the exact shipped tech stack.

## Conventions and constraints

- **Dark-only UI**: The entire portal is locked to dark mode via `color-scheme: dark` and Antd's `darkAlgorithm`; no light-theme path exists.
- **Token sync rule**: Any change to `tokens.ts` must be mirrored in `global.css`'s `:root` custom properties (and vice versa); this is enforced by comments referencing SPEC-023 R-1 and by the fact that bespoke CSS selectors read `var(--accent)`, `var(--surface)`, etc., while Antd reads the `ThemeConfig`.
- **Component styling via Antd `ConfigProvider`**: All Antd components receive their theme through the top-level `ConfigProvider`; per-component style overrides should prefer Antd props before falling back to CSS class selectors in `global.css`.
- **View layout convention**: Every top-level view renders inside a container with class `view-container` (or `view-container-flush` for full-bleed views like chat), providing consistent padding and scrolling behavior.
- **Bounded panes**: Scrollable content regions use the `--bounded-pane-max-height` CSS variable on wrapper elements and the `.digest-bounded` / `.prose-bounded` classes to constrain height and enable independent scrolling (SPEC-041 R-3).
- **Mobile navigation**: Below 992px the sidebar collapses to a 64px icon rail and a floating `mobile-menu-button` opens a left `Drawer`; the rail stays visible at every width.
- **No additional CSS framework**: No Tailwind, Sass, PostCSS plugins, or CSS-in-JS libraries are present — styling is pure CSS + Antd theming.