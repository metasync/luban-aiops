---
kind: frontend_style
name: Operator Portal — Ant Design Dark Theme with CSS Custom Property Tokens
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

The only frontend in the repository is the **Operator Portal** (`products/operator-portal/web-ui/app`), a React 19 SPA built with Vite and styled primarily through **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`). There is no Tailwind, Sass, or CSS-in-JS library beyond what Ant Design ships. Styling follows a dual-token approach:

1. A TypeScript token file (`src/theme/tokens.ts`) defines a `palette` object and an Ant Design `ThemeConfig` using `darkAlgorithm`, mapping palette values to Ant tokens such as `colorPrimary`, `colorBgBase`, `colorBorder`, `borderRadius`, and font families.
2. A global stylesheet (`src/theme/global.css`) declares the same palette as CSS custom properties under `:root` (e.g. `--bg`, `--surface`, `--accent`, `--radius`) so bespoke component styles can consume them without importing the TS tokens.

The two sources are explicitly kept in sync by design comments that call out they mirror each other for SPEC-023 R-1 dark theme parity.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares React 19, Ant Design 6, `@ant-design/x`, `dayjs`, Vite, Vitest, and TypeScript as the full UI stack.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radii, and fonts; builds the `portalTheme: ThemeConfig` passed into Ant's provider.
- `products/operator-portal/web-ui/app/src/theme/global.css` — root-level CSS variables, base reset, app shell layout, chat transcript chrome, markdown rendering, HITL confirmation cards, evidence panels, sticky request banners, and responsive breakpoints.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time via `define`; outputs to `../dist` for nginx serving; proxies `/api` to `http://localhost:8080` in dev.
- `products/operator-portal/web-ui/app/src/App.tsx` — root layout consuming Ant Design `Layout`, `Menu`, `Drawer`, `Tag`, `Avatar`, etc., gated by role-based visibility rules from `./roles.ts`.
- `products/operator-portal/web-ui/app/src/views/...` — per-feature view components (audit, control, incidents, workspace) that compose Ant Design primitives with the shared CSS classes defined in `global.css`.

## Architecture and conventions

- **Design tokens are centralized**: all colors, spacing radius, and typography live in `tokens.ts`. Components never hard-code hex values; they either use Ant Design tokens (via the configured theme) or reference the CSS custom properties exported by `global.css`.
- **Dark-only theme**: `color-scheme: dark` is set on `:root`, and the Ant Design theme uses `darkAlgorithm`. The portal has no light-mode toggle; it is intentionally dark for operator consoles.
- **Bespoke styles coexist with Ant Design**: layout chrome (sidebar, drawer, session panel, chat transcript, approvals inbox, evidence cards, HITL confirmation cards, document panes) is implemented as plain CSS classes in `global.css` and applied to Ant Design containers like `Layout.Sider`, `Layout.Content`, and `Menu`. This avoids fighting Ant's internal DOM structure while keeping visual consistency.
- **Responsive strategy is breakpoint-driven**: the sidebar collapses at Ant Design's `lg` breakpoint (992px) and switches to an off-canvas `Drawer`; a pinned `.mobile-menu-button` appears below 992px. A secondary `max-width: 860px` media query narrows the session panel. No mobile-first framework is used — it is CSS media queries layered over Ant's responsive primitives.
- **Markdown content styling is scoped**: rendered Markdown inside the portal uses a `.md-content` wrapper class with explicit rules for headings, lists, code blocks, tables, blockquotes, links, and horizontal rules, all referencing the shared CSS variables.
- **Feature-specific UI patterns are codified as CSS classes**: e.g. `.session-item`, `.chat-messages`, `.approvals-entry`, `.confirm-card`, `.evidence-card`, `.turn-request-banner`, `.digest-bounded`, `.prose-bounded`. These classes are reused across views rather than being re-implemented per component.
- **Build-time version injection**: `vite.config.ts` reads the repo root `VERSION` file and locks dependency versions from `package-lock.json`, then exposes them as `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants consumed by the Settings view to display the tech stack table.

## Conventions and constraints

- **Token synchronization rule**: `tokens.ts` and `global.css` must stay in lockstep. The comment in `tokens.ts` states the palette is "ported verbatim from the legacy portal's :root design tokens" and that CSS custom properties mirror the TS tokens so both Ant components and bespoke styles share one vocabulary (SPEC-023 R-1).
- **Dark theme is enforced**: `color-scheme: dark` is set globally and the Ant theme algorithm is fixed to `darkAlgorithm`; there is no runtime theme switcher.
- **All bespoke layout uses CSS custom properties**: spacing, borders, backgrounds, and accent colors in `global.css` reference `var(--bg)`, `var(--surface)`, `var(--accent)`, `var(--border)`, `var(--text)`, `var(--text-muted)`, `var(--success)`, `var(--error)`, `var(--warning)`, `var(--code-bg)`, and `var(--radius)` — new styles should follow this pattern instead of introducing new magic values.
- **Responsive behavior is breakpoint-based, not fluid**: the sidebar toggles between inline `Layout.Sider` and a `Drawer` at Ant Design's `lg` breakpoint (992px); additional narrow adjustments exist at 860px. New views should reuse these breakpoints rather than inventing new ones.
- **Accessibility baseline**: `:focus-visible` is globally styled with a 2px accent outline and offset; motion-sensitive animations (e.g. turn arrival flash) respect `prefers-reduced-motion: reduce`.
- **Build artifact convention**: production output goes to `../dist` and is served by nginx; filenames are content-hashed for immutable caching while `index.html` is served no-store, as documented in the vite config comments.