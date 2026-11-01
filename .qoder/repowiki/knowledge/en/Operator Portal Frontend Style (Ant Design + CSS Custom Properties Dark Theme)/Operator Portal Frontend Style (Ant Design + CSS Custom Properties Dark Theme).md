---
kind: frontend_style
name: Operator Portal Frontend Style (Ant Design + CSS Custom Properties Dark Theme)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/nginx.conf
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 + TypeScript SPA built with Vite. Visual styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library, with a **dark-only theme** applied via Ant Design's `ThemeConfig` and `darkAlgorithm`. Global design tokens are declared once in `src/theme/tokens.ts` and mirrored into CSS custom properties in `src/theme/global.css` so that bespoke styles and Ant Design components share one vocabulary.

There is no Tailwind, SCSS, or CSS-in-JS framework beyond Ant Design's own token system. Styles are plain `.css` files consumed by Vite; there is no module-scoped CSS or CSS Modules configuration in `vite.config.ts`.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares dependencies: `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `dayjs`; build tooling is Vite + Vitest + TypeScript.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for palette, radii, fonts, and the Ant Design `ThemeConfig` (`portalTheme`).
- `products/operator-portal/web-ui/app/src/theme/global.css` — global base styles, CSS custom properties under `:root`, layout shell, chat workspace, markdown rendering, evidence cards, HITL confirmation cards, sticky request banner, bounded panes, and responsive rules.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving.
- `products/operator-portal/nginx.conf` — serves the built static assets at `/`.

## Architecture and conventions

### Dual-token strategy
`tokens.ts` defines a `palette` object (bg/surface/surface-alt/border/text/textMuted/accent/accentHover/success/error/warning/codeBg/radius) and maps it to an Ant Design `ThemeConfig` using `antd.darkAlgorithm`. The same values are redeclared as CSS custom properties (`--bg`, `--surface`, `--accent`, …) in `global.css`'s `:root`. Comments explicitly state the intent: "Design tokens mirror src/theme/tokens.ts; antd components consume the ThemeConfig, bespoke styles consume these custom properties" (SPEC-023 R-1 dark theme).

### Dark-only, no light mode
`global.css` sets `color-scheme: dark` on `:root`. There is no theme switcher or light-mode branch in the codebase.

### Component-library-first, bespoke CSS second
Ant Design provides layout primitives (`Layout.Sider`, `Menu`, `Tabs`, `Collapse`, `Typography`, etc.) and the visual baseline. Bespoke classes in `global.css` augment them (e.g., `.app-shell`, `.sidebar-footer`, `.view-container`, `.chat-view`, `.session-panel`, `.turn-group`, `.confirm-card`, `.evidence-*`, `.digest-bounded`, `.prose-bounded`). The CSS avoids overriding Ant Design internals directly where possible and instead wraps or augments them.

### Scoped feature regions in one stylesheet
All global styles live in `global.css` rather than per-component CSS files. Feature areas are visually sectioned by comments referencing SPEC numbers:
- Chat workspace (SPEC-023 R-3)
- Turn arrival flash animation (SPEC-034/035)
- Approvals inbox entries (SPEC-034 R-4)
- Markdown content (ported from legacy `styles.css`)
- Tool evidence groups (SPEC-011 R-4 parity)
- Sticky request banner
- HITL confirmation cards (SPEC-020 R-4)
- Signed-execution receipts (SPEC-037 R-6)
- Owner recovery details (SPEC-063 R-5a)
- Shared view chrome (SPEC-023 R-5)
- Documents drawer bounded panes (SPEC-041 R-3)

### Responsive strategy
Responsive behavior is minimal and breakpoint-driven via standard `@media` queries in `global.css`:
- `.mobile-menu-button` is pinned top-left for off-canvas navigation below Ant Design's `lg` breakpoint (992px).
- `.session-panel` narrows from 260px to 200px at `max-width: 860px`.
- `prefers-reduced-motion: reduce` disables the turn-arrival flash animation.
No mobile-first media query ordering is used; breakpoints are ad-hoc per region.

### Typography and spacing
Fonts are declared in both `tokens.ts` and `global.css`: body uses `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`; code uses `"JetBrains Mono", "Fira Code", monospace`. Border radius is centralized as `--radius: 8px` (and `palette.radius: 8`). Spacing is mostly inline pixel values in CSS rather than a spacing scale.

### Build-time version injection
`vite.config.ts` reads the root `VERSION` file and the lockfile to define `__PLATFORM_VERSION__`, `__REACT_VERSION__`, and `__ANTD_VERSION__` constants, so the Settings panel can display the exact shipped dependency versions. This is enforced by `make validate-version` which follows the constant to this injection point.

## Conventions and constraints

- **Single design-token source**: Palette values live in `src/theme/tokens.ts` and are mirrored into CSS custom properties in `src/theme/global.css`; bespoke styles reference `var(--*)` rather than hard-coded hex values. (Enforced by the comment in `tokens.ts` stating the mirroring contract tied to SPEC-023 R-1.)
- **Dark-only theme**: `color-scheme: dark` is set globally; no light-theme toggle exists.
- **Ant Design as the sole UI library**: Components are rendered with Ant Design primitives; custom CSS augments rather than replaces them.
- **Global CSS over scoped CSS**: All styles are in `global.css`; there is no CSS Modules, CSS-in-JS, or per-component stylesheet convention.
- **Feature-area comments cite SPEC numbers**: Each major style block is annotated with the originating spec requirement (e.g., SPEC-023, SPEC-034, SPEC-037, SPEC-063), tying visual decisions back to the spec-driven development process.
- **Bounded scrollable panes**: Long-form content (pre blocks, evidence, digest tabs, prose collapse) is constrained via `max-height: 280px` or via the `--bounded-pane-max-height` CSS variable on `.digest-bounded` / `.prose-bounded` wrappers, keeping structural chrome pinned while content scrolls.
- **Accessibility basics**: A global `:focus-visible` rule applies a 2px accent outline with offset; `prefers-reduced-motion` is respected for animations.
- **Build output**: Vite builds to `web-ui/dist` (consumed by `nginx.conf`); asset filenames are content-hashed for immutable caching while `index.html` stays no-store (per SPEC-023 R-1).