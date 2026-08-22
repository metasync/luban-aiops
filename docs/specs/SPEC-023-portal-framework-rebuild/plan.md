# SPEC-023 Plan: Portal Framework Rebuild — Multi-Session Workspace UI on Ant Design X

## Approach

Replace the vanilla web-ui with a React 18 + TypeScript app built by Vite,
using Ant Design X for AI surfaces and antd for chrome. A single
platform-owned adapter module (`src/stream/`) is the only code that knows
stream schema v6 frame types or session API shapes; views consume typed
models. The Docker image gains a Node build stage but stays nginx-static at
runtime, so serving, probes, and the `/api/` proxy are untouched.

Stages: foundation (toolchain + theme + auth shell) → adapter (transport +
frame translation, fixture-tested) → session workspace (Appendix A contract)
→ voice input → view migration (control/workspace parity) → delivery close
(vanilla removal, docs, walkthrough).

## Design Per Requirement

### R-1: Framework foundation and build toolchain

- affected files: `products/operator-portal/web-ui/` (new Vite + TS tree),
  `products/operator-portal/Dockerfile`, `products/operator-portal/nginx.conf`,
  `shared/shared-contracts/scripts/validate_version.py`
- approach: Vite with content-hashed output into `dist/`; Dockerfile
  multi-stage (`node:22-alpine` build → existing nginx runtime); the build
  reads root `VERSION` into a build-time `PLATFORM_VERSION` define so
  `validate_version.py` finds it at the new constant's home; nginx keeps
  `no-store` for `index.html` and adds `Cache-Control: public, immutable`
  for `/assets/` only.
- theme: an antd `ConfigProvider`/`XProvider` token set seeded 1:1 from the
  current `:root` custom properties (`--bg`, `--surface`, `--accent`, ...);
  `color-scheme: dark` carried on `:root`.
- alternatives: keep no-build (rejected — spike finding); SSR frameworks
  (rejected — static serving is the deployment invariant).

### R-2: Platform-owned SSE contract adapter

- affected files: `web-ui/src/stream/` (transport, decoder, models),
  `web-ui/src/stream/__tests__/`
- approach: `transport.ts` wraps `fetch` + `response.body.getReader()`
  with abort-controller session switching; `decoder.ts` parses SSE frames
  and maps `eventType` → typed models (`AgentDelta`, `EvidenceItem`,
  `ConfirmationCard`, `StreamTerminal`); `useChatStream()` hook exposes
  them to views. Fixture-frame unit tests assert the mapping; the full
  vocabulary from the current `app.js` dispatch is ported 1:1, including
  the locked-card behavior when a stream ends without
  `confirmation_result`.
- alternatives: framework-owned transport (`useXAgent` defaults — rejected:
  couples the wire protocol to component lifecycle); `EventSource`
  (rejected: cannot POST or send `Authorization`).

### R-3: Multi-session workspace UI

- affected files: `web-ui/src/sessions/` (panel, switcher, store),
  `web-ui/src/chat/` (composer, transcript), `web-ui/src/incidents/`
- approach: `Conversations` renders the panel from
  `GET /api/v1/sessions` (30s poll + refresh on lifecycle events); active
  session id persists per tab via `sessionStorage`; switching aborts the
  previous stream (transport abort controller) and loads the transcript or
  the `transcript_available=false` state; delete wraps an antd confirm
  modal and maps 409 → parked-refusal message, 404 → neutral not-found
  (never ownership hints); incident deep links append to the panel instead
  of replacing the active session.
- alternatives: portal-local history (rejected by SPEC-022).

### R-4: Voice input

- affected files: `web-ui/src/chat/Composer.tsx`, Approval and HITL guide
- approach: `Sender` speech input composes text; on send the request sets
  `input_modality: "voice"`. Capability detection hides the affordance
  where `webkitSpeechRecognition`/`SpeechRecognition` is absent. Approve /
  deny buttons are the only confirmation decision surface; a unit test
  asserts no confirmation handler is reachable from a voice event path.
