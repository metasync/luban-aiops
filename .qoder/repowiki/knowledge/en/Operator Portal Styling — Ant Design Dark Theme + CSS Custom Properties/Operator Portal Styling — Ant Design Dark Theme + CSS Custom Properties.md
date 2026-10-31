---
kind: frontend_style
name: Operator Portal Styling — Ant Design Dark Theme + CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System overview

The only frontend in this repository is the **operator portal** under `products/operator-portal/web-ui/app`. It is a React 19 + Vite + TypeScript SPA built with **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library, styled exclusively through:

1. A single design-token file (`app/src/theme/tokens.ts`) that defines the palette and maps it to an Ant Design `ThemeConfig` using `antdTheme.darkAlgorithm`.
2. A single global stylesheet (`app/src/theme/global.css`) that declares CSS custom properties mirroring those tokens and styles bespoke layout/UX elements (chat transcript, session panel, HITL confirmation cards, evidence groups, sticky request banner, bounded panes).
3. Inline JSX styling via Ant Design's `theme.useToken()` / `theme.config` API where components need dynamic values; no per-component CSS files exist.

There is no Tailwind, Sass/SCSS, CSS-in-JS library beyond Ant Design's built-in theme system, or design-token pipeline tooling — the token file is hand-maintained and explicitly documented as "ported verbatim from the legacy portal's :root design tokens".

## Key files

- `products/operator-portal/web-ui/app/package.json` — declares `react ^19`, `antd ^6.6.2`, `@ant-design/icons ^6`, `@ant-design/x ^2.9`, `vite ^8`, `vitest ^4`, `typescript ~5.9`.
- `products/operator-portal/web-ui/app/vite.config.ts` — React plugin, Vitest config, dev proxy to `/api` → `http://localhost:8080`, build output to `../dist`, injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radii, fonts; exports `palette` (const) and `portalTheme: ThemeConfig`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — `:root` CSS variables mirroring `palette`, base resets, app shell, chat workspace, markdown rendering, evidence groups, HITL confirmation cards, sticky request banner, bounded panes, responsive breakpoints.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` directory.

## Architecture and conventions

### Token model

`tokens.ts` is the canonical definition. The comment on line 3–6 states the contract: "CSS custom properties in global.css mirror these so bespoke styles and antd components stay on one vocabulary (SPEC-023 R-1 dark theme)." The palette keys (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) are duplicated as `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius` in `global.css` `:root`. This dual declaration is intentional — Ant Design consumes the JS `ThemeConfig`, while bespoke CSS selectors consume the CSS variables.

### Ant Design theming

`portalTheme` applies `antdTheme.darkAlgorithm` and overrides `colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBgElevated`, `colorBorder`, `colorBorderSecondary`, `colorText`, `colorTextSecondary`, `colorSuccess`, `colorError`, `colorWarning`, `borderRadius`, `fontFamily`, `fontFamilyCode`. Components are expected to be wrapped by Ant Design's `ConfigProvider` (injected elsewhere in the app tree) rather than receiving inline style objects.

### Global stylesheet structure

`global.css` is organized into named sections separated by comments:

- Root tokens + reset (`:root`, `*`, `html/body/#root`).
- App shell and sidebar (`app-shell`, `sidebar-footer`, `mobile-menu-button`, collapsed rail rules).
- View container and full-bleed variant.
- Chat workspace (session panel, list, message column, composer, turn groups, arrival animation).
- Markdown content renderer (`.md-content` scope for headings, code, pre, blockquote, tables).
- Tool evidence groups (collapsed-by-default cards with bounded `max-height: 280px`).
- Sticky request banner (appears when user bubble scrolls out of view).
- HITL confirmation cards (pending/accent borders, call details, signed-execution receipts, recovery facts grid).
- Responsive breakpoint at `860px` (collapses session panel width).
- Shared view chrome (`.view-toolbar`, `.report-form`, `.incident-section`).
- Bounded panes for documents drawer (`.digest-bounded`, `.prose-bounded` driven by a CSS variable `--bounded-pane-max-height` set by the view).

### Responsive strategy

Responsive behavior is minimal and CSS-media-query based:

- `@media (max-width: 860px)` shrinks the session panel from 260px to 200px.
- The mobile menu button (`.mobile-menu-button`) is pinned top-left and toggles between inline sidebar collapse and an off-canvas drawer depending on whether antd's `lg` breakpoint (992px) has collapsed the Sider.
- No fluid typography, no CSS grid-based layouts — Flexbox is used throughout.

### Accessibility conventions

- `color-scheme: dark` on `:root`.
- Explicit `:focus-visible` rule with 2px accent outline and 2px offset.
- `prefers-reduced-motion` media query disables the `turn-arrive-flash` animation and replaces it with a static tinted background.

### Build-time version injection

`vite.config.ts` reads the root `VERSION` file and the lockfile to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants at build time. The comment references SPEC-023 R-1 and `make validate-version`, which asserts the constant propagates back to the injection point.

## Conventions and constraints

- **Dark theme only.** `color-scheme: dark` is declared in `global.css`; `portalTheme` uses `darkAlgorithm`. There is no light-mode toggle or alternate theme configuration.
- **Tokens are duplicated, not linked.** The CSS variables in `global.css` are a manual mirror of the JS `palette` object — changing a color requires updating both locations. This is documented as a deliberate choice to keep bespoke styles and Ant Design on one vocabulary.
- **No per-component CSS modules or SCSS.** All bespoke styles live in `global.css`; component-specific styling is done via Ant Design's theme API or inline props.
- **Bounded scroll containers use `max-height: 280px`.** Both fenced code blocks in markdown and tool evidence pre blocks cap height at 280px so they do not push the transcript out of view; the same bound is reused for document panes via `--bounded-pane-max-height`.
- **Spec-driven style changes.** Many CSS classes are annotated with their originating spec requirement (e.g. `SPEC-023 R-1`, `SPEC-034 R-1`, `SPEC-037 R-6`, `SPEC-039 R-8`, `SPEC-063 R-5a`, `SPEC-041 R-3`), tying visual decisions to tracked requirements.
- **Build output location.** Vite builds to `../dist` relative to `app/`, served by the product's `nginx.conf`.
- **Node engine constraint.** `package.json` pins `node >= 22.22.2`.
- **No Tailwind / PostCSS / Sass pipeline.** The dependency manifest contains no such tooling; all styling is plain CSS + Ant Design.