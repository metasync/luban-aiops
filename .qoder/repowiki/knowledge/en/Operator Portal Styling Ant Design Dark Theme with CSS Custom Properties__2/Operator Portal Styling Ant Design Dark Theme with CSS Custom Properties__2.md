---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui/app`) is a React 18 + TypeScript SPA built with Vite. Visual styling is centered on **Ant Design v6** (`antd` and `@ant-design/x`) using the built-in dark algorithm, with a single shared design-token layer that synchronizes JavaScript theme configuration and CSS custom properties.

There is no Tailwind, Sass/SCSS, or CSS-in-JS library beyond Ant Design's own token system. Styles are plain CSS modules (global stylesheet) plus component-level inline styles where needed.

## Key files and packages

- `package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 18, Vite 6, Vitest for tests.
- `src/theme/tokens.ts` — defines the canonical palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `success`, `error`, `warning`, `codeBg`, `radius`) and builds an Ant Design `ThemeConfig` via `antd.theme.darkAlgorithm`.
- `src/theme/global.css` — declares matching CSS custom properties under `:root` (`--bg`, `--surface`, `--accent`, etc.) so bespoke styles and Ant components share one vocabulary; also contains all layout, chat, evidence, approvals, markdown, and responsive rules.
- `vite.config.ts` — injects `__PLATFORM_VERSION__` at build time and outputs to `../dist`; dev server proxies `/api` to `http://localhost:8080`.
- `nginx.conf` (at `products/operator-portal/`) serves the built `web-ui/dist` as a static site.

## Architecture and conventions

1. **Single source of truth for tokens.** The comment in `tokens.ts` states that the palette was "ported verbatim from the legacy portal's :root design tokens" and that CSS custom properties mirror the JS values so both Ant Design components and bespoke styles consume the same vocabulary. This is enforced by the explicit mapping between `palette.*` fields and the corresponding `--*` variables in `global.css`.

2. **Dark-only theme.** `color-scheme: dark` is set on `:root`, and the Ant Design theme uses `darkAlgorithm`. There is no light-mode toggle; the entire portal is designed for a dark background (`#0f172a`).

3. **Ant Design as the component foundation.** All UI primitives (Layout, Menu, Typography, Button, Table, etc.) come from Ant Design. Custom overrides target Ant Design class names directly (e.g., `.ant-layout-sider-collapsed .ant-menu-item-group-title`, `.ant-typography`) rather than wrapping components in styled containers.

4. **BEM-like global CSS classes for bespoke chrome.** Layout shells use descriptive class names such as `.app-shell`, `.view-container`, `.session-panel`, `.chat-view`, `.turn-group`, `.confirm-card`, `.approvals-entry`, `.md-content`, `.evidence-card`, `.turn-request-banner`. These live exclusively in `global.css` and are applied across views.

5. **Responsive strategy via CSS media queries.** A single breakpoint at `max-width: 860px` narrows the session panel width; the sidebar navigation folds into an off-canvas drawer below antd's `lg` breakpoint (992px), driven by Ant Design's Sider collapse behavior plus a pinned `.mobile-menu-button`.

6. **Accessibility baseline.** `:focus-visible` gets a 2px accent-colored outline with offset; `prefers-reduced-motion` disables the turn-arrival flash animation while keeping a subtler background tint.

7. **Markdown rendering style.** A dedicated `.md-content` rule set styles headings, lists, code blocks, blockquotes, tables, links, and horizontal rules to match the dark palette, with fenced code blocks capped at `max-height: 280px` so they don't push transcripts out of view.

## Conventions and constraints

- **All colors flow through the `palette` object in `tokens.ts`**; new hues should be added there first and mirrored in `global.css` `:root` custom properties.
- **Border radius is centralized**: `palette.radius` (8) maps to both `borderRadius` in the Ant Design theme and the `--radius` CSS variable used by bespoke elements.
- **Fonts are fixed**: sans-serif stack `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif` for body text and `"JetBrains Mono", "Fira Code", monospace` for code; these are declared in both the Ant Design theme config and `global.css`.
- **Component overrides target Ant Design class selectors** rather than creating wrapper divs with unique class names; this keeps visual changes scoped to Ant primitives.
- **Build-time version injection** (`__PLATFORM_VERSION__`) is part of the frontend asset pipeline and is validated by `make validate-version` per SPEC-023 R-1.
- **No CSS-in-JS per-component stylesheets**: the project relies on one global stylesheet plus Ant Design's theme API, which constrains how much ad-hoc styling can be introduced without touching `global.css` or the token layer.