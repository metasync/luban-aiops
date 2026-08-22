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

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla HTML + CSS + JavaScript** single-page application. There is no component framework, CSS-in-JS library, or build-time toolchain (no Tailwind, Sass, PostCSS, webpack, Vite, etc.). Styling is delivered as a single `styles.css` file linked directly from `index.html`, and behavior lives in a single `app.js`. The UI is served by an Nginx container that statically hosts these three files.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — app shell: two-column layout (sidebar + main), mobile topbar, view sections for Chat / Settings & Debug / Audit trail.
- `products/operator-portal/web-ui/styles.css` — all visual styling, design tokens, responsive rules, animations, and accessibility preferences.
- `products/operator-portal/web-ui/app.js` — DOM manipulation, view navigation, markdown rendering, streaming chat, OIDC auth flow, audit table rendering.
- `products/operator-portal/nginx.conf` — serves the static web UI.

No other frontend assets exist elsewhere in the repository; the remaining products are Python FastAPI services with no client-side code.

## Architecture and conventions

### Design tokens via CSS custom properties
All colors, spacing, and radii are centralized in a `:root` block at the top of `styles.css`:
- Color palette: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`.
- Typography: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`.
- Spacing/radius: `--radius: 8px`.
- Semantic roles: `color-scheme: dark` forces the browser's native dark UI chrome.

This token layer is the single source of truth — every color in the stylesheet references a variable rather than a hard-coded hex value.

### Layout model
- Desktop: CSS Grid `.app-shell` with a fixed 230px sidebar and a fluid main area (`grid-template-columns: 230px minmax(0, 1fr)`).
- Mobile (≤800px): the grid collapses to one column; the sidebar becomes a fixed-position off-canvas drawer (`transform: translateX(-100%)`) toggled via JS class `.open`, with a semi-transparent backdrop.
- Views are `<section>` elements toggled via the `hidden` attribute — they are never destroyed so chat history, session state, and loaded audit rows survive navigation.

### Component-style classes
There is no component framework, but the CSS defines reusable visual primitives:
- Buttons: `.btn-sm`, `.btn-send`, `.icon-button`.
- Cards: `.user-card`, `.evidence-card`, `.tool-execution-card`.
- Badges: `.status-badge` with semantic variants (`.pending`, `.success`, `.error`, `.denied`).
- Navigation: `.nav-item` with `.active` state and an inset accent border.
- Markdown content: `.md-content` with consistent heading, code, blockquote, table, and link styles.

### Animations and motion
- A `thinking-blink` keyframe animates the three-dot "Thinking…" indicator and the stream pulse dot on the Chat nav item.
- A `spin` keyframe drives the spinner inside pending tool execution cards.
- A `prefers-reduced-motion: reduce` media query disables all blinking/spinning animations and transitions for motion-sensitive users.

### Accessibility conventions
- Keyboard focus is explicit: `:focus-visible` gets a 2px accent-colored outline with offset.
- Interactive elements use proper ARIA attributes (`aria-expanded`, `aria-haspopup`, `aria-controls`, `aria-label`, `role="menu"`).
- The `hidden` attribute is enforced globally with `display: none !important` to override any inline `display:flex` set by author rules.
- The mobile drawer supports Escape-to-close and backdrop-click-to-close.

### Responsive strategy
A single breakpoint at `@media (max-width: 800px)` switches between the desktop two-column grid and the mobile drawer pattern. No other breakpoints exist — the rest of the layout uses flexible units (`minmax`, `flex: 1`, `overflow-y: auto`) to adapt within each mode.

### Markdown rendering
The JS includes a lightweight regex-based markdown renderer (`renderMarkdown`) that escapes HTML first, then converts headers, lists, tables, code blocks, links, blockquotes, bold/italic/strikethrough, and paragraphs into HTML. This avoids pulling in a third-party markdown library.

## Conventions and constraints

- **Single-file CSS**: All styles live in `styles.css`; there are no scoped styles, CSS modules, or per-component style files.
- **Dark theme only**: `color-scheme: dark` and the full palette are hardcoded — no light-mode toggle or theme switching exists.
- **Token-only colors**: Hex values appear only in the `:root` token block; all other rules reference `var(--*)` variables.
- **Mobile-first-ish**: Base styles target desktop; mobile behavior is layered via a single `@media (max-width: 800px)` block.
- **No external CSS dependencies**: No CDN imports, no npm packages — the stylesheet is self-contained and versioned via cache-busting query strings on the `<link>` tag.
- **View persistence**: Views are hidden/shown via the `hidden` attribute rather than being created/destroyed, preserving DOM state across navigation.
- **Role-gated views**: The Audit trail view is hidden unless the resolved identity carries an `auditor` or `platform-admin` role (client-side gating only; server re-enforces `audit:read`).
- **Motion sensitivity**: All animations respect `prefers-reduced-motion: reduce` by disabling them while keeping visible state.