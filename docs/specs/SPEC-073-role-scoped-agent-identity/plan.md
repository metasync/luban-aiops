# SPEC-073 Plan: Role-Scoped Agent Identity and Authority

> Binding on approval (2026-11-03). Phase 2 ships an **inert substrate**: no orchestration
> caller, no change to the deployed single-agent turn, no contract change, no gateway/policy
> change. Approval authorizes implementation to *begin* — not a merge, commit/push, deployment,
> or version bump (separate gates).

## Approach

Generalize the one existing authority-narrowing seam — `_ensure_toolkit(bearer_token, read_only)`
and its `::read-only` cache suffix — from a boolean into a **closed three-value agent-role enum**
(`diagnostician`, `orchestrator`, `executor`), carried as a **process-local ContextVar beside
`DELEGATED_TOKEN`** (`AGENT_ROLE`). Every role rides the **same** gateway-forwarded delegated token
(ADR-0004); a role only ever *subtracts* tools, never adds one and never mints a second identity.
The work groups into four stages: (1) the role type + contextvar; (2) per-role toolkit narrowing on
the existing seam; (3) the kernel-internal provenance label on an executor-staged mutation;
(4) fail-closed guards, the inertness proof, and doc reconciliation. All of it lands in
`products/agent-platform` only.

## Design Per Requirement

### R-1: A closed, platform-owned agent-role vocabulary

- affected: a new small module `products/agent-platform/src/agent_service/services/agent_role.py`
  (beside `delegated_identity.py`).
- approach: an `enum.Enum` (or `StrEnum`) `AgentRole` with exactly three members —
  `diagnostician`, `orchestrator`, `executor` — whose `.value`s are plain lowercase platform
  strings. A module-level `AGENT_ROLE: ContextVar[AgentRole | None] = ContextVar("AGENT_ROLE",
  default=None)` mirrors `REQUESTER_IDENTITY`/`CHAT_SESSION_ID`. A binding helper
  `bind_agent_role(role)` validates against the closed set and **fails closed** (raises on an
  unknown value; never coerces). No agentscope import anywhere in the module.
- alternatives rejected: a free-string role (rejected — not closed, model-influenceable);
  per-role broker identities (rejected by ADR-0017 Decision 4); a role as a JWT claim (rejected by
  R-3 — process-local only in phase 2).

### R-2: Per-role toolkit narrowing at the existing seam

- affected: `runtime_kernel.py` — `_ensure_toolkit`, its `cache_key`, and a new `_narrow_for_role`.
- approach: extend the cache key from `(token) + ("::read-only" if read_only else "")` to append
  `::{role.value}` **only when a role is bound** (an unscoped turn keeps today's exact key and one
  cache entry). `_narrow_for_role(definitions, role)` composes with the existing filters:
  `diagnostician` → `_filter_read_only` (read-level only); `executor` → the full discovered set
  (mutating tools still park on HITL, R-4); `orchestrator` → **empty of gateway tools** (delegates,
  invokes nothing). Narrowing is **subtractive-only**: the result is always a subset of the
  unscoped toolkit for the same token.
