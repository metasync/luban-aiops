---
kind: frontend_style
name: Operator Portal Styling — Ant Design Dark Theme with CSS Custom Properties Tokens
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

The only frontend in the repository is the **operator-portal** (`products/operator-portal/web-ui/app/`), a React 19 + TypeScript SPA built with Vite. Visual styling is provided by:

- **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library.
- A **dark-only theme** configured via Ant Design's `ThemeConfig` using `antdTheme.darkAlgorithm`.
- A single global stylesheet `app/src/theme/global.css` that defines CSS custom properties (design tokens) on `:root` and styles bespoke UI regions not covered by Ant Design components.
- No CSS-in-JS, no Tailwind, no Sass/Less preprocessor — plain `.css` consumed directly by Vite.

There is no second frontend; backend products are Python FastAPI services with no client-side assets.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd`, `@ant-design/x`, `@ant-design/icons`, `vite`, `vitest`, `typescript`; build script runs `tsc --noEmit && vite build`.
- `products/operator-portal/web-ui/app/vite.config.ts` — Vite config with `@vitejs/plugin-react`, injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time, serves output to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — JS/TS source of truth for the palette and Ant Design `ThemeConfig` (`portalTheme`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — 739-line global stylesheet defining `:root` design tokens and all bespoke layout/component styles.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` at `/`.

## Architecture and conventions

### Dual token surface

Design tokens live in two synchronized places, both ported from the legacy portal's `styles.css`:

1. `src/theme/tokens.ts` exports a `palette` object and an Ant Design `ThemeConfig` (`portalTheme`) so components consume tokens through Ant Design's theme API.
2. `src/theme/global.css` declares the same values as CSS custom properties (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius`, …) so bespoke CSS rules and third-party rendered content can reference them without importing TS.

The comment in `tokens.ts` explicitly states this dual-surface pattern: "The CSS custom properties in global.css mirror these so bespoke styles and antd components stay on one vocabulary (SPEC-023 R-1 dark theme)."

### Ant Design theme configuration

`portalTheme` maps the palette into Ant Design's token space: `colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBgElevated`, `colorBorder`, `colorText`, `colorTextSecondary`, semantic colors, `borderRadius`, and fonts (`Inter` family plus `JetBrains Mono` / `Fira Code` for code). The theme uses `algorithm: antdTheme.darkAlgorithm` — there is no light-mode toggle.

### Global stylesheet structure

`global.css` is organized as:

- `:root` token declarations + `color-scheme: dark`.
- Reset (`box-sizing: border-box`) and focus-visible outline using `var(--accent)`.
- App shell layout: `.app-shell`, `.sidebar-footer`, `.mobile-menu-button`, collapsed rail overrides for `ant-layout-sider-collapsed`.
- View chrome: `.view-container`, `.view-container-flush`, `.view-toolbar`, `.report-form`.
- Chat workspace (`.chat-view`, `.session-panel`, `.chat-messages`, `.chat-composer`, `.turn-group`, `.composer-selection-bar`).
- Markdown rendering rules under `.md-content` (headings, lists, code blocks, tables, blockquotes).
- Tool evidence groups (`.evidence-turn`, `.evidence-card`, `.evidence-pre`).
- Sticky request banner (`.turn-request-banner`).
- HITL confirmation cards (`.confirm-card`, `.confirm-call`, `.confirm-execution`, recovery details).
- Bounded panes for documents drawer (`.digest-bounded`, `.prose-bounded` driven by `--bounded-pane-max-height`).

### Responsive strategy

Responsive behavior is CSS-media-query based rather than component-driven:

- Sidebar collapses automatically below Ant Design's `lg` breakpoint (992px); a pinned `.mobile-menu-button` opens an off-canvas drawer instead.
- `.session-panel` narrows from 260px to 200px at `max-width: 860px`.
- `prefers-reduced-motion: reduce` disables the `.turn-arrived` flash animation.

No mobile-first breakpoints or utility classes — the stylesheet is desktop-first with targeted media queries.

### Spec-driven style gates

Many style decisions are tied to spec requirements embedded as comments:

- SPEC-023 R-1: dark theme, platform version injection, immutable cache filenames.
- SPEC-019 R-1: hairline dividers replace group titles in collapsed sidebar.
- SPEC-023 R-3: chat workspace layout.
- SPEC-024: extensible selection strip under the composer.
- SPEC-034 R-1 / SPEC-035 R-4: arrival highlight animation for turn groups.
- SPEC-037 R-6: signed-execution receipts on decided cards.
- SPEC-039 R-8: session id display per panel entry.
- SPEC-041 R-3: bounded pane heights.

These are documented conventions, not lint-enforced rules.

### Build-time asset handling

Vite outputs hashed filenames to `../dist` so the runtime nginx serves content-hash assets as immutable-cacheable while `index.html` stays no-store (SPEC-023 R-1). The `make validate-version` target asserts the injected `__PLATFORM_VERSION__` constant against the root `VERSION` file.

## Conventions and constraints

Observed conventions (descriptive):

- All visual tokens flow through the `palette` object in `tokens.ts`; hard-coded color literals are avoided outside `global.css`'s `:root` declaration.
- Bespoke component styles use CSS custom properties (`var(--accent)`, `var(--surface)`, `var(--radius)`) rather than inline hex values.
- Ant Design components receive styling via the `portalTheme` `ThemeConfig` rather than per-component overrides.
- The app is dark-only; `color-scheme: dark` is set globally.
- Fonts are declared once in the Ant Design theme (`Inter` family, `JetBrains Mono` / `Fira Code` for monospace) and reused in `.md-content` and evidence code blocks.
- Layouts use Flexbox throughout; grid is used sparingly (e.g., `.recovery-facts` key/value grid).
- Animations respect `prefers-reduced-motion`.
- Style changes are cross-referenced to their originating spec number in comments (e.g., `/* SPEC-020 R-4 */`).

Enforced rules (source cited):

- Node engine requirement `>=22.22.2` is enforced by npm/yarn when installing dependencies (`package.json` `engines` field).
- The build script requires TypeScript type-checking before bundling (`"build": "tsc --noEmit && vite build"`), so invalid TS in styled components fails the build.
- Platform version injection is asserted by `make validate-version`, which follows the constant to its injection point in `vite.config.ts`.
- Built assets are written to `../dist` and served by the product's `nginx.conf`; changing the output directory would break the deployment contract.