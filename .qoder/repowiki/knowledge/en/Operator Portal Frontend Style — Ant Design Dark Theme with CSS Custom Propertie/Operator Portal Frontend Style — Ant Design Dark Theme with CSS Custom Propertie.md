---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
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

The only frontend in this repository is the **operator portal web UI** under `products/operator-portal/web-ui/app/`. It is a React 18 + TypeScript application built with Vite and styled primarily through **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`). There is no Tailwind, Sass, or CSS-in-JS library; styling uses plain CSS modules via a single global stylesheet plus component-level class names.

## Key files and packages

- `app/package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 18, Vite 6, Vitest.
- `app/src/main.tsx` — bootstraps the app inside `<ConfigProvider theme={portalTheme}>` and imports `./theme/global.css`.
- `app/src/theme/tokens.ts` — central design-token source: a `palette` object (bg, surface, surfaceAlt, border, text, textMuted, accent, success, error, warning, codeBg, radius) and an Ant Design `ThemeConfig` using `antd.darkAlgorithm`.
- `app/src/theme/global.css` — defines matching CSS custom properties on `:root` (`--bg`, `--surface`, `--accent`, …) and all bespoke layout / chat / approvals / markdown styles.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__` at build time; outputs to `../dist` for nginx serving.

## Architecture and conventions

1. **Single source of truth for tokens.** `tokens.ts` is the canonical palette. The comment states that `global.css` mirrors it verbatim so both Ant Design components and bespoke CSS consume one vocabulary. This dual definition (JS token object + `:root` CSS variables) is the enforced convention for keeping Ant Design theming and hand-written styles consistent.

2. **Dark theme by default.** `portalTheme` uses `antdTheme.darkAlgorithm`; `global.css` sets `color-scheme: dark` and a slate-based palette (`#0f172a` background, `#e2e8f0` text). No light-theme toggle exists in the current codebase.

3. **Ant Design as the component foundation.** All interactive UI primitives (Layout, Menu, Drawer, Typography, Form, Table, etc.) are consumed from Ant Design and themed via `ConfigProvider`. Custom overrides live in `global.css` targeting Ant selectors (e.g., `.ant-layout-sider-collapsed .ant-menu-item-group-title`).

4. **Bespoke styles via scoped class names in one global sheet.** Rather than CSS Modules or per-component CSS files, the project uses BEM-style class names (`.app-shell`, `.session-panel`, `.chat-view`, `.approvals-entry`, `.confirm-card`, `.turn-request-banner`) defined in `global.css`. These classes are applied directly in JSX.

5. **Responsive strategy.** Responsive behavior is handled with CSS media queries in `global.css` (e.g., `@media (max-width: 860px)` shrinking the session panel) and by relying on Ant Design's built-in responsive Sider behavior. A mobile menu button (`.mobile-menu-button`) is pinned fixed for off-canvas drawer navigation below the `lg` breakpoint.

6. **Accessibility baseline.** `:focus-visible` is globally styled with the accent color and a 2px offset outline. A `prefers-reduced-motion` media query disables the turn-arrival flash animation. Font stacks use system sans-serif plus Inter; code uses JetBrains Mono / Fira Code monospace families.

7. **Build-time version injection.** `vite.config.ts` reads the root `VERSION` file and exposes it as `__PLATFORM_VERSION__` for runtime display; this is tied to the `make validate-version` check referenced in comments.

## Conventions and constraints

- **All colors must come from the `palette` object in `tokens.ts`** and be reflected as matching `--*` CSS custom properties in `global.css`. This is documented in the file header comment and enforced by the fact that both Ant Design `ThemeConfig` tokens and bespoke CSS rules reference the same values.
- **Custom Ant Design overrides target Ant selectors in `global.css`**, not inline styles or component props. Examples include overriding collapsed sidebar group titles and brand padding.
- **Component-specific visual state is expressed via class name modifiers** (e.g., `.session-item.active`, `.turn-group.turn-arrived`, `.confirm-card.pending`) rather than CSS-in-JS conditional styles.
- **Markdown rendering gets a dedicated style scope** (`.md-content *`) so rendered agent/tool output stays visually distinct from UI chrome.
- **Evidence blocks and tool results share a bounded-height pattern** (`max-height: 280px` with overflow auto) so large outputs do not push transcript content out of view.
- **No other product in this workspace ships frontend code.** All other services are Python FastAPI backends; the operator portal is the sole consumer of this styling system.