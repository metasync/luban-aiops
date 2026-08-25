# SPEC-031 Tasks: Approval Inbox and Persistent Confirmation Cards

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Durable confirmation lifecycle records

- [ ] confirmation-record contract shape in shared-contracts (status enum, decider, timestamps, pending-calls payload) (`shared/shared-contracts/`)
- [ ] `confirmation_records.py`: Postgres-backed store (park insert, resolve/expire update, per-session cap 50 evict-oldest, cascade on session delete) on the existing `AGENT_STATE_DB_URL` posture (`products/agent-platform/src/agent_service/services/`)
- [ ] park/resolve wiring: record written before `confirmation_request` is yielded and outcome before `confirmation_result` flows (`products/agent-platform/src/agent_service/runtime_kernel.py`, `api/v2/routes.py`)
- [ ] registry rehydration: startup + on-miss recovery of pending records across restarts/replicas (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`)
- [ ] store + wiring unit tests (write order, cap/eviction, cascade, rehydration) (`products/agent-platform/tests/`)

## R-2: Persistent cards in the owner transcript

- [ ] session detail payload: additive `confirmations` field from durable records, transcript order, current state (`products/agent-platform/src/agent_service/schemas/v2.py`, `api/v2/routes.py`)
- [ ] gateway session relay passes the field through (`products/platform-gateway/src/platform_gateway/api/routes/sessions.py`, services)
- [ ] route tests: parked/approved/denied/expired cards present after a fresh session-detail fetch (`products/agent-platform/tests/`, `products/platform-gateway/tests/`)

## R-3: Approvals inbox API

- [ ] `GET /api/v2/confirmations` (cross-session, status filter, decider-role scoping, pending items + 30-day history window, metadata-only) (`products/agent-platform/src/agent_service/api/v2/routes.py`)
- [ ] `GET /api/v1/approvals/inbox` gateway route with `enforce_policy(ACTION_APPROVALS_LIST)` + relay (`products/platform-gateway/src/platform_gateway/api/routes/approvals.py`, actions constants, agent-client)
- [ ] default bundle: `approvals:list` allow rule for `approver` + `platform-admin`; `make sync-policy` + `make validate-policy` (`shared/shared-contracts/policies/policy-default.yaml`)
- [ ] route tests: approver lists owner-parked items without session membership; non-decider 403 audited; history ordering + 30-day window (expired items included); metadata-only shape (no transcript text) (`products/platform-gateway/tests/`, `products/agent-platform/tests/`)

## R-4: Race-resilient resolution semantics

- [ ] `ConfirmationAlreadyResolved` carrying decider/decision/decided-at; confirm route answers `409 already_resolved` for resolved records, keeps `404` for unknown ids (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`, `api/v2/routes.py`)
- [ ] gateway passes the structured 409 body through unchanged (`products/platform-gateway/src/platform_gateway/services/gateway_service.py`)
- [ ] race tests: concurrent approve (one execution, one audit event, loser gets the outcome body); stale-tab confirm after resolution; deny-race parity (`products/agent-platform/tests/`, `products/platform-gateway/tests/`)

## R-5: Portal approvals view and persistent cards

- [ ] `ApprovalsView.tsx`: pending-first list + history, 30s/focus polling, pending-count badge, decider-role-only nav entry (`products/operator-portal/web-ui/app/src/views/control/`, `App.tsx`)
- [ ] decision panel reuses `ConfirmationCardView`; decide via existing confirm client; `already_resolved` flips the card to the resolved state (`products/operator-portal/web-ui/app/src/chat/`, `api/client.ts`)
- [ ] owner-side persisted cards: session-detail `confirmations` merged into the turn timeline; decided cards read-only with decider attribution (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`, `stream/useChatStream.ts`)
- [ ] vitest: inbox pending/history/empty, badge count, race-response handling, owner-side persisted card for all four states (`products/operator-portal/web-ui/app/src/views/__tests__/`, `chat/__tests__/`)

## Validation And Docs

- [ ] `mutating-demo.sh` HITL leg extended: owner session detail carries the decided card; approver inbox lists the item with outcome; second approve returns `already_resolved` (`shared/platform-ops/e2e/mutating-demo.sh`)
- [ ] living docs updated: approval-and-hitl (inbox workflow), portal-user-guide (Approvals view), troubleshooting (already_resolved symptom), authorization-matrix (`approvals:list` row)
- [ ] live cluster validation: operator re-login shows the decided card; approver approves from the portal inbox end-to-end

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
