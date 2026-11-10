---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System overview

The only frontend in the repository is the **operator-portal** web UI under `products/operator-portal/web-ui/app/`. It is a React 19 + TypeScript application built with Vite (`@vitejs/plugin-react`), and its styling strategy combines:

1. **Ant Design v6** as the component library, configured via `ConfigProvider`.
2. A single shared theme object in `app/src/theme/tokens.ts` that maps a hand-authored palette to Ant Design's `ThemeConfig` (using `antd.theme.darkAlgorithm`).
3. A parallel set of CSS custom properties in `app/src/theme/global.css` that mirror the same palette for bespoke styles outside Ant components.
4. A flat global stylesheet (`global.css`) — no CSS-in-JS, no SCSS, no Tailwind, no design-token build step.

There are no other product directories containing CSS/HTML; all other products are Python services.

## Key files

- `products/operator-portal/web-ui/app/package.json` — declares `antd`, `@ant-design/icons`, `@ant-design/x`, React 19, Vite, Vitest.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/main.tsx` — root entry that wraps `<App>` in `ConfigProvider` with `portalTheme` and imports `./theme/global.css`.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines `palette` (bg/surface/border/text/accent/success/error/warning/codeBg/radius) and `portalTheme: ThemeConfig`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — ~740 lines of base styles, layout, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, sticky request banner, bounded panes, and view chrome.

## Architecture and conventions

### Dual token source
`tokens.ts` and `global.css` are kept in sync by hand. The comment in `tokens.ts` states the palette was "ported verbatim from the legacy portal's :root design tokens" and that the CSS custom properties "mirror these so bespoke styles and antd components stay on one vocabulary". Every color used by Ant components goes through `portalTheme.token.*`; every bespoke class uses `var(--accent)`, `var(--surface)`, etc. There is no runtime theme switching — `color-scheme: dark` is hardcoded and `darkAlgorithm` is the only algorithm.

### Ant Design configuration
All Ant components receive the theme through `ConfigProvider` at the app root. Overrides are done via `ThemeConfig` fields (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBorder`, `borderRadius`, `fontFamily`, `fontFamilyCode`). No per-component inline style overrides were found in the scanned files.

### Global stylesheet structure
`global.css` is organized into named sections with comments referencing spec requirements:
- App shell / sidebar / mobile menu button
- Chat workspace (SPEC-023 R-3): session panel, transcript, composer, selection bar
- Turn arrival animation (SPEC-034 R-1 / SPEC-035 R-4) with `prefers-reduced-motion`
- Markdown content rendering (`.md-content`)
- Tool evidence groups (SPEC-011 R-4 parity)
- Sticky request banner
- HITL confirmation cards (SPEC-020 R-4)
- Signed-execution receipts (SPEC-037 R-6)
- Owner recovery details (SPEC-063 R-5a)
- Shared view chrome (SPEC-023 R-5)
- Documents drawer bounded panes (SPEC-041 R-3)

### Responsive strategy
Responsive behavior is minimal and breakpoint-driven:
- `.mobile-menu-button` is pinned top-left and toggles an off-canvas drawer below antd's `lg` breakpoint (992px).
- A single `@media (max-width: 860px)` shrinks `.session-panel` from 260px to 200px.
- Bounded panes use a CSS variable `--bounded-pane-max-height` set by the consuming view rather than a media query.
- No fluid typography or container queries were observed.

### Build-time versioning
`vite.config.ts` reads the repo-level `VERSION` file and the local `package-lock.json` to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, and `__ANTD_VERSION__` constants. This lets the Settings view display the exact shipped dependency versions.

## Conventions and constraints

- **Dark-only theme**: `color-scheme: dark` is set on `:root` and `darkAlgorithm` is the only algorithm in `portalTheme`. Light mode is not supported.
- **Token duality**: Palette values live in `tokens.ts` for Ant Design and are duplicated as CSS custom properties (`--bg`, `--surface`, `--accent`, …) in `global.css`. Changes must be mirrored in both places (enforced by human review; there is no automated sync).
- **Spec-linked styles**: Style blocks are annotated with their originating spec requirement (e.g. `SPEC-023 R-1`, `SPEC-020 R-4`, `SPEC-037 R-6`, `SPEC-041 R-3`), tying visual decisions back to formal specs.
- **No utility-first CSS**: Styles are written as explicit BEM-style classes in a single global stylesheet; there is no Tailwind, PostCSS, SCSS, or CSS Modules.
- **Accessibility baseline**: `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion` disables the turn-arrival flash animation.
- **Font stack**: Primary font is `Inter` with system fallbacks; code font is `'JetBrains Mono', 'Fira Code' monospace`, declared in both `portalTheme.fontFamilyCode` and inline `.md-content code` rules.
- **Build output**: Vite emits hashed assets to `web-ui/dist/`, served by the nginx config at the parent level; index.html stays cacheable while static assets are immutable via content hashes.