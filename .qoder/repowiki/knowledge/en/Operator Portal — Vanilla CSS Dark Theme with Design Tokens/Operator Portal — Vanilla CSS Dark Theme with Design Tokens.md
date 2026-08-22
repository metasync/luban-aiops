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

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla HTML + CSS + JavaScript** single-page application served by Nginx. There is no component framework, build step, or CSS preprocessor. Styling is centralized in a single `styles.css` file and driven entirely by **CSS custom properties (design tokens)** defined in the `:root` block. The UI is dark-only (`color-scheme: dark`).

## Key files and packages

- `products/operator-portal/web-ui/styles.css` — all visual styling, design tokens, layout, animations, and responsive behavior.
- `products/operator-portal/web-ui/index.html` — static shell defining the two-column app shell, sidebar navigation, and per-function `<section>` views (chat, audit trail, incidents, permissions, tools, skills, settings).
- `products/operator-portal/web-ui/app.js` — client-side routing, view state, markdown renderer, auth/session handling, and data rendering; contains no styling logic beyond inline error colors.
- `products/operator-portal/nginx.conf` — serves the three files as a static site.

No other frontend assets exist elsewhere in the repo; all other products are Python microservices with no browser-facing code.

## Architecture and conventions

### Design tokens
All colors, spacing, and radii are declared once in `:root`:
- Backgrounds: `--bg`, `--surface`, `--surface-alt`
- Borders: `--border`
- Text: `--text`, `--text-muted`
- Semantic: `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`
- Sizing: `--radius` (8px)

Every rule references these variables rather than hard-coded hex values, so theming changes flow through one place.

### Layout model
- Two-column grid: `.app-shell { display: grid; grid-template-columns: 230px minmax(0, 1fr); }` — fixed-width sidebar + fluid main area.
- Sidebar uses flex column with `margin-top: auto` on `.sidebar-footer` to pin the user card to the bottom, separating identity state from function navigation.
- Views are sibling `<section class="view ...">` elements toggled via the `hidden` attribute; they are never destroyed so chat history and loaded tables survive navigation.

### Responsive strategy
- A mobile top bar (`.mobile-topbar`) with a hamburger button appears below 800px; the sidebar becomes an off-canvas drawer controlled by adding/removing the `.open` class and showing/hiding a backdrop element.
- Above 800px the drawer classes have no effect — the sidebar is always visible.
- No media-query breakpoints are needed for the main layout because the grid's `minmax(0, 1fr)` handles overflow gracefully.

### Component vocabulary
Reusable class names form a small shared vocabulary across views:
- Buttons: `.btn-sm`, `.btn-send`, `.icon-button`
- Tables: `.audit-table`, `.tools-table`, `.policy-matrix-table` (all reuse header/footer/status patterns)
- Badges: `.status-badge` with semantic suffixes (`pending`, `success`, `error`, `denied`, `mutating`)
- Cards: `.evidence-card`, `.confirm-card`, `.tool-execution-card`
- Sections: `.settings-section`, `.nav-section` (auto-hides when every entry inside is hidden)
- Feedback: `.thinking` / `.thinking-dots` with a `thinking-blink` keyframe animation, `.spinner`

### Markdown rendering
A built-in regex-based markdown renderer in `app.js` converts agent responses into HTML that matches the `.md-content` styles in `styles.css` (headings, lists, tables, code blocks, blockquotes). This keeps rendered content visually consistent without pulling in a library.

### Accessibility conventions
- `:focus-visible` gets a 2px accent-colored outline on custom buttons.
- Navigation items use `aria-current="page"` when active.
- Mobile menu buttons carry `aria-expanded` and `aria-label` attributes.
- SVG icons are marked `aria-hidden="true"` with descriptive labels on their parent buttons.
- The `[hidden]` attribute is treated as authoritative (`display: none !important`) even if author rules set `display:flex`.

### Versioning
The stylesheet link includes a cache-busting query string derived from the spec version (`?v=20260821-spec-021-mutate-1`), and the platform version chip in the sidebar is pinned to the root `VERSION` file (enforced by `make validate-version`).

## Conventions and constraints

- **Single-file CSS**: All styles live in `styles.css`; there are no scoped/component stylesheets, preprocessors, or CSS modules.
- **Dark-only theme**: `color-scheme: dark` is set globally; no light-mode toggle exists.
- **Token-first**: New colors must be added to `:root` and referenced via `var(--name)`, not raw hex values.
- **Semantic badge classes**: Status indicators use `.status-badge.<kind>-<value>` (e.g., `sev-critical`, `st-triaging`, `src-alertmanager`) so color mapping stays centralized.
- **View gating is client-side only**: Role visibility of nav items is enforced in `app.js` but comments repeatedly note that the gateway re-enforces policy on every request — the UI gate is convenience only.
- **No external CSS dependencies**: No CDN links, no frameworks, no build toolchain — the portal is deployable as plain static files behind Nginx.