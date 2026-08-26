# SPEC-037 Tasks: Signed Execution Requests and Receipts

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Execution request and receipt contracts

- [x] Add `execution-request.schema.json` and `execution-receipt.schema.json` (`shared/shared-contracts/schemas/`)
- [x] Add canonicalization + digest helpers with stability tests (`products/agent-platform/src/agent_service/services/execution_signing.py`, `tests/test_execution_signing.py`)
- [x] Validate both schemas via the shared-contracts validator (`shared/shared-contracts/scripts/`)

## R-2: Signed requests at resume, fail-closed on missing key

- [x] Add HMAC sign/verify helpers with round-trip and tamper tests (`services/execution_signing.py`, tests)
- [x] Add `execution_signing_key` setting from `AGENT_EXECUTION_SIGNING_KEY` (`products/agent-platform/src/agent_service/runtime_settings.py`, `tests/test_runtime_settings.py`)
- [x] Build and persist one request per approved parked call in `resume_confirmation`; denials construct none (`products/agent-platform/src/agent_service/runtime_kernel.py`, `tests/test_hitl_confirmations.py`)
- [x] Reject execution with audited `execution_rejected` (`signing_unavailable`) when the key is absent (kernel + tests)

## R-3: Argument-digest verification at invocation

- [x] Verify invoked-args digest against the signed envelope for mutating calls; mismatch and absent envelope block and audit (`products/agent-platform/src/agent_service/tools/gateway_tools.py`, `tests/test_gateway_tools.py`)
- [x] Confirm read-only invocations never consult the envelope (tests)

## R-4: Durable execution records beside confirmation records

- [x] Add `ExecutionRecordStore` (memory + Postgres backends, factory, table creation, startup sweep) (`products/agent-platform/src/agent_service/services/execution_records.py`, `tests/test_execution_records.py`)
- [x] Write receipts after tool results with best-effort-durable posture (kernel + tests)
- [x] Expose additive `executions` per confirmation on session detail (`products/agent-platform/src/agent_service/api/v2/routes.py`, tests)

## R-5: Execution audit events

- [x] Extend `audit-event.schema.json` with the three event types and details documentation (`shared/shared-contracts/schemas/audit-event.schema.json`)
- [x] Emit requested/completed/rejected through the canonical emitter with `confirm_id` + `x-request-id` correlation (agent-platform + tests)

## R-6: Receipt visibility on decided confirmation cards

- [x] Map session-detail `executions` onto decided confirmation cards (`products/operator-portal/web-ui/app/src/chat/`, transcript seeding)
- [x] Render read-only receipt badge and digest-match state; legacy decided cards unchanged (`products/operator-portal/web-ui/app/src/chat/__tests__/`)

## Deploy chain

- [x] Add `sync-execution-signing-secret.sh` with `SKIP_EXECUTION_SIGNING_SECRET` guard (`shared/platform-ops/gitops/`)
- [x] Wire into `dev-k8s/deploy.sh` and the agent-service deployment env (`shared/platform-ops/gitops/dev-k8s/`)
- [x] `make overlays` renders the env addition cleanly

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] live check: `mutating-demo.sh` on the `mutating-dev` profile produces signed request + receipt, correlated audit chain, and the receipt badge on the decided card
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
