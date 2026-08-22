# SPEC-023 Tasks: Portal Framework Rebuild — Multi-Session Workspace UI on Ant Design X

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Framework foundation and build toolchain

- [x] Scaffold Vite + React 18 + TypeScript tree under `products/operator-portal/web-ui/app/` (`package.json`, `tsconfig.json`, `vite.config.ts`) with Vitest for unit tests
- [x] Multi-stage Dockerfile: Node build stage → existing nginx runtime stage; hashed assets under `/assets/`; during coexistence the bundle is mounted at `/next/` while the legacy trio keeps serving `/` (`products/operator-portal/Dockerfile`)
- [x] nginx cache policy: `no-store` for `index.html`, `public, immutable` for hashed assets (`^~ /next/assets/` during coexistence; root-level after stage 6); SPA fallback intact (`products/operator-portal/nginx.conf`)
- [x] Build-time `PLATFORM_VERSION` injection from root `VERSION`; `make validate-version` asserts the injection wiring at the new home (`shared/shared-contracts/scripts/validate_version.py`)
- [x] Dark theme: antd/XProvider tokens seeded 1:1 from the current `:root` CSS variables; sidebar/drawer layout shell (SPEC-019) rebuilt (`web-ui/app/src/theme/`, `web-ui/app/src/App.tsx`)
- [x] OIDC shell ported: Keycloak login/logout, token refresh, per-request Bearer (`web-ui/app/src/auth/`)

## R-2: Platform-owned SSE contract adapter

- [x] Transport: `fetch` + `ReadableStream` with abort-controller session switching (`web-ui/app/src/stream/transport.ts`)
- [x] Decoder: schema v6 frame → typed models mapping, ported 1:1 from the vanilla dispatch including locked-card-on-truncation (`web-ui/app/src/stream/decoder.ts`, `models.ts`)
- [x] `useChatStream()` hook exposing typed models to views (`web-ui/app/src/stream/useChatStream.ts`)
- [x] Fixture-frame unit tests covering every schema v6 event type and the truncation terminal state (`web-ui/app/src/stream/__tests__/`)

## R-3: Multi-session workspace UI (SPEC-022 Appendix A)

- [ ] Session panel: list with title, relative last-active, amber *awaiting approval* badge; 30s poll + lifecycle refresh (`web-ui/src/sessions/`)
- [ ] Switch/resume: transcript load with explicit `transcript_available=false` state, stream repointing, per-tab active-session persistence, previous-stream close
- [ ] New session via existing create path; delete with in-UI confirm, 409 parked refusal, neutral 404
- [ ] Confirmation anchoring: cards stay bound to the parking session; approve/deny resumes that session's stream via `POST /api/v1/chat/confirm`
- [ ] Incident deep links: `incident-<id>` sessions open as additional panel entries (`web-ui/src/incidents/`)

## R-4: Voice input

- [ ] `Sender` speech input composing `input_modality: "voice"` turns; capability detection fallback (`web-ui/src/chat/Composer.tsx`)
- [ ] Recognition language selector (`en-US`/`zh-CN` minimum, constant-driven list): default from `navigator.language` with `en-US` fallback, `localStorage` persistence, drives the recognizer `lang` only (never sent to the backend) + unit test for the default/fallback resolution
- [x] Additive `input_modality` query parameter on `GET /api/v1/chat/stream` (gateway route → service → agent client) and agent `GET /api/v2/chat/stream`, recorded on `chat_started` audit `details` + gateway/agent tests for default and `voice` pass-through (commit `67073af`)
- [ ] Invariant II unit test: no voice path reaches a confirmation decision handler
- [ ] Approval and HITL guide voice-readiness subsection updated to record portal voice composition (`docs/guides/`)

## R-5: View migration and role-scoped visibility

- [ ] Audit view: filters, cursor pagination, expandable envelopes — auditor/platform-admin only (`web-ui/src/views/audit/`)
- [ ] Permissions matrix, tools, and skills inventory views (`web-ui/src/views/control/`)
- [ ] Incidents view: list/detail/triage, connector outcomes, session pinning (`web-ui/src/views/incidents/`)
- [ ] Sectioned navigation auto-hide derived from token roles + policy matrix endpoint (SPEC-019 parity)
- [ ] Evidence panel parity: inline anchored turn groups with full-output expander (SPEC-011 R-4)
- [ ] Remove the vanilla web-ui tree once parity is complete (`products/operator-portal/web-ui/app.js`, `styles.css`, legacy `index.html`)

## R-6: Documentation and living state

- [ ] Update operator portal README, operator guide, configuration reference, troubleshooting guide, dev-k8s README (build step, cache behavior, voice availability; drop single-session language)
- [ ] `CHANGELOG.md` entry referencing SPEC-023
- [ ] Release note following the established structure + release-notes index entry
- [ ] Spec index and roadmap backlog updated; spec status set to `delivered`

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (unit + live walkthrough on dev-k8s: login → multi-session create/switch/resume → voice turn → parked badge + anchored approve/deny → delete 409-then-success → incident deep link → per-role visibility)
- [ ] `make verify` green including version lockstep; `make build` + `make deploy` green
- [ ] living state docs updated (see spec `Impact` section)
- [ ] spec status set to `delivered`
