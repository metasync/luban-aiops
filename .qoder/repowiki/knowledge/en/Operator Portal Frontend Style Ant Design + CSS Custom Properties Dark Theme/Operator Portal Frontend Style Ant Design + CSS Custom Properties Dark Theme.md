---
kind: frontend_style
name: 'Operator Portal Frontend Style: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/src/chat/ChatView.tsx
---

# Operator Portal Frontend Style

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a **React 19 + Vite** single-page application styled with **Ant Design 6** as the component library, augmented by `@ant-design/x` for chat-specific primitives. The visual theme is a **dark-only palette** defined in a single source of truth and propagated through two parallel channels:

1. **Ant Design `ThemeConfig`** — `src/theme/tokens.ts` builds an `antd` `ThemeConfig` using `darkAlgorithm`, mapping a local `palette` object to antd tokens (`colorPrimary`, `colorBgBase`, `colorBorder`, `fontFamily`, etc.).
2. **CSS custom properties on `:root`** — `src/theme/global.css` declares the same palette as CSS variables (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--success`, `--error`, `--warning`, `--radius`, …) so bespoke styles and antd components stay on one vocabulary (documented as SPEC-023 R-1 dark theme).

There is no Tailwind, SCSS, or CSS-in-JS beyond the inline `style` attributes used sparingly; styling is a flat combination of Ant Design's built-in classes and hand-authored BEM-style `.css` selectors.

## Key files and packages

| File | Role |
|---|---|
| `app/package.json` | Declares `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `vite`, `vitest`, `dayjs` |
| `app/vite.config.ts` | Injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to localhost:8080 in dev |
| `app/src/theme/tokens.ts` | Single design-token source: `palette` + `portalTheme` (`ThemeConfig`) |
| `app/src/theme/global.css` | Global base styles, CSS custom properties, layout shell, chat/evidence/HITL card/markdown/document panes, responsive rules |
| `app/src/main.tsx` | Wires `<ConfigProvider theme={portalTheme}>` around the app root |
| `app/src/App.tsx` | Uses antd `Layout`, `Menu`, `Drawer`, `Tooltip`, `Tag`, `Typography` for the sidebar shell and navigation |
| `app/src/chat/ChatView.tsx` | Heaviest consumer of custom CSS classes (`evidence-*`, `confirm-card*`, `turn-group`, `composer-selection-bar`, `agent-working`, `turn-request-banner`) |
| `nginx.conf` (product root) | Serves the built `web-ui/dist` at `/` |

## Architecture and conventions

- **Design token discipline**: All colors, spacing radii, and fonts are declared once in `tokens.ts` and mirrored into `global.css` `:root` variables. New UI elements should consume `var(--*)` rather than hard-coded hex values so the palette stays consistent across antd components and bespoke DOM nodes.
- **Dark-only mode**: `color-scheme: dark` is set globally; there is no light-mode toggle. The comment in `global.css` explicitly ties this to SPEC-023 R-1.
- **Component library usage**: Every view imports directly from `antd` (`Button`, `Table`, `Tabs`, `Modal`, `Alert`, `Spin`, `Pagination`, `Collapse`, `Statistic`, `Row`, `Col`, `Select`, `Typography`, `Tag`, `Tooltip`). Components are composed from these primitives rather than wrapped in higher-level abstractions.
- **Custom class naming**: Bespoke styling uses lowercase dot-prefixed CSS classes (`.session-panel`, `.chat-view`, `.evidence-card`, `.confirm-card`, `.approvals-entry`, `.view-toolbar`, `.digest-bounded`, `.prose-bounded`) that mirror the semantic region they style. These are applied via `className="..."` on JSX fragments.
- **Responsive strategy**: A single `@media (max-width: 860px)` breakpoint narrows the session panel; the mobile menu button (`.mobile-menu-button`) toggles an off-canvas drawer below the antd `lg` breakpoint where the `Sider` auto-collapses. No grid framework is used — Flexbox drives the layout.
- **Accessibility baseline**: `:focus-visible` gets a 2px accent outline; `aria-hidden="true"` is used on decorative spacer divs; `prefers-reduced-motion` disables the turn-arrival flash animation.
- **Build-time versioning**: `vite.config.ts` reads the repo root `VERSION` file and injects `__PLATFORM_VERSION__` so the Settings view can display the exact shipped platform version alongside locked dependency versions read from `package-lock.json`.

## Conventions and constraints

- **All theme values flow through `tokens.ts`**: new colors must be added to both the `palette` object and the corresponding `:root` CSS variable in `global.css` (the comment explicitly states they "mirror each other").
- **Bespoke styles use CSS variables, not raw colors**: code blocks, borders, backgrounds, and text colors reference `var(--code-bg)`, `var(--border)`, `var(--surface)`, `var(--text)`, `var(--text-muted)`, `var(--accent)`, etc., keeping them theme-consistent.
- **Fixed-height bounded panes**: scrollable content regions (evidence pre blocks, document digest tabs, prose collapse bodies) cap height via a shared `--bounded-pane-max-height` CSS custom property applied on wrapper elements, then overflow-y auto on the child container (see `.evidence-pre`, `.digest-bounded .ant-tabs-body-holder`, `.prose-bounded .ant-collapse-body`).
- **Chat transcript layout is rigidly structured**: messages live in `.chat-messages`, evidence groups in `.evidence-turn`, confirmation cards in `.confirm-card`, and the composer in `.chat-composer`; new UI must slot into this existing DOM shape rather than introducing a parallel structure.
- **No per-component CSS modules or scoped styles**: styling is global CSS; class names must be sufficiently specific to avoid collisions across views.
- **Testing setup**: Vitest runs in `jsdom` with a setup file at `src/test/setup.ts`; tests co-locate under `__tests__/` next to their source modules.