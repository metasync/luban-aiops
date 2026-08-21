---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark-Theme Single-Page UI
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/app.js
    - products/operator-portal/nginx.conf
---

## What system/approach is used

The only frontend in this repository is the **operator portal** under `products/operator-portal/web-ui/`. It is a **vanilla HTML + CSS + JavaScript single-page application** served by nginx (see `nginx.conf` at the product root). There is no build step, no component framework, no CSS-in-JS, no Tailwind or other utility-first framework. Styling is entirely a single stylesheet (`styles.css`) loaded via `<link rel="stylesheet">` from `index.html`, with cache-busting via a query-string version token.

The visual identity is a **dark theme** defined as CSS custom properties on `:root` (colors named `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`, plus `--radius`). All colors flow through these variables; there are no hard-coded color literals elsewhere in the stylesheet. The font stack is `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif` and code uses `JetBrains Mono / Fira Code` monospace.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — static shell defining the two-column app layout, sidebar navigation, and all view sections (`chat-view`, `settings-view`, `incidents-view`, `audit-view`, `permissions-view`, `tools-view`, `skills-view`). Views are toggled via the `hidden` attribute rather than destroyed/recreated.
- `products/operator-portal/web-ui/styles.css` — the complete design system for the portal: CSS variables, layout grid, sidebar, chat messages, markdown rendering, evidence/audit tables, permissions matrix, incident triage forms, pagination bars, status badges, and animations (`thinking-blink`, `spin`).
- `products/operator-portal/web-ui/app.js` — runtime behavior that drives view switching, mobile drawer, authentication, streaming chat, and data views. It applies class names to dynamically created elements (e.g. `audit-table`, `status-badge`, `btn-sm`, `cited-chip`) which are styled centrally in `styles.css`.
- `products/operator-portal/nginx.conf` — serves the three static files; no asset pipeline.

## Architecture and conventions

1. **CSS Custom Properties as the design token layer.** Every color, spacing radius, and semantic shade is declared once in `:root`. New components must consume `var(--*)` tokens rather than introducing new literal values. This is the only mechanism for theming in the repo.
2. **BEM-like class naming without a preprocessor.** Classes use lowercase-with-dashes names (`sidebar`, `nav-item`, `user-card`, `chat-msg`, `evidence-turn`, `confirm-card`, `audit-toolbar`, `policy-matrix-table`). No nesting, no SCSS/CSS modules — just flat selectors in one file.
3. **View composition via `hidden` attribute.** The HTML declares every function view up front; JS toggles `section.hidden` to show/hide them. This preserves DOM state (chat history, loaded audit rows) across navigation, so styles must handle both visible and hidden states consistently.
4. **Responsive strategy is minimal.** A mobile top bar with hamburger opens the sidebar as an off-canvas drawer below 800px (controlled by JS classes like `.open`); above that width the two-column grid (`grid-template-columns: 230px minmax(0, 1fr)`) is the default. No media-query breakpoints beyond that threshold are present in the stylesheet.
5. **Dynamic content styling via class composition.** `app.js` builds DOM nodes and assigns class strings such as `status-badge ${allowed ? 'success' : 'denied'}` or `incidentBadge(value, kind)` producing `sev-${value}`, `st-${value}`, etc. The stylesheet defines the base shape of each badge and per-kind variants. New dynamic visuals should follow this pattern: define the base class in CSS, compose variant suffixes in JS.
6. **Markdown/evidence rendering is styled as part of the theme.** The `.md-content` selector family styles headings, lists, code blocks, blockquotes, links, tables, and horizontal rules produced by the inline Markdown renderer in `app.js`. Any new rendered content should be wrapped in `.md-content` to inherit consistent typography.
7. **Accessibility is handled inline.** Focus outlines use `:focus-visible` with the accent color; `aria-*` attributes (`aria-expanded`, `aria-haspopup`, `aria-current`, `aria-label`) are set by JS; SVG icons carry `aria-hidden="true"`; the `hidden` attribute is authoritative over author styles via `[hidden] { display: none !important }`.

## Conventions and constraints

- **All colors must come from `:root` variables.** Hard-coded hex values appear only in the initial token declarations; adding new literal colors in component rules breaks the dark-theme contract.
- **New interactive surfaces reuse existing primitives.** Buttons extend `.btn-sm` or `.icon-button`; status indicators use `.status-badge` with a semantic suffix; code snippets use `.md-content pre/code` or the dedicated `--code-bg` background. Do not invent new button/input styles.
- **Views are additive, not modular.** Because there is no bundler, any new feature must add its HTML section to `index.html`, its CSS rules to `styles.css`, and its JS logic to `app.js`. Cross-file coupling is by shared class names and CSS variable names.
- **No CSS preprocessing or linting toolchain exists.** The stylesheet is plain CSS; changes are deployed by pushing the static files through nginx. Versioning is done by appending a query string (e.g. `?v=20260821-spec-020-hitl-5`) to both `styles.css` and `app.js` in `index.html`.
- **Dark mode is enforced globally.** `color-scheme: dark` is set on `:root`; light-mode overrides are not provided and would require editing the root token definitions.