- language selection: a composer-level selector (`en-US` / `zh-CN` minimum,
  list owned by one constant so adding a language is data, not logic)
  drives the recognizer's `lang`; default resolves `navigator.language`
  against the supported set with `en-US` fallback; the choice persists in
  `localStorage`. The selection stays client-side — it never reaches the
  gateway or the audit trail.
- stream modality parity: `GET /api/v1/chat/stream` and the agent's
  `GET /api/v2/chat/stream` gain an additive `input_modality` query
  parameter (`text`|`voice`, default `text`); the gateway records it on
  the `chat_started` audit event's `details` and forwards it upstream.
  Gateway and agent-service tests pin the default and voice pass-through;
  the adapter always sends the parameter explicitly.
- source tree: the new Vite/React/TS project lives in
  `web-ui/app/` (own `package.json`, `index.html`, `src/`) while the
  legacy vanilla trio (`index.html`, `app.js`, `styles.css`) stays at the
  `web-ui/` root and keeps being served by the deployed image until stage
  6 removes it; the build stage runs `npm ci && npm run build` in
  `web-ui/app/` and outputs to `web-ui/dist/`. During coexistence the
  image mounts the compiled SPA at `/next/` (Vite `base: "/next/"`,
  nginx `^~ /next/` with immutable-cache `/next/assets/`) so the rebuild
  is previewable without disturbing the legacy portal; stage 6 flips the
  runtime root to the bundle and drops the `base`. Local development uses
  `npm run dev` with a Vite proxy for `/api/`.

### R-5: View migration and role-scoped visibility

- affected files: `web-ui/src/views/` (audit, permissions, tools, skills,
  incidents), router + nav shell
- approach: port view logic from `app.js` into typed components backed by
  small fetch hooks; navigation sections derive from the token's roles and
  the policy matrix endpoint exactly as today; audit stays
  auditor/platform-admin. Chat-first sequencing ships the workspace value
  early; the release closes only when all views are parity-complete and the
  vanilla tree is deleted.

### R-6: Documentation and living state

- affected files: listed in spec Impact; release close follows the
  established pattern (CHANGELOG section, release note, index, roadmap).

## Sequencing And Dependencies

1. Foundation: Vite/TS toolchain, theme tokens, OIDC shell, Docker build
   stage — depends on nothing
2. Adapter: transport + decoder + fixture tests — depends on stage 1
3. Session workspace: panel, switch/resume, delete, anchoring, deep links —
   depends on stage 2; consumes SPEC-022 API (already shipped)
4. Voice input — depends on stage 3 (composer)
5. View migration (control/workspace parity) — depends on stage 1; can
   overlap stages 3–4
6. Delivery close: vanilla removal, docs, live walkthrough, release — depends
   on all above

## Test Strategy

- unit tests (Vitest): adapter frame-fixture mapping (every schema v6 event
  type), locked-card truncation behavior, session store refresh/badge
  logic, Invariant II voice/confirmation isolation, role-scoped nav
  derivation
- contract tests: none new (backend contracts unchanged); adapter consumes
  existing gateway endpoints only
- integration / overlay validation: `make verify` still green (portal is
  image-only; validator version-lockstep follows `PLATFORM_VERSION`);
  `make build` + `make deploy` on dev-k8s followed by a live walkthrough:
  login → multi-session create/switch/resume → voice turn → parked
  confirmation badge + anchored approve/deny → delete (409 then success) →
  incident deep link → per-role view visibility

## Rollout And Migration

- deployment: image rebuild only; nginx runtime, probes, `/api/` proxy, and
  all backend services unchanged — no secret, overlay, or RBAC changes
- backward compatibility: API surface untouched; the old and new UIs are
  mutually exclusive per image tag (no dual-run); bookmarks work via SPA
  fallback
- rollback: redeploy the previous image tag (GitOps pin) — the rebuild
  carries no durable state migration, so rollback is side-effect-free
