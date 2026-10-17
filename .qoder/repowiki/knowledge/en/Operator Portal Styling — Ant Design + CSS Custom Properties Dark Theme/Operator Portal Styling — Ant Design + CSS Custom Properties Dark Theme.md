---
kind: frontend_style
name: Operator Portal Styling — Ant Design + CSS Custom Properties Dark Theme
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System

The only frontend in the repository is the **operator-portal** Next/React application under `products/operator-portal/web-ui/app`. It is a Vite + React 19 project built with TypeScript, using **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library. There is no Tailwind, SCSS, or CSS-in-JS beyond what Ant Design ships; bespoke styling lives in a single global stylesheet.

## Key files

- `products/operator-portal/web-ui/app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite 8, Vitest.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for the palette and Ant Design `ThemeConfig` (dark algorithm).
- `products/operator-portal/web-ui/app/src/theme/global.css` — CSS custom properties mirroring the tokens, plus all bespoke layout, chat, evidence, HITL confirmation card, and markdown styles.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` at `/`.

## Architecture and conventions

### Dual-token vocabulary

Design tokens are defined once in `src/theme/tokens.ts` as a `palette` object and an Ant Design `portalTheme` `ThemeConfig` using `antdTheme.darkAlgorithm`. The same color values are re-declared as CSS custom properties on `:root` in `global.css` (`--bg`, `--surface`, `--accent`, `--border`, `--text-muted`, `--code-bg`, `--radius`, etc.). The comment in `tokens.ts` states this is "ported verbatim from the legacy portal's :root design tokens" and that the two sources exist so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1 dark theme). Components consume tokens via Ant Design props; hand-written CSS consumes CSS variables.

### Dark-only theme

`color-scheme: dark` is set on `:root`; there is no light-mode toggle or alternate theme configuration. All colors are chosen for a dark background (`#0f172a`).

### Component library usage

Ant Design is used directly (`ant-layout-sider`, `ant-menu`, `ant-tabs`, `ant-collapse`, `ant-typography`, etc.) and its default dark theme is customized through the `portalTheme` passed to the app root. Bespoke overrides target Ant Design class names (e.g. `.ant-layout-sider-collapsed .ant-menu-item-group-title`) rather than using Ant Design's `cssVar` mode extensively.

### Global stylesheet strategy

All non-component CSS lives in `global.css` — there are no per-component CSS modules, styled-components, or CSS-in-JS. Styles follow a BEM-like naming scheme (`session-panel`, `session-item.active`, `confirm-card.pending`, `turn-request-banner.visible`) and rely on CSS custom properties for colors and radii. Layout uses Flexbox and CSS Grid; responsive behavior is handled with a single `@media (max-width: 860px)` breakpoint for the session panel width and a separate mobile drawer path driven by Ant Design's `lg` breakpoint (992px) for the sidebar collapse.

### Accessibility and motion

- A global `:focus-visible` rule gives a 2px accent outline with 2px offset.
- `prefers-reduced-motion: reduce` disables the 4-second turn-arrival flash animation while keeping a static tinted background.
- Markdown rendering (`md-content`) gets dedicated typography rules for headings, code blocks, blockquotes, tables, and links.

### Spec-driven style gates

Many style sections are annotated with spec references, tying visual changes to requirements:
- SPEC-023 R-1 (dark theme), R-3 (chat workspace), R-5 (shared view chrome)
- SPEC-011 R-4 (tool evidence groups parity)
- SPEC-019 R-1 (collapsed sidebar group titles)
- SPEC-020 R-4 (HITL confirmation cards)
- SPEC-024 (extensible selection strip)
- SPEC-034 R-1 / SPEC-035 R-4 (turn arrival highlight)
- SPEC-037 R-6 (signed-execution receipts)
- SPEC-039 R-8 (session id badge)
- SPEC-041 R-3 (documents drawer bounded panes)
- SPEC-063 R-5a (owner recovery detail)

### Build-time version injection

`vite.config.ts` reads the repo-level `VERSION` file and the lockfile to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, and `__ANTD_VERSION__` constants into the bundle, so the Settings page can display the exact shipped dependency versions.

## Conventions and constraints

- **Single source of truth for colors**: the `palette` object in `src/theme/tokens.ts` is the canonical definition; `global.css` mirrors it as CSS custom properties. Adding a new color requires updating both places (documented intent in the file comments).
- **No per-component CSS files**: all bespoke styles go in `global.css`; component JSX uses Ant Design props or plain HTML classes.
- **Dark theme only**: `color-scheme: dark` is enforced at the root; no light-mode switch exists.
- **Responsive breakpoints**: the only viewport-specific CSS is `@media (max-width: 860px)` for the session panel; larger responsive behavior is delegated to Ant Design's built-in `lg` breakpoint handling for the Sider.
- **Motion policy**: animations use `@keyframes` but must respect `prefers-reduced-motion: reduce` (enforced by the media query in `global.css`).
- **Build output**: Vite builds to `../dist` (consumed by `nginx.conf`); content-hashed filenames are relied upon for immutable caching while `index.html` stays no-store (per comment referencing SPEC-023 R-1).
- **Spec traceability**: visual features are annotated with their originating spec number (e.g. `/* SPEC-020 R-4 */`), making the requirement-to-style mapping auditable.