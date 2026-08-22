# SPEC-022 Tasks: Multi-Session Foundations — Session API, Voice-Readiness Contract, and Mutating-Dev Profile

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
Portal multi-session UI work is deferred to the rebuild spec (spec Appendix A).

## R-1: Session management API surface

- [x] Policy bundle: add `session:list` and `session:delete` rules (grants mirror `session:create`); `make sync-policy` + `make validate-policy` green (`shared/shared-contracts/policies/policy-default.yaml`)
- [x] Policy action constants + route-inventory/matrix tests in both gateways (`products/platform-gateway`, `products/tool-gateway` where vocabulary is enumerated)
- [x] Session store: `last_active_at` column (Postgres DDL bootstrap) + touch on create/chat start; title field on `SessionRecord` (`products/agent-platform/src/agent_service/services/session_store.py`)
- [x] Title minting: first user turn recorded server-side, 80-char cap, never rewritten (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [x] Transcript extraction from kernel state snapshot with `transcript_available` fallback (`products/agent-platform/src/agent_service/services/agent_state_store.py`, `api/v2/routes.py`)
- [x] `has_pending(session_id)` on the HITL confirmation registry (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`)
- [x] v2 endpoints: `GET /api/v2/sessions` (cap 50, ordered), extended `GET /api/v2/sessions/{id}`, `DELETE /api/v2/sessions/{id}` (404 foreign/unknown, 409 parked) (`products/agent-platform/src/agent_service/api/v2/routes.py`, `schemas/v2.py`)
- [x] Agent-platform tests: list cap/ordering/ownership, delete 404/409, title cap, transcript fallback, pending flag (`products/agent-platform/tests/`)
- [x] Platform-gateway proxies: `GET /api/v1/sessions`, extended get, `DELETE /api/v1/sessions/{id}` under `enforce_policy`; `session_deleted` audit emission (`products/platform-gateway/src/platform_gateway/`)
- [x] Platform-gateway tests: authz matrix for both new actions across all roles, 404 passthrough, audit emission (`products/platform-gateway/tests/`)

## R-2: Voice-readiness contract

- [x] `input_modality` (optional, default `text`, enum `text|voice`) in `ChatRequest`, agent-platform v2 chat schema, `agent-chat-request.schema.json` (`products/platform-gateway/src/platform_gateway/schemas/api.py`, `products/agent-platform/src/agent_service/schemas/v2.py`, `shared/shared-contracts/schemas/agent-chat-request.schema.json`)
- [x] Gateway forwards modality; recorded in chat log event and audit details (`products/platform-gateway/src/platform_gateway/api/routes/chat.py`)
- [x] Invariant I parity tests: identical policy/auto-allow/HITL outcomes for text vs voice (`products/platform-gateway/tests/`, `products/agent-platform/tests/`)
- [x] Invariant II regression test: `chat/confirm` schema unchanged/rejects modality fields
- [x] Voice-readiness subsection in Approval and HITL guide; configuration-reference field entry

## R-3: Environment-scoped mutating deployment profile

- [x] Create `runtime-profiles/mutating-dev/` (kustomization with `behavior: merge`, `mutating.env`); move `tool-gateway-pod-delete.yaml` from `base/tool-gateway/` (`shared/platform-ops/gitops/`)
- [x] Wire profile into `dev-k8s/kustomization.yaml`; add to `OVERLAYS` in root `Makefile`; `make overlays` green (5 overlays)
- [x] Verify rendered dev-k8s ConfigMap carries `GATEWAY_MUTATING_TOOLS_ENABLED=true`; base keeps `false`; `mutating-demo.sh` unchanged
- [x] Rewrite dev-k8s README opt-in section (profile mechanism, same-tag rollout-restart note, deactivation runbook); update Approval and HITL guide activation checklist

## R-4: Documentation and authorization matrix

- [x] Authorization matrix rows for `session:list` / `session:delete` (`docs/agentic-aiops-platform/authorization-matrix.md`)
- [x] Guide notes: session API available now, multi-session UI ships with the rebuild spec; troubleshooting entries (`docs/guides/`)
- [x] Product README updates (agent-platform, platform-gateway)

## Delivery close

- [x] Version lockstep bump to 0.8.0; CHANGELOG 0.8.0 section
- [x] `make build` then `make verify` green; API walkthrough against dev-k8s
- [x] Spec status → `delivered`, spec index + roadmap updated, release note authored
