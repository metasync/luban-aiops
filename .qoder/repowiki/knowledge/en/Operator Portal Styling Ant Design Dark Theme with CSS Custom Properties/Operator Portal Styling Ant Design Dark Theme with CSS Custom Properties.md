---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Properties'
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

The operator portal (`products/operator-portal/web-ui/app`) is a **React 18 + Vite** application styled with **Ant Design 6** in dark mode. There is no CSS-in-JS library, Tailwind, or Sass pipeline — styling is split between:

1. **Ant Design `ConfigProvider` theme** (programmatic tokens) — applied at the root in `src/main.tsx` via `portalTheme`.
2. **A single global stylesheet** `src/theme/global.css` — defines CSS custom properties that mirror the Ant Design token values so bespoke component styles and third-party rendered content can consume the same palette.
3. **Inline `style` props on Ant components** for layout-specific overrides (e.g. sidebar width, border colors).

No build-time CSS processor is configured; `vite.config.ts` only registers `@vitejs/plugin-react`. The project uses plain `.css` files imported from TypeScript/JSX modules.

## Key files and packages

- `package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 18, Vite 6, Vitest.
- `src/main.tsx` — mounts `<ConfigProvider theme={portalTheme}>` around the app; imports `./theme/global.css`.
- `src/theme/tokens.ts` — central design-token definition: exports a `palette` object (bg, surface, accent, success, error, warning, radius, fonts) and an Ant Design `ThemeConfig` using `antd.darkAlgorithm`.
- `src/theme/global.css` — defines `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) that are exact mirrors of `tokens.ts`; also contains all bespoke view-level CSS (app shell, chat transcript, evidence cards, HITL confirmations, responsive breakpoints).
- `src/App.tsx` — consumes the theme indirectly through Ant Design's dark `Layout.Sider` / `Menu` and applies CSS classes like `app-shell`, `view-container`, `sidebar-brand-spacer`, `mobile-menu-button` defined in `global.css`.
- `vite.config.ts` — builds to `../dist` with content-hashed assets; proxies `/api` to `http://localhost:8080` during dev.

## Architecture and conventions

### Single source of truth for colors
`tokens.ts` is the canonical palette. `global.css` declares matching CSS variables so non-Ant components (markdown rendering, evidence panels, sticky banners) use the same vocabulary. Comments in both files explicitly state they mirror each other per SPEC-023 R-1.

### Dark-only theme
The entire portal ships in dark mode: `color-scheme: dark` is set on `:root`, `antd.darkAlgorithm` is selected, and every semantic color has a dark value. No light-mode toggle exists.

### Component composition pattern
Views are organized as React components under `src/views/{audit,control,incidents}/` plus feature folders (`chat`, `auth`, `stream`, `voice`). Layout chrome (sidebar, drawer, mobile menu button) lives in `App.tsx`; view-specific styles live in `global.css` under named blocks (`.session-panel`, `.chat-view`, `.evidence-card`, `.confirm-card`, `.turn-request-banner`).

### Responsive strategy
Responsive behavior is handled in two places:
- Ant Design `Layout.Sider` breakpoint `lg` (992px) auto-collapses the inline sidebar into a 64px icon rail.
- A custom `useNarrowViewport()` hook watches `max-width: 991px` to switch between drawer-based navigation and collapsed rail.
- A `@media (max-width: 860px)` rule in `global.css` narrows the session panel from 260px to 200px.

### Accessibility baseline
`global.css` sets `color-scheme: dark`, a visible `:focus-visible` outline using `--accent`, and `overflow: hidden` on body to prevent scrollbars while the antd layout handles scrolling internally.

### Build-time version injection
`vite.config.ts` reads the repo root `VERSION` file and injects it as `__PLATFORM_VERSION__`, consumed by `src/version.ts` and displayed next to the "Luban AIOps" brand in the sidebar.

## Conventions and constraints

- **All colors flow through `tokens.ts` → `global.css` variables.** New palette entries must be added in both places; the comment in `tokens.ts` calls this out as a SPEC-023 requirement.
- **Bespoke styles use CSS custom properties, not hardcoded hex values.** Classes like `.session-item:hover { background: var(--surface-alt); }` demonstrate the convention.
- **Ant Design components are themed via `ConfigProvider` once at the root**, not per-component. Inline `style` props are reserved for layout overrides (widths, borders) rather than theming.
- **The app is dark-only**; there is no theme-switching logic.
- **CSS is flat and class-named** (no BEM, CSS Modules, or SCSS). Styles are grouped by feature area inside one file with section comments (e.g. `--- Chat workspace ---`, `--- Tool evidence groups ---`, `--- Sticky request banner ---`, `--- Shared view chrome ---`).
- **Responsive breakpoints are kept minimal**: rely on Ant Design's built-in `lg` breakpoint for the main layout shift, and add small `@media` rules only when needed (860px for the session panel).
- **Build output is immutable-cacheable**: `vite.config.ts` outputs to `../dist` with hashed filenames; `nginx.conf` serves `web-ui/dist` at `/`.