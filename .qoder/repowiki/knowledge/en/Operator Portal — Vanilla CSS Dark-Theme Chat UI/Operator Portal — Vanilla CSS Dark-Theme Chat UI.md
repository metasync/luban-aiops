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

The only frontend in the repository lives under `products/operator-portal/web-ui/` and is a **vanilla HTML + CSS + JavaScript** single-page chat interface served by nginx. There is no build step, no component framework (React/Vue/etc.), no CSS-in-JS, no design-token library, and no responsive framework. Styling is a single flat stylesheet (`styles.css`) loaded directly from `index.html`, with all interactivity implemented in one script (`app.js`).

## Key files and packages

- `products/operator-portal/web-ui/index.html` — minimal semantic shell: `<header class="top-bar">`, `<main class="chat-main">`, `<footer class="chat-input-bar">`, collapsible `<details class="settings-drawer">`.
- `products/operator-portal/web-ui/styles.css` — the entire visual style surface (~445 lines).
- `products/operator-portal/web-ui/app.js` — DOM manipulation, markdown renderer, OIDC login flow, SSE streaming of agent/tool events, and evidence/audit turn groups.
- `products/operator-portal/nginx.conf` — serves these three static files; no asset pipeline.

No external CSS frameworks or JS libraries are referenced; fonts are pulled via system font stacks.

## Architecture and conventions

### Design tokens via CSS custom properties
All colors, spacing, and radii are centralized in a `:root` block at the top of `styles.css`:
- Color palette: `--bg`, `--surface`, `--surface-alt`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-hover`, `--success`, `--error`, `--warning`, `--code-bg`.
- Spacing/radius: `--radius: 8px`.
- Global `color-scheme: dark` enforces a dark theme across native UI chrome.

This is the de facto design-token system for the portal.

### Layout model
A fixed-height flex column `.chat-shell` (max-width 900px, centered) contains three fixed regions: top bar, scrollable chat area, and bottom input bar. The settings panel is a native `<details>` drawer below the input. Evidence and audit cards are rendered inline after each agent reply as collapsed `<details class="evidence-turn">` blocks, per SPEC-011 R-4.

### Markdown rendering
`app.js` ships a small regex-based markdown-to-HTML converter (`renderMarkdown`) that handles headers, bold/italic/strikethrough, code fences, inline code, lists, tables, blockquotes, links, and paragraphs. Styled output is wrapped in a `.md-content` container whose typography rules live in `styles.css` (headings colored `--accent`, code blocks use `--code-bg` and monospace fonts `"JetBrains Mono", "Fira Code"`).

### Component-style classes
There are no reusable components; instead, BEM-like class names describe UI fragments:
- Shell: `.chat-shell`, `.top-bar`, `.chat-main`, `.chat-input-bar`
- Messages: `.chat-msg.user-msg`, `.chat-msg.agent-msg`
- Controls: `.btn-sm`, `.btn-send`
- Settings: `.settings-drawer`, `.settings-grid`, `.settings-section`
- Evidence/audit: `.evidence-turn`, `.evidence-card`, `.status-badge.{pending|success|error|denied}`, `.audit-card`

### Responsive strategy
Responsiveness is minimal: `.chat-shell` uses `max-width: 900px` and `margin: 0 auto`; `.settings-grid` uses `grid-template-columns: repeat(auto-fit, minmax(250px, 1fr))`. No media queries exist — the layout relies on flexbox wrapping and CSS Grid auto-fitting rather than breakpoints.

### Theming constraints
The stylesheet hard-codes a dark theme via `color-scheme: dark` and a fixed slate/blue palette. There is no light-mode variant, no theme switcher, and no mechanism to override tokens at runtime beyond editing `styles.css`.

## Conventions and constraints

- **Single stylesheet**: All styling must go into `products/operator-portal/web-ui/styles.css`; there is no CSS module, SCSS, or split-file convention.
- **CSS variables for all visuals**: Colors, borders, and radius should be expressed through the `--*` custom properties defined in `:root`, not hardcoded hex values scattered through selectors (the existing file follows this pattern consistently).
- **Semantic HTML structure**: The page skeleton uses `<header>`, `<main>`, `<footer>`, and `<details>` for collapsible sections; new UI should follow the same pattern.
- **Class naming**: Use descriptive kebab-case class names grouped by region (shell, messages, controls, settings, evidence); avoid generic utility classes.
- **No external dependencies**: Do not import third-party CSS/JS libraries unless absolutely necessary; the portal is intentionally dependency-free and served statically by nginx.
- **Evidence/audit rendering**: Per SPEC-011 R-4, tool evidence and audit trails are rendered as collapsed `.evidence-turn` groups inserted inline after the agent reply they ground, keeping provenance next to its answer without crowding the response.
- **Markdown output**: Agent responses are rendered through the built-in `renderMarkdown` and styled via `.md-content`; do not inject raw HTML from untrusted sources without escaping.