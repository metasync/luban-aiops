---
kind: frontend_style
name: Operator Portal — Ant Design Dark Theme with CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

# Operator Portal Frontend Style System

## What system/approach is used

The operator portal (`products/operator-portal/web-ui/app`) is a **React 18 + TypeScript** single-page application built with **Vite**. Styling is centered on the **Ant Design (antd v6)** component library, configured via `ConfigProvider` with a custom dark theme. A parallel set of **CSS custom properties** in `src/theme/global.css` mirrors the antd token values so bespoke components and legacy ported styles can consume the same palette without touching antd internals.

Key stack:
- UI framework: React 18 with TypeScript
- Component library: `antd` ^6.1.1 plus `@ant-design/icons` ^6 and `@ant-design/x` ^2.9
- Build toolchain: Vite 6 with `@vitejs/plugin-react`; tests run under Vitest with jsdom
- No CSS-in-JS or utility-first framework (no Tailwind); styling is plain CSS files imported at the app root

## Key files and packages

- `package.json` — declares antd, @ant-design/icons, @ant-design/x, react, dayjs as runtime deps; vite/vitest/typescript as dev deps.
- `vite.config.ts` — injects `__PLATFORM_VERSION__` from the repo root `VERSION` file; builds to `../dist` for nginx serving; proxies `/api` to localhost:8080 during dev.
- `src/main.tsx` — bootstraps React root inside `<ConfigProvider theme={portalTheme}>`, then `<AuthProvider>` wrapping `<App />`; imports `./theme/global.css` once.
- `src/theme/tokens.ts` — defines the `palette` object (bg, surface, accent, success, error, warning, border, text, radius) and maps it into an antd `ThemeConfig` using `darkAlgorithm`. Font families are declared here (`Inter` + JetBrains Mono/Fira Code).
- `src/theme/global.css` — declares `:root` CSS custom properties mirroring `tokens.ts` exactly, sets `color-scheme: dark`, global resets, focus-visible outline, layout shell classes (`.app-shell`, `.view-container`, `.chat-view`, `.session-panel`, …), markdown/evidence/HITL confirmation card styles, and a narrow-viewport media query at 860px.
- `src/App.tsx` — top-level layout using antd `Layout.Sider`/`Layout.Content` with a collapsible sidebar (breakpoint `lg` = 992px), a drawer-based off-canvas menu on narrow screens, and role-gated navigation items. Uses inline `style` props sparingly (e.g., borders referencing `var(--border)`).

## Architecture and conventions

### Single source of truth for colors
`src/theme/tokens.ts` is the canonical palette. The comment states that CSS custom properties in `global.css` mirror these tokens verbatim so both antd components and bespoke styles share one vocabulary. Every color used by antd tokens (`colorPrimary`, `colorBgBase`, `colorText`, etc.) comes from this `palette` object.

### Dark-only theme
The app enforces a dark theme globally: `color-scheme: dark` in `:root`, antd's `darkAlgorithm`, and `theme="dark"` on the antd `Menu` and `Layout.Sider`. There is no light-mode toggle.

### Layout shell
A fixed-height `.app-shell` uses antd `Layout` with a left `Sider` (width 230, collapsed width 64) and a content area. Views render inside a `.view-container` class; the chat view additionally applies `.view-container-flush` to remove padding and own its scrolling. A pinned `.mobile-menu-button` (fixed top-left) toggles either the sider collapse state or opens a Drawer with the full menu on narrow viewports.

### Responsive strategy
- Desktop: inline sidebar collapses to a 64px icon rail below antd's `lg` breakpoint (992px), detected via `useNarrowViewport` which listens to `matchMedia("(max-width: 991px)").
- Narrow mobile (< 860px): a CSS `@media` rule shrinks `.session-panel` from 260px to 200px; the Drawer provides the full labeled navigation.
- Off-canvas drawer parity is noted as future work (stage 5) in comments.

### Typography
Font families are centralized in `tokens.ts` and applied through antd tokens: sans-serif stack `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif` and code stack `"JetBrains Mono", "Fira Code", monospace`. Markdown-rendered content in `.md-content` reuses the same code font.

### Accessibility
- Global `:focus-visible` rule draws a 2px accent-colored outline with offset on all elements.
- The mobile menu button carries an `aria-label` that changes based on viewport/side state.
- Reduced motion is respected via `@media (prefers-reduced-motion: reduce)` disabling the turn-arrival flash animation while keeping a subtle background tint.

### View chrome and shared patterns
Common UI shapes live in `global.css`: `.approvals-entry` cards, `.confirm-card` HITL cards, `.evidence-turn` / `.evidence-card` / `.evidence-pre` blocks for tool evidence, `.turn-request-banner` sticky context banner, `.report-form`, and `.view-toolbar`. These are reused across views rather than duplicated per component.

### Build-time versioning
The platform version string is injected at build time via `vite.config.ts`'s `define` block reading the root `VERSION` file, consumed as `__PLATFORM_VERSION__` and surfaced in the sidebar brand tag. This is enforced by `make validate-version` per the SPEC-023 R-1 comment.

## Conventions and constraints

- **All colors flow through `src/theme/tokens.ts`**: new hues must be added to `palette` and mapped into `portalTheme` before being referenced anywhere else.
- **Bespoke styles use CSS custom properties**, not hard-coded hex values: selectors reference `var(--accent)`, `var(--surface)`, `var(--border)`, `var(--radius)`, etc., defined in `:root` of `global.css`.
- **Dark mode is mandatory**: there is no theme switcher; `color-scheme: dark` and antd `darkAlgorithm` are applied unconditionally at bootstrap.
- **Responsive breakpoints are anchored to antd's `lg` (992px)** for the sidebar collapse and to a custom 860px breakpoint for session panel width; new responsive rules should follow this pattern.
- **Components are styled via a mix of antd props and CSS classes**: antd components receive `theme="dark"` and token overrides through `ConfigProvider`; custom DOM structure uses semantic BEM-like class names (`.app-shell`, `.view-container`, `.chat-view`, `.session-panel`, `.confirm-card`, …) defined in `global.css`.
- **Markdown and evidence rendering share a common stylesheet**: `.md-content` and `.evidence-*` classes style rendered prose uniformly across chat replies and tool outputs.
- **No third-party CSS frameworks beyond antd**: no Tailwind, Sass, CSS Modules, or styled-components are present — plain `.css` files are sufficient and expected.