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
    - products/operator-portal/nginx.conf
---

## What system/approach is used

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla HTML/CSS/JS single-page application** served by an embedded Nginx container. There is no build step, component framework, or CSS preprocessor. Styling is implemented as a single `styles.css` file that defines a dark-themed design token palette via CSS custom properties and applies them throughout the app shell, sidebar navigation, chat view, audit trail, incidents triage, permissions matrix, tools catalog, and skills inventory views.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — static HTML defining the two-column app shell (sidebar + main area) and all function views; views are toggled via the `hidden` attribute rather than destroyed/recreated.
- `products/operator-portal/web-ui/styles.css` — the entire stylesheet (~1200 lines), organized into sections: design tokens (`:root` variables), app shell, sidebar, chat, settings/debug, markdown rendering, evidence/audit cards, HITL confirmation cards, durable audit trail table, incidents triage form, and pagination.
- `products/operator-portal/web-ui/app.js` — client-side logic for view switching, streaming chat, identity/session management, and server calls (not styled).
- `products/operator-portal/nginx.conf` / `Dockerfile` — serve the static assets; no asset pipeline.

## Architecture and conventions

### Design tokens
All colors, spacing, and radii are centralized in `:root`:
- Color scheme: `color-scheme: dark` sets native OS-level dark mode.
- Semantic palette: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`, `--radius`.
- Typography: Inter font stack with monospace fallbacks for code (`JetBrains Mono`, `Fira Code`).

### Layout model
- Two-column grid layout: `.app-shell` uses `grid-template-columns: 230px minmax(0, 1fr)` to pin a fixed-width sidebar and fluid main area.
- Sidebar contains branding/logo, grouped navigation sections (`nav-section` with muted labels), and a pinned user card at the bottom via `margin-top:auto`.
- Views are sibling `<section>` elements inside `.main-area`; only one is visible at a time, toggled by adding/removing the `hidden` attribute. The `[hidden] { display: none !important; }` rule ensures author rules cannot override visibility.

### Component patterns
- **Navigation items**: `.nav-item` with `.active` state using an inset left accent border (`box-shadow: inset 3px 0 0 var(--accent)`).
- **Status badges**: `.status-badge` variants for `pending`, `success`, `error`, `denied`, and mutating actions (`mutating` per SPEC-021 R-3).
- **Evidence/audit cards**: Collapsible `<details>/<summary>` blocks with `.evidence-turn`, `.evidence-card`, and inline tool execution tables (`.tool-execution-card`).
- **HITL confirmation cards**: `.confirm-card` with warning-toned borders, approve/deny action buttons, and locked-state styling via `[data-locked="true"]`.
- **Tables**: Shared `.audit-table` and `.tools-table` with sticky headers, fixed column widths for the tools catalog, and hover row highlighting.
- **Markdown content**: `.md-content` styles for headings, lists, code blocks, blockquotes, links, horizontal rules, and tables rendered from agent responses.

### Accessibility
- Explicit `:focus-visible` outline using the accent color.
- ARIA attributes on interactive elements (`aria-expanded`, `aria-haspopup`, `aria-label`, `role="menu"`, `aria-current="page"`).
- Keyboard focus must remain visible on custom buttons.

### Responsive strategy
- A mobile top bar with hamburger menu appears below 800px (defined in `index.html` comments); the sidebar becomes an off-canvas drawer controlled by JS, while the main area retains full height.
- No media-query breakpoints are present in the provided snippet beyond the mobile topbar behavior described in comments.

### Versioning
- The stylesheet link includes a cache-busting query string tied to spec releases: `?v=20260821-spec-021-mutate-1`, keeping UI assets synchronized with spec versions.

## Conventions and constraints

- **No CSS frameworks or preprocessors** — everything is plain CSS custom properties and class selectors.
- **Design tokens are the single source of truth** for colors, spacing, and radius; new UI elements should consume `var(--*)` variables rather than hardcoding values.
- **View visibility is exclusively managed via the `hidden` attribute**, never via JS-driven `display` toggles, so CSS can enforce it authoritatively.
- **Role-gated features** (Incidents, Audit, Permissions, Tools, Skills) are hidden by default in the HTML and revealed only after identity resolution; the server re-enforces policy on every request regardless of this client-side gating.
- **Section-based navigation grouping** follows SPEC-019 R-1: nav entries are grouped under labeled sections (`Control`, `Workspace`) that hide themselves when all child entries are hidden.
- **Dark-only theme** — `color-scheme: dark` is set globally; no light-mode toggle exists.
- **Sticky headers** are used for long tables (audit results, tools catalog) to keep column labels visible during scroll.