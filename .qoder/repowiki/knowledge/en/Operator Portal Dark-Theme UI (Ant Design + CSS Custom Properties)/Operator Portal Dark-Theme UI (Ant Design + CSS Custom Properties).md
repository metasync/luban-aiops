---
kind: frontend_style
name: Operator Portal Dark-Theme UI (Ant Design + CSS Custom Properties)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The only frontend in this monorepo is the **Operator Portal** under `products/operator-portal/web-ui/app`. It is a **React 18 + TypeScript** SPA built with **Vite** (`vite.config.ts`) and styled primarily with **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`). There is no Tailwind, Sass, or CSS-in-JS library beyond Ant's built-in theming. The build outputs to `dist/` and is served by an nginx container.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares React, Ant Design 6, Vite, Vitest, and TypeScript as dependencies; Node ≥22 engine.
- `products/operator-portal/web-ui/app/vite.config.ts` — Vite config: React plugin, `__PLATFORM_VERSION__` injected from root `VERSION`, dev proxy `/api → http://localhost:8080`, output dir `../dist`, jsdom test environment.
- `products/operator-portal/web-ui/app/src/main.tsx` — Root entry that wraps `<App />` in `ConfigProvider` with a theme object and imports global CSS.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — Single source of truth for design tokens: a `palette` object (bg, surface, accent, success, error, warning, border, text, radius) and an Ant Design `ThemeConfig` using `darkAlgorithm` plus those palette values for primary/background/border/text/success/error/warning colors, `borderRadius`, and fonts (`Inter` / `JetBrains Mono`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — CSS custom properties on `:root` that mirror `tokens.ts` exactly (`--bg`, `--surface`, `--accent`, etc.), plus base resets, layout shell styles (`.app-shell`, `.view-container`, `.session-panel`, `.chat-view`), markdown rendering rules (`.md-content`), evidence/HITL card styles (`.evidence-card`, `.confirm-card`), and a narrow-viewport breakpoint at `max-width: 860px`.
- `products/operator-portal/web-ui/app/src/App.tsx` — Shell component using Ant Design `Layout.Sider` (dark mode) and `Drawer` for mobile navigation; routes between views (`chat`, `incidents`, `audit`, `permissions`, `tools`, `skills`, `settings`).

## Architecture and conventions

1. **Single dark theme, no light-mode toggle.** `color-scheme: dark` is set on `:root`, and Ant Design is configured with `darkAlgorithm`. All components inherit the dark palette.
2. **Dual token channel:** `src/theme/tokens.ts` defines the canonical palette and feeds it into both Ant Design's `ConfigProvider.theme` and the CSS custom properties in `global.css`. Comments explicitly state they are "ported verbatim from the legacy portal's :root design tokens" so bespoke styles and Ant components stay on one vocabulary.
3. **Component styling strategy:**
   - Layout chrome uses Ant Design primitives (`Layout`, `Menu`, `Drawer`, `Button`, `Tag`, `Avatar`, `Typography`, `Alert`, `Spin`).
   - View-specific layout and shared visual patterns (sidebar footer, session list items, chat columns, markdown content, evidence cards, HITL confirmation cards) live in `global.css` as BEM-style class names (`.app-shell`, `.view-container`, `.session-panel`, `.md-content`, `.evidence-card`, `.confirm-card`).
   - Inline `style={{}}` props are used sparingly for small overrides inside `App.tsx`; there is no per-component CSS file convention observed.
4. **Responsive strategy:** A single `@media (max-width: 860px)` block narrows the session panel width. Mobile navigation is handled via an off-canvas `Drawer` triggered by a floating menu button — not via a responsive sidebar collapse alone. The comment notes full drawer parity is planned for a later stage.
5. **Build-time version injection:** `__PLATFORM_VERSION__` is baked into the bundle from the repo root `VERSION` file via Vite's `define`, then displayed as an Ant Design `Tag` in the sidebar.
6. **No CSS framework beyond Ant Design.** No `tailwind.config.*`, no SCSS/Sass, no CSS modules, no styled-components/emotion. Styles are plain CSS imported once in `main.tsx`.

## Conventions and constraints

- **Design tokens must be mirrored:** Any change to `palette` in `tokens.ts` should be reflected in the corresponding `--*` CSS custom property in `global.css` (the code comments treat this as an enforced contract across SPEC-023 R-1 dark theme).
- **Dark-only UI:** New components should assume `color-scheme: dark` and consume either Ant Design tokens via `ConfigProvider` or the `var(--*)` variables — no light-theme branches are present.
- **Class naming:** Shared view chrome and reusable UI fragments use descriptive BEM-like classes in `global.css` rather than scoped CSS modules; new shared UI should follow the same pattern.
- **Mobile behavior:** Narrow screens fold the sidebar into a `Drawer`; the session panel shrinks at `860px`. This is the current responsive baseline.
- **Markdown/evidence/HITL rendering:** Styled via dedicated `.md-content`, `.evidence-*`, `.confirm-*` blocks in `global.css`; new rich content should reuse these selectors to keep visual parity with SPEC-011 / SPEC-020 requirements.