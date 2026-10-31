---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
---

## System Overview

The only frontend in the repository is the **operator portal** (`products/operator-portal/web-ui/app/`), a React 19 + TypeScript SPA built with Vite. There are no other UI packages, storybooks, or design-system repos in this workspace.

Styling is split across two layers:

1. **Ant Design (antd v6)** — the component library and its `ThemeConfig` token system drive layout primitives (`Layout`, `Sider`, `Menu`, `Tabs`, `Collapse`, `Typography`, etc.) via `@ant-design/icons` and `@ant-design/x`. The theme is configured through `src/theme/tokens.ts` using `antd.darkAlgorithm`.
2. **Plain CSS custom properties** — bespoke styles live in `src/theme/global.css` (~740 lines) and consume CSS variables defined on `:root`. These cover app shell chrome, chat transcript layout, session list, HITL confirmation cards, tool evidence groups, markdown rendering, sticky request banners, and bounded panes for documents.

There is no Tailwind, Sass/Less, CSS-in-JS, or utility-first framework. No separate `.module.css` files were found; all styling is centralized in `global.css`.

## Key Files

- `products/operator-portal/web-ui/app/package.json` — declares antd ^6.6.2, @ant-design/icons ^6, @ant-design/x ^2.9, react ^19, vite ^8, vitest ^4.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radii, fonts, mapped into an antd `ThemeConfig` (`portalTheme`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — all bespoke CSS, including dark-mode `:root` tokens, responsive breakpoints, animations, and spec-linked regions.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving.

## Architecture and Conventions

### Dual-token vocabulary
`tokens.ts` defines a `palette` object (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and mirrors every value as a CSS custom property on `:root` in `global.css`. The comment in `tokens.ts` states they are "ported verbatim from the legacy portal's :root design tokens" so that both antd components and bespoke CSS share one vocabulary. This is the de facto design-token layer.

### Dark-only theme
`global.css` sets `color-scheme: dark` and the palette uses slate/navy tones (`#0f172a` background, `#38bdf8` accent). There is no light-mode toggle or alternate algorithm in the codebase.

### Component vs. bespoke boundary
- Layout, navigation, menus, tabs, collapse panels, typography, and form controls come from antd and are themed via `portalTheme`.
- App-shell chrome (sidebar, view container, session panel, chat columns, approval inbox entries, document panes) is hand-written CSS in `global.css`.
- Markdown content rendered inside the portal gets scoped rules under `.md-content`.
- Tool evidence groups get their own section (`.evidence-turn`, `.evidence-card`, `.tool-name`, `.evidence-pre`).

### Responsive strategy
Responsive behavior is CSS-media-query based rather than breakpoint-driven by a framework:
- `@media (max-width: 860px)` narrows the session panel from 260px to 200px.
- The sidebar uses antd's built-in collapsed Sider behavior below its `lg` breakpoint (992px) plus a pinned `.mobile-menu-button` that opens an off-canvas drawer on small screens.
- `prefers-reduced-motion: reduce` disables the turn-arrival flash animation.

### Spec-linked style regions
Comments throughout `global.css` tie visual changes to specific specs (SPEC-011 R-4, SPEC-019 R-1, SPEC-020 R-4, SPEC-023 R-1/R-3/R-5, SPEC-034 R-1/R-4, SPEC-035 R-4, SPEC-037 R-6, SPEC-039 R-8, SPEC-041 R-3, SPEC-063 R-5a). This is the primary traceability mechanism between UI changes and product requirements.

### Build-time version injection
`vite.config.ts` reads the root `VERSION` file and the `package-lock.json` to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time. The Settings view consumes these to display the tech stack table. The comment notes `make validate-version` asserts the constant.

## Conventions and Constraints

- **Single source of color/radius values**: Colors and `radius` are declared once in `tokens.ts` and mirrored into CSS custom properties; bespoke styles reference `var(--*)` rather than hard-coded hex values. (Observed pattern in `global.css`.)
- **Dark mode is the only supported theme**: `color-scheme: dark` is set globally and `antd.darkAlgorithm` is the only algorithm used. (Enforced by `tokens.ts` and `global.css`.)
- **Bounded pane heights**: Document panes use a CSS variable `--bounded-pane-max-height` set per wrapper, consumed by `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body` to cap scrollable content while keeping structural chrome pinned. (Documented in `global.css` comments referencing SPEC-041 R-3.)
- **Accessibility baseline**: A global `:focus-visible` rule provides a 2px accent outline with offset; `prefers-reduced-motion` suppresses animations. (Defined in `global.css`.)
- **No SCSS/Tailwind**: The dependency manifest lists only antd, React, Vite, Vitest, and dayjs — no preprocessors or utility frameworks are present.
- **Build output**: Vite compiles to `app/dist` (consumed by the parent `nginx.conf`); hashed asset filenames enable immutable caching while `index.html` stays no-store. (Declared in `vite.config.ts`.)
- **Spec traceability**: Every major visual region in `global.css` is annotated with the originating SPEC number and requirement letter (e.g., `/* SPEC-023 R-1 */`, `/* SPEC-039 R-8 */`), making the CSS itself a partial requirements artifact.