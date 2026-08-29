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

The only frontend in this repository is the **operator-portal web UI** under `products/operator-portal/web-ui/app/`. It is a React 19 + TypeScript application built with Vite and styled primarily through **Ant Design v6** (`antd` + `@ant-design/icons` + `@ant-design/x`). Visual consistency is achieved by:

- A single Ant Design `ThemeConfig` (`src/theme/tokens.ts`) that enables the `darkAlgorithm` and maps design tokens (colors, border radius, fonts) to a fixed palette.
- A parallel set of CSS custom properties in `src/theme/global.css` that mirror the same palette so bespoke component styles can consume the same vocabulary without importing the TS tokens.
- Global base styles in `global.css` that set `color-scheme: dark`, apply the font stack, and define layout chrome (app shell, sidebar, chat transcript, evidence panels, HITL confirmation cards).

There is no Tailwind, Sass, or CSS-in-JS library beyond what Ant Design ships. No separate theme files exist per view — all styling lives in one global stylesheet plus inline `style` props on a few Ant components.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `dayjs`; dev deps include `vite`, `vitest`, `@vitejs/plugin-react`, `typescript`.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving.
- `products/operator-portal/web-ui/app/src/main.tsx` — root entry that wraps `<App />` in `<ConfigProvider theme={portalTheme}>` and imports `./theme/global.css`.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the `palette` object and `portalTheme` `ThemeConfig` (dark algorithm, primary/surface/border/text colors, `Inter` + `JetBrains Mono` font families, `borderRadius: 8`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — `:root` CSS variables mirroring the palette, app-shell layout, chat workspace, markdown rendering, evidence groups, sticky request banner, HITL confirmation cards, responsive breakpoints, and shared view chrome classes.
- `products/operator-portal/web-ui/app/src/App.tsx` — uses Ant Design `Layout`, `Menu`, `Drawer`, `Tag`, `Avatar`, `Alert`, `Spin` to compose the sidebar + content area; applies the `lg` breakpoint (992px) for collapsible Sider behavior.

## Architecture and conventions

1. **Single source of truth for colors**: The `palette` constant in `tokens.ts` is the canonical definition. `portalTheme` feeds it into Ant Design's token system, and `global.css` re-declares the same hex values as CSS custom properties (`--bg`, `--surface`, `--accent`, etc.) so non-Ant components stay on-brand.

2. **Dark-only theme**: `color-scheme: dark` is declared globally; the Ant Design theme uses `darkAlgorithm`; there is no light-mode toggle or conditional theme switching.

3. **Typography**: Font families are centralized in the Ant Design theme config (`Inter` sans-serif, `JetBrains Mono` / `Fira Code` monospace). Markdown-rendered content inherits these via `.md-content code` rules.

4. **Responsive strategy**: Uses Ant Design's built-in `breakpoint="lg"` on `Layout.Sider` (992px) to auto-collapse the inline sidebar into a 64px icon rail. Below that width, a `Drawer` provides an off-canvas menu, driven by a `useNarrowViewport()` hook that listens to `(max-width: 991px)`. A secondary media query at `860px` narrows the session panel from 260px to 200px.

5. **Accessibility**: Focus outlines use `:focus-visible` with the accent color; mobile menu button exposes `aria-label` toggling between "Open navigation" and "Hide navigation"; reduced-motion preference disables the turn-arrival flash animation.

6. **Build-time versioning**: `vite.config.ts` reads the repo root `VERSION` file and locks dependency versions from `package-lock.json`, injecting them as constants so the Settings view can display the exact shipped tech stack.

7. **Spec-driven style changes**: Many comments in `global.css` and `App.tsx` reference SPEC numbers (e.g., SPEC-023 R-1 dark theme, SPEC-019 R-1 grouping, SPEC-034 R-1 arrival highlight, SPEC-037 R-6 signed-execution receipts, SPEC-041 R-3 bounded panes), tying visual decisions to tracked specs rather than ad-hoc changes.

## Conventions and constraints

- All new UI colors must be added to the `palette` object in `src/theme/tokens.ts` and mirrored as a `--name` CSS variable in `:root` in `global.css`; the comment explicitly states the two locations must stay synchronized.
- Ant Design components receive the theme via the top-level `ConfigProvider`; individual components should not override colors inline unless necessary.
- Bespoke styles should consume CSS custom properties (`var(--bg)`, `var(--accent)`, `var(--radius)`) rather than hardcoding hex values, keeping them consistent with Ant Design tokens.
- The app is dark-only; no light-theme path exists.
- Responsive behavior relies on Ant Design's `lg` breakpoint (992px) plus the custom `860px` breakpoint in `global.css`; new responsive rules should follow the same pattern.
- Build artifacts go to `web-ui/dist` and are served by nginx at `/`; content-hashed filenames enable immutable caching while `index.html` stays no-store (as noted in the vite config comment referencing SPEC-023 R-1).
- There is no component-scoped CSS or CSS modules; all styles are global, so class names should be sufficiently scoped (e.g., `.session-item`, `.confirm-card`, `.evidence-card`) to avoid collisions.