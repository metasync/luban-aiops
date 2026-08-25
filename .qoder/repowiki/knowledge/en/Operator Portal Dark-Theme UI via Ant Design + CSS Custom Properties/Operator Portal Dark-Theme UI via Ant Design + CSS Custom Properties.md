---
kind: frontend_style
name: Operator Portal Dark-Theme UI via Ant Design + CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/index.html
---

## What system/approach is used

The only frontend in this repository is the **Operator Portal** web UI under `products/operator-portal/web-ui/app/`. It is a **React 18 + TypeScript + Vite** application that styles itself with:

- **Ant Design (antd v6)** as the component library, configured globally via `<ConfigProvider theme={...}>` at the app root (`src/main.tsx`).
- A **dark-only theme** built on Ant Design's `darkAlgorithm`, with a custom `ThemeConfig` defined in `src/theme/tokens.ts`.
- **CSS custom properties (design tokens)** declared in `:root` inside `src/theme/global.css`, which mirror the values in `tokens.ts` so bespoke component styles and Ant Design components share one vocabulary. The comment in `tokens.ts` explicitly states they are "ported verbatim from the legacy portal's :root design tokens" and linked to SPEC-023 R-1 dark-theme requirement.
- No CSS-in-JS beyond Ant Design's token system; no Tailwind, Sass, or preprocessors — plain `.css` imported once from `main.tsx`.

There is no other frontend styling code in the repo; backend services are Python FastAPI apps with no embedded HTML/CSS.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares dependencies: `react`, `react-dom`, `antd`, `@ant-design/x`, `@ant-design/icons`, plus Vite/Vitest tooling.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the `palette` object and `portalTheme: ThemeConfig` (primary color, backgrounds, borders, text, success/error/warning, border radius, fonts).
- `products/operator-portal/web-ui/app/src/theme/global.css` — declares `:root` CSS variables (`--bg`, `--surface`, `--accent`, etc.), global resets, layout shell (`.app-shell`, sidebar, drawer), chat workspace layout, markdown rendering rules, evidence/HITL card styles, sticky request banner, and a narrow-viewport breakpoint at 860px.
- `products/operator-portal/web-ui/app/src/main.tsx` — bootstraps React, imports `portalTheme` and `global.css`, and wraps the app in `<ConfigProvider theme={portalTheme}>`.
- `products/operator-portal/web-ui/app/vite.config.ts` — build config: outputs to `../dist`, injects `__PLATFORM_VERSION__` from the repo `VERSION` file, proxies `/api` to `localhost:8080` for dev, and sets `color-scheme: dark` via the `define` block.
- `products/operator-portal/web-ui/app/index.html` — minimal HTML entry declaring `lang="en"`, viewport meta, and `color-scheme: dark`.

## Architecture and conventions

1. **Single source of truth for colors/fonts**: `tokens.ts` holds the canonical palette and font families; `global.css` mirrors them as CSS variables so non-Ant components can consume `var(--accent)`, `var(--surface)`, etc. This dual declaration is intentional per the comment referencing SPEC-023 R-1.
2. **Global theme injection**: All Ant Design components inherit the dark theme through the top-level `ConfigProvider`; individual components do not pass local themes.
3. **Bespoke styles use BEM-like class names** (e.g., `.session-panel`, `.session-item.active`, `.chat-messages`, `.confirm-card.pending`) scoped to feature areas rather than utility classes.
4. **Dark-only mode**: The app forces dark mode via three layers — `color-scheme: dark` in `index.html`, `color-scheme: dark` in `global.css` `:root`, and `algorithm: antdTheme.darkAlgorithm` in the Ant Design theme config. There is no light-mode toggle.
5. **Responsive strategy**: Layout adapts via CSS media queries (not responsive Ant Design props alone). The chat session panel narrows at `max-width: 860px`; the mobile menu button is pinned fixed at desktop breakpoints and the sidebar collapses into an off-canvas drawer below Ant Design's `lg` breakpoint (992px), as documented in the stylesheet comments.
6. **Build-time versioning**: `vite.config.ts` reads the repo root `VERSION` file and injects it as `__PLATFORM_VERSION__`, keeping the UI version in sync with the platform release.
7. **Markdown/evidence rendering**: Global `.md-content` rules style headings, lists, code blocks, tables, and links using the shared token variables, ensuring rendered content matches the portal palette.

## Conventions and constraints

- **All visual tokens flow through `src/theme/tokens.ts` and `:root` CSS variables** — new colors should be added to both places (the comment documents this mirroring requirement tied to SPEC-023 R-1).
- **Components must not hard-code color hex values**; they should reference Ant Design tokens (via `ConfigProvider` theme) or the CSS variables exposed by `global.css`.
- **The portal is dark-only**; there is no mechanism to switch themes, and all three layers (HTML, CSS, Ant Design) enforce `color-scheme: dark`.
- **Responsive behavior is CSS-driven**, not prop-driven: layout shifts are implemented with `@media (max-width: ...)` rules and Ant Design's built-in responsive Sider behavior, not with a separate design-system breakpoint map.
- **Build output is immutable**: Vite emits content-hashed filenames to `../dist` so nginx can cache assets aggressively while `index.html` stays uncached (documented in `vite.config.ts` comments referencing SPEC-023 R-1).
- **Accessibility baseline**: `:focus-visible` gets a 2px accent-colored outline with offset, applied globally to ensure keyboard focus is visible on custom controls.
- **No additional CSS framework**: The project does not use Tailwind, Sass, styled-components, or CSS modules — plain CSS coexists with Ant Design's token system.