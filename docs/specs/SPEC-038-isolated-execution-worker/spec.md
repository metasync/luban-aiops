# SPEC-038: Isolated Execution Worker

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-08-27
- release slice: R4 — Approval-Gated Bounded Actions (R4 closing slice)
- related ADRs: none (spike memo: `docs/workspace/execution-runtime-spike.md`, Phase 2)

## Summary

Approved mutating actions stop executing in-process in agent-service: a
new `execution-runtime` worker product receives the SPEC-037 signed
execution envelope over an authenticated internal handoff, verifies the
signature and the parked-arguments digest, performs the tool-gateway call
with the forwarded delegated token, writes the signed receipt, and returns
the outcome — while the resumed stream blocks on the worker with a bounded
timeout so the operator still watches the result arrive in the same turn.
The worker inherits the SPEC-037 envelope contract verbatim (it becomes
the first production consumer of `execution_signing.verify_envelope`),
single-flight idempotency keyed by `execution_id` makes re-execution of a
mutating action structurally impossible, and the isolation boundary is
enforced at the infrastructure layer (own deployment, ClusterIP-only, no
portal or LLM exposure).

## Motivation

- **Execution is still coupled to the agent process.** SPEC-037 made the
  approval-to-execution binding tamper-evident, but the approved call
  itself runs inside the resumed agent-service turn, sharing the kernel
  process's blast radius, resources, and lifetime. The spike memo
  (`docs/workspace/execution-runtime-spike.md` §4.2) names the isolated
  worker as Phase 2 and the eventual target.
- **The promotion gate is satisfied.** Phase 1 (SPEC-037, signed
  execution requests and receipts) shipped in v0.19.0 and was
  live-verified on the `mutating-dev` profile — per the memo's phasing
  rule, Phase 2 takes its own spec number now, keeping each release one
  vertical slice.
- **The signed envelope was built for this consumer.**
  `execution_signing.verify_envelope` currently has no production call
  site; the spike memo reserved it for Phase 2. Until the worker exists,
  the envelope signature proves integrity only reconstructively — the
  invoking process verifies the digest it computed itself. A separate
  process that re-verifies signature and digest from the envelope is the
  first genuinely independent check in the chain.
- **The boundary is already stated but unenforced.**
  `products/execution-runtime/` is a README stub whose boundary
  statement fixes the invariants (receives signed requests, never
  decides allowance, never bypasses policy or approval). This spec makes
  those invariants real and enforces them at the infrastructure layer.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance signals.

### R-1: The execution-runtime worker product

`products/execution-runtime/` becomes a real product: a Python service
on the shared base-uv image with the house layout (app factory, frozen
`EXECUTION_*` settings module with startup validation, structured JSON
logging, health endpoint), wired into the root Makefile (`PYTHON_PRODUCTS`
and `IMAGE_PRODUCTS`, coordinated image tag, `.images.env` entry, kind
load list) behind the shared `mk/` fragments. The worker carries no LLM
provider keys, no kernel state, and no session data — its only outbound
dependencies are the tool-gateway (execution), the shared state Postgres
(execution records), and the audit-service (best-effort emission).

Acceptance signals:

- `make build` and `make verify` include the new product: its test suite
  runs and its image builds with the coordinated tag alongside the
  existing products.
- The settings module rejects malformed `EXECUTION_*` values at startup
  and the app starts with only a health endpoint before any handoff
  wiring exists.

### R-2: Authenticated internal handoff with fail-closed verification

The worker exposes a single internal endpoint accepting the signed
execution request envelope, the parked arguments, and the confirmer's
delegated token. It authenticates the caller with a dedicated handoff
credential and verifies the envelope before any execution: the handoff
token is compared constant-time against the worker's provisioned secret,
the envelope signature is verified with
`verify_envelope` (the module's first production call site, key
provisioned from the existing `execution-signing-secret`), and the
received arguments' digest is recomputed and compared against the signed
`args_digest`. Any failure rejects before execution and audits
`execution_rejected` with reason `unauthorized`, `signature_invalid`, or
`args_digest_mismatch`. An unprovisioned signing key or handoff secret
fails closed — the worker rejects everything rather than degrading to
unverified execution.

Resolution of the memo's Q-1: the worker holds its own service
credential — a static, scope-limited handoff token shared only with
agent-service, provisioned by a `sync-execution-handoff-secret.sh` in
the deploy chain (same posture as the execution signing secret and the
SPEC-008 R-3 static client credential: it confers no user authority and
authorizes only the handoff operation). Unauthenticated cluster-local
trust is rejected — any pod in the namespace could otherwise submit an
envelope. SPEC-009-style projected workload identity remains the
documented upgrade path, adopted once for all services rather than
bespoke here.

