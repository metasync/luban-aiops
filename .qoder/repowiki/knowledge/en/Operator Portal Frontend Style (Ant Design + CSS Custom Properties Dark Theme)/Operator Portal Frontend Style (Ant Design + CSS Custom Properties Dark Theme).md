---
kind: frontend_style
name: Operator Portal Frontend Style (Ant Design + CSS Custom Properties Dark Theme)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/nginx.conf
---

## What system/approach is used

The operator portal's UI lives in `products/operator-portal/web-ui/app` and is a React 19 + TypeScript SPA built with Vite. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via Ant Design's `ThemeConfig`. A single dark palette is defined once in `app/src/theme/tokens.ts` and applied through the `portalTheme` object using `antdTheme.darkAlgorithm`. The same palette is mirrored as CSS custom properties in `app/src/theme/global.css` so that bespoke component styles consume one vocabulary alongside Ant Design components.

There is no CSS-in-JS library beyond Ant Design's theme tokens, no Tailwind or Sass pipeline — plain `.css` files under `src/theme/` plus per-component JSX. Build-time constants (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) are injected by `vite.config.ts` for the Settings view tech-stack table.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd`, `@ant-design/x`, `@ant-design/icons`, `vite`, `vitest`, `typescript`.
- `products/operator-portal/web-ui/app/vite.config.ts` — Vite config: React plugin, build output to `../dist`, dev proxy `/api → http://localhost:8080`, test environment `jsdom`, and build-time `define` constants.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radius, fonts; exports `palette` and `portalTheme: ThemeConfig`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — global base styles, `:root` CSS custom properties mirroring `tokens.ts`, layout shell, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, sticky request banner, bounded panes, and responsive rules.
- `products/operator-portal/web-ui/nginx.conf` — serves the built `web-ui/dist` at `/`.

## Architecture and conventions

- **Design-token duality**: `tokens.ts` defines the JS-side Ant Design theme; `global.css` declares identical values as `--bg`, `--surface`, `--accent`, etc., so both Ant Design components and hand-written CSS share one palette. The comment in `tokens.ts` explicitly states this mirrors the legacy portal's `:root` design tokens (SPEC-023 R-1).
- **Dark-only theme**: `color-scheme: dark` is set globally; `portalTheme` uses `darkAlgorithm`; all custom properties use dark hex values. No light-mode toggle exists.
- **Typography**: Font families are declared in `portalTheme.token.fontFamily` / `fontFamilyCode` and echoed in `global.css` body and code blocks (`Inter` for prose, `JetBrains Mono` / `Fira Code` for code).
- **Layout shell**: Global CSS defines a full-height app shell with a sidebar (`app-shell`, `sidebar-footer`, `mobile-menu-button`) and a main content area (`view-container`, `view-container-flush`). Sidebar collapses to a 64px icon rail below antd's `lg` breakpoint (992px), switching from inline collapse to an off-canvas drawer.
- **Chat workspace**: Dedicated section in `global.css` (`.chat-view`, `.session-panel`, `.chat-column`, `.chat-messages`, `.turn-group`, `.composer-selection-bar`) implements a two-pane session list + transcript layout with bounded scrollable areas.
- **Markdown rendering**: A shared `.md-content` rule block styles headings, lists, code, preformatted blocks (bounded to 280px), blockquotes, links, tables, and horizontal rules — ported from the legacy portal.
- **Feature-specific modules**: Styles are grouped by feature in the same file — tool evidence groups (`.evidence-turn`, `.evidence-card`, `.evidence-pre`), sticky request banner (`.turn-request-banner`), HITL confirmation cards (`.confirm-card`, `.confirm-call`, `.confirm-execution`), approvals inbox entries (`.approvals-entry`), and bounded document panes (`.digest-bounded`, `.prose-bounded` driven by a `--bounded-pane-max-height` CSS variable).
- **Responsive strategy**: Pure CSS media queries. Two breakpoints observed: `max-width: 860px` narrows the session panel; antd's built-in `lg` breakpoint drives sidebar drawer vs inline behavior.
- **Accessibility**: `:focus-visible` gets a 2px accent outline with offset; `prefers-reduced-motion` disables the turn-arrival flash animation while keeping a static tint.
- **Build & deployment**: `vite build` outputs hashed assets to `web-ui/dist`, served by nginx at `/`. Dev mode proxies `/api` calls to the platform gateway on localhost:8080.

## Conventions and constraints

- All color/radius/font values flow through `tokens.ts` → `portalTheme` for Ant Design and are duplicated as `--var` names in `global.css`'s `:root`. Adding a new token requires updating both locations.
- Component styling must prefer Ant Design theming via `ThemeConfig` tokens; bespoke CSS should reference `var(--*)` variables rather than hard-coded hex values.
- Chat transcripts and evidence panels use bounded scrolling (`max-height: 280px`) so large content does not push the viewport out of view.
- Feature styles are tagged with their originating spec requirement comments (e.g. `SPEC-023 R-1`, `SPEC-034 R-1`, `SPEC-037 R-6`, `SPEC-041 R-3`), tying visual changes back to requirements.
- The portal ships only a dark theme; there is no runtime theme switcher in the current codebase.