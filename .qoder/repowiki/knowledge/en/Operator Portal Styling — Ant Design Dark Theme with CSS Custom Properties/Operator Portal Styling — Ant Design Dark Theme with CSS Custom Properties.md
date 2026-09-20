---
kind: frontend_style
name: Operator Portal Styling — Ant Design Dark Theme with CSS Custom Properties
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

The operator portal (`products/operator-portal/web-ui/app`) is a React 19 + TypeScript application built with Vite and styled using **Ant Design v6** in its dark algorithm, augmented by a small set of hand-authored CSS custom properties (CSS variables) that form the single source of truth for colors, spacing, and typography. The stack is deliberately minimal: no Tailwind, Sass, or CSS-in-JS library beyond Ant Design's built-in theme system.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite, Vitest, and TypeScript as the only runtime dependencies.
- `app/src/theme/tokens.ts` — defines the `palette` object (bg, surface, surfaceAlt, border, text, textMuted, accent, accentHover, success, error, warning, codeBg, radius) and maps it into an Ant Design `ThemeConfig` using `darkAlgorithm`. This is the canonical design-token source.
- `app/src/theme/global.css` — mirrors the same palette as `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) so bespoke component styles and Ant Design components share one vocabulary; also contains all layout, chat transcript, evidence cards, HITL confirmation cards, markdown rendering, sticky request banner, and bounded-pane styles referenced throughout the app.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time via `define`; outputs to `../dist` for nginx serving; proxies `/api` to `http://localhost:8080` in dev.
- `app/src/App.tsx` — root shell using Ant Design `Layout`, `Sider`, `Menu`, `Drawer`, `Tag`, `Avatar`, `Typography`, `Alert`, `Spin`; applies `theme="dark"` to both the Sider and Menu; drives responsive behavior via `breakpoint="lg"` (992px) and a `useNarrowViewport` hook.

## Architecture and conventions

1. **Single token source, dual consumption.** `tokens.ts` exports the `palette` and `portalTheme`; `global.css` repeats the same hex values as CSS custom properties under `:root`. Comments explicitly state this mirroring is intentional so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1). New colors must be added to both places.

2. **Ant Design dark theme is the baseline.** All Ant Design components are consumed with `theme="dark"` (Menu, Sider) and the global `portalTheme` sets `colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorText`, `borderRadius`, `fontFamily`, and `fontFamilyCode`. No light-mode override exists.

3. **BEM-like class names for bespoke UI.** Custom styling uses flat class names scoped to semantic regions: `.app-shell`, `.sidebar-brand`, `.view-container`, `.chat-view`, `.session-panel`, `.evidence-card`, `.confirm-card`, `.turn-group`, `.md-content`, `.digest-bounded`, `.prose-bounded`. There is no per-component CSS file — everything lives in `global.css`.

4. **Responsive strategy is breakpoint-driven, not mobile-first.** A `useNarrowViewport` hook watches `max-width: 991px` to switch between inline `Sider` and off-canvas `Drawer`. CSS media queries use `@media (max-width: 860px)` for session panel width and `@media (prefers-reduced-motion: reduce)` to disable animations. There is no responsive utility framework.

5. **Accessibility tokens are explicit.** `:focus-visible` gets a 2px solid `var(--accent)` outline with 2px offset; `aria-label` attributes are attached to navigation buttons; `aria-hidden="true"` marks decorative spacers.

6. **Build-time versioning is part of the visual layer.** `vite.config.ts` reads the repo `VERSION` file and injects `__PLATFORM_VERSION__`, which is displayed as a `Tag` next to the "Luban AIOps" brand in the sidebar. Dependency versions are similarly injected for the Settings view's tech-stack table.

7. **Spec-driven style gates.** Many CSS blocks are annotated with spec references (SPEC-011, SPEC-019, SPEC-020, SPEC-023, SPEC-024, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041), tying visual behavior to product requirements rather than ad-hoc decisions.

## Conventions and constraints

- **All colors flow through the `palette` object in `tokens.ts`**; hard-coded color literals should not appear in new bespoke styles — they must reference the corresponding `var(--*)` from `global.css`.
- **Custom properties are the shared vocabulary**: components read `var(--bg)`, `var(--surface)`, `var(--accent)`, `var(--border)`, `var(--text)`, `var(--text-muted)`, `var(--code-bg)`, `var(--radius)` rather than re-declaring hex values.
- **Ant Design components are always rendered with `theme="dark"`** where applicable (Menu, Sider); the global `portalTheme` configures the rest.
- **Bespoke classes follow a flat naming convention** (no BEM nesting, no CSS modules): e.g., `.session-item.active`, `.turn-group.turn-arrived`, `.digest-bounded .ant-tabs-body-holder` — modifiers are expressed via adjacent classes, not nested selectors.
- **Animations respect user preference**: the turn-arrival flash animation is disabled when `prefers-reduced-motion: reduce` is set.
- **Bounded panes use a CSS variable height contract**: views set `--bounded-pane-max-height` on wrapper elements and consume it via `.digest-bounded` / `.prose-bounded` selectors to cap scrollable content while keeping chrome pinned.
- **No other frontend styling systems exist elsewhere in the repo.** Backend services are Python FastAPI/Starlette apps with no HTML/CSS; the only UI code is under `products/operator-portal/web-ui/app`.