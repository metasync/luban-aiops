---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design Dark Theme with CSS Custom Properties'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/src/chat/ChatView.tsx
---

## What system/approach is used

The operator portal (`products/operator-portal/web-ui/app`) is a React 18 + TypeScript application built with Vite. Visual styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via a single dark `ThemeConfig` object, and a parallel set of CSS custom properties that power bespoke component styles. There is no Tailwind, CSS-in-JS library (Emotion/Styled Components), or utility-first framework in use.

## Key files and packages

- `package.json` — declares `react`, `antd ^6.1.1`, `@ant-design/icons ^6.0.0`, `@ant-design/x ^2.9.0`; no CSS framework dependency.
- `vite.config.ts` — builds to `../dist` with content-hashed filenames; dev server proxies `/api` to `http://localhost:8080`.
- `src/main.tsx` — wraps the app in `<ConfigProvider theme={portalTheme}>` from Ant Design; imports `./theme/global.css` at the top level.
- `src/theme/tokens.ts` — defines the shared `palette` object and `portalTheme: ThemeConfig` using `antd.darkAlgorithm`, mapping palette values to Ant tokens (`colorPrimary`, `colorBgBase`, `colorBorder`, `borderRadius`, `fontFamily`, etc.).
- `src/theme/global.css` — declares `:root` CSS custom properties (`--bg`, `--surface`, `--accent`, `--success`, `--error`, `--warning`, `--radius`, …) that mirror the JS palette verbatim; contains all bespoke layout and view styles (app shell, sidebar, chat workspace, evidence cards, HITL confirmation cards, markdown rendering, responsive breakpoints).
- `src/App.tsx` — uses Ant Design `Layout`, `Menu`, `Drawer`, `Tooltip` for the chrome; applies global class names like `app-shell`, `sidebar-brand`, `mobile-menu-button` defined in `global.css`.
- `src/chat/ChatView.tsx` — renders messages, tool evidence groups, and HITL confirmation cards using class names such as `evidence-turn`, `evidence-card`, `confirm-card`, `md-content`, `turn-request-banner`.

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` exports a `palette` constant and an `antd` `ThemeConfig`. The same hex values are duplicated into `:root` CSS variables in `global.css` so both Ant components and hand-written CSS consume one vocabulary. The comment in `tokens.ts` explicitly states this mirroring is required so "bespoke styles and antd components stay on one vocabulary".

2. **Dark-only theme**: `color-scheme: dark` is set on `:root`, and the Ant Design theme uses `darkAlgorithm`. No light-mode toggle exists; all views assume the dark palette.

3. **Component styling split**:
   - **Ant Design primitives** (`Button`, `Table`, `Alert`, `Select`, `Typography`, `Layout`, `Menu`, `Drawer`, `Tag`, `Tooltip`, `Spin`) provide base UI elements and inherit the configured theme automatically via `ConfigProvider`.
   - **Custom layout and domain-specific visuals** (app shell, session panel, chat transcript, evidence blocks, HITL confirmation cards, markdown rendering, sticky request banner) are styled with plain CSS classes in `global.css` referencing the CSS variables.

4. **Responsive strategy**: A single `@media (max-width: 860px)` breakpoint narrows the session panel; the mobile menu button toggles an off-canvas drawer below the `lg` breakpoint where Ant's `Sider` auto-collapses. No design-token-driven responsive scaling is used beyond this.

5. **Build-time version injection**: `__PLATFORM_VERSION__` is injected by Vite from the repo root `VERSION` file; this is a build concern rather than a runtime style concern but is part of how the portal's visual identity stays in sync with platform releases.

## Conventions and constraints

- All new visual tokens must be added to `src/theme/tokens.ts`'s `palette` object and mirrored into `:root` CSS variables in `src/theme/global.css` so both Ant and custom CSS can reference them consistently.
- Custom DOM nodes should avoid inline `style` attributes unless necessary; prefer class names defined in `global.css` (the codebase predominantly uses `className="..."` with semantic class names like `session-panel`, `view-container`, `chat-messages`, `composer-selection-bar`).
- Ant Design components are consumed through the app-wide `ConfigProvider` theme; individual components do not pass ad-hoc `theme` props, ensuring consistent token usage across the portal.
- Markdown-rendered content receives the `.md-content` class and is styled by dedicated rules in `global.css` (headings, lists, code blocks, blockquotes, tables) so user-generated text matches the portal's dark palette.
- Evidence and HITL card layouts follow fixed class names (`evidence-turn`, `evidence-card`, `confirm-card`, `confirm-note`, `tool-name`, `evidence-pre`) that are referenced directly from `ChatView.tsx`; adding new evidence types should reuse these classes rather than inventing new ones.