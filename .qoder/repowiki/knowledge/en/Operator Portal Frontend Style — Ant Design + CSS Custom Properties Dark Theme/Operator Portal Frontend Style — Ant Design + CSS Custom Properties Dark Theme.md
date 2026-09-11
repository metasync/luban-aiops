---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design + CSS Custom Properties Dark Theme
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

The Operator Portal web UI (`products/operator-portal/web-ui`) is a React 19 / TypeScript application built with **Vite** and styled primarily through the **Ant Design v6** component library. A single dark theme is enforced globally via `antd`'s `ConfigProvider` using `darkAlgorithm`, and bespoke styling lives in one global stylesheet that mirrors the same token set as CSS custom properties on `:root`. There is no Tailwind, SCSS, or CSS-in-JS; the stack is plain CSS plus Ant Design's built-in theming.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite, Vitest (jsdom).
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` for dev.
- `app/src/main.tsx` — wraps the app in Ant Design's `ConfigProvider` with the portal theme.
- `app/src/theme/tokens.ts` — defines the canonical palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `success`, `error`, `warning`, `codeBg`, `radius`) and maps it to an Ant Design `ThemeConfig` using `darkAlgorithm`.
- `app/src/theme/global.css` — declares the matching CSS custom properties on `:root` and all view-level styles (layout, chat transcript, approvals inbox, markdown rendering, tool evidence panels, HITL confirmation cards, sticky request banner, bounded panes, responsive drawer behavior).
- `nginx.conf` (at `products/operator-portal/`) serves the built `web-ui/dist` at `/`.

## Architecture and conventions

### Single-source design tokens
Tokens are defined once in `tokens.ts` and mirrored verbatim into CSS custom properties in `global.css` so both Ant Design components and hand-written CSS consume the same vocabulary. The comment in `tokens.ts` explicitly ties this to SPEC-023 R-1 dark-theme requirement.

### Global dark theme
`color-scheme: dark` is set on `:root`, and Ant Design's `darkAlgorithm` is applied via `ConfigProvider`. All semantic colors flow from the shared palette; there is no light-mode toggle.

### Component composition pattern
Components import Ant Design primitives directly (`Button`, `Table`, `Modal`, `Tabs`, `Collapse`, `Tag`, `Typography`, etc.) and compose them with minimal local CSS classes scoped to feature areas (e.g., `.session-panel`, `.chat-messages`, `.approvals-entry`, `.confirm-card`). Layout chrome (sidebar, views, toolbar) uses Ant Design's `Layout`, `Menu`, `Drawer`, and `Sider` with small overrides in `global.css`.

### View layout
A full-height app shell uses a fixed-width left sidebar (collapsible to a 64px icon rail) plus a single active function view. On narrow screens (`max-width: 860px`) the session panel shrinks; the spec also documents an off-canvas drawer approach for mobile navigation parity.

### Chat transcript styling
The chat workspace has dedicated CSS modules for session list items, message columns, composer selection bar, turn groups, arrival animations (with `prefers-reduced-motion` support), tool evidence groups, signed-execution receipts, and a sticky "turn request" banner that re-states the user prompt when its bubble scrolls out of view.

### Markdown and code rendering
Markdown content rendered inside the portal uses a `.md-content` class with consistent heading sizes, accent-colored links, bordered tables, and fenced code blocks capped at `max-height: 280px` with their own scrollbars — the same bound reused for tool evidence pre blocks.

### Responsive strategy
Responsive behavior is expressed via CSS `@media` queries in `global.css` (e.g., `.session-panel` width change at 860px). No utility-first framework is used; breakpoints are ad-hoc per feature.

### Build-time asset caching
The Vite build emits content-hashed filenames to `../dist` so assets are immutable-cacheable while `index.html` stays no-store, as documented in the config comments tied to SPEC-023 R-1.

## Conventions and constraints

- **All visual tokens must come from `src/theme/tokens.ts`** — new colors/radii/fonts should be added there first and then mirrored into `global.css` `:root` variables so Ant Design and bespoke CSS stay in sync.
- **Dark mode is the only supported theme** — `color-scheme: dark` and `darkAlgorithm` are hard-coded at the root level.
- **Bounded scrolling for large content** — code blocks, tool evidence, and document panes use `max-height: 280px` with internal overflow to keep transcripts readable; bounded panes in the documents drawer use a CSS variable `--bounded-pane-max-height` set by the view.
- **Accessibility baseline** — focus outlines use the accent color via `:focus-visible`, and animations respect `prefers-reduced-motion: reduce`.
- **Component imports are direct from `antd`** — no wrapper component library exists; features import exactly what they need (e.g., `Button`, `Table`, `Modal`, `Tabs`, `Collapse`, `Tag`, `Typography`, `Alert`, `Pagination`, `Spin`, `Tooltip`, `Statistic`, `Row`, `Col`).
- **Build-time version injection** — platform, React, and Ant Design versions are injected as constants (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) so the Settings page can display the exact shipped tech stack.