- alternatives rejected: a tool-family allowlist (deferred to phase 3's policy role axis — OQ-3);
  a gateway-side role check (phase 3 — OQ-3); splitting the cache unconditionally (would change the
  unscoped path — rejected to preserve byte-identical single-agent behavior).

### R-3: Same-token identity preservation ("on whose behalf")

- affected: `agent_role.py` (the contextvar), `runtime_kernel.py` (set/reset around a role-scoped
  turn, mirroring the `DELEGATED_TOKEN.set`/`.reset` bracket), `services/delegated_identity.py`
  (unchanged — read-only reliance).
- approach: a role-scoped turn sets `AGENT_ROLE` and leaves `DELEGATED_TOKEN` and the SPEC-070
  `REQUESTER_IDENTITY`/`DECIDER_IDENTITY` untouched; the member presents the **same** token as its
  orchestrator. No code path mints, requests, or caches a second broker token for a role. The role
  never becomes a JWT claim, a forwarded header, or any wire field in phase 2.
- alternatives rejected: embedding the role in the delegated token (rejected — a role is an
  authority-narrowing label, not a credential; gate point 2 forbids a per-role mint).

### R-4: Authority-provenance labeling on a role-staged mutation (ADR-0010 pattern)

- affected: the kernel's parked-confirmation record construction (the HITL park path);
  `execution-request.schema.json` is **not** touched.
- approach: when an `executor`-scoped agent stages a mutation, record the staging `AgentRole` on the
  **kernel-internal** parked/confirmation record (a Python field beside the existing park payload),
  following ADR-0010's "provenance rides the signed fact" spirit but **without a wire field** in
  phase 2 (OQ-4). The mutation still parks on the existing HITL confirmation (SPEC-020/030/031) and
  dispatches through the signed at-most-one-dispatch worker (SPEC-037/038/063) with a **distinct
  human** approver; the executor cannot self-approve (SPEC-030 fires unchanged, R-3).
- alternatives rejected: an additive optional `staged_by_role` field on
  `execution-request.schema.json` now (deferred to phase 4 when an audit consumer exists — OQ-4;
  ADR-0017 Decision 6 puts the contract change last).

### R-5: Fail-closed invariants and four-point-gate parity

- affected: `agent_role.py`, `_narrow_for_role`, and the agent-platform test suite.
- approach: an absent/unrecognized role yields the most restrictive posture (no gateway tools /
  read-only), never a wider one. A **guard test** asserts no role-scoped code path is reachable
  from the deployed `/api/v2/chat` and `/chat/stream` handlers (phase 2 wires no caller), and a
  **no-diff test** asserts the single-agent turn is byte-identical with the substrate present but
  unexercised.
- alternatives rejected: wiring a caller in phase 2 (out of scope — the orchestration loop is
  phase 5).

### R-6: Documentation and contract reconciliation

- affected: `docs/agentic-aiops-platform/identity-and-authorization-design.md`, the ADR-0017
  consequence note, the roadmap multi-agent backlog row, and `docs/specs/README.md`.
- approach: on delivery, record the role model + same-token invariant + phase boundaries (what
  phases 3–6 own) in the identity design doc; annotate ADR-0017's consequence that phase 2 is
  delivered; flip the specs-index and roadmap rows to `delivered`. **No v2 contract schema change**
  (phase 6 owns any additive multi-agent framing).
- alternatives rejected: touching `shared/shared-contracts/schemas/` (none in phase 2 — R-4, R-6).

## Sequencing And Dependencies

1. **Stage 1 — role type + contextvar (R-1)** — depends on nothing.
2. **Stage 2 — per-role toolkit narrowing (R-2)** — depends on Stage 1.
3. **Stage 3 — same-token identity preservation (R-3)** — depends on Stage 1; verified against
   Stage 2's narrowing.
4. **Stage 4 — provenance label on an executor-staged mutation (R-4)** — depends on Stages 2–3.
5. **Stage 5 — fail-closed guards + inertness proof (R-5)** — depends on Stages 1–4.
6. **Stage 6 — doc reconciliation (R-6)** — depends on Stages 1–5 being green.

## Test Strategy

- unit tests: the closed enum rejects an out-of-set value (fail-closed); a bound role is immutable
  against any in-process API reachable from model/tool output; `_narrow_for_role` yields
  read-only for `diagnostician`, empty-gateway-tools for `orchestrator`, and a superset-of-read
  (mutating allowed) for `executor`; every role's toolkit ⊆ the unscoped toolkit over a
  representative discovered-tool fixture; an absent role keeps one cache entry with today's key.
- identity tests: a member presents the **same** delegated token as its orchestrator; a test fails
  if the broker exchange is invoked more than once per user for a multi-role turn; the requester
  `VerifiedHuman` (namespace/subject) is unchanged across a delegation hop; the role never appears
  as a claim/header/wire field.
- provenance tests: an executor-staged mutation produces a parked record carrying the staging role;
  a `diagnostician`/`orchestrator` context cannot stage at all; the SPEC-030 self-approval block
  still fires for a role-staged mutation.
- contract tests: `execution-request.schema.json` and `agent-stream-event.schema.json` are
  byte-unchanged; no agentscope type leaks on any serialized role surface.
- inertness/guard tests: no role-scoped path is reachable from `/api/v2/chat`/`/chat/stream`; the
  single-agent turn shows no behavioral diff; root `make verify` green with the substrate present
  but unexercised. **No live-cluster or browser evidence at phase 2** (OQ-5).

## Rollout And Migration

- deployment/configuration changes required: **none**. The substrate is inert; no env flag, no
  overlay change, no gateway/policy change, no migration.
- backward compatibility: the unscoped (today's) turn keeps its exact toolkit cache key and one
  cache entry; the deployed single-agent path is byte-identical (R-5).
- rollback approach: revert the `products/agent-platform` commits; there is no persisted state,
  contract, or configuration to unwind.
