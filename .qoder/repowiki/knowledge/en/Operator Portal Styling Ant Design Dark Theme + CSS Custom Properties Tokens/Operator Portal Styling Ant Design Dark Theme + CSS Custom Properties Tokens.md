---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme + CSS Custom Properties Tokens'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System / Approach

The only frontend in the repository is the **operator-portal** web UI under `products/operator-portal/web-ui/app/`. It is a React 19 + TypeScript application built with Vite and styled primarily through **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) using the dark theme algorithm, with a small set of bespoke component styles defined in a single global stylesheet.

There is no Tailwind, Sass/Less pipeline, CSS-in-JS library (other than Antd's own), or design-system package — just plain `.css` plus a TypeScript token file that mirrors the same palette into Antd's `ThemeConfig`.

## Key Files

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd ^6.6.2`, `@ant-design/icons`, `@ant-design/x`, `vite`, `vitest`, `typescript ~5.9.3`.
- `products/operator-portal/web-ui/app/vite.config.ts` — Vite config; injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time via `define`; outputs to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for the color palette, radius, and fonts; exports `palette` and `portalTheme` (Antd `ThemeConfig` using `antdTheme.darkAlgorithm`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — all bespoke CSS: CSS custom properties on `:root`, layout shell, chat workspace, evidence cards, HITL confirmation cards, markdown rendering, sticky request banner, bounded panes, and a narrow-viewport breakpoint at 860px.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` at `/`.

## Architecture and Conventions

### Dual-token vocabulary (SPEC-023 R-1)
The comment in `tokens.ts` states the design intent explicitly: the palette is "ported verbatim from the legacy portal's :root design tokens" and the CSS custom properties in `global.css` mirror them so "bespoke styles and antd components stay on one vocabulary." The two sources are:

1. `src/theme/tokens.ts` → consumed by Antd via `portalTheme.token` (`colorPrimary`, `colorBgBase`, `colorText`, `borderRadius`, `fontFamily`, etc.).
2. `:root` in `global.css` → consumed by bespoke CSS classes via `var(--bg)`, `var(--surface)`, `var(--accent)`, `var(--border)`, `var(--text-muted)`, `var(--radius)`, `var(--code-bg)`.

This keeps Antd components and hand-written CSS sharing the same semantic names.

### Dark-only theme
`global.css` sets `color-scheme: dark` on `:root`, and `portalTheme` uses `antdTheme.darkAlgorithm`. There is no light-mode toggle or conditional theme provider in the codebase — the portal is dark-only.

### Component styling strategy
- Antd primitives (`Layout`, `Menu`, `Button`, `Table`, `Tabs`, `Collapse`, `Typography`, `Drawer`, `Modal`, etc.) are styled exclusively through the injected `portalTheme` — no per-component overrides in TSX props where avoidable.
- Bespoke layout and domain-specific visuals (chat transcript, session list, evidence cards, HITL confirmation cards, sticky request banner, bounded panes) live in `global.css` as BEM-style class names prefixed with feature areas (`.chat-view`, `.session-panel`, `.evidence-card`, `.confirm-card`, `.turn-request-banner`, `.digest-bounded`, `.prose-bounded`).
- No scoped CSS modules, no CSS-in-JS, no utility-first framework.

### Responsive strategy
Responsive behavior is minimal and CSS-media-query driven:
- A single breakpoint at `max-width: 860px` narrows `.session-panel` from 260px to 200px.
- Comments reference antd's `lg` breakpoint (992px) for Sider auto-collapse vs. off-canvas drawer behavior, but the actual mobile drawer logic lives in TSX components rather than CSS.
- No grid system beyond Flexbox and CSS Grid used directly (e.g., `.recovery-facts` uses `grid-template-columns: max-content 1fr`).

### Accessibility conventions observed
- `:focus-visible` gets a 2px accent outline with 2px offset.
- `prefers-reduced-motion: reduce` disables the `.turn-group.turn-arrived` flash animation while keeping a static background tint.
- Semantic HTML elements (`<summary>`, `<dt>/<dd>`) are used for native expanders inside confirmation and recovery detail sections.

### Build-time versioning
`vite.config.ts` reads the root `VERSION` file and the local `package-lock.json` to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, and `__ANTD_VERSION__` as compile-time constants. The comment ties this to SPEC-023 R-1 and the `make validate-version` check.

## Conventions and Constraints

- **Design tokens are dual-sourced**: colors/radius/fonts are declared once in `src/theme/tokens.ts` and mirrored into `:root` CSS custom properties in `global.css` so both Antd and bespoke CSS consume the same values. (Enforced by the explicit comment in `tokens.ts` referencing SPEC-023 R-1 dark theme.)
- **Theme is dark-only**: `color-scheme: dark` is set globally and `antdTheme.darkAlgorithm` is the only algorithm configured; no light-mode path exists.
- **Bespoke styles go in `global.css`**, not per-component CSS files; Antd components are themed via the `portalTheme` `ThemeConfig` rather than inline overrides.
- **CSS class naming follows a feature-area prefix convention** (`.chat-*`, `.session-*`, `.evidence-*`, `.confirm-*`, `.approvals-*`, `.view-toolbar`, `.digest-bounded`, `.prose-bounded`) — observed throughout `global.css`.
- **Bounded scroll regions use a single CSS variable**: views set `--bounded-pane-max-height` on wrappers and `.digest-bounded .ant-tabs-body-holder` / `.prose-bounded .ant-collapse-body` clamp scrolling via that variable (documented in the `global.css` comments referencing SPEC-041 R-3).
- **Build output goes to `web-ui/dist`** and is served by nginx at `/`; content-hashed filenames are enabled by default Vite behavior for immutable caching (commented as SPEC-023 R-1).
- **Node engine requirement**: `package.json` pins `node >= 22.22.2`.