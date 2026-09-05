---
kind: frontend_style
name: 'Operator Portal Frontend Style: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 + TypeScript SPA built with Vite and styled using **Ant Design v6** in dark mode. There is no CSS-in-JS library beyond Antd's built-in theme engine; bespoke styles live in a single global stylesheet (`app/src/theme/global.css`). The design token system is two-layered:

1. A TypeScript `palette` object in `app/src/theme/tokens.ts` defines the canonical color palette, radius, and font families.
2. That same palette is mirrored into CSS custom properties on `:root` (e.g. `--bg`, `--surface`, `--accent`, `--text-muted`, `--radius`) so that both Antd components and hand-written CSS consume one vocabulary.

The Antd theme is configured via `ThemeConfig` with `antdTheme.darkAlgorithm` and maps palette values to Antd tokens (`colorPrimary`, `colorBgBase`, `colorBorder`, etc.). Fonts are set through Antd's `fontFamily` / `fontFamilyCode` tokens, while markdown-rendered content uses matching fonts directly in CSS.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite 8, Vitest.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radii, and fonts; exports `portalTheme: ThemeConfig`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — all bespoke UI styles, scoped under BEM-style class names (`.app-shell`, `.session-panel`, `.chat-view`, `.md-content`, `.confirm-card`, `.turn-request-banner`, etc.) and driven by CSS custom properties.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs hashed assets to `../dist` served by nginx.

## Architecture and conventions

- **Dark-only theme.** `color-scheme: dark` is set globally; there is no light-mode toggle or conditional theme logic observed in the codebase.
- **Token mirroring.** Comments in `tokens.ts` explicitly state that CSS custom properties mirror the TS palette so "bespoke styles and antd components stay on one vocabulary" (SPEC-023 R-1). Changes to the palette should be made in `tokens.ts`; the CSS variables are kept in sync manually.
- **BEM-like class naming.** Styles use descriptive block/element classes (`.session-item`, `.session-item-title`, `.approvals-entry-header`, `.digest-bounded .ant-tabs-body-holder`) rather than component-scoped CSS modules or CSS-in-JS. Global scope is accepted because the app is small and the stylesheet is intentionally centralized.
- **Responsive strategy via CSS media queries.** Breakpoints are inline: `@media (max-width: 860px)` collapses the session panel width; the sidebar uses Antd's responsive `Sider` behavior plus a pinned `.mobile-menu-button` drawer trigger below `lg` (992px).
- **Accessibility hooks baked into CSS.** `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion` disables the turn-arrival flash animation; keyboard focus is explicitly preserved on custom controls.
- **Markdown rendering theming.** A dedicated `.md-content` rule set styles headings, lists, code blocks, tables, and links using the shared CSS variables, keeping rendered user content visually consistent with the shell.
- **Feature-scoped style regions.** The stylesheet groups rules by feature with comments referencing spec requirements (e.g. `SPEC-011 R-4 parity`, `SPEC-020 R-4`, `SPEC-034 R-1 / SPEC-035 R-4`, `SPEC-037 R-6`, `SPEC-039 R-8`, `SPEC-041 R-3`), tying visual changes back to product specs.

## Conventions and constraints

- **Use Antd components as the base UI surface.** All interactive elements go through Antd (`Layout`, `Menu`, `Tabs`, `Collapse`, `Typography`, `Modal`, etc.); bespoke CSS only augments layout, spacing, and brand-specific visuals.
- **Never hard-code colors in components.** Colors must come from CSS custom properties (`var(--accent)`, `var(--surface)`, `var(--border)`, …) defined in `global.css`, which themselves derive from `tokens.ts`.
- **Radius and spacing follow the token.** `border-radius: var(--radius)` (8px) is reused across cards, inputs, and badges; padding/margins are expressed in px but consistently paired with the tokenized colors.
- **Monospace font for code/evidence.** Code blocks, tool names, and evidence output use `"JetBrains Mono", "Fira Code", monospace` both in Antd's `fontFamilyCode` token and in `.md-content code` / `.tool-name` selectors.
- **Build-time version injection is part of the shipped UI.** `vite.config.ts` embeds the platform version and locked dependency versions so the Settings view can display an accurate tech stack table — this is enforced by the root `make validate-version` target referenced in the config comment.
- **Assets are immutable-cacheable.** The Vite build emits content-hashed filenames to `../dist`, served by nginx with `index.html` cached as no-store per the config comment (SPEC-023 R-1).

No other frontend styling systems exist in this repository; all backend services are Python microservices without embedded UIs.