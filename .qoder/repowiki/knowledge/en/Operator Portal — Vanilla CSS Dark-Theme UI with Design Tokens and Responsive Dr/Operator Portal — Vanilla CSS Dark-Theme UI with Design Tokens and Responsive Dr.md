---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark-Theme UI with Design Tokens and Responsive Drawer
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

The only frontend in this monorepo is the **operator-portal web UI** (`products/operator-portal/web-ui/`), built as a **vanilla HTML + CSS + JavaScript single-page application**. There is no component framework, build step, or CSS preprocessor. Styling is centralized in a single `styles.css` file loaded directly by `index.html`, with `app.js` handling view navigation, streaming chat rendering, and identity-driven gating.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — app shell (sidebar + main area) defining all views: Chat, Settings & Debug, and Audit trail (durable).
- `products/operator-portal/web-ui/styles.css` — the entire stylesheet (~850 lines) containing design tokens, layout, components, and responsive rules.
- `products/operator-portal/web-ui/app.js` — client-side logic that toggles views via the `hidden` attribute and renders streamed agent responses inline.
- `products/operator-portal/nginx.conf` — serves the static files; no asset pipeline.

No other product contains frontend code; the remaining services are Python FastAPI backends.

## Architecture and conventions

### Design tokens via CSS custom properties
All visual constants live in a `:root` block at the top of `styles.css`:
- Color palette: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`.
- Spacing/radius: `--radius: 8px`.
- The theme is explicitly dark via `color-scheme: dark`.

These tokens are reused everywhere (borders, backgrounds, text colors, status badges, code blocks), ensuring consistent appearance across sidebar, chat messages, settings panels, evidence cards, and audit tables.

### Layout model
- Two-column grid: `.app-shell { display: grid; grid-template-columns: 230px minmax(0, 1fr); }` — fixed-width sidebar + fluid main area.
- Sidebar holds branding, function nav, user card, and version info pinned to the bottom via `margin-top: auto`.
- Views are `<section>` elements toggled with the native `hidden` attribute; they are never destroyed so chat history and session state survive navigation.

### Component patterns
- **Buttons**: `.btn-sm` for small actions; `.icon-button` for icon-only controls (login/logout, menu toggle). Hover states use `--surface-alt`.
- **Cards**: `.user-card`, `.evidence-card`, `.evidence-turn` share border, radius, and surface color.
- **Status badges**: `.status-badge.pending|success|error|denied` derive from token colors.
- **Markdown rendering**: `.md-content` styles cover headings, lists, code, pre, blockquote, links, hr, tables — applied to streamed agent responses.
- **Evidence / tool execution**: per-turn collapsible groups using `<details>/<summary>` styled as `.evidence-turn` with inline tables for tool call results.
- **Audit table**: sticky header (`position: sticky; top: 0`) on `th` so column labels remain visible while scrolling through events.

### Responsive strategy
- A single `@media (max-width: 800px)` breakpoint switches the two-column grid to a single column.
- The sidebar becomes an **off-canvas drawer** (`transform: translateX(-100%)` → `translateX(0)`) with a translucent backdrop (`.sidebar-backdrop`).
- A mobile topbar (`.mobile-topbar`) appears only below 800px, exposing a hamburger button and portal title.
- Motion-sensitive users get `@media (prefers-reduced-motion: reduce)` which disables blinking dots, spinning spinners, and transitions while preserving visual state.

### Accessibility conventions
- Keyboard focus is explicit: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` ensures custom buttons stay visible.
- Interactive elements carry ARIA attributes (`aria-expanded`, `aria-controls`, `aria-haspopup`, `aria-label`, `role="menu"`).
- Decorative SVGs use `aria-hidden="true"`; meaningful icons (hamburger, login/logout arrows) are paired with `aria-label`.
- The `[hidden] { display: none !important; }` rule overrides any author-set `display:flex` to keep view toggling authoritative.

### Content structure
- Chat messages distinguish user vs agent via `.chat-msg.user-msg` (left accent border, surface background) and `.chat-msg.agent-msg` (transparent, left border).
- A "thinking…" placeholder with animated dots (`.thinking-dots`) signals first-token latency before content arrives.
- Settings & Debug exposes gateway URL, user ID, session/request IDs, and raw identity JSON in `<pre>` blocks.

## Conventions and constraints

- **Single-file stylesheet**: All styling lives in `styles.css`; there are no scoped/component stylesheets, CSS modules, or preprocessors.
- **Token-first**: New colors must be added to the `:root` variables rather than hard-coded literals elsewhere in the sheet.
- **View visibility via `hidden`**: New functions are added as a new `<button class="nav-item">` plus a sibling `<section class="view …" hidden>` — no routing library.
- **Dark theme only**: `color-scheme: dark` and the full token set lock the UI to a dark palette; no light-mode toggle exists.
- **Responsive threshold**: 800px is the sole breakpoint; no additional breakpoints are defined.
- **Reduced motion respected**: Animations for thinking dots, stream pulse, and spinner are wrapped in `prefers-reduced-motion`.
- **Role-gated views**: The Audit trail view button is `hidden` by default and shown only when the resolved identity carries an audit-allowed role (server re-enforces `audit:read` on every query).
- **Static serving**: The UI is served as plain static assets by nginx; cache-busting uses a query-string version suffix (`?v=20260813-usercard3`) on both `styles.css` and `app.js`.