# v0.24.0 — Portal and Backend Dependency Hygiene

Date: 2026-08-28
Release type: minor (SPEC-042, the fourth R5 slice; dependency-only —
no new routes, actions, event types, or execution paths)

## Summary

SPEC-042 closes the two maintainability signals the v0.23.2 train
surfaced: 53 antd deprecation warnings in the portal's vitest suite and
a portal/backend upgrade check showing the portal several majors behind
its upstreams. The portal migrates off every deprecated antd v6 API it
uses and locks the posture with a zero-tolerance vitest guard, applies
the recorded refresh adopt set (including React 19), and every backend
product re-locks inside its declared ranges at latest stable. The
adoption policy throughout is **latest stable only** — no alpha, beta,
RC, or dev builds — with one recorded exception: the OpenTelemetry
instrumentation packages ship upstream on a permanent 0.xb channel and
stay at their locked SDK pairing.

## Portal (R-1 … R-4)

### R-1 — deprecated antd API migration

- The two off-canvas/document `Drawer`s move `width` → `size`
  (260px navigation drawer in `App.tsx`, 560px document drawer in
  `DocumentsView.tsx`); antd 6's `size` accepts numbers, so the pixel
  widths render unchanged.
- Every `Alert` usage moves `message` → `title` — twenty sites across
  ten view files (the spec's 2026-08-28 inventory recorded fifteen
  across nine; the five extra sites shipped in the v0.23.x line are
  migrated in the same pass). `description` is not deprecated and
  stays.
- Grep audit clean: no `width=` Drawer and no `message=` Alert remain
  under `src/`, and the vitest suite emits zero antd deprecation
  warnings.

### R-2 — deprecation regression guard

- The vitest setup intercepts `console.error`/`console.warn` and fails
  the suite at teardown on any `[antd: …] … deprecated` warning, with
  the offending text in the failure message. Non-deprecation output
  passes through untouched. Proven during delivery by re-introducing a
  deprecated prop (suite failed as required) and reverting.

### R-3 — managed refresh adopt set

| Package | From | To |
|---|---|---|
| antd | 6.6.1 | 6.6.2 |
| @testing-library/react | 16.3.2 | 16.3.3 |
| @testing-library/dom | 10.4.0 | 10.4.1 |
| typescript | 5.6.3 | 5.9.3 |
| vite | 6.4.3 | 8.2.2 |
| @vitejs/plugin-react | 4.7.0 | 6.1.1 |
| vitest | 3.2.7 | 4.1.11 |
| jsdom | 25.0.1 | 30.0.1 |
| @types/node | 22.10.x | 22.20.1 |
| @ant-design/x, @ant-design/icons, dayjs | unchanged | already latest stable |

- `engines.node` rises to `>=22.22.2` (jsdom 30's floor); the
  Dockerfile stays on the `node:22-alpine` line, which satisfies it.
- TypeScript 7.x (the native tsgo line) stays parked as too new for a
  safety-critical portal build gate; 5.9.x is the latest stable 5.x.

### R-4 — React 19

- react / react-dom move 18.3.1 → 19.2.8 with @types/react 19.2.18
  and @types/react-dom 19.2.5, zero peer-dependency warnings (antd,
  @ant-design/x, and @testing-library/react all already declared React
  19 support).
- No production code changes were forced by React 19. Two
  `useApprovalsInbox` hook tests needed React 19 state-flush timing
  fixes: `waitFor` around the hook's asynchronous error flush after a
  failed refresh and around the optimistic decided-record move, plus a
  deferred resync mock so the test observes the move before the server
  truth takes over. Behavioral intent unchanged.

## Backend (R-5)

- All eight Python products re-lock inside their declared ranges:
  agentscope 2.0.6 → **2.0.7.post1** (a PEP 440 post-release is a
  final stable release), fastapi → **0.141.1**, uvicorn → **0.52.4**;
  pydantic, httpx, kubernetes, psycopg, pyjwt, pyyaml,
  prometheus-client, and the OTel SDK/API/exporter were already
  current.
- **Cryptography caps adjudicated up**: the six declaring products
  (identity-broker, audit-service, incident-service, platform-gateway,
  skills-hub, tool-gateway) move `>=43.0,<45.0` → `>=43.0,<51.0` and
  lock 50.0.1. The JWT/signing call-site review found only the
  long-stable surface (`rsa.generate_private_key`, PEM/DER
  serialization, PKCS8/SubjectPublicKeyInfo formats), all unchanged
  through cryptography 50.x.
- **Redis (`<7.0`) and elasticsearch (`<9.0`) caps stay parked**:
  the deployed redis server is 7.2 (client 6.x fully compatible;
  client majors 7/8 were API-removal releases) and no Elasticsearch
  server is deployed in dev (the client major follows the server
  major).
- **OTel instrumentation stays** at the locked 0.65b0 pairing with SDK
  1.44.0 — upstream's permanent 0.xb channel is the single recorded
  exception to latest-stable, and the pairing is not chased.

## Verification

- Portal: vitest suite green with the R-2 guard active and zero antd
  deprecation warnings; `tsc --noEmit` and the vite production build
  green on the refreshed set.
- Backend: all eight product suites green under frozen sync after the
  re-lock; `make verify` green at 0.24.0.
- agentscope is the runtime kernel per ADR-0002, so the bump carried
  the kernel-verification leg: full gate plus a live check of the
  chat, HITL confirmation, and approved-mutating paths
  (`mutating-demo.sh` incl. the HITL leg).
- Live browser walkthrough: sign-in, a streamed chat turn, the session
  panel, Approvals (pending + history), and the Documents drawer with
  no rendering or interaction regressions.

## Posture

No behavior, contract, policy, audit, or execution change — routes,
actions, event types, and execution paths are untouched. The release is
dependency-only plus the two portal test-timing fixes listed above;
identity, policy, audit, and execution safety semantics are unchanged.
