---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
---

# Operator Portal Frontend Style

## System and Approach

The only frontend in this repository is the **operator-portal** web UI (`products/operator-portal/web-ui/app/`), a React 19 + TypeScript application built with Vite. Styling is centered on **Ant Design v6** as the component library, with a custom dark theme applied via `ConfigProvider`. The design system is defined by a single source of truth: a JavaScript token file that mirrors CSS custom properties (design tokens) so both Ant Design components and bespoke styles consume the same vocabulary.

## Key Files

- `app/src/theme/tokens.ts` — Central palette and Ant Design `ThemeConfig` (dark algorithm, colors, border radius, fonts).
- `app/src/theme/global.css` — Global base styles, CSS custom properties on `:root`, layout chrome, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, sticky request banner, bounded panes, and responsive rules.
- `app/src/main.tsx` — Bootstraps React root, wraps the app in `ConfigProvider` with `portalTheme`, and imports `global.css`.
- `app/src/App.tsx` — Layout shell using `antd.Layout.Sider` (dark mode, collapsible to 64px rail), drawer for narrow viewports, and role-based menu visibility.
- `app/package.json` — Declares dependencies: `react`, `react-dom`, `antd`, `@ant-design/icons`, `@ant-design/x`, `dayjs`; dev deps include `vite`, `vitest`, `@vitejs/plugin-react`, `jsdom`.
- `app/vite.config.ts` — Injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` in dev.

## Architecture and Conventions

### Token model
- `tokens.ts` defines a `palette` object (bg, surface, surfaceAlt, border, text, textMuted, accent, accentHover, success, error, warning, codeBg, radius) and a `portalTheme` `ThemeConfig` mapping those values into Ant Design's dark algorithm tokens (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBorder`, `colorText`, etc.).
- `global.css` declares the same values as CSS custom properties under `:root` (`--bg`, `--surface`, `--accent`, `--radius`, …). Comments explicitly state they are "ported verbatim from the legacy portal's :root design tokens" and that bespoke styles and antd components stay on one vocabulary. This dual declaration is the contract between JS-side theming and CSS-side styling.

### Theme application
- `main.tsx` renders `<ConfigProvider theme={portalTheme}>` around the entire tree, so all Ant Design components inherit the dark palette, font families (`Inter` / `-apple-system` / `JetBrains Mono` for code), and 8px border radius.
- Components use Ant Design primitives (`Layout`, `Menu`, `Button`, `Tag`, `Avatar`, `Alert`, `Drawer`, `Typography`) rather than raw HTML/CSS for chrome; bespoke visual tweaks live in `global.css`.

### Layout and responsive strategy
- Desktop: `Layout.Sider` with `theme="dark"`, width 230px, breakpoint `lg` (992px), collapsed width 64px. A pinned `.mobile-menu-button` sits fixed top-left to toggle collapse or open an off-canvas `Drawer`.
- Narrow viewport: below 992px the Sider auto-collapses and navigation moves into a left `Drawer` of size 260px. The session panel in the chat view narrows from 260px to 200px at ≤860px.
- Focus management: `:focus-visible` gets a 2px solid `var(--accent)` outline with 2px offset, ensuring keyboard accessibility on custom controls.

### View chrome conventions
- Each page lives inside `.view-container` (padding 20px 24px); the chat view uses `.view-container-flush` (no padding, full bleed) because it owns its own scrolling.
- Shared toolbar pattern: `.view-toolbar` flex row with 8px gap for filters/actions.
- Report forms use `.report-form` bordered card style.
- Bounded panes (documents viewer): `.digest-bounded .ant-tabs-body-holder` and `.prose-bounded .ant-collapse-body` scroll within a CSS variable-driven `max-height` (`--bounded-pane-max-height` set per wrapper) so structural chrome stays pinned.

### Domain-specific UI patterns
- Chat workspace: `.chat-view` splits a 260px `.session-panel` (list of sessions with active/accent highlight) and a flexible `.chat-column` transcript area. Messages use `.turn-group`; newly arrived turns flash with a 4s `turn-arrive-flash` animation (disabled under `prefers-reduced-motion`).
- Sticky request banner: `.turn-request-banner` appears when a user bubble scrolls out of view, re-stating the request above the transcript with an accent left border and gradient background.
- Evidence groups: `.evidence-turn` / `.evidence-card` / `.evidence-pre` render tool results in bounded 280px scrollable blocks with monospace font.
- HITL confirmation cards: `.confirm-card` variants for pending/warning states, with `.confirm-call`, `.confirm-call-hint`, `.confirm-call-details` (native `<summary>` expander), and signed-execution receipt rows.
- Markdown rendering: `.md-content` styles headings (accent color), lists, inline `code`, fenced `pre` (280px max height), blockquotes (accent left border), links, tables, strong/emphasis — ported from the legacy portal.

### Build-time asset strategy
- Output goes to `web-ui/dist/`, served by nginx (`nginx.conf` not shown but referenced). Build emits content-hashed filenames for immutable caching while `index.html` is no-store.
- Platform version and locked dependency versions are injected as `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants consumed by the Settings view.

## Conventions and Constraints

- **Single source of truth for colors**: Palette values live in `tokens.ts` and are mirrored as CSS variables; new colors must be added to both places (enforced by comments referencing SPEC-023 R-1).
- **Dark-only theme**: `color-scheme: dark` is set globally; Ant Design `ConfigProvider` uses `darkAlgorithm`; no light-mode toggle exists.
- **Component library boundary**: Visual chrome is built from Ant Design components; custom CSS classes in `global.css` are reserved for layout shells, domain-specific panels, and overrides that Ant Design does not expose.
- **Responsive breakpoints**: Desktop sidebar collapses at antd's `lg` (992px); session panel tightens at 860px; mobile drawer replaces inline nav below 992px.
- **Accessibility**: Visible focus outlines via `:focus-visible`; reduced-motion media query disables animations; semantic elements used for expanders (`<summary>`).
- **Bounded scrolling**: Long content (fenced code blocks, evidence pre, digest tabs, prose collapse) uses explicit `max-height` with internal overflow to keep the surrounding layout stable.
- **Spec-driven naming**: Many CSS class comments reference SPEC numbers (SPEC-019, SPEC-020, SPEC-023, SPEC-024, SPEC-031, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041), tying visual behavior to platform specifications.