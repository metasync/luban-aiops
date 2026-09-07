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
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/vite.config.ts
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React + TypeScript SPA built with **Vite** and styled exclusively via the **Ant Design (antd) v6** component library. There is no Tailwind, styled-components, Emotion, or inline `css` template literals in the codebase; all visual styling flows through antd's theme configuration plus a single global stylesheet.

## Key files and packages

- `app/package.json` — declares `antd ^6.6.2`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`, React 19, Vite, Vitest.
- `app/src/theme/tokens.ts` — defines the canonical palette (`bg`, `surface`, `accent`, `success`, `error`, `warning`, `border`, `radius`, …) and builds an antd `ThemeConfig` using `antd.darkAlgorithm`. Fonts are set to Inter for body text and JetBrains Mono / Fira Code for code.
- `app/src/theme/global.css` — mirrors the same tokens as CSS custom properties on `:root` (`--bg`, `--surface`, `--accent`, …) so bespoke styles and antd components share one vocabulary. It also contains all portal-specific layout, chat transcript, evidence cards, HITL confirmation cards, sticky request banner, markdown rendering, and responsive rules.
- `app/src/main.tsx` — wraps the app in `<ConfigProvider theme={portalTheme}>` from antd to apply the dark theme globally.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx serving.
- `nginx.conf` (in `products/operator-portal/`) serves the built `dist/` directory.

## Architecture and conventions

1. **Single source of truth for colors**: The `palette` object in `tokens.ts` is the only place color values are declared. They are consumed both by antd's `ThemeConfig.token` and by `global.css` `:root` variables. Comments explicitly state that bespoke styles and antd components must stay on this shared vocabulary (referencing SPEC-023 R-1).

2. **Dark-only theme**: `color-scheme: dark` is set on `:root`, and antd uses `darkAlgorithm`. No light-mode toggle exists; the entire portal is designed for a dark SRE/operator aesthetic.

3. **Component library usage**: Every UI component is imported directly from `antd` (e.g., `Layout`, `Menu`, `Table`, `Button`, `Modal`, `Tag`, `Typography`, `Tabs`, `Collapse`, `Statistic`). Custom CSS classes are used only for layout shells (`.app-shell`, `.view-container`, `.chat-view`, `.session-panel`, `.turn-group`, `.confirm-card`, `.evidence-*`, `.md-content`) and for overriding antd behavior in collapsed sidebar states (`.ant-layout-sider-collapsed .ant-menu-item-group-title { display: none }`).

4. **Responsive strategy**: A single breakpoint at `max-width: 860px` narrows the session panel; below antd's `lg` breakpoint (992px) the sidebar switches from an inline drawer to an off-canvas drawer via antd's built-in collapse behavior. A pinned `.mobile-menu-button` appears at small viewports. Reduced-motion preferences are respected via `@media (prefers-reduced-motion: reduce)`.

5. **Bounded panes**: Long content areas (code blocks, tool evidence, digest tabs, prose panels) use a fixed `max-height` with internal scrolling, driven by a CSS variable `--bounded-pane-max-height` set per wrapper. This prevents large transcripts or logs from pushing the page chrome out of view.

6. **Accessibility basics**: `:focus-visible` gets a 2px accent outline with offset; `color-scheme: dark` helps native controls; animations fade out when reduced motion is preferred.

7. **No design-token framework beyond CSS vars**: There is no token file generator, no stylelint config, no CSS-in-JS runtime. Tokens live in two synchronized places (`tokens.ts` and `global.css`) and are referenced by comments linking back to spec requirements (SPEC-019, SPEC-020, SPEC-023, SPEC-024, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041).

## Conventions and constraints

- All colors, radii, and fonts flow through the `palette` object in `src/theme/tokens.ts`; ad-hoc hex values in component JSX are not observed.
- Custom CSS classes follow BEM-like naming rooted at portal feature areas (`.session-*`, `.chat-*`, `.confirm-*`, `.evidence-*`, `.md-content *`, `.approvals-entry-*`, `.digest-bounded`, `.prose-bounded`).
- Markdown-rendered content is scoped under the `.md-content` class so its typography, code blocks, tables, and links inherit the portal's dark palette consistently.
- Build-time constants (`__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__`) are injected via Vite's `define` so the Settings view can report the exact shipped tech stack.
- The portal is served statically by nginx from `web-ui/dist`; asset filenames are hashed for immutable caching while `index.html` is cached with no-store semantics.