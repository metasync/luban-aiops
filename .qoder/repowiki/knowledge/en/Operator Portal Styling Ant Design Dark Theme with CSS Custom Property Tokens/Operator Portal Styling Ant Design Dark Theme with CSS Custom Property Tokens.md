---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Property Tokens'
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

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 18 + TypeScript application built with Vite. Visual styling is centered on **Ant Design v6** (`antd` and `@ant-design/x`) configured via the `ConfigProvider` theme API, paired with a small set of hand-authored CSS custom properties that mirror the design tokens so bespoke component styles stay on the same vocabulary as Ant Design's internal tokens.

There is no CSS-in-JS library (no styled-components, Emotion, etc.), no Tailwind, and no SCSS preprocessor — only plain `.css` imported from `main.tsx`. The build produces content-hashed static assets served by nginx at `/`.

## Key files and packages

- `app/package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, plus Vite/Vitest tooling.
- `app/src/theme/tokens.ts` — single source of truth for the palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `success`, `error`, `warning`, `codeBg`, `radius`) and the `portalTheme: ThemeConfig` passed to `antd`'s `ConfigProvider` using `darkAlgorithm`.
- `app/src/theme/global.css` — defines matching CSS custom properties under `:root` (`--bg`, `--surface`, `--accent`, …) plus all bespoke layout/typography rules for the app shell, chat transcript, evidence cards, approval inbox entries, markdown rendering, sticky request banners, and confirmation cards.
- `app/src/main.tsx` — bootstraps React, wraps the tree in `<ConfigProvider theme={portalTheme}>`, and imports `global.css` once.
- `app/src/App.tsx` — uses Ant Design `Layout`, `Menu`, `Drawer`, `Tag`, `Badge`, `Avatar`, `Typography` for the sidebar chrome; applies dark mode via antd's `theme="dark"` on `Layout.Sider` and `Menu`.
- `app/vite.config.ts` — builds into `../dist`, injects `__PLATFORM_VERSION__` from the root `VERSION` file, and proxies `/api` to `localhost:8080` during dev.

## Architecture and conventions

### Token layering
Design tokens live in one place (`tokens.ts`) and are consumed in two parallel ways:
1. **Ant Design components** receive them through `portalTheme.token` (e.g. `colorPrimary`, `colorBgBase`, `colorBorder`, `fontFamily`).
2. **Custom CSS** reads the same values via CSS custom properties declared in `global.css` (`var(--accent)`, `var(--surface)`, …).

The comment in `tokens.ts` states this is a verbatim port from the legacy portal's `:root` design tokens so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1). This dual-token approach lets new custom components use either `theme.colorPrimary` or `var(--accent)` interchangeably without drifting.

### Dark-first theme
`color-scheme: dark` is set globally, and `antd`'s `darkAlgorithm` is the only algorithm used. There is no light-mode toggle — the entire portal is dark-only.

### Layout and responsive strategy
- Desktop: a fixed-width `Layout.Sider` (230px) with an inline `Menu` provides navigation; it collapses to a 64px icon rail when toggled or when the viewport drops below antd's `lg` breakpoint (992px).
- Narrow viewports: a `Drawer` slides in the full labeled menu, driven by a `useNarrowViewport()` hook that watches `matchMedia("(max-width: 991px)")`. A pinned floating `mobile-menu-button` (`.mobile-menu-button`) stays visible at top-left across all widths.
- A second media query at `max-width: 860px` narrows the chat session panel from 260px to 200px.
- Motion preferences are respected via `@media (prefers-reduced-motion: reduce)` for the turn-arrival flash animation.

### Component styling patterns
- Views are wrapped in `.view-container` (with a `.view-container-flush` variant for chat) providing consistent padding and scroll behavior.
- Markdown content rendered inside transcripts uses a shared `.md-content` rule block (headings, lists, code blocks, tables, blockquotes) styled against the token variables.
- Domain-specific visual modules (chat transcript, evidence groups, HITL confirmation cards, approvals inbox entries, sticky request banners) each have their own class families scoped to `src/theme/global.css` rather than per-component CSS files.
- No CSS modules, BEM prefixes, or utility classes are used — class names are flat and descriptive (e.g. `.session-item`, `.confirm-card`, `.turn-group.turn-arrived`).

### Build-time versioning
The platform version string is injected at build time via `define: { __PLATFORM_VERSION__: ... }` in `vite.config.ts` and displayed in the sidebar brand alongside the title. This is enforced by the root `make validate-version` target referenced in the config comments.

## Conventions and constraints

- **Single theme entry point**: All theme configuration flows through `portalTheme` in `tokens.ts`; components must not hard-code color hex values directly — they should consume `theme.colorXxx` props or `var(--token)` CSS variables.
- **Dark-only**: No light-mode switch exists; `color-scheme: dark` and `darkAlgorithm` are applied globally.
- **CSS custom property parity**: Any new design token added to `tokens.ts` palette must be mirrored as a `--name` variable in `global.css` so both Ant Design and custom CSS can reference it.
- **Responsive breakpoints**: Use antd's built-in `breakpoint="lg"` on `Layout.Sider` and the `useNarrowViewport()` hook for drawer logic; avoid ad-hoc media queries unless extending existing ones in `global.css`.
- **Accessibility**: Focus outlines are preserved via a global `:focus-visible` rule (2px accent outline); motion-sensitive animations are gated behind `prefers-reduced-motion`.
- **No external style frameworks**: No Tailwind, Sass, CSS Modules, or CSS-in-JS libraries are present — adding one would require updating `package.json`, `vite.config.ts`, and the build pipeline.