Acceptance signals:

- Handoff tests: a valid token + valid envelope + digest-matching
  arguments proceed; a wrong handoff token yields `401` and executes
  nothing; a tampered envelope (any field changed) yields a structured
  rejection with `signature_invalid`; mutated arguments yield
  `args_digest_mismatch`; each rejection path audits
  `execution_rejected` with its reason.
- Missing-secret posture tests: with the signing key or the handoff
  secret unset, every handoff is rejected — no unsigned execution path
  exists.

### R-3: Worker-side execution and receipt authorship

After verification the worker performs the tool-gateway call, presenting
the forwarded delegated token as the bearer (identity posture unchanged:
the tool-gateway still evaluates `tools:mutate` admission and policy on
the confirmer's delegated identity). The delegated token is in-memory
only — never persisted, never logged. On completion the worker signs
and writes the receipt into the shared `execution_records` table
(copy-with-parity store module on the same Postgres posture, receipts
close only `status='requested'` rows — first write wins) and emits
`execution_completed` (or `execution_rejected` on a failed invocation)
through the canonical fire-and-forget emitter with `confirm_id` and the
forwarded `x-request-id`, then returns the receipt and the gateway
result. A worker crash after execution but before the receipt lands is
reconciled by a documented recovery query against the tool-gateway's own
`tool_invoked` audit — never by automatic retry.

Acceptance signals:

- Executor tests: the gateway call carries the forwarded bearer token;
  the token never appears in logs or persisted records; succeeded,
  failed, and gateway-timeout outcomes map onto the receipt status
  `succeeded` / `failed` / `timeout`.
- Record tests (memory + Postgres parity): the receipt closes a
  `requested` row exactly once; a second close attempt (late arrival)
  does not overwrite and the late completion is logged/audited, not
  lost.
- The recovery query (correlating `confirm_id` / `x-request-id` against
  `tool_invoked` events) is documented in the approval-and-HITL guide.

### R-4: Blocking handoff on the resumed stream

Approved mutating invocations in a resumed turn are handed to the worker
instead of calling the tool-gateway inline: agent-service keeps its
SPEC-037 invocation-boundary verification (envelope presence and digest
match) *before* the handoff goes out, then awaits the worker response
with a bounded timeout. The resumed stream blocks on that await, so the
operator watches the result arrive in the same turn; the returned
gateway result flows through the existing evidence-frame and transcript
paths unchanged. Read-only tools never hand off and are untouched.

Resolution of the memo's Q-2: a dedicated knob
`AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` (default 60 — the worker's own
30s gateway-call budget plus verification and receipt overhead), not the
HITL timeout, which governs how long a *parked* confirmation stays
answerable and is an unrelated concern.

Fail-closed posture: if the worker URL or the handoff token is not
configured, a mutating resume rejects execution with reason
`worker_unavailable` (audited) — there is no silent fallback to
in-process execution. A handoff timeout surfaces a structured timeout
result in the stream and closes the record with a `timeout` receipt
(first-write-wins per R-3); a late worker completion then lands as R-3's
late-arrival case. Any handoff transport error rejects with
`worker_unavailable`.

Acceptance signals:

- Resume-path tests: an approved mutating call hands off the signed
  envelope, the parked arguments, and the delegated token, and the
  stream resumes with the worker-returned result; read-only calls never
  touch the handoff client.
- Posture tests: unset worker URL or token rejects with
  `worker_unavailable` before any handoff attempt; a timed-out handoff
  yields the structured timeout result and a `timeout` receipt close; a
  late receipt after timeout close does not overwrite it.

### R-5: Single-flight idempotency keyed by `execution_id`

The worker executes each `execution_id` at most once: an in-process
single-flight registry joins a concurrent duplicate handoff onto the
in-flight execution (both callers receive the same outcome), and a
repeat handoff after completion returns the recorded outcome without
re-executing. Re-execution of a mutating action is never automatic — no
retry, queue, or scheduler exists in the worker. The registry is bounded
(completed entries evicted after a capped retention window) and the
deployment runs a single replica, which keeps the in-process registry
authoritative.

Acceptance signals:

- Concurrency test: two simultaneous handoffs with the same
  `execution_id` produce exactly one gateway call and both callers
  receive the same receipt/result.
- Replay test: a handoff for a completed `execution_id` returns the
  recorded outcome and issues no gateway call.
- Eviction test: entries older than the retention window are dropped
  without affecting in-flight executions.

### R-6: Deployment and infrastructure-level isolation

The worker ships as its own dev-k8s deployment behind the existing base
overlay: a Deployment (non-root securityContext, `enableServiceLinks:
false`, same probe posture as the other services) and a ClusterIP
Service — and nothing else. Isolation is enforced at the infrastructure
layer: no HTTPRoute, no platform-gateway route, and no portal surface
references the worker; its only inbound path is the authenticated
handoff from agent-service. The deployment mounts the
`execution-signing-secret` (as `EXECUTION_SIGNING_KEY`) and the new
handoff secret; agent-service gains `AGENT_EXECUTION_WORKER_URL` and
`AGENT_EXECUTION_HANDOFF_TOKEN`. The deploy chain gains
`sync-execution-handoff-secret.sh` honoring
`SKIP_EXECUTION_HANDOFF_SECRET=true` for CI, matching the existing
`SKIP_*_SECRETS` pattern.

Acceptance signals:

- `make overlays` renders all overlays with the new Deployment, Service,
  and env additions; no overlay introduces an external route for the
  worker.
- Deploy chain: `deploy.sh` invokes the new sync script; the worker pod
  starts with its secrets mounted and its health endpoint green.
- Live check: `mutating-demo.sh` on the `mutating-dev` profile completes
  the HITL leg with the worker pod performing the gateway call — the
  audit chain (`execution_requested` → `tool_invoked` →
  `execution_completed`) correlates across agent-service, the worker,
  and the tool-gateway, and the decided card still shows the receipt
  badge.

## Non-Goals

- Async execution queues, retries, schedules — rejected in the spike
  memo; the approval-queue remainder stays parked as the R5-shaped
  scope (SPEC-030 memo option C). Recorded re-evaluation trigger
  (operator sign-off 2026-08-27): when more team members work
  concurrently, simultaneous approved actions may contend on the single
  worker pod — if that concurrent volume produces queueing pressure, R5
  re-evaluates and promotes the queue/pool spec at that signal.
- Multi-replica workers — single-flight is in-process; the deployment
  pins `replicas: 1` and scaling requires a durable flight registry
  (part of the same R5 re-evaluation).
- Receipt exposure changes — receipts stay owner-visible on the session
  surface (the memo's Q-3, resolved by SPEC-037 R-6; the approver
  surface stays decision-metadata-only).
- Workload-identity or mTLS handoff authentication — the cross-service
  upgrade path applies once to all services, not bespoke here.
- NetworkPolicy — no overlay uses one today; the no-route + ClusterIP +
  authenticated-handoff posture is the enforcement surface.
- Any change to approval tiers, policy semantics, HITL timeout, or
  read-only tool paths.
- New contracts — `execution-request.schema.json` and
  `execution-receipt.schema.json` are inherited verbatim; the rejection
  reasons ride the existing `execution_rejected` details payload.

## Impact

- products touched: `products/execution-runtime` (new product: worker
  service, handoff API, executor, record store, single-flight registry),
  `products/agent-platform` (handoff client, resume-path routing, new
  settings knobs), `shared/platform-ops/gitops` (handoff-secret sync
  script, dev-k8s worker manifests, agent-service env additions), root
  `Makefile` (product wiring)
- contracts touched: none — the SPEC-037 schemas are inherited verbatim;
  audit events reuse the three SPEC-037 `event_type` values
- identity / policy / audit / execution safety impact: execution moves
  to an isolated process under an independently verified signature; the
  execution identity posture (confirmer's delegated token evaluated by
  the tool-gateway) is unchanged, no grant is widened, no approval
  surface changes; the chain gains a second, independent verification
  point
- living state docs to update on delivery: `products/execution-runtime`
  README (stub → real boundary and configuration), approval-and-HITL
  guide (worker path + recovery query), configuration-reference (new
  knobs and secret), dev-k8s README, CHANGELOG, delivery-roadmap, spec
  index

## Open Questions

None — the memo's Q-1 is resolved in R-2 (dedicated static handoff
credential in the SPEC-008 R-3 posture; unauthenticated cluster-local
trust rejected) and Q-2 in R-4 (dedicated
`AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` knob, default 60s); Q-3 was
resolved by SPEC-037 R-6. All resolvable at draft; must stay empty
before approval.

## Changelog

- 2026-08-27: approved by the operator with one recorded condition —
  the single-replica / no-queue posture carries an explicit R5
  re-evaluation trigger: concurrent approved actions from multiple team
  members working simultaneously (recorded in the Non-Goals and the
  roadmap backlog row). Implementation proceeds in a fresh session.
- 2026-08-27: created as `draft` from the execution-runtime spike memo
  (Phase 2) after the memo's promotion gate was satisfied — Phase 1
  (SPEC-037) delivered in v0.19.0 and live-verified on the
  `mutating-dev` profile.
