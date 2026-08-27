---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
---

## What system/approach is used

The only frontend in this monorepo is the **operator-portal web UI** (`products/operator-portal/web-ui/app`), a React 18 + TypeScript application built with Vite. Styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via an Ant Design `ThemeConfig` object, and a parallel set of **CSS custom properties** (design tokens) that bespoke component styles consume. There is no Tailwind, Sass, or CSS-in-JS library beyond what Ant Design ships.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, plus Vite/Vitest tooling.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — defines the canonical palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and exports an Ant Design `ThemeConfig` (`portalTheme`) using `darkAlgorithm`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — declares the same token values as `:root` CSS variables (`--bg`, `--surface`, `--accent`, …) so non-Ant components can reference them; also contains all bespoke layout, chat transcript, approvals inbox, markdown rendering, evidence cards, sticky request banner, and HITL confirmation card styles.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__` at build time and configures the dev proxy to `/api` → `http://localhost:8080`.
- `products/operator-portal/web-ui/app/src/App.tsx` — root layout using Ant Design `Layout.Sider`/`Layout.Content`, applies the dark menu theme, and wires responsive behavior (sidebar collapses at antd's `lg` breakpoint = 992px, drawer opens below it).
- `products/operator-portal/web-ui/nginx.conf` — serves the built `dist/` assets under `/`.

## Architecture and conventions

1. **Single source of truth for colors**: `src/theme/tokens.ts` is the authoritative design-token file. Its comment states the palette was "ported verbatim from the legacy portal's :root design tokens" and that `global.css` mirrors it so both Ant Design components and bespoke styles share one vocabulary. This is the contract referenced by SPEC-023 R-1 (dark theme).

2. **Dual token consumption**:
   - Ant Design components receive `portalTheme` via the Ant ConfigProvider so tokens like `colorPrimary`, `colorBgBase`, `colorBorder`, `fontFamily`, and `borderRadius` flow into every `Button`, `Menu`, `Tag`, `Alert`, etc.
   - Hand-written CSS classes in `global.css` read from `var(--accent)`, `var(--surface)`, `var(--border)`, `var(--radius)`, etc., keeping custom layouts (`.app-shell`, `.session-panel`, `.chat-view`, `.approvals-entry`, `.md-content`, `.evidence-card`, `.confirm-card`, `.turn-request-banner`) consistent with the Ant theme.

3. **Dark-only mode**: The app sets `color-scheme: dark` on `:root` and uses Ant's `darkAlgorithm`; there is no light-theme toggle. All bespoke styles are written for the dark palette.

4. **Responsive strategy**: Responsive behavior is achieved through a combination of Ant Design breakpoints (`breakpoint="lg"` on `Layout.Sider`, which auto-collapses at 992px) and a custom `useNarrowViewport()` hook that listens to `max-width: 991px` to switch between inline sidebar and an off-canvas `Drawer`. A `mobile-menu-button` is pinned at top-left for quick access. Additional media queries in `global.css` adjust the session panel width at `max-width: 860px`.

5. **View chrome convention**: Every view renders inside a `.view-container` wrapper; the chat view additionally adds `.view-container-flush` to remove padding and own its scrolling. Shared toolbar/report patterns live as `.view-toolbar` and `.report-form` classes.

6. **Component-specific style domains in global.css**: Styles are grouped by feature area rather than per-component SCSS files — chat workspace (`.chat-view`, `.session-panel`, `.chat-messages`, `.composer-selection-bar`), markdown content (`.md-content`), tool evidence groups (`.evidence-turn`, `.evidence-card`, `.evidence-pre`), sticky request banner (`.turn-request-banner`), HITL confirmation cards (`.confirm-card`), and approvals inbox entries (`.approvals-entry`).

7. **Accessibility hooks**: `:focus-visible` outline is globally set to `var(--accent)` with 2px offset; the mobile menu button carries `aria-label` text that changes based on viewport state; reduced-motion preference disables the turn-arrival flash animation.

## Conventions and constraints

- **All visual tokens must go through `tokens.ts`**. New colors or radii should be added to the `palette` object and mirrored in `global.css` `:root` variables; bespoke styles must use `var(--...)` rather than hard-coded hex values (observed consistently across `global.css`).
- **Ant Design dark theme is mandatory** — `portalTheme` uses `darkAlgorithm` and the app never switches algorithms; new components should not introduce light-mode overrides.
- **Custom CSS class names follow BEM-like naming** scoped to feature areas (e.g. `.session-panel-*`, `.chat-*`, `.approvals-entry-*`, `.evidence-*`, `.confirm-*`) and are defined centrally in `global.css` instead of co-located with components.
- **Responsive breakpoints are centralized**: the antd `lg` breakpoint (992px) drives the Sider collapse, while `860px` is used for the session panel narrowing in CSS; the `useNarrowViewport()` hook mirrors the 991px threshold for drawer vs. collapsed rail logic.
- **Build-time version injection**: `vite.config.ts` reads the repo root `VERSION` file and defines `__PLATFORM_VERSION__`, which is displayed as a Tag next to the brand in the sidebar — tying the UI to the platform version without runtime fetches.
- **SPEC references anchor styling decisions**: comments throughout `global.css` and `App.tsx` cite SPEC numbers (SPEC-019, SPEC-020, SPEC-023, SPEC-031, SPEC-034, SPEC-035, SPEC-037) that govern behaviors such as collapsed sidebar grouping, arrival highlight animations, approvals inbox card layout, and signed-execution receipts.