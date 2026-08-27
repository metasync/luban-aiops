# SPEC-038 Tasks: Isolated Execution Worker

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: The execution-runtime worker product

- [x] Scaffold `products/execution-runtime/`: `pyproject.toml` (version lockstep) + `uv.lock`, base-uv `Dockerfile`, `Makefile` (python + image fragments, image `luban-aiops/execution-runtime`), `.python-version`
- [x] Add `src/execution_runtime/` app factory with `/health/live` + `/health/ready`, structured logging, and `x-request-id` propagation (`products/execution-runtime/src/execution_runtime/`)
- [x] Add frozen `EXECUTION_*` settings module with startup validation (`products/execution-runtime/src/execution_runtime/core/config.py`, `tests/test_config.py`)
- [x] Wire into root `Makefile`: `PYTHON_PRODUCTS` / `IMAGE_PRODUCTS`, `.images.env` `EXECUTION_RUNTIME_IMAGE`, kind load list

## R-2: Authenticated internal handoff with fail-closed verification

- [x] Add worker signing copy (canonicalization, `sign_envelope` / `verify_envelope`, `build_receipt`) with round-trip, tamper, and cross-verification tests (`products/execution-runtime/src/execution_runtime/services/execution_signing.py`, tests)
- [x] Add `POST /api/v1/executions/handoff` with handoff-token auth (constant-time), envelope signature verification, and args-digest re-verification — each failure structured and audited (`api/routes/handoff.py`, tests)
- [x] Test the missing-secret posture: unset signing key or handoff token rejects every handoff (tests)

## R-3: Worker-side execution and receipt authorship

- [x] Add executor invoking the tool-gateway with the forwarded delegated token; timeout and error mapping; token never logged or persisted (`services/executor.py`, tests)
- [x] Add execution records store copy (memory + Postgres, shared `execution_records` table, first-write-wins receipt close, late-arrival no-overwrite) (`services/execution_records.py`, tests)
- [x] Add audit emitter copy emitting `execution_completed` / `execution_rejected` with `confirm_id` + forwarded `x-request-id` (`services/audit_emitter.py`, tests)
- [x] Document the crash-window recovery query (correlate `execution_requested` vs tool-gateway `tool_invoked`) in the approval-and-HITL guide (`docs/guides/approval-and-hitl.md`)

## R-4: Blocking handoff on the resumed stream

- [x] Add `execution_worker_client.py` handoff client with timeout and transport-error mapping (`products/agent-platform/src/agent_service/services/execution_worker_client.py`, tests)
- [x] Add `execution_worker_url`, `execution_handoff_token`, `execution_worker_timeout_seconds` (default 60, > 0) settings (`products/agent-platform/src/agent_service/runtime_settings.py`, tests)
- [x] Route mutating invocations through the handoff after the existing envelope verification; keep read-only paths untouched; missing worker config rejects `worker_unavailable` before any handoff (`tools/gateway_tools.py`, tests)
- [x] Map handoff timeout onto the structured timeout result and the `timeout` receipt close (first-write-wins) (kernel + tests)

## R-5: Single-flight idempotency keyed by `execution_id`

- [x] Add single-flight registry: concurrent join, post-completion replay without re-execution, bounded retention eviction (`services/single_flight.py`, tests)
- [x] Pin the `replicas: 1` invariant and the durable-registry scaling note in the product README (`products/execution-runtime/README.md`)

## R-6: Deployment and infrastructure-level isolation

- [x] Add `base/execution-runtime/` manifests: Deployment (non-root, `enableServiceLinks: false`, `/health/live` + `/health/ready` probes) + ClusterIP Service + `runtime-config.env`; wire into `base/kustomization.yaml` (`shared/platform-ops/gitops/dev-k8s/`)
- [x] Mount `execution-signing-secret` as `EXECUTION_SIGNING_KEY` and the handoff secret as `EXECUTION_HANDOFF_TOKEN` on the worker deployment
- [x] Add `sync-execution-handoff-secret.sh` with `SKIP_EXECUTION_HANDOFF_SECRET` guard and wire into `dev-k8s/deploy.sh` (`shared/platform-ops/gitops/`)
- [x] Add `AGENT_EXECUTION_WORKER_URL` and `AGENT_EXECUTION_HANDOFF_TOKEN` to the agent-service deployment/config (`shared/platform-ops/gitops/dev-k8s/base/agent-platform/`)
- [x] `make overlays` renders all overlays; confirm no HTTPRoute or gateway route references the worker Service

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] live check: `mutating-demo.sh` on the `mutating-dev` profile executes via the worker pod with the correlated cross-service audit chain and the receipt badge on the decided card
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
