---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
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

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React + TypeScript SPA built with **Vite** and styled primarily through the **Ant Design (antd v6)** component library. Visual consistency is achieved by configuring antd's `ConfigProvider` with a custom `ThemeConfig` that uses antd's `darkAlgorithm`, mapping a single source-of-truth palette to antd tokens (primary, background, border, text, success/error/warning, radius, fonts). The same palette is mirrored as CSS custom properties in `src/theme/global.css` so bespoke styles and antd components share one vocabulary. There is no Tailwind, SCSS, or CSS-in-JS beyond these two files; styling is a mix of antd components plus scoped global CSS classes.

## Key files and packages

- `app/package.json` — declares `react 19`, `antd ^6.6.2`, `@ant-design/icons ^6`, `@ant-design/x ^2.9`, Vite, Vitest, TypeScript.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` in dev; configures Vitest with jsdom.
- `app/src/main.tsx` — mounts the app inside an antd `ConfigProvider` using the theme from `theme/tokens.ts`.
- `app/src/theme/tokens.ts` — defines the canonical `palette` object and `portalTheme: ThemeConfig` consumed by antd.
- `app/src/theme/global.css` — defines `:root` CSS custom properties mirroring `tokens.ts`, sets `color-scheme: dark`, base typography, layout shell, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, sticky request banner, responsive breakpoints, and bounded panes for documents.
- View/component files under `app/src/views/...` and `app/src/chat/...` — consume antd components directly; custom UI is layered via CSS classes defined in `global.css`.

## Architecture and conventions

- **Single design token source**: `tokens.ts` holds the palette; `global.css` mirrors it as CSS variables (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius`). Comments explicitly state this dual-mirror is required by SPEC-023 R-1 so both antd and bespoke styles stay on one vocabulary.
- **Dark-only theme**: `color-scheme: dark` is set globally; antd uses `darkAlgorithm`; all colors are chosen for a dark slate palette (background `#0f172a`, surface `#1e293b`, accent `#38bdf8`). No light-mode toggle exists.
- **Typography**: Font families are declared once in `portalTheme.token.fontFamily` / `fontFamilyCode` and reused in CSS (`Inter` stack for body, `JetBrains Mono` / `Fira Code` for code).
- **Layout shell**: A full-height `.app-shell` with an antd `Layout.Sider` sidebar and a `.view-container` main area. On narrow screens (`max-width: 860px`) the session panel shrinks; a `.mobile-menu-button` provides off-canvas drawer navigation below antd's `lg` breakpoint (992px), per SPEC-019.
- **Chat workspace**: Dedicated `.chat-view` split into a fixed-width `.session-panel` (260px, shrinking to 200px) and a flex column transcript. Messages use `.turn-group` with optional arrival highlight animation (`.turn-arrived` fades a tint over 4s, respects `prefers-reduced-motion`).
- **Markdown rendering**: A shared `.md-content` class styles headings, lists, links, tables, and fenced code blocks with bounded height (`max-height: 280px`) to keep transcripts scrollable.
- **Evidence & HITL cards**: Collapsed-by-default `.evidence-turn` groups and `.confirm-card` blocks follow consistent borders, radii, and spacing; signed-execution receipts are rendered inline.
- **Sticky request banner**: `.turn-request-banner` pins context above scrolling transcript when the originating user bubble scrolls out of view.
- **Bounded panes**: Documents views use a CSS variable `--bounded-pane-max-height` applied to wrapper elements; `.digest-bounded` and `.prose-bounded` constrain inner antd tabs/collapse bodies so structural chrome stays pinned while content scrolls.
- **Responsive strategy**: Pure CSS media queries; no responsive utility framework. Breakpoints are minimal (860px for session panel, 992px referenced for antd Sider behavior).

## Conventions and constraints

- **Use antd components for all interactive primitives** — buttons, tables, modals, alerts, tags, selects, etc., are imported from `antd` and themed via the root `ConfigProvider`; custom overrides go through CSS classes in `global.css`, not inline styles.
- **Never hard-code colors in components** — colors must come from the shared palette via CSS custom properties (e.g. `var(--accent)`, `var(--surface)`) or antd tokens; new colors must be added to `tokens.ts` first.
- **Mirror every token in CSS variables** — any change to `tokens.ts` palette must be reflected in `global.css` `:root` variables so bespoke styles remain consistent (enforced by comments referencing SPEC-023 R-1).
- **Keep code blocks bounded** — fenced code and evidence pre blocks use `max-height: 280px` with internal overflow so they never push transcript content out of view.
- **Respect reduced motion** — animations like turn-arrival flash are wrapped in `@media (prefers-reduced-motion: reduce)` to disable motion for users who prefer it.
- **Build-time version injection** — platform and dependency versions are injected via Vite `define` constants (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) and validated against the root `VERSION` file by `make validate-version`.
- **No CSS modules / no per-component stylesheets** — styling lives exclusively in `global.css`; component files import antd components and apply class names that match selectors in that file.