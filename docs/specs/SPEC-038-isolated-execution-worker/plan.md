# SPEC-038 Implementation Plan

One new product does the execution work (execution-runtime); one
existing product grows a thin handoff client (agent-platform). The
SPEC-037 envelope contract is inherited verbatim — no new schemas, no
schema changes — and the resume stream keeps its "approve → watch it
happen" shape by blocking on the worker with a bounded timeout. Duplicated
substrate (canonicalization/signing, execution records, audit emitter)
ships copy-with-parity per the workspace posture; the shared-sdk
extraction spike's revisit triggers govern any later consolidation.

## R-1 execution-runtime worker product

- `products/execution-runtime/`: new product with the house layout —
  `pyproject.toml` (version locked to the platform version per the
  lockstep validator) + `uv.lock`, `Dockerfile` FROM
  `luban-aiops/base-uv:al2023` (WORKDIR re-declaration,
  `COPY --chown=app:app`, `uv sync --frozen --no-dev`), `Makefile`
  including `mk/python.mk` + `mk/image.mk` (image name
  `luban-aiops/execution-runtime`), `.python-version` (3.12).
- `src/execution_runtime/`: `app.py` factory (FastAPI, structured JSON
  logging with `x-request-id` propagation, `/healthz`), `core/config.py`
  frozen settings (`EXECUTION_*` prefix): `execution_signing_key`
  (`EXECUTION_SIGNING_KEY`), `handoff_token` (`EXECUTION_HANDOFF_TOKEN`),
  `tool_gateway_url` (`TOOL_GATEWAY_URL`),
  `gateway_timeout_seconds` (`EXECUTION_GATEWAY_TIMEOUT_SECONDS`,
  default 30 — parity with agent-service's `INVOKE_TIMEOUT_SECONDS`),
  `state_store_backend` / `state_db_url` (same
  `EXECUTION_STATE_STORE_BACKEND` / `EXECUTION_STATE_DB_URL` posture as
  the other state-backed services), `audit_service_url` /
  `audit_client_id` / `audit_client_secret` (unset = log-only parity),
  single-flight retention knob (`EXECUTION_FLIGHT_RETENTION_SECONDS`,
  default 900).
- Root `Makefile`: add `execution-runtime` to `PYTHON_PRODUCTS` and
  `IMAGE_PRODUCTS`; `build` writes
  `EXECUTION_RUNTIME_IMAGE=luban-aiops/execution-runtime:$(IMAGE_TAG)`
  into `.images.env` and includes it in the kind load list.

## R-2 authenticated handoff with fail-closed verification

- `api/routes/handoff.py`: `POST /api/v1/executions/handoff` — body
  `{request: <signed envelope>, arguments: <parked args>,
  delegated_token: <confirmer bearer>}`; response
  `{receipt: <signed receipt envelope>, result: <gateway result dict>}`.
  Rejections return structured 4xx bodies carrying the reason; transport
  headers never leak the token or the envelope.
- Auth + verification order (all fail-closed, all before any execution):
  1. `Authorization: Bearer <handoff-token>` compared constant-time
     against `EXECUTION_HANDOFF_TOKEN` → `401 unauthorized`;
  2. `verify_envelope(request, request["signature"], signing_key)` →
     structured rejection `signature_invalid` (first production call
     site of the module);
  3. `canonical_digest(arguments)` compared constant-time against the
     envelope's `args_digest` → structured rejection
     `args_digest_mismatch`.
- `services/execution_signing.py` (worker copy): `canonical_json`,
  `canonical_digest`, `sign_envelope`, `verify_envelope`,
  `build_receipt` — byte-parity with the agent-platform module, pinned
  by cross-verification tests (envelope signed by agent-platform tests
  verifies under the worker copy and vice versa).
- Missing `EXECUTION_SIGNING_KEY` or `EXECUTION_HANDOFF_TOKEN` → every
  handoff rejected at the corresponding check; the app still serves
  `/healthz`.
- Every rejection audits `execution_rejected` (reason, `confirm_id` from
  the envelope, forwarded `x-request-id`) through the canonical emitter.

## R-3 worker-side execution and receipt authorship

- `services/executor.py`: one-shot `httpx.AsyncClient` POST to
  `{tool_gateway_url}/api/v2/tools/invoke` with the forwarded delegated
  token as bearer and the 30s budget; `httpx.TimeoutException` maps to a
  structured `TIMEOUT` result (same shape as agent-service's), gateway
  error shapes pass through. The delegated token is never logged or
  persisted (log-redaction test).
- `services/execution_records.py` (worker copy):
  `ExecutionRecordStore` protocol with memory + Postgres backends on the
  shared `execution_records` table (same in-place creation and
  startup-sweep posture). Receipt write closes only a
  `status='requested'` row — first write wins; a close attempt on an
  already-closed row returns the existing receipt (the late-arrival
  case) and logs/audits the late completion instead of overwriting.
- Receipt construction via the worker copy of `build_receipt`
  (status mapped from the result: `succeeded` / `failed` / `timeout`,
  correlating `request_id` = the handoff's forwarded `x-request-id`).
- `services/audit_emitter.py` (worker copy, fire-and-forget parity):
  `execution_completed` at receipt write (status, duration_ms,
  `request_id`), `execution_rejected` at verification or invocation
  failure; all carry `confirm_id`.
- Crash-window recovery: the approval-and-HITL guide gains the recovery
  query — correlate `confirm_id` / forwarded `x-request-id` from
  `execution_requested` against tool-gateway `tool_invoked` events to
  determine whether a missing receipt's call actually executed. No retry
  mechanism exists in the worker; the query is operator-run.

## R-4 blocking handoff on the resumed stream

- `products/agent-platform/src/agent_service/services/execution_worker_client.py`:
  `handoff(request, arguments, delegated_token, settings) -> dict` —
  POST to `AGENT_EXECUTION_WORKER_URL` with
  `Authorization: Bearer AGENT_EXECUTION_HANDOFF_TOKEN`, client timeout
  `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` (new `runtime_settings` knob,
  default 60); raises structured errors for transport failure and
  timeout carrying the worker's rejection reason where one exists.
- `runtime_settings.py`: three new knobs — `execution_worker_url`
  (`AGENT_EXECUTION_WORKER_URL`), `execution_handoff_token`
  (`AGENT_EXECUTION_HANDOFF_TOKEN`), `execution_worker_timeout_seconds`
  (`AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS`, default 60, validated > 0).
- `tools/gateway_tools.py` mutating branch: the existing
  `_verify_execution_request` check stays (defense in depth, and it
  keeps the fail-closed `EXECUTION_REJECTION` posture for missing-key
  resumes); on pass, mutating calls hand off instead of calling
  `invoke_gateway_tool` — the returned `result` dict flows into the
  existing `ToolChunk` / evidence-frame path unchanged. Missing worker
  URL or token on a mutating call rejects with `worker_unavailable`
  (audited) before any handoff attempt — no in-process fallback exists.
  Read-only closures are untouched.
- Timeout path: a handoff timeout yields the structured timeout result
  (code `TIMEOUT`, distinguishing text) so the resumed-stream frame
  handling writes the `timeout` receipt close (first-write-wins) — the
  same receipt-close path SPEC-037 uses today; the worker's late
  completion afterwards lands as R-3's already-closed case.

## R-5 single-flight idempotency

- `services/single_flight.py` (worker): asyncio registry keyed by
  `execution_id` — the first handoff creates the flight and runs the
  executor; concurrent duplicates await the same future; completed
  flights cache their `(receipt, result)` and serve repeats directly
  until eviction (`EXECUTION_FLIGHT_RETENTION_SECONDS`, bounded entry
  count). The gateway call happens exactly once per `execution_id`.
- The registry is in-process and authoritative because the deployment
  pins `replicas: 1`; the README boundary section records that scaling
  requires a durable flight registry first.

## R-6 deployment and infrastructure isolation

- `shared/platform-ops/gitops/dev-k8s/base/execution-runtime/`:
  `execution-runtime-deployment.yaml` (non-root securityContext
  runAsUser 1000, seccomp RuntimeDefault, `enableServiceLinks: false`,
  env from `platform-runtime-config` + the two secrets, liveness/readiness
  on `/healthz`, prometheus annotations parity), `execution-runtime-service.yaml`
  (ClusterIP, port 8000), `runtime-config.env`
  (`TOOL_GATEWAY_URL=http://tool-gateway:8000`, state backend pointed at
  the sessions Postgres). Wired into `base/kustomization.yaml` resources
  (+ configMapGenerator envs entry). No HTTPRoute, no gateway patch —
  grep-level check in the live leg that no route references the Service.
- Secrets: the worker deployment mounts `execution-signing-secret` as
  `EXECUTION_SIGNING_KEY` (`optional: true`, fail-closed parity) and the
  new `execution-handoff-secret` as `EXECUTION_HANDOFF_TOKEN`.
  agent-service deployment gains `AGENT_EXECUTION_HANDOFF_TOKEN` from
  the handoff secret and `AGENT_EXECUTION_WORKER_URL`
  (`http://execution-runtime:8000`) via `agent-platform/runtime-config.env`.
- `shared/platform-ops/gitops/sync-execution-handoff-secret.sh`:
  generate-or-reuse handoff token, write `execution-handoff-secret`,
  honor `SKIP_EXECUTION_HANDOFF_SECRET=true`; wired into
  `dev-k8s/deploy.sh` beside the other sync scripts.
- `mutating-dev` profile inherits the worker from base — no profile
  patch needed.

## Sequencing And Dependencies

1. Worker product scaffold + settings (R-1) — depends on nothing
2. Signing copy + handoff route with verification and rejection audit
   (R-2) — depends on 1
3. Executor + record store + audit emitter copy (R-3) — depends on 2
4. Single-flight registry (R-5) — depends on 3 (wraps the executor)
5. agent-platform handoff client + resume-path routing + timeout posture
   (R-4) — depends on the handoff contract shape from 2; parallel with 4
6. Deploy chain + overlays (R-6) — depends on 1–5
7. Live check on `mutating-dev` + doc updates — depends on 6

## Test Strategy

- unit tests (`products/execution-runtime/tests/`): settings validation;
  signing copy round-trip + tamper rejection + cross-verification with
  agent-platform-signed envelopes; handoff auth/verification matrix
  (valid, wrong token, tampered envelope, mutated args, missing secrets);
  executor result/timeout mapping and token-redaction; record store
  memory + Postgres parity, first-write-wins close, late-arrival
  no-overwrite; single-flight concurrency join, replay no-reexecute,
  eviction
- unit tests (`products/agent-platform/tests/`): worker client timeout
  and transport-error mapping; mutating handoff routing with envelope
  verification intact; read-only untouched; `worker_unavailable`
  fail-closed posture; timeout receipt close; runtime settings knobs
- contract tests: no schema changes — the existing SPEC-037 schema
  validators stay green; `make validate-policy` unaffected
- integration / overlay validation: `make overlays` renders all three
  overlays with the worker manifests and env additions; live check runs
  `mutating-demo.sh` on the `mutating-dev` profile and asserts the
  worker pod performed the call (worker `execution_completed` audit
  emission), the cross-service audit chain correlates, the decided card
  shows the receipt badge, and no route exposes the worker

## Rollout And Migration

- deployment changes: new Deployment/Service and two env additions via
  the deploy chain; new handoff secret synced at deploy; overlays
  re-render
- backward compatibility: read-only flows and denial flows are untouched;
  the `mutating-dev` profile's operator-visible behavior is unchanged
  (approve → watch it happen), only the executing process moves; decided
  cards and receipts render identically
- fail-closed posture: an unprovisioned worker secret or missing worker
  URL blocks mutating execution (by design); rollback restores the
  pre-spec behavior by redeploying the previous images — there is no
  feature flag, matching SPEC-037's rollback stance
