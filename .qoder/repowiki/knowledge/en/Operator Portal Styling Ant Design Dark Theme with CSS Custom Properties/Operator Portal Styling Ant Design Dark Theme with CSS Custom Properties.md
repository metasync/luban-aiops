---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React + TypeScript SPA built with **Vite** and styled primarily via the **Ant Design v6** component library in its dark theme. A single global stylesheet (`app/src/theme/global.css`) defines CSS custom properties (design tokens) that mirror the Ant Design `ThemeConfig` defined in `app/src/theme/tokens.ts`. This dual-source approach lets Ant components consume typed tokens while bespoke styles reference the same palette through `var(--*)` variables, keeping the UI on one vocabulary.

There is no Tailwind, Sass, or CSS-in-JS beyond what Ant ships; styling is plain CSS modules-free global CSS plus inline `style` props for small layout tweaks.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite 8, Vitest.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time from the repo root `VERSION` file and `package-lock.json`; outputs to `../dist` for nginx serving.
- `app/src/theme/tokens.ts` — exports `palette` (bg, surface, accent, success, error, warning, border, text, codeBg, radius) and `portalTheme: ThemeConfig` using `antd.darkAlgorithm`.
- `app/src/theme/global.css` — defines `:root` CSS custom properties mirroring `palette`, plus all view-level classes (`.app-shell`, `.session-panel`, `.chat-view`, `.approvals-entry`, `.md-content`, `.evidence-*`, `.confirm-card`, `.turn-request-banner`, bounded panes).
- `app/src/App.tsx` — composes the Ant `Layout.Sider`/`Menu` sidebar, role-gated navigation groups (Control / Workspace), drawer-based mobile nav, and per-view routing.

## Architecture and conventions

### Design-token model
- Tokens are declared once in `tokens.ts` as a `const` palette object and mapped into an Ant `ThemeConfig` (`colorPrimary`, `colorBgBase`, `colorBgContainer`, `colorBorder`, `colorText`, `borderRadius`, fonts).
- The same values are duplicated as CSS custom properties under `:root` so non-Ant DOM nodes can consume them via `var(--accent)`, `var(--surface)`, etc. Comments explicitly call this out as a port from the legacy portal's `styles.css` and tie it to SPEC-023 R-1 dark-theme requirement.
- Font families are centralized: sans-serif stack `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial` and monospace stack `"JetBrains Mono", "Fira Code"`.

### Theming strategy
- The app is **dark-only**: `color-scheme: dark` is set on `:root`, and Ant is configured with `algorithm: antdTheme.darkAlgorithm`. There is no light-mode toggle.
- Brand/accent color is `#38bdf8` (sky blue); semantic colors use green/red/yellow variants. All radii go through `--radius: 8px`.

### Layout and responsive behavior
- App shell uses Ant `Layout` with a collapsible `Sider` (width 230, collapsed width 64). Below the `lg` breakpoint (992px) the Sider auto-collapses and a left `Drawer` provides full-label navigation; a fixed-position `.mobile-menu-button` toggles between drawer and collapse modes.
- View containers use `.view-container` (scrollable) or `.view-container-flush` (full-bleed, used by chat). Chat adds a fixed-width `.session-panel` (260px, shrinks to 200px below 860px) beside a flex column transcript.
- Bounded panes (documents, evidence) use a CSS variable `--bounded-pane-max-height` set by the view and consumed by `.digest-bounded .ant-tabs-body-holder` / `.prose-bounded .ant-collapse-body` to cap scrollable regions.

### Component styling conventions
- Bespoke UI pieces (session items, approval cards, confirmation cards, markdown content, tool evidence blocks, sticky request banners) live in `global.css` as class names prefixed by feature area (`.session-*`, `.approvals-*`, `.confirm-*`, `.md-content`, `.evidence-*`).
- Markdown rendering gets a dedicated `.md-content` scope with headings colored accent, code blocks capped at `max-height: 280px`, blockquotes with accent left borders, and tables styled with surface backgrounds.
- Animations are minimal and respect accessibility: `.turn-group.turn-arrived` fades an accent tint over 4s but is disabled under `prefers-reduced-motion: reduce`.

### Build-time versioning
- `vite.config.ts` reads the repo root `VERSION` and `package-lock.json` to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`, which are consumed at runtime (e.g., `./version.ts` → displayed in the sidebar brand tag). This ties the shipped bundle's visible tech stack to locked dependency versions.

## Conventions and constraints

- **Dark theme only** — enforced by setting `color-scheme: dark` and applying `darkAlgorithm` to the Ant theme config; no light-mode path exists in the codebase.
- **Single source of truth for colors** — every token flows from `tokens.ts` into both Ant's `ThemeConfig` and `:root` CSS variables; comments document this synchronization and tie it to SPEC-023 R-1.
- **Bounded scrolling for long content** — code blocks, evidence panels, and document panes use `max-height: 280px` (or a view-scoped `--bounded-pane-max-height`) so expanding large output never pushes the transcript off-screen.
- **Responsive breakpoints** — the sidebar collapses at Ant's `lg` (992px) and switches to a drawer; session panel narrows at 860px. These are hard-coded in `App.tsx` and `global.css` media queries.
- **Accessibility basics** — `:focus-visible` outline uses the accent token; animations honor `prefers-reduced-motion`; menu buttons carry `aria-label` attributes.
- **Spec-driven style changes** — many CSS rules are annotated with spec references (SPEC-019, SPEC-020, SPEC-023, SPEC-031, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041), indicating that visual changes are tied to numbered platform specs rather than ad-hoc design decisions.