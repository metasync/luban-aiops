---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark Theme with Design Tokens and View-Based Layout
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

The only frontend in this repository is the **Operator Portal** (`products/operator-portal/web-ui/`), a single-page application built with vanilla HTML, CSS, and JavaScript served by an embedded Nginx container. There is no component framework, build step, or CSS preprocessor — styling is pure CSS loaded directly via `<link>`.

The visual style is a **dark theme** defined entirely through CSS custom properties (design tokens) on `:root`, establishing a consistent palette of background, surface, border, text, accent, success, error, warning, and code colors. A shared `--radius: 8px` token standardizes corner radii across buttons, cards, inputs, and badges.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — app shell, sidebar navigation, and view containers for Chat, Settings & Debug, Incidents, Audit trail, Permissions, Tools, and Skills.
- `products/operator-portal/web-ui/styles.css` — all styling, organized as a flat stylesheet grouped by UI region (sidebar, chat, settings, markdown rendering, evidence/audit tables, incidents triage).
- `products/operator-portal/web-ui/app.js` — client-side routing between views, authentication flow, data fetching, and DOM rendering; contains inline Markdown-to-HTML conversion rather than a library.
- `products/operator-portal/nginx.conf` — serves the three static files from a minimal Nginx image.

No external CSS frameworks, design systems, or component libraries are referenced. The font stack defaults to Inter with system fallbacks; monospace uses JetBrains Mono / Fira Code.

## Architecture and conventions

### Design tokens
All colors and spacing primitives live in `:root` variables at the top of `styles.css`. Components consume them exclusively — there are no hard-coded color literals elsewhere in the stylesheet. This makes the dark theme swappable by overriding the root variables.

### Two-column app shell
The layout is a fixed-width sidebar (`230px`) plus a fluid main area, implemented with CSS Grid (`grid-template-columns: 230px minmax(0, 1fr)`). On screens ≤ 800px the sidebar becomes an off-canvas drawer toggled by a hamburger button, with a backdrop overlay that closes it on tap or Escape.

### View-based navigation
Each function (Chat, Settings, Incidents, Audit, Permissions, Tools, Skills) is a `<section class="view">` hidden via the native `hidden` attribute. Navigation never destroys DOM nodes — it toggles visibility so chat history, session state, and loaded audit rows persist across switches. Active view is indicated by an `.active` class with an accent-colored left inset border.

### Role-gated sections
Navigation entries are grouped into two collapsible sections — **Control** (Incidents, Audit, Permissions) and **Workspace** (Tools, Skills, Settings). Section headers hide automatically when every entry inside them is hidden, driven by `syncNavSectionVisibility()` in `app.js`. Visibility is gated by role sets (`AUDIT_ROLES`, `INCIDENT_VIEW_ROLES`, `INCIDENT_ACT_ROLES`) and re-enforced server-side by the gateway policy engine.

### Shared table vocabulary
Audit events, permissions matrix, tools catalog, skills inventory, and incidents list all reuse a common table pattern: an `audit-toolbar` filter bar above, an `audit-results` scrollable body, and an `audit-footer` status line below. Tables use the shared `.audit-table` class with sticky header columns and hover-highlighted rows.

### Status and semantic badges
A single `.status-badge` class carries shape and typography; semantic meaning is conveyed by suffix classes (`success`, `error`, `denied`, `pending`). Incident-specific variants extend this with `sev-*`, `st-*`, `src-*`, `dsp-*`, `prio-*` prefixes applied via `incidentBadge()` in `app.js`, keeping color semantics centralized in the stylesheet.

### Markdown rendering
Agent responses and triage reports are rendered through a small inline Markdown-to-HTML converter in `app.js` that escapes HTML first, then transforms headings, lists, links, blockquotes, code blocks, tables, bold/italic, strikethrough, and paragraphs. Styles for `.md-content` provide matching dark-theme typography for headings, code, blockquotes, tables, and horizontal rules.

### Evidence and tool-execution panels
Per-turn evidence groups (tool calls, audit references, cited guidance chips) are rendered as collapsed `<details>` blocks appended after each agent message, using `.evidence-turn`, `.evidence-card`, `.cited-chips`, and `.cited-chip` classes. Tool execution details use a dedicated `.tool-execution-card` table.

## Conventions and constraints

- **Dark-only**: `color-scheme: dark` is set globally; no light-mode toggle exists.
- **CSS custom properties are the single source of truth** for colors, radius, and spacing — new components must derive values from `var(--*)` rather than introducing new literals.
- **Accessibility baseline**: `[hidden] { display: none !important }` overrides author rules; `:focus-visible` gets a 2px accent outline; interactive elements carry `aria-*` attributes (`aria-expanded`, `aria-haspopup`, `aria-current`, `aria-label`); SVG icons use `aria-hidden="true"`.
- **Mobile-first responsive behavior**: the sidebar drawer pattern activates at ≤ 800px via CSS classes toggled by JS; beyond that width the drawer styles have no effect.
- **No build step**: files are served raw; cache busting is done via query-string version stamps on `<link>` and `<script>` tags (e.g. `?v=20260820-tools-columns`).
- **Client-side gating is convenience only**: comments throughout `app.js` explicitly state that role checks hide UI elements but the gateway re-enforces policies (`audit:read`, `incident:*`, `policy:read`, `tools:list`, `skills:read`) on every request.
- **Version chip**: the platform version displayed in the logo row is sourced from a constant in `app.js` and must match the root `VERSION` file, enforced by `make validate-version`.