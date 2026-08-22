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

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla single-page application** served by nginx. It uses:
- A single `styles.css` file (no preprocessors, no framework).
- A single `app.js` module for DOM manipulation and routing.
- A static `index.html` that declares the two-column app shell and all view sections.
- No component library, no CSS-in-JS, no build step beyond versioned asset cache-busting via query strings.

Styling is driven entirely by **CSS custom properties (design tokens)** declared in `:root`, establishing a dark theme with semantic color roles and spacing/radius tokens.

## Key files and packages
- `products/operator-portal/web-ui/styles.css` — all visual styling, design tokens, layout, animations, and responsive behavior.
- `products/operator-portal/web-ui/index.html` — semantic HTML structure, role-gated nav items, ARIA attributes, and `<section>` views.
- `products/operator-portal/web-ui/app.js` — client-side router, markdown renderer, auth/session handling, and view renderers.
- `products/operator-portal/nginx.conf` — serves the three static files.

## Architecture and conventions

### Design tokens
All colors, spacing, and radii are centralized in `:root` at the top of `styles.css`:
- Backgrounds: `--bg`, `--surface`, `--surface-alt`
- Text: `--text`, `--text-muted`
- Borders: `--border`
- Semantic colors: `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`
- Code background: `--code-bg`
- Radius: `--radius`

Typography uses `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`; code uses `"JetBrains Mono", "Fira Code", monospace`.

### Layout
- Two-column grid: `.app-shell { display: grid; grid-template-columns: 230px minmax(0, 1fr); }` — fixed-width sidebar + fluid main area.
- Sidebar uses flex column with `margin-top: auto` on the footer to pin identity controls below the function list.
- Views are `<section class="view ...">` elements toggled via the `hidden` attribute; views are never destroyed so chat history and state survive navigation.
- Navigation sections (`.nav-section`) hide their label when every entry inside them is hidden.

### Responsive strategy
- Mobile breakpoint at `800px`: a hamburger header (`.mobile-topbar`) opens the sidebar as an off-canvas drawer with a backdrop overlay.
- Above 800px the drawer classes have no effect; the sidebar is always visible.
- Chat input bar, settings grid, and tables use `flex`/`grid` with `minmax`/`auto-fit` for fluid reflow.

### Component vocabulary
Reusable patterns are defined as classes rather than components:
- Buttons: `.btn-sm`, `.btn-send`, `.icon-button`
- Badges: `.status-badge` with kind prefixes (`pending`, `success`, `error`, `denied`, `mutating`, `sev-*`, `st-*`, `src-*`, `prio-*`)
- Cards: `.evidence-card`, `.confirm-card`, `.tool-execution-card`
- Tables: `.audit-table`, `.policy-matrix-table`, `.tools-table` (fixed layout with explicit column widths)
- Inputs: shared border/background/focus styles across settings, audit toolbar, incidents form
- Markdown rendering: `.md-content h1..h6`, `.md-content pre/code`, `.md-content blockquote`, `.md-content table`

### Animations
- `thinking-blink` keyframes animate the three-dot "thinking…" indicator and the stream pulse dot on the Chat nav item.
- `spin` keyframes power the spinner element.

### Accessibility
- `color-scheme: dark` set globally.
- `[hidden] { display: none !important; }` ensures JS-driven visibility wins over inline styles.
- `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` keeps focus visible on custom buttons.
- ARIA attributes (`aria-expanded`, `aria-haspopup`, `aria-current`, `aria-label`, `role="menu"`) on interactive elements.
- Keyboard support: Escape closes the mobile drawer and user menu.

### View-specific conventions
- Audit trail, incidents, permissions, tools, and skills views share a consistent toolbar/results/footer pattern (filters on top, scrollable results, status line below).
- Evidence and HITL confirmation cards follow SPEC references embedded in comments (SPEC-011, SPEC-013, SPEC-015, SPEC-019, SPEC-020, SPEC-021).
- Role gating is implemented client-side via `Set` lookups against `currentRoles()` but comments consistently note that the server re-enforces policy on every request.

## Conventions and constraints
- **No CSS frameworks or preprocessors** — everything is plain CSS.
- **Single-file stylesheet** — all styles live in one `styles.css`; there is no modularization or component-scoped CSS.
- **Design tokens are the single source of truth** for colors, radius, and semantic meaning; new UI elements should consume `var(--*)` rather than hardcoding values.
- **Dark theme is enforced** via `color-scheme: dark` and token values; no light-mode toggle exists.
- **Views are hidden, not unmounted** — navigation toggles `hidden` and `active` classes; this preserves state across switches.
- **Mobile-first drawer**: sidebar becomes an off-canvas drawer under 800px using the same CSS classes; no separate mobile stylesheet.
- **Versioning**: CSS and JS are loaded with query-string cache busters (`?v=20260822-spec-022-sessions-1`) tied to spec releases.
- **Role-based visibility** follows the convention of hiding nav entries via `hidden` and guarding view content with JS role checks, while relying on the gateway for actual authorization.