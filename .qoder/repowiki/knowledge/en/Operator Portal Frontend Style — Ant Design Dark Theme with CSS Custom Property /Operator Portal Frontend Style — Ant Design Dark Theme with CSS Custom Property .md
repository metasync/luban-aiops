---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Property Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/nginx.conf
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui/app`) is a React 19 + TypeScript SPA built with Vite. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via an Ant Design `ThemeConfig` that enables the built-in dark algorithm. A single source of truth for colors, spacing and typography lives in `src/theme/tokens.ts` and is mirrored as CSS custom properties in `src/theme/global.css` so both Ant Design components and bespoke component styles consume one vocabulary. The app ships as a static bundle served by nginx from `dist/`.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, plus Vite/Vitest tooling.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the `palette` object (bg, surface, border, text, accent, success, error, warning, codeBg, radius) and the `portalTheme: ThemeConfig` that maps those tokens to Ant Design's token keys (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorText`, `borderRadius`, `fontFamily`, `fontFamilyCode`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — declares `:root` CSS custom properties mirroring `tokens.ts`, sets `color-scheme: dark`, global resets, focus-visible outline, the app shell layout, chat transcript/evidence/HITL card styles, markdown rendering rules, and responsive breakpoints.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `http://localhost:8080` in dev.
- `products/operator-portal/web-ui/nginx.conf` — serves the built `dist/` directory.

## Architecture and conventions

1. **Single-token design system.** All visual tokens are defined once in `src/theme/tokens.ts`. The comment explicitly states that CSS custom properties in `global.css` mirror these values so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1). Components should never hard-code color hexes; they use Ant Design theme tokens or the CSS variables exposed by `global.css`.

2. **Dark-only theme.** The root stylesheet sets `color-scheme: dark` and the Ant Design theme uses `darkAlgorithm`. There is no light-mode toggle; the entire portal is designed for a dark background (`#0f172a`) with surface layers (`#1e293b`, `#334155`) and an accent blue (`#38bdf8`).

3. **Typography tokens.** Font families are centralized: UI uses `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`; code uses `"JetBrains Mono", "Fira Code", monospace`. Both are set via Ant Design tokens and repeated in the CSS for `.md-content code` blocks.

4. **Layout via CSS classes over utility frameworks.** No Tailwind or CSS-in-JS library is used beyond Ant Design's own styled primitives. Layout patterns (app-shell sidebar + view, session panel, chat column, view-container, view-toolbar) are expressed as BEM-style class names in `global.css`.

5. **Responsive strategy.** Breakpoints are inline `@media` queries in `global.css` (e.g., `max-width: 860px` narrows the session panel). Navigation switches between an inline `ant-layout-sider` and an off-canvas drawer based on whether the sider is collapsed, coordinated with a fixed-position `.mobile-menu-button`.

6. **Component-scoped styling.** Each feature area has its own section in `global.css` (chat workspace, approvals inbox, markdown content, tool evidence groups, HITL confirmation cards, sticky request banner, bounded panes for documents). Styles reference CSS variables rather than raw colors, keeping them theme-aware.

7. **Build-time version injection.** `vite.config.ts` reads the repo root `VERSION` file and the lockfile to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`, which are consumed by the Settings view to display the tech stack table.

## Conventions and constraints

- **Use Ant Design tokens, not raw CSS colors.** New components must consume `theme.token.*` values (primary, bg, text, border, etc.) or the CSS variables defined in `:root`; ad-hoc hex literals are discouraged per the token-mirror convention.
- **Dark mode is the only supported mode.** The `color-scheme: dark` declaration and `darkAlgorithm` enforce this at the root level.
- **CSS variables are the shared vocabulary.** Bespoke styles reference `var(--bg)`, `var(--surface)`, `var(--accent)`, `var(--border)`, `var(--text)`, `var(--text-muted)`, `var(--success)`, `var(--error)`, `var(--warning)`, `var(--code-bg)`, `var(--radius)` instead of repeating palette values.
- **Bounded scrolling for long content.** Transcript messages, code blocks, and evidence panels use `max-height` (e.g., 280px) with their own scrollbars so expanding content does not push the rest of the page out of view.
- **Accessibility baseline.** A global `:focus-visible` rule draws a 2px accent-colored outline with offset; reduced-motion media queries disable animations like the turn-arrival flash when `prefers-reduced-motion: reduce` is set.
- **Spec-driven style changes.** Many style additions are tied to spec requirements referenced in comments (e.g., SPEC-019 R-1 for grouped navigation, SPEC-020 R-4 for HITL cards, SPEC-023 R-1/R-3/R-5 for theme/layout, SPEC-034/035 for arrival highlights, SPEC-037 R-6 for signed-execution receipts, SPEC-039 R-8 for session IDs, SPEC-041 R-3 for bounded document panes). New UI work should follow the same pattern of documenting the spec reference in the CSS.