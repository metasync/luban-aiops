# v0.20.0 — Isolated Execution Worker (SPEC-038)

Date: 2026-08-27
Release type: minor (new internal service and handoff contract; no
approval, policy, HITL, or owner/approver surface change)

## Summary

v0.20.0 delivers Phase 2 of the execution-runtime spike
(`docs/workspace/execution-runtime-spike.md`) and closes R4: approved
mutating calls no longer execute in-process in agent-service. A new
`execution-runtime` worker product receives the SPEC-037 signed
execution envelope over an authenticated internal handoff,
independently re-verifies the signature and the parked-arguments
digest, performs the tool-gateway call under the forwarded confirmer
delegated token, authors the signed receipt on the shared
`execution_records` table, and emits the correlated execution audit
events. The resumed stream blocks on the worker under a bounded
timeout, single-flight idempotency makes re-execution structurally
impossible, and every missing credential fails closed — there is no
in-process fallback. The approval chain, receipt badge, and audit
correlation delivered in v0.19.0 are unchanged from the operator's
viewpoint; the chain simply gains a second, independent verification
point and an isolated executor.

## What Changed

### The execution-runtime worker product (R-1)

- New `products/execution-runtime` product in full lockstep:
  FastAPI app with `/health/live` + `/health/ready`, structured
  logging and `x-request-id` propagation, frozen `EXECUTION_*`
  settings with startup validation, base-uv Dockerfile, and root
  Makefile wiring (tests, images, kind load).

### Authenticated internal handoff, fail-closed (R-2)

- `POST /api/v1/executions/handoff` authenticates agent-service with a
  static handoff token (constant-time comparison), then verifies the
  envelope signature and recomputes the invoked arguments' digest —
  the worker becomes the first production consumer of
  `execution_signing.verify_envelope`. Each failure is structured and
  audited (`unauthorized` / `signature_invalid` /
  `args_digest_mismatch` / `bad_request`). An unset signing key or
  handoff token rejects every handoff; no degradation path exists.

### Worker-side execution and receipt authorship (R-3)

- The executor invokes the tool-gateway with the forwarded confirmer
  delegated token (identity, policy, and risk-tier evaluation
  unchanged), never logging or persisting the token. The record store
  copy writes receipts to the shared `execution_records` table with
  first-write-wins close semantics, and the audit emitter copy emits
  `execution_completed` / `execution_rejected` with `confirm_id` and
  the forwarded `x-request-id`. The approval-and-HITL guide documents
  the crash-window recovery query (correlate `execution_requested`
  against tool-gateway `tool_invoked`; the worker has no retry path).

### Blocking handoff on the resumed stream (R-4)

- agent-service gains `execution_worker_client.py` plus three settings
  knobs (`AGENT_EXECUTION_WORKER_URL`, `AGENT_EXECUTION_HANDOFF_TOKEN`,
  `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` default 60s). After the
  existing SPEC-037 invocation-boundary verification, mutating calls
  route through the handoff; read-only paths are untouched. Missing
  worker configuration or any handoff transport error rejects the
  resume with an audited `worker_unavailable` rejection; a handoff
  timeout lands as the structured timeout result and closes the record
  with a `timeout` receipt.

### Single-flight idempotency (R-5)

- An in-process registry keyed by `execution_id` joins concurrent
  handoffs onto one execution, replays completed outcomes without
  re-executing, and bounds retention (900s plus a completion cap with
  eviction). The deployment pins `replicas: 1`; scaling beyond it
  requires a durable registry first (recorded in the product README
  and the roadmap's R5 re-evaluation trigger).

### Infrastructure-enforced isolation (R-6)

- dev-k8s gains `base/execution-runtime/` (non-root Deployment with
  house probes, ClusterIP Service, runtime-config fragment) wired into
  the base kustomization, mounting `execution-signing-secret` and the
  new `execution-handoff-secret`. `sync-execution-handoff-secret.sh`
  provisions the token (generate → reuse ladder, skippable) and is
  wired into `deploy.sh`; `sync-audit-secrets.sh` registers the worker
  as an audit ingest client. agent-service receives
  `AGENT_EXECUTION_WORKER_URL` + the handoff token via optional
  `secretKeyRef`. No HTTPRoute or gateway route references the worker
  Service — it is reachable only inside the cluster.

## Validation

- Execution-runtime suite 64 passed (handoff auth/verification matrix
  incl. non-ASCII header hardening, missing-secret posture, executor
  token handling, record store both backends with first-write-wins,
  audit emission, single-flight concurrency/replay/eviction and
  failed-flight joiner release); agent-platform suite 547 passed
  (handoff client fail-closed matrix, worker routing, timeout mapping,
  settings). Pre-commit review remediations: failed single-flight
  futures now release concurrent joiners, and the handoff route's
  constant-time comparisons are byte-wise so attacker-controlled
  non-ASCII tokens/signatures land structured audited rejections
  instead of bare 500s.
- `make verify` green: full product test suites, three kustomize
  overlays, policy validation, version lockstep 0.20.0.
- Live check: `mutating-demo.sh` HITL leg on the `mutating-dev`
  profile — the approved call executes via the execution-runtime pod,
  the receipt badge renders on the decided card, and the correlated
  `execution_requested` / `execution_completed` chain lands on the
  durable trail from both service vantage points.
