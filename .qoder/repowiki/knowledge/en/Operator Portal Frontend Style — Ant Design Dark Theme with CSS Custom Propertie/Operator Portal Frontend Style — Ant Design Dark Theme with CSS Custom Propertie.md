---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
---

## What system/approach is used

The only frontend in the repository is the **operator-portal web UI** (`products/operator-portal/web-ui/app`), a React + TypeScript application built with Vite. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via a single `ThemeConfig` object that applies Ant Design's `darkAlgorithm`. A parallel set of **CSS custom properties** under `:root` mirrors the same palette so bespoke component styles and third-party rendered content (e.g. markdown) consume one vocabulary. The build injects locked dependency versions (`__REACT_VERSION__`, `__ANTD_VERSION__`) into the bundle for display in Settings.

There is no Tailwind, Sass, or CSS-in-JS library beyond Ant Design's built-in theming; styling is plain CSS scoped to `app/src/theme/global.css` plus per-component imports of Ant Design components.

## Key files and packages

- `app/package.json` — declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `vite`, `vitest`; Node ≥ 22.22.2.
- `app/vite.config.ts` — Vite config with React plugin, Vitest jsdom environment, dev proxy `/api → http://localhost:8080`, and `define` injection of platform/dependency versions.
- `app/src/theme/tokens.ts` — single source of truth for colors, radii, and fonts; exports `palette` and `portalTheme: ThemeConfig` using `antd.darkAlgorithm`.
- `app/src/theme/global.css` — global base styles, CSS custom property tokens (`--bg`, `--surface`, `--accent`, …), app shell layout, chat workspace chrome, markdown/evidence/HITL card styles, sticky request banner, responsive breakpoints, and bounded-pane helpers.
- `app/src/main.tsx` — mounts `<ConfigProvider theme={portalTheme}>` around the app root so all Ant components inherit the dark theme.
- Component files under `src/chat/`, `src/views/*` import Ant Design primitives directly (Layout, Menu, Table, Modal, Tag, Typography, etc.) and compose them with the shared theme.

## Architecture and conventions

1. **Single design token source.** `tokens.ts` defines the palette once; `global.css` repeats the same values as CSS variables so non-Ant components stay consistent. Comments explicitly state this dual-porting is required by SPEC-023 R-1 (dark theme).
2. **Dark-only theme.** `color-scheme: dark` is set on `:root`; `portalTheme` uses `darkAlgorithm`. No light-mode toggle exists.
3. **Typography.** Font families are declared in both places: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif` for body and `"JetBrains Mono", "Fira Code", monospace` for code, mirrored between `tokens.ts` and `global.css`.
4. **Component styling strategy.** Visual composition is done by composing Ant Design components (Layout/Sider/Menu for the sidebar, Table/Tag/Modal/Tabs for views). Custom visual tweaks live in `global.css` targeting Ant selectors (e.g. `.ant-layout-sider-collapsed .ant-menu-item-group-title`) rather than overriding component props extensively.
5. **Layout model.** A full-height app shell with a collapsible sidebar (inline on desktop, drawer below antd's `lg` breakpoint ~992px) and a single active view pane. Chat uses a two-column `.chat-view` with a fixed-width session list and a scrollable transcript column.
6. **Responsive behavior.** Media queries in `global.css` adjust session panel width at `max-width: 860px`; the mobile menu button is pinned fixed top-left and opens an off-canvas drawer below the breakpoint where Sider auto-collapses.
7. **Accessibility.** `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion` disables the turn-arrival flash animation while keeping a static tint.
8. **Bounded panes.** Document/narrative panes use a CSS variable `--bounded-pane-max-height` applied to wrapper classes `.digest-bounded` / `.prose-bounded` to constrain scrolling within panels without moving structural chrome.
9. **Build-time versioning.** `vite.config.ts` reads `VERSION` and `package-lock.json` to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` so the Settings view can report the exact shipped tech stack.

## Conventions and constraints

- All color/radius/font values flow from `src/theme/tokens.ts`; new UI elements should extend `palette` and/or `portalTheme` rather than hardcoding hex values.
- Bespoke CSS must reference the CSS custom properties (`var(--bg)`, `var(--accent)`, `var(--radius)`, …) defined in `global.css` instead of duplicating literals.
- The portal is dark-only; adding a theme toggle would require changes to both `tokens.ts` and `global.css` `:root` variables.
- Ant Design components are consumed directly — there is no wrapper component library abstracting them away.
- The app shell layout (sidebar + one view) and chat two-column layout are enforced through the global CSS classes `.app-shell`, `.chat-view`, `.session-panel`, `.chat-column`.
- Responsive breakpoints follow Ant Design's `lg` (992px) for the sidebar collapse and add a dedicated `860px` breakpoint for the session panel width.
- Test setup runs in `jsdom` (configured in `vite.config.ts` test block) with `src/test/setup.ts` as the setup file.