---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme + CSS Custom Properties'
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

The only frontend in this repository is the **operator-portal** (`products/operator-portal/web-ui/app`). It is a React 19 + Vite application styled with:

- **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library.
- A **dark-only theme** configured via Ant Design's `ThemeConfig` using `antdTheme.darkAlgorithm`.
- A parallel set of **CSS custom properties** on `:root` that mirror the JS palette, consumed by bespoke `.css` classes and by Ant Design components through the theme.
- Plain **global CSS** (no Sass/Less/PostCSS pipeline) under `app/src/theme/global.css` (~740 lines).
- No design-system framework beyond Ant Design; no Tailwind, no CSS-in-JS library, no utility-first approach.

There is no other UI code in the repo — backend services are Python/FastAPI, samples are shell/Python scripts, and shared assets live under `shared/platform-ops/dashboards/` (Grafana dashboards, not web UI). The author guidelines explicitly call out the "operator-portal styling card" as a known module boundary, confirming this is the sole scope for `frontend_style`.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite 8, Vitest.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for the palette and Ant Design `ThemeConfig` (`portalTheme`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — global base styles, CSS custom properties, layout chrome, chat workspace, markdown rendering, HITL confirmation cards, evidence groups, sticky request banner, bounded panes.
- `products/operator-portal/nginx.conf` — serves the built static bundle.

## Architecture and conventions

### Dual-token vocabulary

`src/theme/tokens.ts` defines a `palette` object and maps it into an Ant Design `ThemeConfig` named `portalTheme`. The same color values are redeclared as CSS custom properties on `:root` in `global.css` (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius`, etc.). The file header documents this as a port from the legacy portal's `styles.css` and ties it to SPEC-023 R-1 dark-theme requirement. Components consume tokens via Ant Design's theme API; bespoke styles consume CSS variables.

### Dark-only, no light mode

`:root { color-scheme: dark; }` forces the browser's native dark UI. There is no theme toggle or light-mode branch in the codebase.

### Layout model

- Full-height app shell using `.app-shell` with an Ant Design `Layout.Sider` sidebar plus one active view.
- Sidebar collapses to a 64px icon rail; a pinned `.mobile-menu-button` toggles an off-canvas drawer below antd's `lg` breakpoint (992px).
- Views render inside `.view-container` (scrollable) or `.view-container-flush` (full-bleed, e.g. chat).
- Chat workspace uses a fixed-width `.session-panel` (260px, shrinks to 200px at ≤860px) beside a flex column transcript.

### Component-scoped CSS

Styles are written as plain class names in `global.css` (BEM-ish naming: `.session-item`, `.confirm-card`, `.evidence-card`, `.turn-group`, `.digest-bounded`, `.prose-bounded`). There are no scoped CSS modules or CSS-in-JS per-component style files.

### Responsive strategy

Responsive behavior is minimal and media-query based:
- `@media (max-width: 860px)` narrows the session panel.
- `@media (prefers-reduced-motion: reduce)` disables the turn-arrival flash animation.
- The mobile menu button is always visible and switches between inline sidebar folding and drawer opening depending on viewport size relative to antd's breakpoints.

No responsive breakpoints are defined for content grids; the primary pattern is horizontal flex layouts that naturally wrap.

### Accessibility conventions

- `:focus-visible` gets a 2px accent outline with offset.
- Comments explicitly state keyboard focus must stay visible on custom controls.
- Native `<summary>` elements are used for expanders (confirmation details, recovery facts).

### Bounded panes

Scrollable panes use a CSS variable `--bounded-pane-max-height` set by the parent view, applied to `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body` so structural chrome stays pinned while content scrolls. Code blocks and evidence panels cap height at 280px.

### Spec-driven style gates

Style decisions are cross-referenced to specs throughout the CSS comments (SPEC-023 R-1 dark theme, SPEC-019 R-1 collapsed nav labels, SPEC-020 R-4 HITL cards, SPEC-011 R-4 evidence parity, SPEC-034/SPEC-035 arrival highlight, SPEC-037 signed-execution receipts, SPEC-039 session id display, SPEC-041 bounded panes, SPEC-063 owner recovery detail). This is the documented enforcement mechanism rather than lint rules.

## Conventions and constraints

Observed conventions (descriptive):
- All colors flow through the `palette` object in `tokens.ts`; new colors should be added there and mirrored in `:root` CSS custom properties.
- Ant Design components receive `portalTheme` via the theme provider; bespoke overrides go in `global.css` using CSS variables.
- Class names follow a flat `.block` / `.block-element` convention without a preprocessor namespace.
- Markdown-rendered content is styled via a `.md-content` wrapper selector.
- Animations respect `prefers-reduced-motion`.
- The build injects locked dependency versions (`__REACT_VERSION__`, `__ANTD_VERSION__`) into the runtime for the Settings inventory table.

Enforced rules (from authoritative sources):
- **Dark theme**: `color-scheme: dark` and `antdTheme.darkAlgorithm` are declared in `global.css` and `tokens.ts`; the comment cites SPEC-023 R-1 as the requirement driving the dark-only palette.
- **Token parity**: `tokens.ts` and `global.css` must stay synchronized — the file header states the CSS custom properties "mirror" the JS palette so bespoke styles and Ant Design components share one vocabulary.
- **Build output**: `vite.config.ts` sets `build.outDir = "../dist"` and the comment notes content-hashed filenames make assets immutable-cacheable while `index.html` stays no-store (SPEC-023 R-1).
- **Version injection**: `make validate-version` asserts the `__PLATFORM_VERSION__` constant injected from the root `VERSION` file (documented in `vite.config.ts`).
- **Node engine**: `package.json` pins `engines.node >= 22.22.2`.

