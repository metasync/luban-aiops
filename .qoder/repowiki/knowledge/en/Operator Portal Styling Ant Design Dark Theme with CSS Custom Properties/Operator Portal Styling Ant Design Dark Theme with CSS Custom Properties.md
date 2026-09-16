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
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 + TypeScript SPA built with **Vite** and styled primarily through the **Ant Design v6** component library. A single dark theme is enforced across the entire application — there is no light-mode toggle. The styling approach combines:

- **Ant Design `ConfigProvider`** wrapping the app root, configured via a `ThemeConfig` object that maps Ant tokens to a custom palette.
- **CSS custom properties (design tokens)** declared in `:root` so both bespoke styles and Ant components consume one vocabulary.
- **Scoped global CSS** under `app/src/theme/global.css` for layout shell, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, and responsive behavior.
- **Tailwind-like utility classes are not used**; all visual rules live in the single global stylesheet or as inline style objects where needed.

## Key files and packages

- `app/package.json` — declares dependencies: `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite 8, Vitest.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` in dev.
- `app/src/main.tsx` — mounts React inside an Ant `ConfigProvider` that receives the theme config.
- `app/src/theme/tokens.ts` — defines the canonical `palette` object (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and the `portalTheme: ThemeConfig` mapping those values into Ant Design's token surface (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBgElevated`, `colorBorder`, `colorText`, `colorTextSecondary`, `colorSuccess`, `colorError`, `colorWarning`, `borderRadius`, `fontFamily`, `fontFamilyCode`). Uses `antd.darkAlgorithm`.
- `app/src/theme/global.css` — single source of truth for design tokens as CSS variables (`--bg`, `--surface`, `--accent`, etc.), base resets, the full-height app shell, sidebar/folded-rail behavior, chat session panel, transcript, composer selection bar, turn-group arrival animation, tool evidence groups, sticky request banner, HITL confirmation cards, markdown content styling, view toolbar, bounded panes, and an `860px` breakpoint that narrows the session panel.
- `nginx.conf` (at `products/operator-portal/`) serves the built `web-ui/dist` at `/`.

## Architecture and conventions

1. **Single dark theme, no switch.** `global.css` sets `color-scheme: dark` on `:root`. The Ant Design theme uses `darkAlgorithm`, and every token in `tokens.ts` is a dark-surface color.
2. **Dual token sync between TS and CSS.** The comment in `tokens.ts` states the palette was "ported verbatim from the legacy portal's :root design tokens" and that CSS custom properties mirror the TS constants so "bespoke styles and antd components stay on one vocabulary." Every color/radius value appears in both `palette` and the `:root` block of `global.css`.
3. **Ant Design is the UI primitive layer.** All views import directly from `antd` (`Layout`, `Menu`, `Sider`, `Table`, `Button`, `Modal`, `Tag`, `Typography`, `Tabs`, `Collapse`, `Statistic`, `Alert`, `Spin`, `Pagination`, `Select`, `Segmented`, `Tooltip`, `Col`, `Row`, `type TableColumnsType`, etc.). No third-party UI kit competes with it.
4. **Global CSS owns layout chrome, not per-component CSS modules.** There are no `.module.css` files. Layout pieces like `.app-shell`, `.sidebar-footer`, `.mobile-menu-button`, `.session-panel`, `.chat-view`, `.view-container`, `.view-toolbar`, `.digest-bounded`, `.prose-bounded` are defined once in `global.css` and reused by many components.
5. **Responsive strategy is CSS-media-query based**, centered on a single `max-width: 860px` breakpoint that shrinks the session panel width. The sidebar also has documented behavior for folding into an off-canvas drawer below antd's `lg` breakpoint (992px), implemented via the mobile menu button class.
6. **Bounded panes use a CSS variable convention.** Views set `--bounded-pane-max-height` on wrapper elements; `global.css` applies `max-height` to `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body` so structural chrome stays pinned while content scrolls.
7. **Build-time version injection ties the UI to platform releases.** `vite.config.ts` reads the repo-level `VERSION` file and the lockfile to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`, which appear in the Settings view's tech-stack table.

## Conventions and constraints

- **All colors must come from the shared palette.** New hues should be added to both `tokens.ts` `palette` and the `:root` block in `global.css` so Ant Design and bespoke CSS stay synchronized. This is enforced by the explicit comment in `tokens.ts` referencing SPEC-023 R-1 dark theme.
- **Custom focus indicators are mandatory.** `:focus-visible` is globally overridden to a 2px accent outline with 2px offset, ensuring keyboard navigation remains visible on custom controls.
- **Code blocks and preformatted output use monospace fonts** (`JetBrains Mono`, `Fira Code`) consistently across markdown-rendered content and evidence panels, matching the `fontFamilyCode` token.
- **Transcript/evidence content is height-bounded.** Pre blocks and evidence panels cap at `max-height: 280px` with internal scrolling so long tool results do not push messages out of view.
- **Turn arrivals get a timed highlight.** Turn groups that receive new content after an external decision add the `.turn-arrived` class, triggering a 4s background fade plus an inset accent border; `prefers-reduced-motion` disables the animation and leaves a muted tint.
- **Sidebar grouping switches to hairline dividers when collapsed.** Group titles are hidden in `.ant-layout-sider-collapsed` and replaced with top borders to avoid truncated labels.
- **Markdown rendering follows a fixed rule set.** Headings are accent-colored, links use the accent color, tables inherit border/text tokens, and code blocks use the `code-bg` token with rounded corners.
- **HITL confirmation cards follow a card-based layout** with `.confirm-card`, pending state via `.confirm-card.pending` (warning border), and nested `.confirm-call`, `.confirm-call-details`, `.confirm-note`, and signed-execution receipt rows (SPEC-020 R-4 / SPEC-037 R-6).
- **No Tailwind, CSS-in-JS, or CSS modules** are present in this project; adding one would break the established single-style-sheet + Ant Design token pattern.