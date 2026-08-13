---
kind: frontend_style
name: Operator Portal — Vanilla CSS Dark-Theme Chat UI
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

The only frontend in this repository is the **Operator Portal** (`products/operator-portal/web-ui/`), a single-page chat/debug interface built with **vanilla HTML + CSS + JavaScript**. There is no framework (React, Vue, Svelte), no component library, no build toolchain, no CSS-in-JS, and no design-token system beyond plain CSS custom properties. The page is served directly by an Nginx container configured via `nginx.conf`.

## Key files and packages

- `products/operator-portal/web-ui/index.html` — static shell defining the chat layout: top bar, message area, evidence panel, prompt input, and a collapsible Settings & Debug drawer.
- `products/operator-portal/web-ui/styles.css` — the entire stylesheet (~405 lines). Defines a dark theme via `:root` variables and all layout/style rules.
- `products/operator-portal/web-ui/app.js` — client-side logic for OIDC login flow, session management, streaming chat via Server-Sent Events, markdown rendering, and evidence-panel updates.
- `products/operator-portal/nginx.conf` — serves the three files above as a static site.

No other product in the repo contains frontend code; the remaining services are Python FastAPI backends.

## Architecture and conventions

### Design tokens (CSS custom properties)
All visual values are centralized in `:root` at the top of `styles.css`:
- Palette: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`.
- Spacing/radius: `--radius: 8px`.
- Theme mode: `color-scheme: dark` forces browser-native dark inputs.

These variables are consumed everywhere else in the stylesheet, making it the single source of truth for colors and radii.

### Layout model
- A `.chat-shell` flex column fills `100vh`, max-width `900px`, centered.
- Top bar (`.top-bar`) is fixed-height with title and identity badge.
- Main chat area (`.chat-main`) is `flex: 1` with vertical overflow.
- Input bar (`.chat-input-bar`) is pinned to the bottom with a border-top separator.
- Settings drawer uses the native `<details>/<summary>` element styled as a collapsible section with a responsive grid (`grid-template-columns: repeat(auto-fit, minmax(250px, 1fr))`).

### Typography
- Font stack: `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif`.
- Code font stack: `"JetBrains Mono", "Fira Code", monospace`.
- Headings inside rendered markdown (`.md-content h1..h6`) are colored `--accent` with decreasing sizes.

### Message styling
- User messages (`.chat-msg.user-msg`): dark surface background with a left accent border.
- Agent messages (`.chat-msg.agent-msg`): transparent background with a left border line.
- Markdown content is rendered into `.md-content` divs via a hand-rolled regex-based renderer in `app.js` that supports headers, lists, tables, blockquotes, code blocks, links, bold/italic/strikethrough, and paragraphs.

### Evidence panel
A dedicated `.evidence-panel` shows tool invocations as cards (`.evidence-card`) with:
- Status badges (`.status-badge.pending|success|error|denied`) using semantic color classes.
- Inline spinner animation (`@keyframes spin`).
- Collapsible `<details>` sections for parameters and data summaries.
- Metadata row (`.evidence-meta`) showing source system, duration, risk level, timestamp.

### Responsive strategy
- No media queries exist. Responsiveness comes from Flexbox/Grid auto-layout (`auto-fit`, `minmax`) and percentage/flex sizing.
- The viewport is locked to `100vh` with `overflow: hidden` on body; scrolling occurs inside `.chat-main`.

### State persistence
- Auth sessions and pending OIDC requests are stored in `window.sessionStorage` under keys `luban.portal.authSession` and `luban.portal.authRequest`.
- Token refresh is scheduled based on decoded JWT `exp` claims with a 60-second margin.

## Conventions and constraints

- **Single-file CSS**: All styles live in one flat stylesheet; there are no modules, preprocessors, or scoped styles.
- **BEM-like class naming**: Classes use descriptive kebab-case names (`.chat-shell`, `.top-bar`, `.settings-drawer`, `.evidence-card`) rather than utility classes or a framework convention.
- **Dark-only theme**: `color-scheme: dark` plus a fixed slate palette means light-mode support is not implemented.
- **No external CSS dependencies**: The stylesheet is self-contained; no CDN fonts or icon libraries are referenced (system fonts are used).
- **Markdown rendering is inline**: The JS `renderMarkdown()` function escapes HTML first, then applies regex transforms — no third-party markdown library is used.
- **Evidence panel state is keyed by `call_id`**: A `Map` in `app.js` tracks evidence cards so `tool_call` and `tool_result` events can be correlated.
- **Error display uses CSS variables**: Errors are injected as `<p style="color: var(--error)">` elements rather than through a dedicated error class.
- **Static asset cache-busting**: Both `styles.css` and `app.js` are loaded with query-string version stamps (`?v=20260805-chat-layout`) in `index.html`.