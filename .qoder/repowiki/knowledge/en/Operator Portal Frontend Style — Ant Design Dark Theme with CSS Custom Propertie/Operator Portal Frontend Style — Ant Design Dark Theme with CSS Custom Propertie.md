---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
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

The operator portal web UI (`products/operator-portal/web-ui/app`) is a React 18 + TypeScript application built with Vite. Styling is centered on **Ant Design v6** (`antd` and `@ant-design/x`) configured via Ant Design's `ThemeConfig` to run in the built-in dark algorithm. A single source of truth for colors, spacing, and typography lives in `src/theme/tokens.ts`, which exports both an Ant Design theme object and a plain `palette` constant. The same palette values are mirrored as CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) in `src/theme/global.css`, so bespoke component styles can consume design tokens through CSS variables while Ant Design components consume them through the theme API.

There is no Tailwind, Sass/SCSS, or CSS-in-JS library beyond what Ant Design ships; styling is a mix of global CSS (BEM-style class names) and Ant Design component props.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6`, `@ant-design/x ^2.9`, React 18, Vite 6, Vitest.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the `palette` object and `portalTheme: ThemeConfig` using `antd.darkAlgorithm`; sets primary color, background, text, border, success/error/warning, border radius, and fonts (`Inter` / `JetBrains Mono`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — root-level `:root` CSS custom properties mirroring `tokens.ts` (explicitly documented as ported from the legacy portal's `styles.css`); global resets, layout shell, chat workspace, markdown rendering, evidence groups, HITL confirmation cards, sticky request banner, view chrome, and responsive breakpoints.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__` at build time; outputs to `../dist` for nginx serving; proxies `/api` to `localhost:8080` in dev.
- `products/operator-portal/web-ui/nginx.conf` — serves the built static assets.

## Architecture and conventions

1. **Single token source**: `tokens.ts` is the canonical definition of colors, radii, and fonts. `global.css` mirrors it as CSS variables so non-Ant Design code stays on the same vocabulary. Comments explicitly tie this to SPEC-023 R-1 (dark theme).
2. **Dark-only theme**: `color-scheme: dark` is set on `:root`; the Ant Design theme uses `darkAlgorithm`. No light-mode toggle exists in the current codebase.
3. **Component styling model**: Layout chrome (sidebar, app shell, session panel, chat transcript, approvals inbox, markdown content, evidence cards, HITL confirmation cards) is implemented as global CSS classes under `global.css`. Component logic lives in `.tsx` files under `src/chat`, `src/views/*`, `src/auth`, `src/api`, etc., and composes Ant Design primitives (`Layout`, `Menu`, `Card`, `Typography`, etc.) with the shared theme.
4. **Responsive strategy**: Uses CSS `@media` queries (e.g. `max-width: 860px` for collapsing the session panel) and relies on Ant Design's built-in responsive behavior for the sidebar (`lg` breakpoint where the Sider auto-collapses). A fixed-position mobile menu button opens an off-canvas drawer below that breakpoint.
5. **Accessibility baseline**: `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion` disables the turn-arrival flash animation.
6. **Build-time versioning**: Platform version is read from the repo root `VERSION` file and injected as `__PLATFORM_VERSION__` into the bundle via Vite `define`, keeping the frontend version in sync with the product release manifest.
7. **Markdown/evidence styling**: A shared `.md-content` stylesheet renders headings, lists, code blocks, blockquotes, links, tables, and horizontal rules consistently across views that display rendered Markdown (transcripts, documents, evidence panels). Code blocks and preformatted output are capped at 280px height with internal scrolling to keep transcripts readable.

## Conventions and constraints

- All visual tokens must be defined in `src/theme/tokens.ts` and mirrored in `:root` CSS variables in `global.css`; ad-hoc hex literals in component styles should be avoided so the palette stays centralized.
- Ant Design components are styled exclusively through the `portalTheme` `ThemeConfig` passed to the Ant Design provider; direct overrides of Ant Design internals should go through CSS variable overrides rather than inline styles.
- Bespoke component classes follow BEM-style naming (e.g. `.session-item`, `.session-item-title`, `.session-item-meta`) scoped under feature-specific sections of `global.css`.
- The portal is intentionally dark-only; there is no theme switcher, and all CSS variables assume a dark palette.
- Responsive behavior is kept minimal: one breakpoint (`860px`) toggles between inline sidebar and drawer-based navigation; larger screens use a fixed-width 260px session panel.
- Animations respect `prefers-reduced-motion`; motion is only used for transient arrival highlights (turn groups, approval cards) and is disabled when the user prefers reduced motion.
- Build artifacts are hashed filenames served by nginx; `index.html` is not cached while asset files are immutable-cacheable, as enforced by the Vite build config and referenced in comments tied to SPEC-023 R-1.