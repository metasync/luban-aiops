---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark-Theme UI with Design Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/app.js
    - products/operator-portal/nginx.conf
---

## What system/approach is used

The only frontend in this repository is the **Operator Portal** under `products/operator-portal/web-ui/`. It is a **vanilla HTML + CSS + JavaScript** single-page application served by nginx (see `nginx.conf` at the portal root). There is no build step, no component framework, no CSS-in-JS, and no design-system library. Styling is done entirely through one stylesheet (`styles.css`) loaded from `index.html`, with all layout, theming, and responsive behavior expressed as plain CSS.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — static shell defining the two-column app layout, sidebar navigation, and four function views (Chat, Settings & Debug, Incidents, Audit trail).
- `products/operator-portal/web-ui/styles.css` — the complete style sheet (~1040 lines) that defines the theme, layout, components, and responsive rules.
- `products/operator-portal/web-ui/app.js` — client-side logic for view navigation, authentication flow, streaming chat rendering, audit-trail pagination, incident triage list/detail, and markdown rendering.
- `products/operator-portal/nginx.conf` — serves the three static files; no asset pipeline.

No other CSS/SCSS/Tailwind/design-token files exist anywhere else in the repo. The remaining products are Python FastAPI services with no browser-facing assets.

## Architecture and conventions

### Theme tokens via CSS custom properties
All visual appearance is driven by a `:root` block of CSS variables that act as design tokens:
- Colors: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`.
- Spacing/shapes: `--radius` (8px), consistent font stack (`Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`).
- A global `color-scheme: dark` enforces a dark palette throughout.

These tokens are referenced everywhere instead of hard-coded colors, so changing the palette requires editing only the `:root` block.

### Layout model
- A fixed-height `app-shell` uses CSS Grid with a 230px sidebar and a fluid main area (`grid-template-columns: 230px minmax(0, 1fr)`).
- Views are `<section>` elements toggled via the `hidden` attribute; they are never destroyed, preserving chat history, session state, and loaded audit rows across navigation.
- Active view selection is tracked in JS via a `VIEWS` map and an `activeViewId`; the `.nav-item.active` class plus an inset accent border highlight the current function.

### Component vocabulary
Reusable UI building blocks are defined once and reused across views:
- Buttons: `.btn-sm` (small outlined button), `.btn-send` (primary action).
- Badges: `.status-badge` with semantic modifier classes (`pending`, `success`, `error`, `denied`, `sev-*`, `st-*`, `src-*`, `dsp-*`, `prio-*`) — each maps a value to a color using the token palette.
- Cards/panels: `.evidence-card`, `.user-card`, `.version-card`, `.incident-section`, `.tool-execution-card`.
- Code display: `.md-content pre/code` styled with `--code-bg` and monospace fonts (`JetBrains Mono`, `Fira Code`).
- Collapsible details: native `<details>/<summary>` used for evidence groups, audit detail rows, and raw output panels.

### Markdown rendering
Agent responses and triage reports are rendered through a built-in `renderMarkdown()` function in `app.js` that escapes HTML then applies regex-based transforms for code blocks, inline code, headers, bold/italic/strikethrough, links, blockquotes, lists, tables, and paragraphs. Styled via the `.md-content` selector family in `styles.css`.

### Responsive strategy
A single breakpoint at `@media (max-width: 800px)` switches from the two-column grid to a mobile layout:
- The sidebar becomes an off-canvas drawer toggled by a hamburger button in a new `.mobile-topbar`.
- A `.sidebar-backdrop` overlay closes the drawer on tap or Escape.
- The main area keeps full height; the drawer slides over it rather than stacking.

### Accessibility conventions
- Keyboard focus is always visible via a global `:focus-visible` rule with a 2px accent outline.
- Navigation items use `aria-current="page"` when active.
- The hamburger menu exposes `aria-expanded` and `aria-controls`.
- Decorative SVGs carry `aria-hidden="true"` while interactive buttons have explicit `aria-label`s.
- The `[hidden]` attribute is the authoritative visibility mechanism (CSS forces `display: none !important`).

### Role-gated views
Client-side gating hides nav items and actions based on the resolved identity's roles (`AUDIT_ROLES`, `INCIDENT_VIEW_ROLES`, `INCIDENT_ACT_ROLES` sets in `app.js`). Comments explicitly note this is convenience-only; the gateway re-enforces `audit:read`, `incident:*`, etc. on every request.

## Conventions and constraints

- **One stylesheet per product**: the operator portal centralizes all styling in `styles.css`; there are no scoped stylesheets, modules, or preprocessors.
- **Token-first styling**: colors, spacing, and radii come exclusively from `:root` CSS variables — no magic numbers for colors appear outside the token block.
- **Dark-mode only**: `color-scheme: dark` and the token values assume a dark background; no light-mode toggle exists.
- **Semantic badge modifiers**: status-like data is displayed by combining the shared `.status-badge` class with a kind+value modifier (e.g. `sev-critical`, `st-triaged`, `dsp-delivered`, `prio-high`), keeping presentation decoupled from data values.
- **Native collapsible sections**: expandable content uses `<details>/<summary>` rather than custom toggle widgets, relying on browser semantics.
- **Mobile-first responsive switch**: the desktop two-column layout is the default; mobile behavior is layered in via a single `@media (max-width: 800px)` block.
- **Versioned assets**: `index.html` loads `styles.css?v=20260817-incident-triage` and `app.js?v=20260817-incident-triage`, using a query-string cache-buster tied to the release tag.
- **No third-party CSS frameworks**: no Tailwind, Bootstrap, Material, or similar — the entire UI is hand-authored CSS.