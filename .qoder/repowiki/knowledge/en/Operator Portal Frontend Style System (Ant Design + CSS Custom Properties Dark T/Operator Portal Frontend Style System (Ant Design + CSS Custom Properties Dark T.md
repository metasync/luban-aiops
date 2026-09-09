---
kind: frontend_style
name: Operator Portal Frontend Style System (Ant Design + CSS Custom Properties Dark Theme)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/src/App.tsx
    - products/operator-portal/web-ui/app/src/chat/ChatView.tsx
---

# Operator Portal Frontend Style System

## What system/approach is used

The operator portal (`products/operator-portal/web-ui`) is a React 19 + TypeScript SPA built with **Vite** and styled primarily through the **Ant Design v6** component library. The visual identity is a **dark-only theme** defined via Ant Design's `ThemeConfig` plus a parallel set of CSS custom properties on `:root`, so that both Ant components and bespoke DOM nodes share one vocabulary.

Key stack:
- **React 19** with `@vitejs/plugin-react`
- **Ant Design 6.6** (`antd`, `@ant-design/icons`, `@ant-design/x`)
- **TypeScript ~5.9**, **Vitest** for tests, **jsdom** test environment
- **Day.js** for date formatting
- No CSS-in-JS or Tailwind — styling is split between Ant Design tokens and a single global stylesheet.

## Key files and packages

| File | Role |
|---|---|
| `app/src/theme/tokens.ts` | Single source of truth for palette, radius, fonts; exports `portalTheme: ThemeConfig` consumed by Ant `<ConfigProvider>` |
| `app/src/theme/global.css` | All bespoke styles; declares `--bg`, `--surface`, `--accent`, etc. as CSS custom properties mirroring `tokens.ts` |
| `app/vite.config.ts` | Injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; builds to `../dist` served by nginx |
| `app/package.json` | Declares dependencies (`antd ^6.6.2`, `react ^19.2.8`, `@ant-design/*`); Node ≥ 22.22.2 engine constraint |
| `app/src/App.tsx` | Root layout using Ant `Layout`/`Sider`/`Menu`; applies `.app-shell`, `.mobile-menu-button`, sidebar chrome |
| `app/src/chat/ChatView.tsx` | Heaviest consumer of bespoke classes (`.evidence-*`, `.confirm-card*`, `.turn-group`, `.agent-working`) |
| `app/src/views/**/*.tsx` | Feature views compose Ant primitives with shared `.view-toolbar`, `.report-form`, `.incident-section` classes |

## Architecture and conventions

### Dual token surface
`tokens.ts` defines a `palette` object (bg, surface, surfaceAlt, border, text, textMuted, accent, success, error, warning, codeBg, radius) and maps it into an Ant Design `ThemeConfig` using `darkAlgorithm`. The same hex values are re-declared as CSS custom properties in `global.css` under `:root` (e.g. `--accent: #38bdf8`). Comments explicitly state this is a port from the legacy portal's `styles.css` and is required by SPEC-023 R-1 dark-theme rule. This dual surface lets Ant components get themed via props while hand-written elements consume `var(--accent)` directly.

### Global stylesheet as design system
`global.css` is the single source of all non-Ant styles. It establishes:
- A dark color scheme (`color-scheme: dark`)
- Base typography (`Inter` font stack, monospace fallbacks for code)
- Layout shell (`.app-shell`, `.sidebar-footer`, `.view-container`, `.view-container-flush`)
- Chat workspace grid (`.chat-view`, `.session-panel`, `.chat-column`, `.chat-messages`, `.chat-composer`)
- Evidence cards (`.evidence-turn`, `.evidence-card`, `.evidence-pre`, `.tool-name`)
- HITL confirmation cards (`.confirm-card`, `.confirm-call`, `.confirm-note`)
- Sticky request banner (`.turn-request-banner`)
- Markdown rendering rules (`.md-content h1..h6`, `pre`, `blockquote`, `table`)
- Bounded panes for documents (`.digest-bounded`, `.prose-bounded` driven by a `--bounded-pane-max-height` CSS variable set per wrapper)

### Responsive strategy
Responsive behavior is handled with plain CSS media queries rather than a responsive framework:
- Sidebar collapses below Ant Design's `lg` breakpoint (992px), switching from inline drawer to off-canvas drawer controlled by a pinned `.mobile-menu-button` fixed at top-left.
- Session panel narrows from 260px to 200px at ≤860px.
- `prefers-reduced-motion` disables the 4s turn-arrival flash animation.
- No mobile-first breakpoints beyond these two thresholds.

### Component composition pattern
Components use Ant Design primitives (`Layout`, `Menu`, `Card`, `Tabs`, `Collapse`, `Typography`, `Button`, `Input`, `Modal`, `Drawer`, `Table`, `Tag`, `Space`, `Tooltip`, `Popconfirm`, `Select`, `Form`, `List`, `Descriptions`, `Badge`, `Alert`, `Empty`, `Tree`, `Upload`, `Switch`, `Radio`, `Checkbox`, `DatePicker`, `TimePicker`, `InputNumber`, `AutoComplete`, `Transfer`, `TreeSelect`, `Cascader`, `Rate`, `ColorPicker`, `Segmented`, `Steps`, `Timeline`, `Tour`, `Watermark`, `Image`, `Statistic`, `Flex`, `Grid`, `Affix`, `BackTop`, `Breadcrumb`, `Calendar`, `Carousel`, `ConfigProvider`, `FloatButton`, `InfiniteScroll`, `Input`, `Layout`, `Menu`, `Pagination`, `Popover`, `Progress`, `QRCode`, `Result`, `Segmented`, `Skeleton`, `Slider`, `Space`, `Spin`, `Stat`, `Steps`, `Switch`, `Table`, `Tabs`, `Tag`, `TimePicker`, `Timeline`, `Tooltip`, `Tour`, `Transfer`, `Tree`, `TreeSelect`, `Upload`, `Watermark`, `theme`) and layer bespoke CSS class names on top for layout and visual polish. Inline `style` props are used sparingly (e.g. padding overrides).

### Build-time asset strategy
The Vite config outputs to `../dist` with content-hashed filenames (default Vite behavior) so assets are immutable-cacheable while `index.html` stays no-store. Platform version and locked dependency versions are injected as `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` constants, surfaced in the Settings view's tech-stack table.

## Conventions and constraints

- **Dark theme only**: `color-scheme: dark` is declared globally; no light-mode toggle exists.
- **Single token source**: Palette values live in `tokens.ts` and must be mirrored in `global.css` CSS variables — comments explicitly call out this requirement (SPEC-023 R-1).
- **CSS custom properties over hard-coded colors**: Bespoke selectors reference `var(--accent)`, `var(--surface)`, `var(--border)`, `var(--text-muted)`, `var(--code-bg)`, `var(--radius)` instead of literal hex values.
- **Bounded scroll containers**: Long content areas (evidence pre blocks, markdown `pre`, digest/prose panes) use `max-height: 280px` with `overflow-y: auto` to keep transcripts readable without pushing content off-screen.
- **Accessibility baseline**: `:focus-visible` gets a 2px accent outline with offset; `aria-hidden="true"` is used on decorative spacer divs.
- **Motion preference respected**: The `turn-arrived` arrival flash animation is disabled when `prefers-reduced-motion: reduce` is set.
- **Feature-scoped class naming**: Classes follow a feature prefix pattern (`session-*`, `chat-*`, `evidence-*`, `confirm-*`, `approvals-entry*`, `turn-*`) scoped to their semantic area rather than a flat namespace.
- **No utility CSS framework**: There is no Tailwind, Bootstrap, or CSS Modules — styling is centralized in `global.css` with Ant Design providing the base component styles.
- **Spec-driven style changes**: Many style additions are tied to spec requirements referenced inline (e.g. `SPEC-023 R-1`, `SPEC-019 R-1`, `SPEC-011 R-4 parity`, `SPEC-020 R-4`, `SPEC-034 R-1`, `SPEC-035 R-4`, `SPEC-037 R-6`, `SPEC-039 R-8`, `SPEC-041 R-3`), indicating that UI changes are tracked against product specs.