---
kind: frontend_style
name: Operator Portal Styling — Ant Design Dark Theme with CSS Custom Properties Tokens
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

## System / Approach

The only frontend in the repository is the **operator-portal** under `products/operator-portal/web-ui/app`. It is a React 19 + TypeScript application built with Vite, styled primarily through **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) and a small set of bespoke global CSS rules. There is no Tailwind, Sass, CSS-in-JS library, or component library beyond Ant Design.

Theming is centralized around two files:

- `app/src/theme/tokens.ts` — defines the design-token palette and an Ant Design `ThemeConfig` using `antdTheme.darkAlgorithm`.
- `app/src/theme/global.css` — declares the same tokens as CSS custom properties on `:root` for bespoke styles that bypass Ant Design.

The theme is applied at the root via `<ConfigProvider theme={portalTheme}>` in `src/main.tsx`, making Ant Design components consume the dark palette automatically.

## Key Files

- `products/operator-portal/web-ui/app/package.json` — declares dependencies (`antd ^6.6.2`, `react ^19.2.8`, `@vitejs/plugin-react`, `vitest`).
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/main.tsx` — bootstraps React StrictMode, wraps the app in `ConfigProvider` with `portalTheme` and `AuthProvider`, imports `global.css`.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radius, fonts; exports `palette` (as const) and `portalTheme`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — CSS custom properties mirroring `tokens.ts`, plus layout, chat transcript, evidence cards, HITL confirmation cards, markdown rendering, and responsive breakpoints.

## Architecture and Conventions

1. **Dual token surface.** The palette lives once in `tokens.ts` and is mirrored into CSS custom properties (`--bg`, `--surface`, `--accent`, `--border`, `--text-muted`, `--code-bg`, `--radius`, etc.) so Ant Design components get the theme programmatically while hand-written CSS reads the same values from `var(--*)`. The comment in `tokens.ts` explicitly states this mirrors the legacy portal's `:root` design tokens (SPEC-023 R-1).

2. **Dark-only theme.** `color-scheme: dark` is set on `:root`; there is no light-mode toggle. All color variables are dark-slate tones with a sky-blue accent (`#38bdf8`).

3. **Typography.** Font families are declared inside the Ant Design `ThemeConfig.token`: sans-serif stack `'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif'` and monospace stack `"JetBrains Mono", "Fira Code", monospace`. These are reused in `.md-content code`, `.tool-name`, and `.recovery-fact > dd` selectors in `global.css`.

4. **BEM-like class naming for bespoke styles.** Global CSS uses flat BEM-style class names scoped by feature sections (e.g., `.session-panel`, `.chat-view`, `.confirm-card`, `.approvals-entry`, `.turn-group.turn-arrived`, `.digest-bounded`, `.prose-bounded`). Components themselves are TSX files under `src/views/`, `src/chat/`, `src/auth/`, `src/stream/`, `src/voice/`; they compose Ant Design primitives rather than defining their own CSS modules.

5. **Responsive strategy.** A single `@media (max-width: 860px)` breakpoint narrows the session panel width. Sidebar collapse behavior relies on Ant Design's `Sider` auto-collapse at its `lg` breakpoint (992px), with a pinned `.mobile-menu-button` that opens an off-canvas drawer below that breakpoint (documented in comments referencing SPEC-019).

6. **Accessibility conventions baked into CSS.** `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion: reduce` disables the `.turn-arrived` flash animation; keyboard focus visibility is called out in a comment.

7. **Spec-driven style gates.** Many CSS blocks carry inline references to spec requirements (e.g., `SPEC-023 R-1`, `SPEC-019 R-1`, `SPEC-020 R-4`, `SPEC-034 R-1`, `SPEC-035 R-4`, `SPEC-037 R-6`, `SPEC-039 R-8`, `SPEC-041 R-3`), tying visual decisions back to product specs.

8. **Build-time asset hashing.** Vite output goes to `web-ui/dist` with content-hashed filenames so assets are immutable-cacheable while `index.html` stays no-store (per `vite.config.ts` comment citing SPEC-023 R-1). The parent `nginx.conf` serves this directory at `/`.

## Conventions and Constraints

- **Design tokens are single-sourced in `tokens.ts`** and mirrored into `global.css` `:root` custom properties. Any new color must be added to both places (enforced by the comment in `tokens.ts` stating the CSS properties mirror the JS palette).
- **All bespoke styling goes through `global.css`**; there are no per-component CSS modules, SCSS files, or inline style objects used for layout/theming.
- **Ant Design is the sole UI component library.** Components import from `antd` and `@ant-design/icons`; custom overrides target Ant Design's generated class names (e.g., `.ant-layout-sider`, `.ant-layout-sider-collapsed`, `.ant-tabs-body-holder`, `.ant-collapse-body`).
- **The theme is dark-only** — `color-scheme: dark` and `darkAlgorithm` are the only configuration paths present.
- **Responsive breakpoints are minimal:** 860px (session panel shrink) and reliance on Ant Design's internal `lg` breakpoint at 992px for sidebar collapse.
- **Motion is reduced when requested:** `@media (prefers-reduced-motion: reduce)` suppresses the turn-arrival flash animation.
- **Spec references in comments act as traceability anchors** for visual changes (SPEC-023, SPEC-019, SPEC-020, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041).
- **Build-time version injection** (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) is enforced by `make validate-version` (referenced in `vite.config.ts`), ensuring the runtime tech-stack table matches the locked bundle.