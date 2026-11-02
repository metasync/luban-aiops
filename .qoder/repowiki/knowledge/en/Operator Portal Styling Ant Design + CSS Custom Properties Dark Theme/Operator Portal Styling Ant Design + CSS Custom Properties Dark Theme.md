---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System

The only frontend in the repository is the **operator-portal** SPA under `products/operator-portal/web-ui/app/`. It is a React 19 / TypeScript application built with Vite and styled primarily through:

- **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library.
- A single global stylesheet `app/src/theme/global.css` (739 lines) defining CSS custom properties on `:root` plus layout, chat, evidence, HITL confirmation card, and markdown styles.
- A TypeScript theme definition `app/src/theme/tokens.ts` that maps the same palette into an Ant Design `ThemeConfig` using `darkAlgorithm`.

There is no Tailwind, Sass/Less pipeline, CSS-in-JS library, or design-token generator — tokens are hand-maintained in two places that mirror each other by comment.

## Key files

- `products/operator-portal/web-ui/app/package.json` — declares antd ^6.6.2, @ant-design/icons ^6.0.0, @ant-design/x ^2.9.0, react ^19.2.8; build via `vite build`, test via `vitest run`.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the `palette` object and `portalTheme: ThemeConfig` (dark algorithm, primary/accent/surface/border/text tokens, `Inter` + JetBrains Mono font stack).
- `products/operator-portal/web-ui/app/src/theme/global.css` — `:root` CSS custom properties mirroring `tokens.ts`, base resets, `.app-shell` sidebar layout, `.chat-view` session+transcript layout, `.md-content` prose rules, evidence cards, sticky request banner, HITL confirmation cards, bounded-pane panes, and a narrow-viewport media query at 860px.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` directory.

## Architecture and conventions

1. **Single source of truth is the TS palette; CSS variables are kept in sync manually.** The comment in `tokens.ts` states the palette was "ported verbatim from the legacy portal's :root design tokens" and that `global.css` mirrors it so bespoke styles and antd components share one vocabulary. There is no tooling enforcing this synchronization — it is a developer convention.

2. **Dark theme is the only theme.** `color-scheme: dark` is set on `:root`; `portalTheme.algorithm = antdTheme.darkAlgorithm` applies the same scheme to Ant Design. No light-mode toggle exists.

3. **Design tokens flow two ways:**
   - Ant Design components consume `portalTheme` via Antd's `ConfigProvider` (the `ThemeConfig` sets `colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBorder`, `colorText`, `borderRadius`, fonts).
   - Hand-written CSS consumes `--bg`, `--surface`, `--accent`, `--border`, `--text`, `--radius`, etc. defined on `:root`.

4. **Layout uses Ant Design Layout + bespoke CSS.** The app shell is an `ant-layout-sider` sidebar with a pinned mobile-menu button, collapsed icon rail, and drawer fallback below the `lg` breakpoint (992px). Chat views use a fixed-width `.session-panel` (260px, 200px at ≤860px) next to a flex column transcript.

5. **Component-scoped CSS classes live in `global.css`, not per-component stylesheets.** Classes such as `.chat-view`, `.session-item`, `.confirm-card`, `.evidence-card`, `.turn-request-banner`, `.digest-bounded`, `.prose-bounded` are flat BEM-style names in one file.

6. **Responsive strategy is minimal.** Only two breakpoints exist: the Ant Design `lg` breakpoint (992px) referenced in comments for the Sider auto-collapse, and a custom `@media (max-width: 860px)` that narrows the session panel. No fluid typography or grid system beyond Flexbox.

7. **Accessibility touches are explicit but sparse:** `:focus-visible` outline uses `--accent`, `prefers-reduced-motion` disables the turn-arrival animation, and comments call out keyboard focus requirements for custom controls.

8. **Markdown rendering gets its own style block** (`.md-content h1..h6`, `pre`, `blockquote`, `table`) ported from the legacy portal, with code blocks capped at 280px height.

## Conventions and constraints

- **Token parity between `tokens.ts` and `global.css` is documented but not enforced.** The comment in `tokens.ts` says the CSS custom properties "mirror these so bespoke styles and antd components stay on one vocabulary (SPEC-023 R-1 dark theme)". There is no lint rule, script, or type assertion that verifies the two lists match.
- **All visual values go through the shared palette.** Components reference `var(--*)` CSS variables rather than hard-coded hex values in `global.css`; Ant Design components receive colors via `portalTheme.token`.
- **The build injects dependency versions into the UI.** `vite.config.ts` reads `package-lock.json` and `package.json` to define `__REACT_VERSION__` and `__ANTD_VERSION__` constants consumed by the Settings view (documented in the config comment referencing SPEC-023 R-1).
- **Output goes to `../dist`** so the sibling `nginx.conf` can serve it as `/` without a separate web server step.
- **No responsive framework or utility CSS class library is used.** Layout is achieved with Flexbox and a handful of named classes in `global.css`.
- **Tests cover component behavior, not styles.** Vitest runs under jsdom; there are no visual regression tests or CSS-specific assertions visible.