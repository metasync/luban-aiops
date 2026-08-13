---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark Theme with CSS Variables
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/app.js
---

## What system/approach is used

The Operator Portal (`products/operator-portal/web-ui/`) is a **vanilla HTML + CSS + JavaScript** single-page chat UI served by an embedded Nginx container. There is no frontend framework, component library, build step, or CSS preprocessor. Styling is entirely in one stylesheet (`styles.css`), and the page structure lives in `index.html`, with all interactivity in `app.js`. The UI renders Markdown responses client-side via a custom regex-based renderer rather than a markdown library.

## Key files and packages

- `products/operator-portal/web-ui/styles.css` — sole stylesheet defining the entire visual design system.
- `products/operator-portal/web-ui/index.html` — static shell (chat shell, top bar, evidence drawer, settings drawer, prompt input).
- `products/operator-portal/web-ui/app.js` — DOM manipulation, streaming SSE handling, OIDC login flow, and client-side Markdown rendering.
- `products/operator-portal/nginx.conf` — serves the three files above as a static site.

No external CSS frameworks, theme engines, design-token libraries, or preprocessors are referenced.

## Architecture and conventions

### Design tokens via CSS custom properties
All colors, spacing, and radii are centralized in a `:root` block at the top of `styles.css`:
- Background/surface palette: `--bg`, `--surface`, `--surface-alt`, `--border`
- Text palette: `--text`, `--text-muted`
- Semantic colors: `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`
- Code background: `--code-bg`
- Shared radius: `--radius`

This is the repository's only design-token mechanism; every color and border radius references these variables.

### Dark-only theme
The root sets `color-scheme: dark` and all token values are dark-mode swatches. There is no light-mode variant or media-query toggle — the portal is intentionally dark-only.

### Layout model
A fixed-height `.chat-shell` flex column contains four sections:
1. `.top-bar` — sticky header with title, identity badge, login/logout buttons.
2. `.chat-main` — scrollable message area with user/agent message variants (`.user-msg`, `.agent-msg`).
3. Collapsible drawers using native `<details>` elements: `.evidence-drawer` (tool-call audit) and `.settings-drawer` (debug/session/identity controls).
4. `.chat-input-bar` — fixed footer textarea + send button.

Responsive behavior is minimal: the shell is constrained to `max-width: 900px` and centered; the settings grid uses `grid-template-columns: repeat(auto-fit, minmax(250px, 1fr))` for fluid columns.

### Component-style class naming
Classes follow a flat BEM-like convention without nesting: `chat-shell`, `top-bar`, `top-bar-title`, `chat-msg`, `chat-msg.user-msg`, `chat-msg.agent-msg`, `evidence-drawer`, `evidence-card`, `status-badge`, `audit-card`, etc. No CSS modules, scoped styles, or shadow DOM are used.

### Evidence panel pattern
Tool invocations are surfaced through a collapsed `<details id="evidence-drawer">` that stays out of the way until opened. Each tool call becomes an `.evidence-card` with a status badge (`pending | success | error | denied`) and optional nested `<pre>` for parameters/data. An audit table is appended after stream completion. This pattern is documented inline in both `index.html` and `app.js` as implementing SPEC-011 R-4.

### Markdown rendering
`app.js` includes a hand-rolled `renderMarkdown()` function that escapes HTML first, then applies regex transforms for code blocks, inline code, headers, bold/italic/strikethrough, links, blockquotes, lists, tables, and paragraphs. Styled output is wrapped in `.md-content`, whose typography rules live in `styles.css`.

### Interactions driven from JS
There are no CSS-only interactive components beyond `<details>` toggles. All dynamic behavior (streaming SSE, OIDC login/callback, session management, token refresh scheduling, evidence card creation/update) is implemented in `app.js` and manipulates classes like `status-badge.pending|success|error|denied` and `chat-msg.user-msg|agent-msg`.

## Conventions and constraints

- **Single stylesheet**: All styling must go into `styles.css`; there is no per-component CSS file.
- **Dark-only**: Do not add light-mode overrides; the portal is intended to be consumed in dark mode only (`color-scheme: dark`).
- **Token-first**: New colors must use existing `--*` CSS variables rather than hard-coded hex values.
- **Native collapsibles**: Use `<details>/<summary>` for secondary panels (evidence, settings); do not introduce custom dropdowns.
- **Class scope**: Classes are global; avoid reusing names across unrelated features since there is no scoping mechanism.
- **No build step**: Files are served directly by Nginx; cache-busting is done via query-string version suffixes on `<link>` and `<script>` tags (e.g., `?v=20260810-evidence-drawer`).
- **Accessibility baseline**: The portal relies on semantic HTML (`<header>`, `<main>`, `<footer>`, `<details>`) and does not implement ARIA attributes beyond what those elements provide.

## Confidence
high — The entire frontend style surface is confined to three small files under `products/operator-portal/web-ui/`, and the patterns described above are fully observable in those files.