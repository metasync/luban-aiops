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

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla HTML + CSS + JavaScript** single-page application served by nginx. There is no build step, framework, or component library. Styling lives entirely in one stylesheet (`styles.css`), the markup in `index.html`, and behavior in `app.js`. The UI uses a **CSS custom properties (design tokens) dark theme** defined in `:root` at the top of the stylesheet.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — single-page shell with two-column layout (sidebar + main area) and hidden `<section>` views for Chat, Audit trail, Incidents, Permissions, Tools, Skills, Settings & Debug.
- `products/operator-portal/web-ui/styles.css` — all visual styling; defines the design token palette, layout, components, and view-specific styles.
- `products/operator-portal/web-ui/app.js` — client-side routing, markdown rendering, OIDC session management, and data-driven views over the gateway API.
- `products/operator-portal/nginx.conf` — serves the static assets.

No external CSS frameworks, preprocessors, or JS libraries are referenced; fonts are loaded via system font stacks (`Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`) and code via `"JetBrains Mono", "Fira Code", monospace`.

## Architecture and conventions

### Design tokens
All colors, spacing, and radii are centralized in `:root`:
- Background/surface/border tokens: `--bg`, `--surface`, `--surface-alt`, `--border`
- Text tokens: `--text`, `--text-muted`
- Semantic tokens: `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`
- Utility tokens: `--code-bg`, `--radius`

This makes the entire portal a **dark theme only** (`color-scheme: dark`).

### Layout
- Two-column grid: fixed 230px sidebar + fluid main area (`grid-template-columns: 230px minmax(0, 1fr)`).
- Mobile drawer: below 800px the sidebar becomes an off-canvas drawer toggled by a hamburger button; a backdrop closes it.
- Views are never destroyed — they are toggled via the `hidden` attribute so chat history, audit rows, and session state survive navigation.

### Component vocabulary
Reusable patterns are consistently applied across views:
- `.status-badge` with semantic kind prefixes (`pending`, `success`, `error`, `denied`, `mutating`, plus incident kinds `sev-*`, `st-*`, `src-*`, `dsp-*`, `prio-*`).
- `.audit-toolbar` / `.audit-results` / `.audit-footer` shared between Audit trail, Incidents, Permissions, Tools, and Skills views to keep filter bars, scrollable results, and pagination consistent.
- `.btn-sm` for small action buttons.
- `.evidence-*` classes for inline tool-call evidence grouped per chat turn.
- `.confirm-card` for human-in-the-loop approval surfaces.
- `.md-content` rules style server-rendered Markdown inside the chat stream.

### Accessibility
- `:focus-visible` outline using `--accent` on all interactive elements.
- ARIA attributes on the mobile menu (`aria-expanded`, `aria-controls`, `aria-label`), user menu (`role="menu"`, `aria-haspopup`), and active nav item (`aria-current="page"`).
- `[hidden] { display: none !important; }` ensures the `hidden` attribute is authoritative even when author rules set `display:flex`.

### Responsive strategy
- Desktop-first grid with a breakpoint at ~800px that switches the sidebar into a drawer mode.
- No media-query-based color/theme switching — the dark palette is always active.
- Tables use explicit column widths (e.g., tools table) to prevent free-form description columns from collapsing other columns to border width.

### Security posture reflected in the UI
- Role-gated navigation entries (Audit, Incidents, Permissions, Tools, Skills) are hidden until the resolved identity qualifies; comments repeatedly note that this is client-side convenience only and the gateway re-enforces policy on every request.
- Confirmation cards carry a warning-toned border and a `data-locked` attribute to visually distinguish pending vs. locked HITL decisions.

## Conventions and constraints

- **Single stylesheet**: all styles live in `styles.css`; there are no scoped/component CSS modules, SCSS, or CSS-in-JS.
- **Design tokens first**: new colors must be added as CSS variables in `:root` rather than hard-coded hex values elsewhere.
- **Dark-only theme**: `color-scheme: dark` is enforced globally; no light-mode toggle exists.
- **View reuse pattern**: list/detail/filter/footer layouts reuse `.audit-toolbar`, `.audit-results`, `.audit-footer`, and `.audit-table` across multiple feature views instead of defining per-view table styles.
- **Status badges**: all status indicators go through `.status-badge` with a semantic modifier class; ad-hoc colored spans are not used.
- **Markdown content**: rendered Markdown is wrapped in `.md-content` so the dedicated typography rules apply uniformly.
- **Mobile drawer**: any new full-screen view should respect the existing `#sidebar-backdrop` overlay and `setSidebarDrawerOpen` helper so navigation remains consistent on narrow screens.
- **Version chip**: the platform version shown in the sidebar logo row is kept in sync with the root `VERSION` file via `make validate-version`; long-term it will be sourced from the gateway `/api/v1/version` endpoint.