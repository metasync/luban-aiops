---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark Theme with Design Tokens and Responsive Sidebar
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/app.js
    - products/operator-portal/nginx.conf
    - products/operator-portal/Dockerfile
---

## What system/approach is used

The Luban AIOps platform has a single, minimal frontend: the **operator-portal** web UI under `products/operator-portal/web-ui/`. It is a **vanilla HTML + CSS + JavaScript** application served by an nginx container (see `nginx.conf` in the same product directory). There are no component frameworks, CSS-in-JS libraries, preprocessors, or build tools — just three files:

- `index.html` — the app shell (sidebar + main area with multiple views)
- `styles.css` — all styling, including design tokens, layout, animations, and responsive rules
- `app.js` — client-side logic for navigation, OIDC login flow, streaming chat, evidence rendering, and audit trail pagination

The portal is intentionally lightweight: it renders markdown via a small inline regex-based renderer in `app.js`, uses native `<details>`/`<summary>` for collapsible sections, and communicates with backend services through plain `fetch()` calls.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — defines the two-column app shell, sidebar navigation (Chat / Settings & Debug / Audit trail), user card, and view sections. Views are toggled via the `hidden` attribute so state survives navigation.
- `products/operator-portal/web-ui/styles.css` — contains the entire visual style, including CSS custom properties (design tokens), layout, typography, animations, and media queries.
- `products/operator-portal/web-ui/app.js` — handles OIDC login/logout, token refresh, chat streaming, tool evidence rendering, cited guidance chips, and the durable audit trail view.
- `products/operator-portal/Dockerfile` and `products/operator-portal/nginx.conf` — serve the static files via nginx; no asset pipeline.

No other CSS/HTML/JS exists elsewhere in the repo. All other products are Python microservices with no frontend code.

## Architecture and conventions

### Design tokens
All colors, spacing, and radii are centralized in a `:root` block at the top of `styles.css`:

| Token | Value | Usage |
|---|---|---|
| `--bg` | `#0f172a` | Page background |
| `--surface` | `#1e293b` | Cards, sidebar, inputs |
| `--surface-alt` | `#334155` | Hover states, table headers |
| `--border` | `#475569` | Borders, dividers |
| `--text` | `#e2e8f0` | Primary text |
| `--text-muted` | `#94a3b8` | Secondary text, labels |
| `--accent` | `#38bdf8` | Links, active nav, primary buttons |
| `--accent-hover` | `#7dd3fc` | Hover on accent elements |
| `--success` | `#4ade80` | Success badges, stream dot |
| `--error` | `#f87171` | Error badges, denied outcomes |
| `--warning` | `#fbbf24` | Warning states |
| `--code-bg` | `#1a2332` | Code blocks, preformatted output |
| `--radius` | `8px` | Border radius everywhere |

The theme is explicitly set to dark mode via `color-scheme: dark`.

### Layout model
A fixed two-column grid (`grid-template-columns: 230px minmax(0, 1fr)`) creates a left sidebar and a flexible main area. The sidebar holds branding, identity controls, and function navigation; the main area hosts one `view` at a time (chat, settings, audit). Views are never destroyed — they are shown/hidden via the `hidden` attribute, preserving scroll position and DOM state.

### Typography
Font stack: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`. Monospace font stack for code: `"JetBrains Mono", "Fira Code", monospace`.

### Responsive strategy
Below `800px` the sidebar collapses into an off-canvas drawer triggered by a hamburger button in a mobile topbar. The drawer slides in from the left with a backdrop overlay. Transitions and animations are disabled for users who prefer reduced motion via `@media (prefers-reduced-motion: reduce)`.

### Accessibility conventions
- Keyboard focus is visible via a global `:focus-visible` rule using `--accent`.
- Navigation items use `aria-current="page"` when active.
- The mobile menu button exposes `aria-expanded` and `aria-controls`.
- The user popup menu uses `role="menu"` and `aria-haspopup="menu"`.
- Decorative SVGs carry `aria-hidden="true"`.
- The `[hidden]` attribute is authoritative — even if author styles set `display:flex`, hidden elements are forced to `display: none !important`.

### View/function pattern
New features are added as another sidebar button plus a sibling `<section class="view ...">` in the HTML. The `VIEWS` map in `app.js` wires them together. Role-gated views (like the audit trail) are hidden via `nav.hidden = true` based on the resolved identity's roles.

### Evidence and audit UI patterns
- Tool execution evidence is rendered as per-turn `<details>` groups appended inline after the agent reply that grounds them.
- Status badges use semantic classes: `.status-badge.pending`, `.status-badge.success`, `.status-badge.error`, `.status-badge.denied`.
- The durable audit trail view uses a sticky-header table (`position: sticky; top: 0`) with a persistent toolbar above and a pagination footer below.

## Conventions and constraints

1. **Single-file CSS**: All styles live in `styles.css`; there are no component-scoped stylesheets, no CSS modules, and no preprocessors.
2. **CSS custom properties for theming**: New colors must be added to the `:root` block and referenced via `var(--name)` — raw hex values should not be duplicated across selectors.
3. **Dark-only theme**: `color-scheme: dark` is set globally; no light-mode toggle exists.
4. **Responsive breakpoint**: The only breakpoint is `800px` for the mobile drawer; no other breakpoints exist.
5. **Motion policy**: Animations (`thinking-blink`, spinner rotation, drawer transition) are suppressed under `prefers-reduced-motion: reduce`.
6. **View visibility**: Views are controlled exclusively via the `hidden` attribute; JS should not toggle `display` directly for view switching.
7. **No external CSS dependencies**: No CDN links, no import statements, no bundler — everything is self-contained in the three files.
8. **Static assets versioned by query string**: The stylesheet and script are loaded with cache-busting query strings (`?v=20260816-cited-guidance`).
9. **Role gating is client convenience only**: Comments in `app.js` explicitly state that server-side enforcement (e.g., `audit:read`) is the source of truth; the UI hides the audit view but does not rely on it for security.