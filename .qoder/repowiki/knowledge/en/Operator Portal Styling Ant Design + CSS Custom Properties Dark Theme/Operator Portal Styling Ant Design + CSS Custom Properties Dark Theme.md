---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
---

## System / Approach

The only frontend in the repository is the **operator-portal** (`products/operator-portal/web-ui/app/`), a React 19 + Vite application. Styling is built on two layers:

1. **Ant Design v6** as the component library, configured via `ThemeConfig` with `antdTheme.darkAlgorithm`.
2. **Plain CSS** (no Sass/Less/Tailwind) for bespoke layout and view-specific styles, driven by CSS custom properties defined in `src/theme/global.css`.

There is no design-token framework beyond the hand-authored `tokens.ts` / `global.css` pair; there is no Tailwind, styled-components, CSS-in-JS, or utility-first system.

## Key Files

- `app/src/theme/tokens.ts` — single source of truth for the palette and antd `ThemeConfig`.
- `app/src/theme/global.css` — global base styles, CSS custom properties, layout shell, chat workspace, markdown rendering, HITL confirmation cards, evidence groups, sticky request banner, shared view chrome, bounded panes, and narrow-viewport rules.
- `app/package.json` — declares `antd`, `@ant-design/icons`, `@ant-design/x`, `react`, `dayjs`; build tooling is Vite + Vitest + TypeScript.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` served by nginx.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` at `/`.

## Architecture and Conventions

### Dual token vocabulary
`tokens.ts` defines a `palette` object (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and maps it into an antd `ThemeConfig`. The same values are mirrored verbatim as `:root` CSS custom properties (`--bg`, `--surface`, …, `--radius`) so that bespoke CSS and antd components consume one vocabulary. The comment in `tokens.ts` explicitly states this is "ported verbatim from the legacy portal's :root design tokens" and ties it to SPEC-023 R-1 dark theme.

### Dark-only theme
`global.css` sets `color-scheme: dark` on `:root`; there is no light-mode toggle or algorithm branch. All colors are chosen for a dark background (`#0f172a`).

### Component styling strategy
- Ant Design components receive their appearance through the `portalTheme` passed at app root (via antd's `ConfigProvider`); developers do not override antd styles inline.
- Bespoke UI pieces (chat session panel, turn groups, approval inbox entries, HITL confirmation cards, evidence cards, sticky request banner, bounded panes) are written as plain CSS classes in `global.css` using BEM-like names (e.g. `.session-item`, `.turn-group.turn-arrived`, `.confirm-card`, `.evidence-card`, `.digest-bounded`, `.prose-bounded`).
- Layout uses CSS Flexbox throughout; Grid is used sparingly (e.g. `.recovery-facts` grid for dt/dd pairs).

### Responsive strategy
Responsive behavior is minimal and breakpoint-driven in `global.css`:
- A pinned `.mobile-menu-button` appears at small widths; comments document that below antd's `lg` breakpoint (992px) the sidebar folds into an off-canvas drawer.
- A `@media (max-width: 860px)` rule narrows `.session-panel` from 260px to 200px.
- No mobile-first media queries; breakpoints are added ad hoc where needed.

### Accessibility conventions
- `:focus-visible` gets a 2px accent outline with offset.
- `prefers-reduced-motion: reduce` disables the `.turn-group.turn-arrived` flash animation.
- Comments call out keyboard focus visibility requirements for custom controls.

### Content styling
Markdown content rendered inside the portal is styled via a `.md-content` scope covering headings, lists, code blocks (with `JetBrains Mono` / `Fira Code` monospace font), blockquotes, links, tables, and horizontal rules. Code blocks and fenced output are capped at `max-height: 280px` with internal scrolling so they don't push transcript content out of view.

### Spec-linked style features
Many style blocks are annotated with spec references, tying visual behavior to product specs:
- SPEC-023 R-1: dark theme, platform version injection, immutable-cacheable hashed assets.
- SPEC-019 R-1: grouped navigation labels in collapsed sidebar.
- SPEC-023 R-3: chat workspace layout.
- SPEC-024: extensible selection strip under the composer.
- SPEC-034 R-1 / SPEC-035 R-4: arrival highlight animation for turn groups.
- SPEC-037 R-6: signed-execution receipts on decided HITL cards.
- SPEC-039 R-8: session id badge per entry.
- SPEC-041 R-3: bounded panes for documents drawer tabs/collapse.
- SPEC-063 R-5a: owner recovery detail on decided cards.

### Build-time asset strategy
Vite builds to `web-ui/dist`; filenames are content-hashed so assets are immutable-cacheable while `index.html` stays no-store (SPEC-023 R-1). The dev server proxies `/api` to `http://localhost:8080` (platform-gateway).

## Conventions and Constraints

- **Single theme source**: new colors must be added to both `tokens.ts` `palette` and the matching `:root` CSS custom property in `global.css`; the files' comments state they mirror each other.
- **Dark-only**: the app sets `color-scheme: dark` and contains no light-mode logic.
- **No CSS preprocessors or utility libraries**: the dependency list has no Sass, Less, PostCSS, or Tailwind; all bespoke styles live in `global.css`.
- **Ant Design overrides go through `ThemeConfig`**, not inline style props or class overrides, except for the bespoke layout classes in `global.css`.
- **Spec annotations**: style changes tied to a spec carry a `SPEC-NNN R-N` comment linking the CSS to the requirement.
- **Bounded scrollables**: long-form content (pre blocks, evidence pre, digest/prose panes) use a fixed `max-height` (280px for code/evidence, `--bounded-pane-max-height` for panes) with internal overflow rather than letting them expand the page.
- **Monospace font stack**: code, tool names, and recovery facts consistently use `"JetBrains Mono", "Fira Code", monospace`.
- **Font family**: body text uses `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`.