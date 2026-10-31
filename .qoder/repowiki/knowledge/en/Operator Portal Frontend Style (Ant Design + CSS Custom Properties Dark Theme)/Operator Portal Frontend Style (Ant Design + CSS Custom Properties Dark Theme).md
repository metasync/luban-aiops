---
kind: frontend_style
name: Operator Portal Frontend Style (Ant Design + CSS Custom Properties Dark Theme)
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/main.tsx
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System / Approach

The operator portal is a React 19 + TypeScript SPA built with Vite (`products/operator-portal/web-ui/app`). Visual styling is composed from two layers:

1. **Ant Design v6** as the component library and theme engine, configured via `ConfigProvider` with a `ThemeConfig` object.
2. **A single global stylesheet** (`app/src/theme/global.css`) that defines CSS custom properties mirroring the JS palette, plus bespoke layout/animation rules for chat, HITL confirmation cards, evidence panels, and view chrome.

There is no Tailwind, SCSS preprocessor, CSS-in-JS runtime, or design-token build step — tokens are duplicated between `src/theme/tokens.ts` and `:root` in `global.css` so Ant Design components consume the JS `ThemeConfig` while hand-written CSS consumes the CSS variables.

## Key Files

- `products/operator-portal/web-ui/app/package.json` — declares `antd ^6.6.2`, `@ant-design/x ^2.9.0`, `@ant-design/icons ^6.0.0`, React 19, Vite 8, Vitest.
- `products/operator-portal/web-ui/app/vite.config.ts` — injects `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` at build time; outputs to `../dist` for nginx; proxies `/api` to `localhost:8080` in dev.
- `products/operator-portal/web-ui/app/src/main.tsx` — mounts `ConfigProvider` wrapping the app tree with `portalTheme`.
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — exports `palette` (bg/surface/border/text/accent/success/error/warning/codeBg/radius) and `portalTheme` (`darkAlgorithm`, color tokens, `borderRadius: 8`, font families).
- `products/operator-portal/web-ui/app/src/theme/global.css` — ~740 lines of base styles, CSS custom properties on `:root`, `.app-shell` sidebar layout, chat session panel, turn groups, evidence cards, sticky request banner, HITL confirmation cards, markdown rendering, shared view toolbar, and bounded-pane panes.

## Architecture and Conventions

- **Dark-only theme**: `color-scheme: dark` is set on `:root`; `portalTheme.algorithm = antdTheme.darkAlgorithm`. No light-mode toggle exists.
- **Token duplication by design**: The comment in `tokens.ts` states the palette is "ported verbatim from the legacy portal's :root design tokens" and the CSS custom properties mirror it so bespoke styles and Ant Design stay on one vocabulary. This is referenced as SPEC-023 R-1 (dark theme).
- **CSS class naming**: Hand-written classes use a flat BEM-like scheme under a few root namespaces (`app-shell`, `sidebar-*`, `view-container*`, `chat-*`, `session-panel*`, `turn-group`, `evidence-*`, `confirm-card*`, `md-content`, `view-toolbar`, `digest-bounded`, `prose-bounded`). There is no per-component CSS file; all bespoke styles live in `global.css`.
- **Component composition**: Components import named Ant Design primitives (`Layout`, `Menu`, `Button`, `Modal`, `Table`, `Tabs`, `Collapse`, `Tag`, `Typography`, etc.) directly from `antd` rather than through an internal wrapper layer. Icons come from `@ant-design/icons`.
- **Responsive strategy**: A single breakpoint at `max-width: 860px` narrows the session panel; the sidebar uses Ant Design's built-in `lg` breakpoint (992px) where the Sider auto-collapses, with a pinned `.mobile-menu-button` opening an off-canvas drawer below that threshold. No mobile-first media-query cascade — the desktop layout is primary.
- **Accessibility signals**: `:focus-visible` gets a 2px accent outline; animations respect `prefers-reduced-motion: reduce` (turn-arrive flash is disabled); code blocks use monospace fonts (`JetBrains Mono`, `Fira Code`) for tool names and evidence.
- **Spec-driven style anchors**: Many selectors are annotated with their originating spec requirement (SPEC-011 R-4 evidence parity, SPEC-019 R-1 collapsed menu grouping, SPEC-020 R-4 HITL cards, SPEC-023 R-1/R-3/R-5, SPEC-034 R-1 arrival highlight, SPEC-035 R-4, SPEC-037 R-6 signed receipts, SPEC-039 R-8 session id, SPEC-041 R-3 bounded panes, SPEC-063 R-5a recovery detail). This makes the CSS readable as a living spec trace.
- **Build-time versioning**: `vite.config.ts` reads the repo root `VERSION` and `package-lock.json` to inject `__PLATFORM_VERSION__`, `__REACT_VERSION__`, `__ANTD_VERSION__` into the bundle, so the Settings view can display the exact shipped tech stack.

## Conventions and Constraints

- **Observed conventions** (descriptive):
  - All bespoke UI state classes are prefixed with the feature area (`chat-`, `session-`, `turn-`, `evidence-`, `confirm-`, `approvals-entry-`, `recovery-*`) rather than using a framework-specific scope mechanism.
  - Semantic colors are always read from CSS custom properties (`var(--accent)`, `var(--surface)`, `var(--border)`, `var(--text-muted)`, `var(--code-bg)`), never hard-coded hex values in bespoke selectors.
  - Rounded corners consistently use `var(--radius)` (8px) across cards, badges, and code blocks.
  - Long-form content (pre blocks, evidence output, digest/prose panes) is capped at `max-height: 280px` with its own scrollbar instead of expanding the transcript viewport.
  - Collapsible details inside cards use native `<details>/<summary>` elements styled via `.confirm-call-details` / `.confirm-execution-recovery` rather than Ant Design expanders.
  - Component imports are explicit named imports from `antd` (e.g. `import { Button, Modal, Segmented, Tag, Typography } from "antd"`), not wildcard imports.
  - Tests run under jsdom via Vitest (`vite.config.ts test.environment = "jsdom"`) with a setup file at `./src/test/setup.ts`.

- **Enforced / documented rules** (authoritative sources):
  - SPEC-023 R-1 mandates the dark theme and the token-sync contract between `tokens.ts` and `global.css` (documented in the `tokens.ts` header comment).
  - SPEC-023 R-1 also requires `make validate-version` to assert the injected `PLATFORM_VERSION` constant against the root `VERSION` file (enforced by the Makefile target referenced in `vite.config.ts`).
  - SPEC-023 R-1 requires content-hashed asset filenames with `index.html` served no-store (enforced by Vite's default hash behavior and the nginx config serving `web-ui/dist`).
  - SPEC-019 R-1 documents the collapsed-sidebar grouping convention (group titles hidden, hairline dividers used instead) — enforced by the `.ant-layout-sider-collapsed .ant-menu-item-group-title { display: none }` rule.
  - SPEC-020 R-4 documents the HITL confirmation card visual contract, reflected in the `.confirm-card*` selector family.
  - SPEC-034 R-1 / SPEC-035 R-4 document the turn-arrival highlight animation (2px accent edge + fading background over 4s), enforced by the `.turn-group.turn-arrived` keyframes and the `prefers-reduced-motion` override.