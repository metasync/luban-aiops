---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
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

The operator portal (`products/operator-portal/web-ui`) is a React + TypeScript SPA built with Vite. Styling is centered on **Ant Design v6** using the `darkAlgorithm` theme, and a single source of truth for design tokens that is mirrored into both the Ant Design `ThemeConfig` and browser CSS custom properties consumed by bespoke component styles.

Key libraries: `antd`, `@ant-design/icons`, `@ant-design/x`, `react`/`react-dom`. No CSS-in-JS or utility-first framework (e.g., Tailwind) is used; styling is plain CSS in one global stylesheet plus per-component JSX.

## Key files and packages

- `app/package.json` — declares antd 6.x, React 19, Vite build, Vitest testing.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` served by nginx; proxies `/api` to localhost:8080 in dev.
- `app/src/theme/tokens.ts` — defines the `palette` object and `portalTheme: ThemeConfig` (dark algorithm, primary/accent colors, border radius, fonts).
- `app/src/theme/global.css` — declares `:root` CSS custom properties mirroring `tokens.ts` (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius`), sets `color-scheme: dark`, and contains all bespoke layout/component styles (chat view, session panel, approvals inbox, evidence cards, HITL confirmation cards, sticky request banner, bounded panes, markdown rendering).
- `nginx.conf` (at `products/operator-portal/`) serves the built `dist/` directory.

## Architecture and conventions

1. **Single token source.** The palette lives in `src/theme/tokens.ts` and is referenced by two consumers:
   - The Ant Design `ThemeConfig` (`portalTheme`) so built-in components inherit the same colors, radii, and fonts.
   - A parallel set of CSS custom properties in `global.css` (`:root { --accent: #38bdf8; ... }`) so hand-written component styles stay on the same vocabulary without importing TS.
   This dual mirror is explicitly documented as part of SPEC-023 R-1 dark-theme requirement.

2. **Dark-only theme.** `color-scheme: dark` is declared globally; no light-mode toggle exists. All bespoke classes reference `var(--*)` tokens rather than hard-coded hex values.

3. **Component styling via class names over CSS modules.** Components use plain CSS class names (e.g., `.session-panel`, `.chat-view`, `.confirm-card`, `.approvals-entry`, `.evidence-card`, `.turn-group.turn-arrived`) scoped through BEM-like prefixes. There are no CSS Modules, styled-components, or Tailwind classes observed in the codebase.

4. **Responsive strategy.** Breakpoints are handled inline with `@media (max-width: 860px)` rules (e.g., shrinking `.session-panel` from 260px to 200px). A mobile menu button (`.mobile-menu-button`) toggles an off-canvas drawer below antd's `lg` breakpoint (992px) where the `Sider` auto-collapses. No responsive grid framework is used.

5. **Accessibility baseline.** Global `:focus-visible` rule gives a 2px accent-colored outline with offset. A `prefers-reduced-motion` media query disables the `turn-arrive-flash` animation while keeping a muted background tint.

6. **Bounded panes pattern.** Long content areas (digest tabs, prose collapse) use a shared `--bounded-pane-max-height` CSS variable applied to wrapper elements, with `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body` constraining scroll height. This keeps structural chrome pinned while content scrolls.

7. **Build-time versioning.** `vite.config.ts` reads the root `VERSION` file and the lockfile to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants, enabling the Settings view to display the exact shipped tech stack.

## Conventions and constraints

- **Design tokens must be defined in `src/theme/tokens.ts` and mirrored to `:root` CSS variables in `global.css`** — the comment in `tokens.ts` states this is required by SPEC-023 R-1 dark theme so both Ant Design and bespoke styles share one vocabulary.
- **All bespoke styles must consume `var(--*)` tokens**, never hard-coded color literals, ensuring consistency with the Ant Design theme.
- **Dark mode is enforced globally** via `color-scheme: dark`; no light-mode switch is implemented.
- **Custom focus indicators must remain visible** — the global `:focus-visible` rule enforces a 2px accent outline for keyboard navigation.
- **Long-form content uses bounded panes** — transcript messages, evidence blocks, and document panes cap height at 280px (or a CSS-variable-driven `--bounded-pane-max-height`) with internal scrolling instead of expanding the page.
- **Animations respect reduced motion** — the turn-arrival flash animation is disabled under `prefers-reduced-motion: reduce`, falling back to a static tint.
- **Build output is immutable-cacheable** — Vite emits content-hashed filenames to `../dist`, which nginx serves; `index.html` stays no-store per SPEC-023 R-1.