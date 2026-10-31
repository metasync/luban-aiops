Single Vite + React 18 + TypeScript SPA under `web-ui/app/`, built in a Node stage and served by an unprivileged nginx container (`Dockerfile` multi-stage). Runtime layout: `App.tsx` owns the antd two-column shell (sidebar + content), role-gated navigation entries, and instantiates two independent session workspaces — one for operation mode (Chat, Incidents, Documents, Settings) and one gated to `STUDIO_ROLES` for development mode (Studio). Cross-cutting concerns are split into sibling feature folders:
- `auth/` — OIDC flow (`oidc.ts`), `AuthContext` provider with silent token refresh ~60s before expiry, and `storage.ts` for persisted `AuthSession`.
- `api/` — thin typed wrappers over `requestJson` (`client.ts`) which injects `x-request-id` and bearer tokens; modules per domain (`approvals`, `authorizations`, `documents`, `incidents`, `models`, `sessions`).
- `chat/` — conversation UI plus streaming transport (`stream/decoder.ts`, `transport.ts`, `useChatStream.ts`) and evidence/recovery polling hooks.
- `sessions/` — `useSessionWorkspace` hook owning active-session pointer, list polling, and authorization-return handling.
- `views/` — route-level components grouped by concern (`audit/`, `control/`, `incidents/`, `workspace/`).
- `voice/` — Web Speech API integration for voice input.
- `theme/` — global CSS and design tokens.

The nginx layer (`nginx.conf`) serves hashed `/assets/` as immutable, proxies `/api/` and `/health/` to `platform-gateway:8000` with `proxy_buffering off` and a 3600s read timeout for SSE streams, and returns 404 for private `/api/v2/`. Build-time constants (`PLATFORM_VERSION`, locked React/Antd versions) are injected via `vite.config.ts` from the repo root `VERSION` and `package-lock.json`.