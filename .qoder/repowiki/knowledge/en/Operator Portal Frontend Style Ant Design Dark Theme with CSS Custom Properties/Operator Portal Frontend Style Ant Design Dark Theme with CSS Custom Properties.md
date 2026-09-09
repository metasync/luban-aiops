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
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 + TypeScript SPA built with Vite. Styling is centered on **Ant Design v6** using its `ConfigProvider` theme API, combined with a hand-authored dark theme and a shared set of CSS custom properties that act as the single source of truth for colors, spacing, and typography.

There is no CSS-in-JS library, Tailwind, or SCSS pipeline — styling is plain CSS imported once in `src/main.tsx`, plus inline styles only where component props require it (e.g. antd `Layout.Sider` border). The build target is a static bundle served by nginx from `dist/`.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite, Vitest.
- `app/src/theme/tokens.ts` — defines the `palette` object and `portalTheme: ThemeConfig` fed into antd's `darkAlgorithm`. Colors are ported verbatim from the legacy portal's `:root` tokens (see comment referencing SPEC-023 R-1).
- `app/src/theme/global.css` — defines `:root` CSS custom properties mirroring `tokens.ts` exactly, plus all bespoke layout/component styles (chat transcript, session panel, approvals inbox, markdown rendering, evidence cards, sticky request banner, HITL confirmation cards, bounded panes, responsive breakpoints).
- `app/src/main.tsx` — root entry that wraps the app in `<ConfigProvider theme={portalTheme}>` and imports `global.css`.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `http://localhost:8080` in dev.
- `app/src/App.tsx` — antd `Layout` shell with `Sider` (width 230, collapsedWidth 64, breakpoint `lg`), drawer-based navigation on narrow viewports, and role-gated menu sections.

## Architecture and conventions

### Single token source, two consumers
`tokens.ts` and `global.css` share an identical palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `success`, `error`, `warning`, `codeBg`, `radius`). Ant Design components consume the values via the `ThemeConfig` token map; bespoke CSS classes consume them via CSS variables (`var(--accent)`, `var(--surface)`, etc.). This dual consumption keeps third-party antd components and hand-written styles visually consistent without coupling them.

### Dark-only theme
`:root { color-scheme: dark; }` forces the browser's native UI (scrollbars, selection) into dark mode. There is no light-mode toggle — the entire portal ships dark.

### Typography
Font families are declared in both places:
- antd `ThemeConfig.token.fontFamily` / `fontFamilyCode` in `tokens.ts`
- `body` font-family and `.md-content code` / `.tool-name` monospace rules in `global.css`
Both use Inter/system fonts for prose and JetBrains Mono/Fira Code for code.

### Layout model
A fixed-width left `Layout.Sider` (230px, collapses to a 64px icon rail) plus a scrollable content area. On narrow viewports (`max-width: 991px`, matching antd's `lg` breakpoint), the sidebar becomes a left-placed `Drawer` while the 64px rail stays pinned via a floating `.mobile-menu-button` button. Session list panels use a fixed width (260px, shrinking to 200px below 860px) with a full-height chat column beside them.

### Component-scoped CSS
Bespoke styles live in one file under semantic class names (`session-panel`, `chat-view`, `turn-group`, `confirm-card`, `approvals-entry`, `evidence-card`, `view-container`, `view-toolbar`, `digest-bounded`, `prose-bounded`). There is no per-component stylesheet; the convention is to scope each visual region with a BEM-like prefix so the global file remains navigable.

### Responsive strategy
Breakpoints are ad-hoc media queries rather than a design-token-driven system:
- `991px` drives the Sider collapse / drawer switch.
- `860px` shrinks the session panel.
- `prefers-reduced-motion: reduce` disables the 4-second turn-arrival flash animation.
No fluid typography or container queries are used.

### Accessibility signals
- `:focus-visible` gets a 2px accent outline with offset.
- ARIA labels are attached to the mobile menu button and login/logout buttons.
- Keyboard focus visibility is explicitly preserved on custom controls.

### Build-time versioning
`vite.config.ts` reads the repo root `VERSION` and the lockfile to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants, which surface in the Settings view's platform inventory table.

## Conventions and constraints

- **Colors must come from the shared palette.** New hues should be added to both `tokens.ts` and `global.css` `:root` before being consumed anywhere else.
- **All antd components must be wrapped in the root `ConfigProvider` with `portalTheme`.** Inline overrides are discouraged; antd's `theme` token map is the intended customization point.
- **Custom CSS uses CSS variables, not hard-coded hex literals.** Bespoke selectors reference `var(--accent)`, `var(--surface)`, `var(--border)`, `var(--radius)` to stay in sync with the theme.
- **Dark mode is mandatory.** No light-theme branch exists; `color-scheme: dark` is enforced at the root.
- **Responsive behavior follows antd's `lg` breakpoint (992px)** for switching between inline sidebar and off-canvas drawer, as documented in `App.tsx` comments.
- **Bounded panes** (documents digest tabs, prose collapse bodies) use a CSS variable `--bounded-pane-max-height` set on the wrapper element, with max-height applied via `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body`.
- **Animations respect reduced motion.** The turn-arrival flash animation is disabled when `prefers-reduced-motion: reduce` matches.
- **Build artifacts go to `web-ui/dist`**, hashed for immutable caching, served by nginx from `/` per the config comments.