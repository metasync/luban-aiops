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

The operator portal (`products/operator-portal/web-ui/app`) is a React 18 + TypeScript application built with Vite. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via a single dark `ThemeConfig` applied through `<ConfigProvider>` at the app root in `src/main.tsx`. There is no CSS-in-JS library, Tailwind, or SCSS pipeline — styling is plain CSS (imported as `./theme/global.css`) plus Ant Design's token-based theme overrides.

## Key files and packages

- `package.json` — declares `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 18, Vite 6, Vitest.
- `vite.config.ts` — builds to `../dist`, injects `__PLATFORM_VERSION__` from the repo root `VERSION` file; dev server proxies `/api` to `http://localhost:8080`.
- `src/main.tsx` — renders `<ConfigProvider theme={portalTheme}>` wrapping the entire app; imports `./theme/global.css` once.
- `src/theme/tokens.ts` — defines the design palette (`bg`, `surface`, `accent`, `success`, `error`, `warning`, `border`, `text`, `textMuted`, `codeBg`, `radius`) and maps it into an antd `ThemeConfig` using `darkAlgorithm`.
- `src/theme/global.css` — declares matching CSS custom properties under `:root` (`--bg`, `--surface`, `--accent`, etc.) so bespoke component styles consume the same tokens; also contains all layout, chat transcript, evidence cards, HITL confirmation cards, markdown rendering, view chrome, and a narrow-viewport media query.
- `src/App.tsx` — uses antd `Layout.Sider`/`Layout.Content` for the sidebar + content shell, `Menu` for navigation, `Drawer` for off-canvas mobile nav, and applies CSS classes like `app-shell`, `view-container`, `view-container-flush`, `sidebar-footer`, `mobile-menu-button` defined in `global.css`.

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` exports a `palette` object that is both fed into antd's `ThemeConfig` and mirrored verbatim as CSS custom properties in `global.css`'s `:root`. The comment in `tokens.ts` explicitly states this dual mapping keeps "antd components [and] bespoke styles [on] one vocabulary" (referenced by SPEC-023 R-1 dark theme).

2. **Dark-only theme**: `color-scheme: dark` is set on `:root`; antd is forced into `darkAlgorithm`; every antd menu/layout is rendered with `theme="dark"`. No light-mode toggle exists.

3. **Token-driven typography**: Font families are declared in the antd theme config (`Inter` stack for body, `JetBrains Mono` / `Fira Code` for code) and reused in CSS (e.g., `.md-content code`).

4. **Component-scoped CSS classes**: Bespoke UI pieces use BEM-like class names in `global.css` (`.session-panel`, `.chat-view`, `.evidence-card`, `.confirm-card`, `.turn-request-banner`, `.view-toolbar`, `.report-form`, `.incident-section`) rather than per-component CSS modules. These classes are referenced directly from JSX via `className`.

5. **Responsive strategy**: A single breakpoint at `max-width: 860px` narrows the session panel width; the app shell additionally listens to antd's `lg` breakpoint (992px) via `useNarrowViewport()` to switch between inline `Layout.Sider` and an off-canvas `Drawer` for navigation. A pinned `.mobile-menu-button` stays visible at every width.

6. **Build-time versioning**: The platform version string is injected at build time via Vite's `define` (`__PLATFORM_VERSION__`) and surfaced in the sidebar brand tag, keeping the UI in lockstep with the repository `VERSION` file.

7. **Spec-referenced style rules**: Many CSS sections are annotated with spec references (SPEC-019 R-1, SPEC-020 R-4, SPEC-023 R-1/R-3/R-5, SPEC-024), tying visual behavior to product specifications.

## Conventions and constraints

- All color values flow through the `palette` object in `tokens.ts`; new UI colors should be added there first and mirrored in `global.css` `:root` to keep antd and bespoke styles synchronized.
- Custom focus outlines use `outline: 2px solid var(--accent)` via the global `:focus-visible` rule — custom controls must not suppress focus indicators.
- Layout shells consistently use the `app-shell` class on the root `Layout`, and views wrap their content in either `view-container` (scrollable, padded) or `view-container-flush` (full-bleed, e.g., chat).
- Sidebar navigation items are grouped into `Control` and `Workspace` sections via antd `Menu` groups; group titles are hidden when the sider is collapsed and replaced by hairline dividers (see `.ant-layout-sider-collapsed .ant-menu-item-group`).
- Markdown and tool output rendering share a consistent code block style using `var(--code-bg)` and monospace fonts, applied to `.md-content pre/code` and `.evidence-pre`.
- Evidence groups and HITL confirmation cards follow fixed card shapes with `border: 1px solid var(--border)`, `border-radius: var(--radius)`, and `background: var(--surface)` to maintain visual parity across feature areas.