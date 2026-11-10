---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## What system/approach is used

The only frontend in the repository lives under `products/operator-portal/web-ui/app/`. It is a **React 19 + Vite** application built with **TypeScript**, styled via:

- **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library.
- A single global stylesheet `app/src/theme/global.css` for bespoke layout, animation, and domain-specific UI (chat transcript, HITL confirmation cards, evidence groups, session sidebar).
- A design-token layer in `app/src/theme/tokens.ts` that defines the palette and an Ant Design `ThemeConfig` using `darkAlgorithm`.
- CSS custom properties on `:root` (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--radius`, …) consumed by both the bespoke CSS and mirrored from the JS tokens.

There is no Tailwind, Sass/Less, CSS Modules, or CSS-in-JS beyond Ant Design's own token system. Responsive behavior is handled through Ant Design's built-in breakpoints (e.g. `lg` at 992px where the `Sider` auto-collapses) plus one small `@media (max-width: 860px)` rule in `global.css` that narrows the session panel.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares React 19, Ant Design 6.x, Vite 8, Vitest, TypeScript ~5.9.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radius, fonts, and the `portalTheme: ThemeConfig` passed to Ant Design.
- `products/operator-portal/web-ui/app/src/theme/global.css` — all bespoke stylesheets (739 lines); contains app shell, chat workspace, markdown rendering, evidence groups, sticky request banner, HITL confirmation cards, and shared view chrome.
- `products/operator-portal/nginx.conf` — serves the built static assets at `/`.

## Architecture and conventions

1. **Dual vocabulary for design tokens.** `tokens.ts` exports a `palette` object and maps it onto Ant Design's `ThemeConfig.token`. The same hex values are redeclared as CSS custom properties in `global.css`'s `:root`. The comment in `tokens.ts` states this is "ported verbatim from the legacy portal's :root design tokens" so bespoke styles and Ant Design components share one vocabulary. This is documented as part of SPEC-023 R-1 dark theme.

2. **Dark-only theme.** `color-scheme: dark` is set on `:root`; `portalTheme.algorithm` uses `antdTheme.darkAlgorithm`. No light-theme toggle exists in the codebase.

3. **Global CSS, not scoped modules.** All bespoke styles live in one file (`global.css`). Components import it directly rather than using CSS Modules or CSS-in-JS. Class names follow a flat BEM-like convention (`.session-item`, `.turn-group`, `.confirm-card`, `.evidence-card`, `.view-toolbar`, etc.).

4. **SPEC-driven style gates.** Many rules are annotated with their originating spec, e.g. `/* --- Chat workspace (SPEC-023 R-3) --- */`, `/* SPEC-034 R-1 / SPEC-035 R-4: arrival highlight… */`, `/* SPEC-020 R-4 */`, `/* SPEC-037 R-6 */`, `/* SPEC-063 R-5a */`, `/* SPEC-041 R-3, v0.25.1 polish */`. This ties visual decisions back to the specification compendium.

5. **Responsive strategy.** Relies on Ant Design's responsive Sider (auto-collapses below `lg` = 992px). A pinned `.mobile-menu-button` appears at `top: 12px; left: 12px` when the sidebar folds, opening an off-canvas drawer instead. One narrow-viewport override at `860px` shrinks the session panel width.

6. **Accessibility basics baked into the stylesheet.** `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion: reduce` disables the turn-arrival flash animation; semantic `<summary>` elements are used for native expanders inside confirmation cards.

7. **Build-time version injection.** `vite.config.ts` reads the root `VERSION` file and the lockfile to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants, so the Settings view can display the exact shipped tech stack.

## Conventions and constraints

- **Design tokens are single-sourced in `tokens.ts` and mirrored into CSS custom properties in `global.css`.** The mirror is intentional so bespoke CSS and Ant Design consume the same palette (documented in `tokens.ts` comments referencing SPEC-023 R-1).
- **All bespoke styling goes in `global.css`; there are no per-component CSS files, no SCSS, no Tailwind config, and no CSS Modules.** Observed across every class in the file.
- **The portal is dark-only.** Both `color-scheme: dark` and `antdTheme.darkAlgorithm` enforce this; no alternate theme configuration exists.
- **Style rules are traced to specs.** Comments like `SPEC-023 R-1`, `SPEC-020 R-4`, `SPEC-037 R-6`, `SPEC-063 R-5a`, `SPEC-041 R-3` tie visual changes to numbered requirements.
- **Bounded panes use a CSS variable `--bounded-pane-max-height`** set by the view wrapper and consumed by `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body` to constrain scrollable regions (see `global.css` lines 723–738).
- **Code blocks and monospace text consistently use `"JetBrains Mono", "Fira Code", monospace`**, declared in both `tokens.ts` (`fontFamilyCode`) and the `.md-content code` / `.tool-name` selectors.
- **The build output is immutable-cacheable:** `outDir: "../dist"` with content-hashed filenames, served by nginx (per the `vite.config.ts` comment referencing SPEC-023 R-1).
- **No other product directory contains frontend styling.** The remaining seven Python services have no CSS/HTML/JS; the operator portal is the sole frontend.