---
kind: frontend_style
name: 'Operator Portal Frontend Style: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React + TypeScript SPA built with **Vite** and styled primarily via the **Ant Design (antd v6)** component library. The visual identity is a **dark-only theme** driven by `antd`'s `ThemeConfig` plus a parallel set of CSS custom properties that bespoke styles consume. There is no Tailwind, SCSS, Sass, or CSS-in-JS library in use — styling is plain CSS modules / global CSS layered over antd's default dark algorithm.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite, Vitest.
- `app/src/theme/tokens.ts` — single source of truth for colors, radii, and fonts; exports a `palette` object and an `antd` `ThemeConfig` (`portalTheme`) using `antdTheme.darkAlgorithm`.
- `app/src/theme/global.css` — defines `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) that mirror `tokens.ts` verbatim; contains all bespoke layout, chat transcript, evidence cards, HITL confirmation cards, markdown rendering, and responsive rules.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` in dev.
- `app/src/main.tsx` — wraps the app in Antd's `ConfigProvider` with `portalTheme` so every antd component inherits the dark palette.
- `app/src/App.tsx` — composes the sidebar/layout shell using antd `Layout`, `Menu`, `Drawer`, `Tooltip`, `Typography`, `Tag`, `Modal`, `Space`, `Button`, `Divider`, `Badge`, `Avatar`, `Dropdown`, `Select`, `Input`, `Form`, `Table`, `Tabs`, `Collapse`, `Alert`, `Spin`, `Statistic`, `Col`, `Row`.

## Architecture and conventions

1. **Single design-token source**: `tokens.ts` owns the color palette, border radius, and font families. The comment explicitly states the CSS custom properties in `global.css` are "ported verbatim from the legacy portal's :root design tokens" so bespoke styles and antd components share one vocabulary (SPEC-023 R-1 dark theme).
2. **Dark-only runtime**: `color-scheme: dark` is set on `:root`; no light-mode toggle exists. All custom properties resolve to dark values.
3. **Component vs. bespoke split**: Layout chrome (sidebar, header, drawer) uses antd primitives; domain-specific UI (chat transcript rows, session list items, approval cards, evidence panels, markdown content, sticky request banners, bounded panes) is implemented as plain CSS classes in `global.css` and composed inside React components via `className`.
4. **Responsive strategy**: Handled entirely in CSS media queries in `global.css`. The chat view collapses its session panel below 860px; the mobile menu button appears when the antd `Sider` auto-collapses below `lg` (992px), opening an off-canvas drawer instead of inline navigation.
5. **Accessibility baseline**: A global `:focus-visible` rule draws a 2px accent outline with offset; `prefers-reduced-motion` disables the turn-arrival flash animation while keeping a static tint.
6. **Build-time versioning**: `vite.config.ts` reads the root `VERSION` file and the lockfile to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants consumed by the Settings view's tech-stack table.
7. **No CSS framework beyond antd**: No Tailwind config, no Sass/SCSS, no styled-components/emotion, no MUI — confirmed by grep across the web-ui source.

## Conventions and constraints

- **All antd theming goes through `ConfigProvider` with `portalTheme`** in `main.tsx`; individual components do not override antd tokens locally.
- **Bespoke styles must reference CSS custom properties** (`var(--bg)`, `var(--surface)`, `var(--accent)`, `var(--border)`, `var(--radius)`) rather than hard-coded hex values, keeping them in sync with the antd theme.
- **Design tokens live only in `src/theme/tokens.ts`**; `global.css` mirrors them but is treated as the CSS surface layer, not the source of truth for JS-side theme decisions.
- **Spec-driven style changes**: Comments in `global.css` tie visual behavior to spec requirements (e.g., SPEC-023 R-1 dark theme, SPEC-019 R-1 collapsed sidebar grouping, SPEC-011 R-4 parity for tool evidence, SPEC-020 R-4 HITL cards, SPEC-034/SPEC-035 arrival highlights, SPEC-037 R-6 signed-execution receipts, SPEC-039 R-8 session ID display, SPEC-041 R-3 bounded panes). New UI features should be referenced similarly.
- **Chat transcript layout is fixed-width and scroll-bounded**: Session panel is 260px wide (200px under 860px); code blocks and evidence previews are capped at `max-height: 280px` with their own scrollbars so expanding content does not push messages out of view.
- **Markdown rendering uses a dedicated `.md-content` scope** with accent-colored headings, muted blockquotes, bordered tables, and monospace code blocks — ensuring rendered skill/incident content matches the portal palette.
- **Production output**: Vite builds to `web-ui/dist/` with content-hashed filenames for immutable caching; `nginx.conf` serves `dist/` at `/`.