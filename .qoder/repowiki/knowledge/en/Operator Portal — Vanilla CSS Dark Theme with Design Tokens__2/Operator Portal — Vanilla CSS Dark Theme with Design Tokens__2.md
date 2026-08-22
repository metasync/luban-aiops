---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark Theme with Design Tokens
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/app.js
    - products/operator-portal/Dockerfile
    - products/operator-portal/nginx.conf
---

## What system/approach is used

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla HTML + CSS + JavaScript** single-page application. There is no component framework, CSS-in-JS library, or build toolchain — just three files served by an nginx container:

- `index.html` — the app shell and view templates (Chat, Audit trail, Incidents, Permissions, Tools, Skills, Settings & Debug).
- `styles.css` — the entire stylesheet (~1200 lines), defining a dark theme via CSS custom properties.
- `app.js` — client-side routing, authentication flow, streaming chat, and data views.

No preprocessors (SCSS/Less), no Tailwind, no design-system package. The UI is styled directly in a single CSS file using BEM-style class names and CSS variables.

## Key files and packages

- `products/operator-portal/web-ui/styles.css` — design tokens, layout, component styles, markdown/evidence/incident styling.
- `products/operator-portal/web-ui/index.html` — semantic HTML structure with ARIA attributes (`aria-expanded`, `aria-current`, `role="menu"`, `aria-label`).
- `products/operator-portal/web-ui/app.js` — DOM manipulation, fetch calls to `/api/v1/*`, role-based gating, streaming SSE handling.
- `products/operator-portal/nginx.conf` / `Dockerfile` — serve the static files; no asset pipeline.

There are no `package.json`, `tailwind.config.*`, `theme.*`, or component-library references anywhere in the repo for this portal.

## Architecture and conventions

### Design tokens
All colors, spacing, and typography are centralized in a `:root` block at the top of `styles.css`:

```css
:root {
  color-scheme: dark;
  --bg: #0f172a;
  --surface: #1e293b;
  --surface-alt: #334155;
  --border: #475569;
  --text: #e2e8f0;
  --text-muted: #94a3b8;
  --accent: #38bdf8;
  --accent-hover: #7dd3fc;
  --success: #4ade80;
  --error: #f87171;
  --warning: #fbbf24;
  --code-bg: #1a2332;
  --radius: 8px;
}
```

Semantic token names (`--bg`, `--surface`, `--text-muted`, `--accent`, `--success`, `--error`, `--warning`) are reused throughout the stylesheet rather than hard-coded hex values. The `color-scheme: dark` declaration enables native browser dark-mode form controls.

### Layout
- Two-column grid shell: `.app-shell { display: grid; grid-template-columns: 230px minmax(0, 1fr); }` — fixed-width sidebar + fluid main area.
- Sidebar uses flex column with `margin-top: auto` on the footer so the user card pins to the bottom while the function list stays clean.
- Views are sibling `<section>` elements toggled via the `hidden` attribute; they are never destroyed, preserving chat history and loaded data across navigation.

### Component vocabulary
Reusable patterns are expressed as classes, not components:
- Buttons: `.btn-sm`, `.btn-send`, `.icon-button`.
- Status badges: `.status-badge.success | .error | .pending | .denied | .mutating`.
- Tables: shared `.audit-table` plus per-view modifiers (`policy-matrix-table`, `tools-table`).
- Evidence cards: `.evidence-card`, `.evidence-turn`, `.confirm-card`.
- Markdown content: `.md-content` with rules for headings, code blocks, tables, blockquotes.

### Responsive strategy
- Mobile drawer: below ~800px the sidebar becomes an off-canvas drawer toggled by a hamburger button (`#menu-button`), with a backdrop overlay. Above 800px the drawer classes have no effect.
- No media-query breakpoints are defined in the current CSS snippet; the mobile behavior is driven by JS toggling an `.open` class and the `sidebar-backdrop` element.

### Accessibility
- Keyboard focus is explicit: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }`.
- Navigation items use `aria-current="page"` when active.
- Menu buttons declare `aria-expanded`, `aria-haspopup="menu"`, and `aria-label`.
- SVG icons carry `aria-hidden="true"`.

### Theming constraints
- The portal is **dark-only**: `color-scheme: dark` and all tokens are dark palette values. There is no light-theme toggle or `@media (prefers-color-scheme)` override.
- The accent color (`--accent: #38bdf8`) drives interactive highlights, links, and the active nav indicator inset border.
- Code blocks use a dedicated `--code-bg` background with monospace font stack (`JetBrains Mono`, `Fira Code`, monospace).

## Conventions and constraints

Observed conventions (descriptive):
- All visual state lives in `styles.css`; there is no inline `style=` usage in the HTML beyond minimal dynamic overrides in `app.js` (e.g., `p.style.color = "var(--error)"` for error messages).
- View visibility is controlled exclusively through the `hidden` attribute and the `.active` class on nav items — no `display: none` toggling in JS.
- Role-based UI gating is implemented in `app.js` by checking `currentRoles()` against role sets (`AUDIT_ROLES`, `INCIDENT_VIEW_ROLES`, `INCIDENT_ACT_ROLES`) and hiding/showing nav entries accordingly; comments explicitly note that server-side policy re-enforcement happens on every request regardless.
- Section headers (`.nav-section`) hide automatically when every entry inside them is hidden, via `syncNavSectionVisibility()`.
- Version display is a hardcoded constant `PLATFORM_VERSION = "v0.8.0"` in `app.js`, synchronized with the root `VERSION` file via `make validate-version` (enforced by the Makefile target referenced in comments).
- Asset cache-busting uses query-string version stamps on the CSS and JS `<script>` tags (e.g., `?v=20260822-spec-022-sessions-1`).

Enforced rules (from documented specs referenced in code comments):
- SPEC-019 R-1: Platform version chip must match the root VERSION file; enforced by `make validate-version`.
- SPEC-019 R-1: Function navigation is grouped into sections (Control, Workspace) with automatic section-header hiding.
- SPEC-019 R-3: Permissions matrix view renders the live role × action policy bundle from the gateway.
- SPEC-019 R-4: Tools and Skills views are read-only inventories proxied through the gateway.
- SPEC-011 R-4: Chat evidence is rendered inline after each agent reply in collapsed groups.
- SPEC-013 R-5: Durable audit trail view is role-gated (auditor / platform-admin) and paginated with cursor-based loading.
- SPEC-015 R-6: Incident triage view supports list/detail/report modes with auto-refresh.
- SPEC-020 R-4: HITL confirmation cards render inline approval surfaces with warning-toned borders.
- SPEC-021 R-3: Mutating tools show a required-confirmation badge in the catalog.

Constraints that do NOT exist:
- No responsive breakpoint system is defined in CSS; mobile behavior is handled via JS-driven drawer toggling.
- No CSS modules, scoped styles, or component libraries are used — everything is global class names in one stylesheet.
- No theme switching mechanism exists; the portal is locked to the dark palette.