---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Properties Tokens'
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

## System Overview

The only frontend in this repository is the **operator-portal web UI** (`products/operator-portal/web-ui/app`), a React 18 + TypeScript application built with Vite. It uses **Ant Design (antd v6)** as its component library and applies a **dark theme** via Ant Design's `ThemeConfig`. There is no Tailwind, SCSS, or CSS-in-JS beyond what Ant Design provides — styling is a combination of Ant Design tokens, a small set of global CSS custom properties, and scoped CSS classes for portal-specific layout.

## Key Files and Packages

- `package.json` — declares `react`, `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, plus Vite/Vitest tooling. No CSS framework dependency.
- `vite.config.ts` — builds to `../dist`; serves `/api` proxy to `localhost:8080` in dev; injects `__PLATFORM_VERSION__` at build time.
- `src/theme/tokens.ts` — single source of truth for the palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `success`, `error`, `warning`, `codeBg`, `radius`) and the `portalTheme: ThemeConfig` passed into Ant Design's dark algorithm.
- `src/theme/global.css` — defines matching CSS custom properties on `:root` (`--bg`, `--surface`, `--accent`, etc.) so bespoke styles and Ant Design components stay on one vocabulary; also contains all portal-specific layout, chat transcript, evidence card, approval inbox, markdown rendering, and responsive rules.
- `src/App.tsx` — root shell using `antd.Layout`/`Layout.Sider`/`Layout.Content`/`Drawer`/`Menu`; drives the sidebar, drawer-based mobile nav, and view routing.

## Architecture and Conventions

### Token model
Tokens are declared once in `tokens.ts` as a `const` palette object and mapped into an Ant Design `ThemeConfig` using `antd.darkAlgorithm`. The same color values are mirrored as CSS custom properties in `global.css` under `:root`. This dual declaration keeps Ant Design components and hand-written CSS sharing one visual vocabulary. Comments in both files explicitly reference SPEC-023 R-1 (dark theme) as the governing requirement.

### Component styling approach
- **Ant Design components**: styled through the `ThemeConfig` token overrides (primary color, background, border, text, radius, fonts). Components are used with their default DOM structure; no per-component CSS modules or styled-components are used.
- **Portal chrome**: layout classes like `.app-shell`, `.view-container`, `.sidebar-footer`, `.mobile-menu-button`, `.session-panel`, `.chat-view`, `.turn-group`, `.evidence-card`, `.confirm-card`, `.approvals-entry`, `.md-content` live in `global.css`. They compose Ant Design primitives (Layout, Menu, Drawer, Tag, Typography) with minimal CSS.
- **Markdown/evidence rendering**: `.md-content` styles are ported from the legacy portal's `styles.css` and apply consistently to rendered content inside transcripts and documents.

### Responsive strategy
- Desktop: inline `Layout.Sider` sidebar (width 230px, collapsible to 64px icon rail).
- Narrow viewport (`max-width: 991px`, aligned with antd's `lg` breakpoint): the Sider auto-collapses and a left-placed `Drawer` provides the full labeled menu; a fixed-position `.mobile-menu-button` toggles it.
- Chat session panel narrows from 260px to 200px below 860px.
- Reduced motion: `@media (prefers-reduced-motion: reduce)` disables the turn-arrival flash animation.

### Build-time versioning
`vite.config.ts` reads the repo root `VERSION` file and exposes it as `__PLATFORM_VERSION__`, which is consumed by the app to display the platform version tag next to the brand. This is enforced by `make validate-version` (referenced in comments).

## Conventions and Constraints

- **Dark theme only**: `color-scheme: dark` is set on `:root`; the Ant Design theme uses `darkAlgorithm`. Light mode is not implemented.
- **Single token source**: colors, spacing radius, and font families are defined in `tokens.ts` and mirrored into CSS variables — new tokens should be added in both places to keep Ant Design and bespoke styles consistent.
- **CSS class naming**: portal-specific classes use kebab-case BEM-like names (e.g., `.session-item`, `.turn-group.turn-arrived`, `.evidence-pre`) rather than CSS modules; they are applied directly in JSX via the `className` prop.
- **Accessibility baseline**: `:focus-visible` gets a visible 2px accent outline; navigation buttons carry `aria-label`s; reduced-motion media query is respected for animations.
- **No utility-first CSS**: there is no Tailwind config, no PostCSS plugins, and no CSS-in-JS runtime — styling is plain CSS + Ant Design tokens.
- **Scoped to operator portal**: this styling system applies only to `products/operator-portal/web-ui/app`; backend services have no frontend assets.