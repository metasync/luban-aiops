---
kind: frontend_style
name: Operator Portal Frontend Style — Ant Design Dark Theme with CSS Custom Properties
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/src/chat/ChatView.tsx
---

## What system/approach is used

The only frontend in this repository is the **Operator Portal web UI** (`products/operator-portal/web-ui/app`), a React 19 + TypeScript application built with **Vite**. Visual styling is centered on **Ant Design v6** (`antd`, `@ant-design/icons`, `@ant-design/x`) configured via a single `ThemeConfig` object that enables the dark algorithm. Global base styles live in one stylesheet (`app/src/theme/global.css`) and are consumed by both bespoke component markup (via CSS classes) and Ant Design components (via the theme). There is no Tailwind, Sass, CSS-in-JS library, or design-system framework beyond Ant Design.

## Key files and packages

- `app/package.json` — declares `react ^19`, `antd ^6`, `@ant-design/icons ^6`, `@ant-design/x ^2`, plus Vite/Vitest tooling.
- `app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist`; proxies `/api` to `localhost:8080` in dev.
- `app/src/theme/tokens.ts` — central palette (`bg`, `surface`, `surfaceAlt`, `border`, `text`, `textMuted`, `accent`, `success`, `error`, `warning`, `codeBg`, `radius`) and the `portalTheme: ThemeConfig` applied to Ant Design's `darkAlgorithm`.
- `app/src/theme/global.css` — defines CSS custom properties under `:root` that mirror `tokens.ts` verbatim so bespoke styles and Ant Design share one vocabulary; also contains all layout, chat transcript, evidence cards, HITL confirmation cards, markdown rendering, sticky request banner, and responsive rules.
- `app/src/App.tsx` — root shell using Ant Design `Layout`/`Sider`/`Menu`/`Drawer`/`Tooltip`/`Typography`/`Modal`/`Tabs`/`Input`/`Button`/`Tag`/`Space`/`Divider`/`Select`/`Form`/`Upload`/`Table`/`Alert`/`Badge`/`Popconfirm`/`Skeleton`/`Spin`/`Empty`/`Descriptions`/`Collapse`/`Tooltip`/`Popover`/`Transfer`/`Tree`/`Steps`/`Timeline`/`Tour`/`Watermark`/`Image`/`Statistic`/`Result`/`Avatar`/`Breadcrumb`/`Dropdown`/`Menu`/`Pagination`/`Progress`/`Rate`/`Segmented`/`Slider`/`Switch`/`TimePicker`/`DatePicker`/`AutoComplete`/`Cascader`/`Checkbox`/`ColorPicker`/`ConfigProvider`/`DateRangePicker`/`Descriptions`/`Divider`/`Drawer`/`Dropdown`/`Form`/`Image`/`Input`/`InputNumber`/` Mentions`/`Modal`/`PageHeader`/`Pagination`/`Popconfirm`/`Popover`/`Progress`/`Radio`/`Rate`/`Result`/`Segmented`/`Select`/`Skeleton`/`Slider`/`Space`/`Spin`/`Stat`/`Statistic`/`Steps`/`Switch`/`Table`/`Tabs`/`Tag`/`Text`/`TimePicker`/`Timeline`/`Title`/`Tooltip`/`Tour`/`Transfer`/`Tree`/`TreeSelect`/`Typography`/`Upload`/`Watermark`/`useApp`/`useBreakpoint`/`useForm`/`useGetPopupContainer`/`useImage`/`useMenu`/`useMessage`/`useModal`/`useNotification`/`useSearchParams`/`useStyleRegister`/`useToken`/`useUpdatePassword`/`useUpload`/`useWatermark`.
- `app/src/chat/ChatView.tsx` — heavy consumer of Ant Design primitives for the session list, message transcript, evidence groups, and HITL confirmation cards.
- `nginx.conf` (at `products/operator-portal/`) serves the built `web-ui/dist` directory.

## Architecture and conventions

1. **Single source of truth for colors**: `tokens.ts` exports a `palette` const; `global.css` re-declares the same hex values as CSS custom properties (`--bg`, `--surface`, `--accent`, …). The comment in `tokens.ts` explicitly states they are "ported verbatim from the legacy portal's :root design tokens" so bespoke styles and Ant Design stay on one vocabulary. This dual declaration is the enforced contract between JS theme config and raw CSS.

2. **Dark-only theme**: `color-scheme: dark` is set on `:root`, and Ant Design's `darkAlgorithm` is the only algorithm used. No light-mode toggle exists.

3. **Component styling strategy**:
   - **Ant Design components** are styled exclusively through the `ConfigProvider` theme (`portalTheme`); inline overrides are avoided except where necessary (e.g., small padding tweaks in `App.tsx`).
   - **Custom UI elements** (session panel, chat transcript, evidence cards, approval entries, sticky request banner, markdown content) use plain CSS classes defined in `global.css`. Class names follow a flat BEM-like scheme rooted at domain concepts (`session-panel`, `chat-view`, `evidence-card`, `confirm-card`, `turn-group`, `view-container`, `md-content`).
   - **No CSS modules, no scoped styles, no CSS-in-JS**: all custom styles are global selectors in one file.

4. **Responsive behavior** is handled with CSS media queries in `global.css` (e.g., `.session-panel` width change at `max-width: 860px`) and Ant Design's built-in responsive breakpoints (`lg` at 992px triggers Sider collapse). A fixed-position `.mobile-menu-button` provides an off-canvas drawer trigger below the breakpoint.

5. **Design tokens usage pattern**: Components reference CSS variables directly in `style={{}}` props (e.g., `color: var(--accent)`) rather than importing them from `tokens.ts`, keeping runtime color access trivial while the authoritative values remain centralized.

6. **Build-time version injection**: `vite.config.ts` reads the repo root `VERSION` and the lockfile to embed `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` into the bundle, which the Settings view uses to display the tech stack table.

7. **Spec-driven style evolution**: Comments throughout `global.css` tie visual decisions to specs (SPEC-019, SPEC-020, SPEC-023, SPEC-034, SPEC-035, SPEC-037, SPEC-039, SPEC-041), indicating that UI changes are tracked alongside feature specs rather than ad-hoc.

## Conventions and constraints

- **Palette must not be duplicated**: `tokens.ts` and `global.css` must stay in sync; the comment in `tokens.ts` treats the CSS custom properties as the canonical mirror of the JS palette.
- **All custom UI uses the shared CSS variables**: bespoke components should never hard-code hex colors; they must consume `var(--bg)`, `var(--surface)`, `var(--accent)`, etc., so theme changes propagate uniformly.
- **Ant Design is the sole component library**: new interactive widgets should extend Ant Design primitives rather than introducing another UI kit.
- **Dark mode is the only supported theme**: there is no mechanism to switch algorithms or themes at runtime.
- **Global CSS is the only stylesheet**: no per-component CSS files, CSS modules, or preprocessors are used; new visual rules belong in `app/src/theme/global.css`.
- **Responsive breakpoints**: desktop-first layout with Ant Design's `lg` breakpoint (992px) controlling sidebar collapse; mobile-specific overrides are added via `@media` queries in `global.css`.
- **Accessibility baseline**: `:focus-visible` outline is globally set to 2px solid `var(--accent)` with 2px offset; `color-scheme: dark` is declared; aria attributes are used on decorative elements (e.g., `aria-hidden="true"` on spacer divs).
- **Bounded panes**: scrollable regions (pre blocks, evidence panels, digest tabs, prose collapse) use a consistent `max-height: 280px` bound with its own scrollbar so expanding content does not push the transcript out of view.