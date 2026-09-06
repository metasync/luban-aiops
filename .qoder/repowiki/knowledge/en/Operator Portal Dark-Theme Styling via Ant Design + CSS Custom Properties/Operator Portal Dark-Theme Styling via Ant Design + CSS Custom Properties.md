---
kind: frontend_style
name: Operator Portal Dark-Theme Styling via Ant Design + CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/App.tsx
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 / TypeScript application built with Vite and styled using **Ant Design 6** as the component library, wrapped in a single dark theme. There is no Tailwind or CSS-in-JS runtime beyond what Ant Design uses; bespoke styling lives in one global stylesheet (`src/theme/global.css`) that defines CSS custom properties mirroring the design tokens exported from `src/theme/tokens.ts`. The app root (`src/main.tsx`) mounts `<ConfigProvider theme={portalTheme}>` so Ant components consume the centralized palette, while custom components reference the same tokens through CSS variables.

## Key files and packages

- `products/operator-portal/web-ui/app/package.json` — declares `antd`, `@ant-design/icons`, `@ant-design/x`, `react`, `vite`, `vitest`; Node ≥22.22.2.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for the palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `accentHover`, `success`, `error`, `warning`, `codeBg`, `radius`) and the `antd.ThemeConfig` (`portalTheme`) applied via `darkAlgorithm`.
- `products/operator-portal/web-ui/app/src/theme/global.css` — defines `:root` CSS custom properties that mirror `tokens.ts`, plus all layout, chat, evidence, HITL confirmation card, markdown, and bounded-pane styles.
- `products/operator-portal/web-ui/app/src/main.tsx` — entry point that imports `global.css` and wraps the app in `ConfigProvider` with `portalTheme`.
- `products/operator-portal/web-ui/app/src/App.tsx` — applies `theme="dark"` to antd `Layout`/`Drawer` instances to enforce dark mode on shell chrome.

## Architecture and conventions

1. **Single design-token file drives both JS and CSS.** `tokens.ts` exports a `palette` object and an `antd` `ThemeConfig`; `global.css` declares the same colors as `--bg`, `--surface`, `--accent`, etc. under `:root`. Comments in `tokens.ts` explicitly state this mirroring exists so “bespoke styles and antd components stay on one vocabulary” (SPEC-023 R-1).
2. **Dark-only theme.** `color-scheme: dark` is set globally, `portalTheme` uses `antdTheme.darkAlgorithm`, and `App.tsx` passes `theme="dark"` to antd shell components. No light-mode toggle exists in the codebase.
3. **CSS Modules are not used.** All custom classes live in `global.css` and are referenced by plain class names in JSX (e.g. `.chat-view`, `.session-panel`, `.confirm-card`, `.md-content`).
4. **BEM-like naming without a preprocessor.** Class names follow a flat, descriptive convention scoped by semantic regions (`.chat-*`, `.session-*`, `.approvals-entry*`, `.evidence-*`, `.confirm-*`, `.view-container*`, `.digest-bounded`, `.prose-bounded`).
5. **Responsive strategy is CSS-media-query based.** A single `@media (max-width: 860px)` narrows the session panel; comments note that below antd’s `lg` breakpoint (992px) the sidebar collapses into an off-canvas drawer, handled by antd’s responsive Sider behavior rather than custom breakpoints.
6. **Accessibility hooks are explicit.** `:focus-visible` gets a 2px accent outline; `prefers-reduced-motion` disables the turn-arrival flash animation; keyboard focus rules are called out in comments.
7. **Content rendering has its own scope.** Markdown output is styled via the `.md-content` selector block (headings, lists, code blocks, tables, links), keeping rendered prose visually consistent with the dark palette.
8. **Bounded panes use a CSS variable contract.** Views set `--bounded-pane-max-height` on wrapper elements; `.digest-bounded` and `.prose-bounded` then apply `max-height` + `overflow-y: auto` to content areas so structural chrome stays pinned while content scrolls.

## Conventions and constraints

- **All visual tokens flow through `src/theme/tokens.ts`**; new colors must be added there and will automatically propagate to both Ant Design components and CSS custom properties in `global.css` (enforced by the documented mirroring contract, SPEC-023 R-1).
- **Custom UI must use the shared CSS variables** (`var(--accent)`, `var(--surface)`, `var(--border)`, `var(--radius)`) rather than hard-coded hex values, ensuring consistency with the antd theme.
- **HITL confirmation cards, evidence groups, and turn arrival animations** follow the class conventions defined in `global.css` (`.confirm-card`, `.evidence-turn`, `.turn-group.turn-arrived`); new interactive states should reuse these patterns instead of inventing ad-hoc styles.
- **Markdown-rendered content must be wrapped in `.md-content`** to inherit the documented heading/code/table/link styles.
- **No secondary theme or token override mechanism exists** — the portal is dark-only, so adding a light theme would require changes across `tokens.ts`, `global.css`, and every `theme="dark"` prop in `App.tsx`.