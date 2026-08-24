---
kind: frontend_style
name: 'Operator Portal: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 18 + TypeScript SPA built with Vite. Styling is centered on **Ant Design v6** as the component library, configured with a custom dark theme via `antd`'s `ThemeConfig`. A single global stylesheet (`src/theme/global.css`) defines CSS custom properties that mirror the JS palette in `src/theme/tokens.ts`, so both bespoke DOM elements and Ant Design components consume one shared design vocabulary. There is no Tailwind, SCSS, or CSS-in-JS beyond what Ant Design ships — styling is plain CSS modules (global) plus inline `style` objects for small per-component overrides.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 18, Vite 6, Vitest.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — central `palette` object and `portalTheme: ThemeConfig` that maps tokens to Ant Design's dark algorithm (`colorPrimary`, `colorBgBase`, `colorBorder`, `borderRadius`, fonts).
- `products/operator-portal/web-ui/app/src/theme/global.css` — `:root` CSS custom properties mirroring `tokens.ts` (`--bg`, `--surface`, `--accent`, `--text`, `--border`, `--radius`, …), plus all bespoke layout and view styles (app shell, sidebar, chat transcript, evidence cards, HITL confirmations, markdown rendering, responsive rules).
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` in dev.
- `products/operator-portal/web-ui/app/src/App.tsx` — root layout using `antd.Layout.Sider` (dark, collapsible to 64px rail) and `Drawer` for narrow viewports; applies `view-container` / `view-container-flush` classes from `global.css`.
- `products/operator-portal/web-ui/app/src/views/**` — feature views (`audit`, `control`, `incidents`) composed from Ant Design primitives and the shared CSS classes.
- `products/operator-portal/web-ui/nginx.conf` — serves the built `dist/` assets at `/`.

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` exports a `palette` constant and an `antd` `ThemeConfig` built on `darkAlgorithm`. The same hex values are duplicated into `global.css` as `:root` CSS variables (`--bg`, `--surface`, `--accent`, etc.) so non-Ant components can reference them via `var(--...)`. Comments in both files explicitly state they mirror each other (SPEC-023 R-1 dark theme).

2. **Dark-only UI**: `color-scheme: dark` is set globally; the app has no light-mode toggle. All custom CSS uses the `--*` variables, which resolve to dark palette values.

3. **Layout shell**: A fixed-width `Layout.Sider` (230px, breakpoint `lg` = 992px) provides navigation; below the breakpoint it auto-collapses to a 64px icon rail and a left-placed `Drawer` shows the full menu. A pinned `.mobile-menu-button` toggles between drawer and collapse. This pattern is enforced by `App.tsx` and styled in `global.css`.

4. **View chrome**: Every page wraps its content in `.view-container` (padding 20px 24px) or `.view-container-flush` (full-bleed, used by the chat view). Toolbar rows use `.view-toolbar`; report forms use `.report-form`.

5. **Chat transcript layout**: The chat view uses a two-column Flexbox layout (`.chat-view`): a 260px `.session-panel` (collapses to 200px under 860px) and a flex-1 `.chat-column` holding messages, composer, and selection bar. Message turns group user bubbles with sticky `.turn-request-banner` when scrolled out of view.

6. **Evidence & HITL UI**: Tool evidence groups are collapsed by default with `.evidence-turn` / `.evidence-card` / `.evidence-pre` (bounded height 280px). HITL confirmation cards use `.confirm-card` with variant classes like `.pending` (warning border). These follow SPEC-011 R-4 and SPEC-020 R-4 parity notes in the stylesheet.

7. **Markdown rendering**: A `.md-content` class family styles headings, lists, code blocks, blockquotes, links, tables, and horizontal rules — ported from the legacy portal's `styles.css`.

8. **Responsive strategy**: No media-query framework. Breakpoints are hard-coded in `global.css` (e.g. `@media (max-width: 860px)` for session panel width) and in `App.tsx` via `window.matchMedia("(max-width: 991px)")` to switch between inline Sider and Drawer.

9. **No per-component CSS modules**: Components import only `antd` components and rely on the global stylesheet for layout classes. Inline `style` props are used sparingly for dynamic values (e.g. margins, gaps).

## Conventions and constraints

- **Design tokens must stay in sync**: `tokens.ts` and `global.css` :root variables are declared together and comments explicitly call out that they mirror each other (SPEC-023 R-1). Changing a color requires updating both locations.
- **Use Ant Design dark theme exclusively**: The `portalTheme` uses `darkAlgorithm`; all `Menu`, `Layout.Sider`, and other themed components are rendered with `theme="dark"`.
- **Bespoke UI uses CSS custom properties, not raw hex**: New custom components should reference `var(--bg)`, `var(--surface)`, `var(--accent)`, `var(--border)`, `var(--text)`, `var(--text-muted)`, `var(--success)`, `var(--error)`, `var(--warning)`, `var(--code-bg)`, `var(--radius)` rather than hardcoding colors.
- **Focus accessibility**: `:focus-visible` is globally styled with a 2px accent outline and 2px offset; custom controls must preserve this behavior.
- **Font stack**: Body uses `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`; code uses `"JetBrains Mono", "Fira Code", monospace` — both declared in `tokens.ts` and echoed in `global.css`.
- **Breakpoint discipline**: Layout breakpoints are centralized in `App.tsx` (991px for Sider lg) and `global.css` (860px for session panel); new responsive rules should align with these thresholds.
- **Build-time version injection**: Platform version is injected via Vite `define` as `__PLATFORM_VERSION__` and displayed in the sidebar tag; this is enforced by `make validate-version` following the constant to this injection point.