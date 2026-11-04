---
kind: frontend_style
name: 'Operator Portal Styling: Ant Design + CSS Custom Properties Dark Theme'
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/vite.config.ts
    - products/operator-portal/web-ui/app/src/theme/tokens.ts
    - products/operator-portal/web-ui/app/src/theme/global.css
---

## System

The only frontend in the repository is the **operator portal** (`products/operator-portal/web-ui/app`), a React 19 + Vite SPA. It uses:

- **Ant Design 6** (`antd`, `@ant-design/icons`, `@ant-design/x`) as the component library.
- A single global stylesheet (`app/src/theme/global.css`) for bespoke layout, chat workspace, HITL confirmation cards, tool evidence groups, and markdown rendering.
- A TypeScript theme file (`app/src/theme/tokens.ts`) that defines the design-token palette and an Ant Design `ThemeConfig` using `darkAlgorithm`.
- CSS custom properties on `:root` (e.g. `--bg`, `--surface`, `--accent`, `--border`, `--radius`) that mirror the TS palette so both Ant Design components and bespoke CSS consume one vocabulary.
- No Tailwind, Sass, CSS-in-JS, or utility framework — plain CSS with BEM-style class names.

There is no other UI code in the repo; all other products are Python services.

## Key files

- `products/operator-portal/web-ui/app/package.json` — declares `react`, `antd`, `@ant-design/x`, `@ant-design/icons`; Node ≥22.22.2.
- `products/operator-portal/web-ui/app/vite.config.ts` — Vite config with `@vitejs/plugin-react`, Vitest/jsdom testing, dev proxy to `/api` → `http://localhost:8080`, and build output to `../dist` (served by nginx).
- `products/operator-portal/web-ui/app/src/theme/tokens.ts` — single source of truth for colors, radii, fonts, and the `portalTheme: ThemeConfig` passed into Ant Design.
- `products/operator-portal/web-ui/app/src/theme/global.css` — ~740 lines of global base styles, app shell, sidebar, chat session panel, transcript, HITL confirmation cards, tool evidence groups, markdown renderer, sticky request banner, bounded panes, and responsive rules.
- `products/operator-portal/nginx.conf` — serves the built `web-ui/dist` at `/`.

## Architecture and conventions

1. **Design tokens live in TypeScript, not CSS.** `tokens.ts` exports `palette` (colors, radius) and `portalTheme` (Ant Design `ThemeConfig`). The comment states these were "ported verbatim from the legacy portal's :root design tokens" and that `global.css` mirrors them so bespoke styles and Ant Design stay on one vocabulary (SPEC-023 R-1 dark theme).

2. **CSS custom properties are the runtime token surface.** `global.css` declares `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius` on `:root`. All bespoke selectors reference these variables rather than hard-coded hex values.

3. **Dark-only theme.** `color-scheme: dark` is set on `:root`; Ant Design is configured with `algorithm: antdTheme.darkAlgorithm`. There is no light-mode toggle.

4. **Typography.** Primary font: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`. Code font: `"JetBrains Mono", "Fira Code", monospace`. Both are declared in `portalTheme.token.fontFamily` / `fontFamilyCode` and repeated in `.md-content code` and `.tool-name`.

5. **Layout model.** A full-height `.app-shell` pairs an Ant Design `Layout.Sider` sidebar with a `.view-container` main area. On narrow viewports (`max-width: 860px`) the session panel shrinks; comments document a future off-canvas drawer for below the `lg` breakpoint (992px).

6. **Component-specific style regions in one file:**
   - Chat workspace (session list + transcript): `.chat-view`, `.session-panel`, `.chat-column`, `.chat-messages`, `.chat-composer`, `.turn-group`.
   - Arrival highlight animation for post-decision turns: `.turn-group.turn-arrived` with a 4s fade-out keyframe, suppressed under `prefers-reduced-motion: reduce`.
   - Tool evidence groups: `.evidence-turn`, `.evidence-card`, `.evidence-pre` (bounded to `max-height: 280px`).
   - Sticky request banner: `.turn-request-banner` (gradient background, accent left border).
   - HITL confirmation cards: `.confirm-card`, `.confirm-call`, `.confirm-execution`, recovery detail grid `.recovery-facts`.
   - Markdown content: `.md-content h1–h6`, `pre`, `blockquote`, `table`, links.
   - Shared view chrome: `.view-toolbar`, `.report-form`, `.incident-section`.
   - Bounded panes: `.digest-bounded`, `.prose-bounded` driven by a CSS variable `--bounded-pane-max-height` set per wrapper.

7. **Responsive strategy.** Minimal breakpoints: `max-width: 860px` narrows the session panel; comments note the Sider auto-collapses at Ant Design's `lg` (992px) and a mobile menu button toggles an off-canvas drawer. No mobile-first media-query cascade — the desktop layout is primary.

8. **Accessibility signals.** `:focus-visible` gets a 2px accent outline with offset. Animations respect `prefers-reduced-motion: reduce`. Comments explicitly call out keyboard focus visibility on custom controls.

9. **Build-time version injection.** `vite.config.ts` reads the root `VERSION` file and injects `__PLATFORM_VERSION__`, plus locked `__REACT_VERSION__` and `__ANTD_VERSION__` from `package-lock.json`, so the Settings page can display the exact shipped dependency versions.

## Conventions and constraints

- **All color/radius/font values flow through `src/theme/tokens.ts`** and are mirrored as CSS custom properties in `src/theme/global.css` — bespoke styles must use `var(--*)`, never raw hex values (enforced by the explicit porting comment referencing SPEC-023 R-1).
- **Ant Design is styled via its `ThemeConfig`**, not by overriding component classes directly; bespoke overrides target Ant Design DOM nodes (e.g. `.ant-layout-sider-collapsed .ant-menu-item-group-title`) only when necessary.
- **Bounded scrollable blocks** (markdown `pre`, evidence `pre`, digest/prose panes) share the same height bound pattern (`max-height: 280px` or `--bounded-pane-max-height`) so long content never pushes the transcript out of view.
- **Spec-driven style changes are annotated inline.** Many rule blocks carry spec references such as `(SPEC-023 R-1)`, `(SPEC-019 R-1)`, `(SPEC-034 R-1 / SPEC-035 R-4)`, `(SPEC-037 R-6)`, `(SPEC-063 R-5a)`, `(SPEC-041 R-3)` tying visual behavior to requirements.
- **No Tailwind/Sass/PostCSS pipeline** — the project has no `tailwind.config.*`, no `.scss` files, and no PostCSS plugins in `vite.config.ts`.
- **Testing setup** uses Vitest with jsdom (`test.environment: "jsdom"`, `setupFiles: ["./src/test/setup.ts"]`); tests coexist alongside sources under `__tests__/` within each feature directory.