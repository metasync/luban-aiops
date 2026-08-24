---
kind: frontend_style
name: Operator Portal Web UI — Ant Design Dark Theme with CSS Custom Properties
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

The only frontend in this repository is the **operator-portal web UI** under `products/operator-portal/web-ui/app/`. It is a React 18 + TypeScript application built with Vite and styled using:

- **Ant Design (antd) v6** as the component library, configured with the `darkAlgorithm` theme.
- A single global stylesheet (`src/theme/global.css`) that defines CSS custom properties mirroring the Ant Design tokens.
- A design-token file (`src/theme/tokens.ts`) that centralizes the palette and feeds both Ant Design's `ThemeConfig` and the CSS variables.
- No CSS-in-JS libraries beyond Ant Design's built-in styling; no Tailwind, Sass, or preprocessors.

## Key files and packages

- `package.json` — declares dependencies: `react`, `antd`, `@ant-design/icons`, `@ant-design/x`, `dayjs`; dev deps include `vite`, `vitest`, `@vitejs/plugin-react`, `typescript`.
- `vite.config.ts` — builds to `../dist`, injects `__PLATFORM_VERSION__` from the repo root `VERSION` file, proxies `/api` to `localhost:8080` in dev, runs tests in `jsdom`.
- `src/theme/tokens.ts` — exports `palette` (bg, surface, accent, success, error, warning, border, text, radius, etc.) and `portalTheme: ThemeConfig` mapping those values into Ant Design tokens via `darkAlgorithm`.
- `src/theme/global.css` — defines `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, `--border`, `--text`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius`) plus global resets, focus-visible outlines, layout shell styles, chat workspace chrome, markdown rendering, evidence groups, sticky request banners, HITL confirmation cards, and shared view toolbar/report forms. Includes a narrow-viewport media query at 860px.
- `src/App.tsx` — composes the Ant Design `Layout`/`Sider`/`Menu`/`Drawer` shell, applies the dark sidebar menu, and wires views (chat, incidents, audit, permissions, tools, skills, settings).
- `src/main.tsx` — entry point that boots React and imports the theme globals.

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` is the canonical palette. The same hex values are exported as a JS object and re-declared as CSS custom properties in `global.css`. Comments explicitly state they are "ported verbatim from the legacy portal's :root design tokens" and that CSS custom properties mirror the TS tokens so bespoke styles and Ant Design components share one vocabulary.

2. **Dark-only theme**: `color-scheme: dark` is set on `:root`, Ant Design is forced into `darkAlgorithm`, and the entire palette uses slate/dark backgrounds (`#0f172a`, `#1e293b`, `#334155`) with a sky-blue accent (`#38bdf8`). There is no light-mode toggle.

3. **Component styling strategy**:
   - Ant Design components receive visual overrides through the `portalTheme` `ThemeConfig` (primary color, background tokens, border radius, fonts).
   - Layout chrome and domain-specific UI (sidebar, session panel, chat transcript, evidence cards, HITL confirmations, markdown rendering) are written as plain CSS classes in `global.css`.
   - Inline `style` props are used sparingly inside components (e.g., spacing, borders) but color/typography values come from CSS variables rather than hard-coded hexes.

4. **Responsive strategy**:
   - Desktop: an inline `Layout.Sider` sidebar (width 230px, collapsed width 64px icon rail) with antd's `breakpoint="lg"` auto-collapsing behavior.
   - Narrow viewport (<992px): the drawer takes over for full navigation while the 64px rail stays visible; a pinned `.mobile-menu-button` toggles the drawer.
   - A separate `@media (max-width: 860px)` shrinks the session panel from 260px to 200px.

5. **Typography**: Font families are declared once in `portalTheme.token.fontFamily` / `fontFamilyCode` and echoed in `global.css` body rules. Headings, code blocks, and monospace content use Inter/system fonts plus JetBrains Mono/Fira Code.

6. **Build-time version branding**: The platform version string is injected by Vite from the repo root `VERSION` file and displayed in the sidebar brand tag.

## Conventions and constraints

- **All colors flow through `tokens.ts`**: new colors should be added to the `palette` object first, then mirrored into `:root` CSS variables in `global.css` so both Ant Design and bespoke CSS can consume them.
- **No per-component CSS modules or scoped stylesheets**: all custom class names live in `global.css` (e.g., `.app-shell`, `.view-container`, `.session-panel`, `.chat-view`, `.evidence-card`, `.confirm-card`).
- **Dark mode is enforced globally**: there is no theme switcher; `color-scheme: dark` and `darkAlgorithm` are applied unconditionally.
- **Responsive breakpoints are tied to Ant Design's `lg` (992px)** for the sidebar collapse and a custom 860px breakpoint for the chat session panel.
- **Accessibility baseline**: `:focus-visible` gets a 2px accent-colored outline with offset; navigation buttons carry `aria-label`s; the mobile menu button toggles based on `useNarrowViewport()`.
- **Markdown and evidence rendering** have dedicated style blocks in `global.css` (`.md-content`, `.evidence-turn`, `.evidence-pre`, `.turn-request-banner`) ensuring consistent look-and-feel across chat transcripts.
- **CSS variable naming follows the token keys**: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius` — keeping the CSS vocabulary aligned with the TS palette.