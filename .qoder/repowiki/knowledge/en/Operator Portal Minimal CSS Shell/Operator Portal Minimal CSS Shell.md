---
kind: frontend_style
name: Operator Portal Minimal CSS Shell
category: frontend_style
scope:
    - '**'
source_files:
    - products/operator-portal/web-ui/styles.css
    - products/operator-portal/web-ui/index.html
    - products/operator-portal/web-ui/app.js
---

The repository contains a single, minimal frontend in `products/operator-portal/web-ui/` consisting of three files: `index.html`, `styles.css`, and `app.js`. There is no component framework, build step, or design-token system — the UI is a vanilla HTML/CSS/JS shell served by nginx.

**Styling approach**
- A single flat stylesheet (`styles.css`) defines a dark color scheme via CSS custom properties on `:root` (`color-scheme: dark`, background `#0f172a`, text `#e2e8f0`).
- Layout uses CSS Grid (`.grid` with `auto-fit` + `minmax(320px, 1fr)`) and a centered `.app-shell` container; no responsive breakpoints beyond the grid auto-fit.
- Reusable visual building blocks are plain class names: `.panel` (glassmorphism-style card), `.actions` (flex row for buttons), `.eyebrow` / `.subtitle` (typographic hierarchy), and `<pre>` for raw output.
- All global resets are minimal: `box-sizing: border-box`, body gradient background, and inherited font stack (`Inter, Arial, sans-serif`).

**HTML structure**
- `index.html` is a static page loaded directly from nginx; it links `styles.css` and `app.js` with cache-busting query strings (`?v=20260727-final-cleanup`).
- The DOM is organized into semantic `<section>` panels for Gateway, Prompt, Session, Identity/Login, and Response, each using simple `<input>`, `<textarea>`, `<button>`, `<dl>/<dt>/<dd>`, and `<pre>` elements.

**JavaScript behavior**
- `app.js` is a single script that wires DOM event listeners to fetch-based API calls against `/api/v1/*` endpoints on the same origin (or a configurable gateway URL).
- It implements an OIDC login flow (login → callback → token refresh), session storage for access/refresh tokens, SSE streaming for chat responses, and basic error rendering into `<pre>` elements.
- No module bundler, transpiler, or framework is used — everything runs as-is in the browser.

**Architecture & conventions**
- Zero dependencies: no package.json, no npm/yarn, no CSS-in-JS, no component library. The portal is intentionally a thin debugging/ops shell rather than a production-grade SPA.
- Styling is co-located with the HTML page in one CSS file; there is no BEM, utility-first, or scoped styling convention beyond simple class names.
- The UI is not responsive-aware beyond the CSS Grid auto-fit; no media queries exist.