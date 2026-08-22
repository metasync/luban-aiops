---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
---

## What system/approach is used

The only frontend in this monorepo is the **operator portal** (`products/operator-portal/web-ui/app`), a React 18 + TypeScript SPA built with **Vite**. Visual styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via a single dark-mode `ThemeConfig`. A parallel set of **CSS custom properties** under `src/theme/global.css` mirrors the token values so that bespoke (non-AntD) components stay on the same design vocabulary. The app uses no CSS-in-JS, no Tailwind, and no SCSS — plain `.css` files consumed by Vite.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `vite`, `typescript`, `vitest` as the entire UI dependency surface.
- `products/operator-portal/web-ui/app/src/main.tsx` — bootstraps the app inside `<ConfigProvider theme={portalTheme}>`, importing both the AntD theme config and `./theme/global.css`.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the canonical palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and builds an AntD `ThemeConfig` using `darkAlgorithm`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — declares the matching `:root` CSS variables (`--bg`, `--surface`, …) plus global layout styles for the app shell, sidebar, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, view toolbars, and a narrow-viewport breakpoint at 860px.
- `products/operator-portal/web-ui/app/src/App.tsx` — composes the antd `Layout`/`Menu`/`Drawer` shell; applies `className="app-shell"`, `view-container`, `view-container-flush`, and `sidebar-footer` classes defined in `global.css`.
- `products/operator-portal/web-ui/app/vite.config.ts` — build configuration that outputs to `../dist`, injects `__PLATFORM_VERSION__` from the repo root `VERSION` file, proxies `/api` to `http://localhost:8080` in dev, and runs tests under `jsdom`.

## Architecture and conventions

1. **Single source of truth for tokens.** `tokens.ts` is the authoritative palette; `global.css` is explicitly documented as mirroring it verbatim so AntD components and hand-written CSS share one vocabulary. Comments reference SPEC-023 R-1 (dark theme).
2. **AntD theme override, not theming per component.** All visual customization goes through the top-level `ConfigProvider` theme object — individual components do not receive inline style overrides except for small layout tweaks (e.g., `borderInlineEnd: "1px solid var(--border)"`).
3. **Bespoke styles live in one stylesheet.** Non-component-specific chrome (layout grid, chat workspace columns, markdown rendering, evidence groups, HITL cards, view toolbars) is written as flat CSS classes in `global.css` rather than per-component CSS modules or styled-components.
4. **Dark-only mode.** `color-scheme: dark` is set on `:root`; the AntD theme uses `darkAlgorithm`; the menu and sider are forced to `theme="dark"`. No light-theme toggle exists.
5. **Responsive strategy is minimal.** A single `@media (max-width: 860px)` shrinks the session panel width; a separate `Drawer` provides an off-canvas sidebar for narrow viewports (documented as legacy drawer parity). Full responsive drawer parity is noted as future stage 5.
6. **Build-time version injection.** `vite.config.ts` reads the repository root `VERSION` file and exposes it as `__PLATFORM_VERSION__`, which is displayed in the sidebar tag — tying the UI build artifact to the platform version.
7. **No CSS framework beyond AntD.** There is no Tailwind, Sass, PostCSS plugins, CSS modules, or CSS-in-JS library. Styles are plain CSS imported once in `main.tsx`.

## Conventions and constraints

- **Token synchronization:** Adding a new color must be done in `tokens.ts` first, then mirrored in `global.css` `:root`. This is enforced by comments referencing SPEC-023 R-1 and the explicit statement that CSS custom properties mirror the TS tokens.
- **Use CSS variables for bespoke styles:** Hand-written selectors reference `var(--accent)`, `var(--surface)`, etc., never hard-coded hex values, so the palette stays centralized.
- **AntD components consume the theme via `ConfigProvider`:** Components are not individually themed; they inherit from the provider's `ThemeConfig`.
- **Class naming follows BEM-like semantic names in `global.css`:** `.app-shell`, `.view-container`, `.session-panel`, `.chat-view`, `.md-content`, `.evidence-card`, `.confirm-card`, `.view-toolbar`, `.report-form` — these are reused across views rather than scoped per component.
- **Accessibility baseline:** `:focus-visible` gets a 2px accent outline with offset; mobile menu button carries `aria-label="Open navigation"`; sign-in/sign-out buttons carry `aria-label` attributes.
- **Markdown content styling is centralized:** All rendered markdown (headings, code blocks, blockquotes, tables, links) is styled via the `.md-content` selector family in `global.css`, ensuring consistent appearance regardless of where markdown is rendered.
- **Version pinning:** The UI depends on pinned major versions of React (^18.3.1), AntD (^6.1.1), Vite (^6.0.5), and TypeScript (~5.6.3); Node engine is locked to `>=22`.
- **Test environment:** UI tests run under `jsdom` via Vitest (configured in `vite.config.ts`), meaning styles are evaluated in a DOM-like environment but without full browser rendering.