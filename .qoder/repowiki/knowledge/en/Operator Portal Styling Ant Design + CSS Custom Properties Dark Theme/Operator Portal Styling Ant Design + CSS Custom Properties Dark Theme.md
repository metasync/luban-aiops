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
    - products/operator-portal/nginx.conf
---

## What system/approach is used

The operator portal's UI (`products/operator-portal/web-ui`) is a React 19 / Vite application styled with **Ant Design v6** (`antd`, `@ant-design/x`, `@ant-design/icons`) using the built-in dark algorithm. There is no Tailwind, SCSS, or CSS-in-JS library beyond what Ant Design ships; bespoke styling lives in a single global stylesheet and is driven by CSS custom properties (design tokens) that mirror the Ant Design theme config.

## Key files and packages

- `app/package.json` — declares `react`, `antd ^6.6.2`, `@ant-design/x ^2.9.0`, `@ant-design/icons ^6.0.0`; build tooling is Vite + Vitest + TypeScript.
- `app/src/theme/tokens.ts` — defines the shared palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and an Ant Design `ThemeConfig` (`portalTheme`) that maps those values to antd tokens (`colorPrimary`, `colorBgBase`, `colorBorder`, `fontFamily`, etc.) and enables `darkAlgorithm`.
- `app/src/theme/global.css` — declares the same token values as `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, …), sets `color-scheme: dark`, and contains all bespoke component styles (chat transcript, session panel, approvals inbox, evidence cards, HITL confirmation cards, sticky request banner, markdown rendering, bounded panes). The file header explicitly states it mirrors `tokens.ts` so antd components and bespoke styles share one vocabulary (SPEC-023 R-1).
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving; proxies `/api` to `localhost:8080` in dev.
- `app/index.html` — entry HTML consumed by Vite.
- `nginx.conf` (in `products/operator-portal/`) — serves the built `web-ui/dist` at `/`.

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` is the canonical design-token definition. It is duplicated into `global.css` as CSS custom properties so both Ant Design components (via `ThemeConfig`) and hand-written CSS selectors consume the same palette. The comment in `tokens.ts` calls this out as a port from the legacy portal's `styles.css`.
2. **Dark-only theme**: The app forces a dark experience via `antd`'s `darkAlgorithm` and `:root { color-scheme: dark }`. No light-mode toggle exists in the codebase.
3. **Component-scoped CSS classes over utility-first**: Bespoke UI uses BEM-style class names (`.session-panel`, `.chat-messages`, `.confirm-card`, `.evidence-card`, `.turn-request-banner`, `.digest-bounded`, `.prose-bounded`) rather than inline styles or a utility framework. These live exclusively in `global.css`.
4. **Responsive strategy**: A single breakpoint at `max-width: 860px` narrows the session panel; below Ant Design's `lg` breakpoint (992px) the sidebar collapses into an off-canvas drawer (handled by Ant Design layout behavior plus a pinned `.mobile-menu-button`).
5. **Accessibility hooks**: `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion` disables the turn-arrival flash animation while keeping a static tint.
6. **Bounded scrollable panes**: Long content areas (markdown `<pre>`, evidence `<pre>`, digest tabs, prose collapse) are constrained via `max-height: var(--bounded-pane-max-height)` on wrapper classes so structural chrome stays pinned while content scrolls.
7. **Spec-driven style gates**: Many comments tie rules to SPEC numbers (SPEC-011 R-4, SPEC-019 R-1, SPEC-020 R-4, SPEC-023 R-1/R-3/R-4/R-5, SPEC-034 R-1/R-4, SPEC-035 R-4, SPEC-037 R-6, SPEC-039 R-8, SPEC-041 R-3), indicating the visual contract is tracked alongside functional specs.

## Conventions and constraints

- **Use Ant Design tokens for everything that touches antd components**; do not override antd internals with raw CSS unless necessary. The `portalTheme` mapping in `tokens.ts` is the place to adjust brand colors, radii, and fonts.
- **All non-antd visual tokens must be declared as `:root` CSS custom properties** in `global.css` and referenced via `var(--name)` in bespoke styles, keeping them synchronized with `tokens.ts`.
- **No per-component CSS modules or SCSS**: the entire bespoke stylesheet is centralized in `src/theme/global.css`; adding new UI should append to this file rather than creating new CSS files.
- **Dark mode only**: new components must assume `color-scheme: dark` and use the existing token variables; no light-theme branches are present.
- **Build-time version injection**: platform, React, and Ant Design versions are baked into the bundle via `vite.config.ts` `define`, so runtime feature detection of the stack is unnecessary.
- **Responsive behavior is minimal and breakpoint-based**, relying on Ant Design's responsive layout primitives plus the single 860px media query in `global.css`.
- **Markdown and code rendering follow a fixed visual contract**: headings are accent-colored, code blocks use `--code-bg` with `JetBrains Mono`/`Fira Code`, and long fenced blocks are capped at 280px height with their own scrollbar to keep transcripts readable.