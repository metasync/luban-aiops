---
kind: frontend_style
name: Operator Portal — Minimal Vanilla CSS Dark Theme
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/app.js
---

The Luban AIOps platform has a single frontend: the Operator Portal under `products/operator-portal/web-ui/`. It is a static, vanilla-JS application served by Nginx with no build step, framework, or component library.

**Styling system and approach**
- Pure CSS (no preprocessors, no CSS-in-JS, no utility frameworks). All styles live in a single `styles.css` file.
- Uses CSS custom properties via `:root` to define a dark color scheme (`color-scheme: dark`) with a slate palette (`#0f172a`, `#111827`, `#e2e8f0`, `#93c5fd`, `#cbd5e1`).
- Layout relies on modern CSS Grid (`.grid` with `auto-fit` + `minmax(320px, 1fr)`) and Flexbox (`.actions`) for responsive panels. No media queries are present; responsiveness is achieved through grid auto-fitting.
- The visual language is flat and minimal: rounded panels (`border-radius: 16px`), subtle borders using semi-transparent slate tones, and a gradient background on `body`.

**Key files**
- `products/operator-portal/web-ui/index.html` — single-page HTML shell with semantic sections (`hero`, `panel`, `grid`) and form controls.
- `products/operator-portal/web-ui/styles.css` — all styling, including global resets, typography (`Inter, Arial, sans-serif`), panel/card styles, form inputs, buttons, and `<pre>` output blocks.
- `products/operator-portal/web-ui/app.js` — unstyled client logic handling OIDC login flow, session management, prompt submission, and server-sent event streaming.
- `products/operator-portal/nginx.conf` and `Dockerfile` — serve the static assets via Nginx.

**Architecture and conventions**
- No design tokens, theme variables beyond the root `:root` block, or shared style libraries. Each UI element is styled directly in `styles.css`.
- Class naming follows a simple BEM-like convention (`app-shell`, `hero`, `eyebrow`, `subtitle`, `grid`, `panel`, `actions`, `metadata`) without strict enforcement.
- The portal is intentionally minimal: it exposes Gateway URL configuration, identity/login actions, session creation, prompt input, and response/output areas as separate panels.
- There is no CSS linting, style guide, or automated consistency checks visible in the repository.

**Constraints and observed rules**
- The entire UI is contained within one HTML file and one CSS file; no additional stylesheets are loaded.
- The dark theme is enforced globally via `color-scheme: dark` and explicit color values rather than light/dark toggle support.
- Responsive behavior is achieved solely through CSS Grid's `auto-fit` / `minmax` pattern; no breakpoint-based overrides exist.