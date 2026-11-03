# SPEC-073: Role-Scoped Agent Identity and Authority

## Status

- status: `draft`
- owner: chi
- created: 2026-11-03
- release slice: the **multi-agent / bounded-autonomy program** — phase 2 of the phased SPEC
  series [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md) gates
  ([memo](../../workspace/multi-agent-orchestration-spike.md) §7). No target version is pinned
  at `draft`; a version is slotted at `approved`, per the SPEC-071/072 pattern.
- related ADRs: [ADR-0017](../../adr/0017-bounded-read-only-multi-agent-orchestration.md)
  (`accepted` 2026-11-03 — the gate this spec realizes, **Decision 4** in particular:
  role-scoped agents on the *same* delegated token narrowed per role, at the toolkit + policy
  layer, not a super-agent and not per-role broker identities);
  [ADR-0011](../../adr/0011-composition-carries-no-authority.md) (amended by ADR-0017 at
  Decision 3 only — a composition still carries no mutation authority);
  [ADR-0004](../../adr/0004-broker-mediated-token-delegation.md) (broker-mediated delegated
  token — the *one* identity edge this spec preserves);
  [ADR-0010](../../adr/0010-signed-execution-envelopes-declare-authority-provenance.md)
  (signed envelopes declare authority provenance — the labeling pattern R-4 follows);
  [ADR-0007](../../adr/0007-browser-flow-single-hitl-gate.md) (one HITL gate per mutating flow)
  and [ADR-0013](../../adr/0013-durable-single-use-execution-claims.md) (durable single-use
  dispatch claims) — both stay authoritative on the mutation path. **No new ADR is expected**:
  ADR-0017 already fixed the control-flow, autonomy-ceiling, and identity-model decisions; this
  spec is the first downstream substrate it unblocks.
- extends: [SPEC-004](../SPEC-004-deny-by-default-policy-enforcement/spec.md) (deny-by-default),
  [SPEC-007](../SPEC-007-read-only-tool-execution-framework/spec.md) (`BaseTool`/`ToolRegistry`
  seam + read/write tiers), [SPEC-018](../SPEC-018-kernel-middleware-alignment/spec.md) (the
  four-point adoption gate), [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)
  (`VerifiedHuman` requester/decider identity contextvars), and the governed mutation path
  [SPEC-037](../SPEC-037-signed-execution-requests/spec.md) /
  [SPEC-038](../SPEC-038-isolated-execution-worker/spec.md) /
  [SPEC-063](../SPEC-063-crash-safe-execution/spec.md).

> SDD note: `spec.md` is drafted first and carries **six Open Questions** that block `approved`
> (see `## Open Questions`). Approval authorizes the [plan](plan.md) / [tasks](tasks.md) — not
> yet written — and lets implementation **begin**. It does **not** authorize a merge,
> commit/push, deployment, or a version bump; those stay separate boundaries, and the standing
> "review before any merge/deploy" constraint governs. This is phase 2 of a five-spec series:
> the **policy role axis** (§4.2), **audit & attribution** (§4.3), **bounded autonomous
> diagnosis** (§5), and the **v2 multi-agent contract** (§4.5) are separate later specs and are
> explicitly out of scope here.

## Summary

Build the **role-scoped identity & authority substrate** the ADR-0017 phased series needs first:
a closed, platform-owned **agent-role** concept (`diagnostician`, `planner`/`orchestrator`,
`executor`) that narrows a sub-agent's authority **at the toolkit layer** while every role rides
the **same** gateway-forwarded delegated token (ADR-0004) — no per-role broker identity, no
second identity edge, no new principal. It preserves "on whose behalf" end-to-end (the human
requester's `sub` is unchanged when an orchestrator delegates to a member), labels the authority
provenance of a role-staged mutation (the ADR-0010 pattern), and keeps every mutation on the
existing HITL-gated, signed, at-most-one-dispatch path with a **distinct human approver**
(no agent approves another agent's mutation). Like SPEC-070's substrate, it ships **inert by
default** — no orchestration caller exists until phase 5 — so the deployed single-agent turn is
byte-identical and the four-point gate holds by construction.

## Motivation

- **ADR-0017 is accepted but gates on this substrate.** ADR-0017 Decision 4 fixed the *model*
  (role-scoped agents on the same delegated token, narrowed per role at the toolkit + policy
  layer) but explicitly leaves the *mechanism* to the downstream SPECs: "how per-role agents
  carry narrowed authority on the delegated-token/broker model, with ADR-0010 provenance"
  (memo §7 step 2). Nothing downstream (policy axis, audit attribution, bounded diagnosis,
  contract) is decision-complete until the identity/authority seam exists.
- **The seam already half-exists.** `_ensure_toolkit(bearer_token, read_only)`
  (`runtime_kernel.py:501`) already builds a **per-token cached** gateway toolkit and already
  narrows to read-level tools via `_filter_read_only` when `read_only=True` (the automated
  diagnostic-turn path). Role-scoping generalizes this one existing seam from a boolean to a
  closed role vocabulary — it is not a new execution surface.
- **Identity is single-edge today and must stay that way.** ADR-0004 gives the platform exactly
  one identity edge: a short-lived delegated token (`sub`=user, `act`=agent-platform,
  `aud`=tool-gateway, `roles` copied), relayed as `Bearer` and read from the `DELEGATED_TOKEN`
  contextvar at call time; SPEC-070 adds the strict `REQUESTER_IDENTITY`/`DECIDER_IDENTITY`
  `VerifiedHuman` contextvars. Gate point 2 ("identity carried only by the gateway-forwarded
  delegated token") forbids a per-role broker mint — so a role must be an **authority-narrowing
  label on the one token**, never a new credential. This spec is where that invariant is made
  concrete and testable before any orchestrator exists to violate it.
- **Why now.** The operator accepted ADR-0017 (2026-11-03) and directed opening this first
  spec. Sequencing identity/authority first is the memo's own order (§7): a later phase that
  added a policy role axis or an audit attribution dimension without a fixed identity substrate
  would be building on an unmapped edge.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.
Phase 2 delivers an **inert substrate**: every requirement is provable by unit/contract tests
over the role-narrowing and identity-preservation seams with **no orchestration caller** and
**no change to the deployed single-agent path** (mirroring SPEC-070's inert-substrate
acceptance).

### R-1: A closed, platform-owned agent-role vocabulary

Introduce an **agent-role** as a closed, platform-owned enum — `diagnostician`,
`planner`/`orchestrator`, `executor` — bound to an agent-construction context, **immutable** for
the life of that context (the SPEC-056 `session_type` posture: fixed at birth, never promoted or
converted in place), and **never model-chosen** (a role is a platform fact, not derivable from
model output, tool output, or any request field the model controls). No agentscope type appears
in any role representation (gate point 4).

Acceptance criteria:

- The role set is a closed enum; constructing a role-scoped context with a value outside the set
  is rejected (fail-closed), not coerced.
- A role, once bound, cannot be changed by any in-process API reachable from model output or a
  tool result; an attempt is a no-op or an error, asserted by a test.
- The role reduces to a plain platform string with no agentscope import on any serialized
  surface; a contract/serialization test asserts no agentscope type leaks.

### R-2: Per-role toolkit narrowing at the existing seam

Generalize `_ensure_toolkit`'s `read_only` narrowing into a **per-role toolkit restriction** on
the same code path and the same per-token cache (keyed by `(token, role)`): a `diagnostician`
sees **read-level tools only** (reusing `_filter_read_only`); an `executor` may see mutating
tools (which still park on the existing HITL confirmation — R-4); a `planner`/`orchestrator`
holds **no direct tool authority** (it delegates; it does not itself invoke tools). Narrowing is
**subtractive only** — a role's toolkit is always a subset of what the underlying token's
`roles` already permit at the gateway; phase 2 never *grants* a tool the token could not reach.

Acceptance criteria:

- Given one delegated token, a `diagnostician` context's toolkit contains no mutating tool; an
  `executor` context's toolkit is a superset of the diagnostician's read tools and may contain
  mutating tools; a `planner` context's toolkit is empty of gateway tools.
- The cache is split per `(token, role)` and only when a role could change the built toolkit —
  an unrole-scoped (today's single-agent) turn keeps one cache entry, byte-identical to current
  behavior.
- Narrowing never adds a tool: for every role, the role toolkit ⊆ the unscoped toolkit for the
  same token, asserted over a representative discovered-tool fixture.

### R-3: Same-token identity preservation ("on whose behalf")

Every role-scoped agent rides the **same** gateway-forwarded delegated token (ADR-0004): no
per-role broker mint, no new identity edge, no additional signing authority. The human
requester's identity (`sub`, and the SPEC-070 `VerifiedHuman` `namespace`/`subject`) is
**preserved end-to-end** when an orchestrator delegates to a member — a member acts *as the same
human*, with a narrowed toolkit, never as a distinct principal. The role is carried beside the
token as process-local context (a contextvar alongside `DELEGATED_TOKEN`), not inside it and not
as a new claim on the delegated token.

Acceptance criteria:

- A member agent's tool call presents the **same** delegated token as its orchestrator; no code
  path mints, requests, or caches a second broker token for a role (asserted by a test that
  fails if the broker exchange is invoked more than once per user for a multi-role turn).
- The requester `VerifiedHuman` (namespace/subject) is unchanged across a delegation hop; a test
  asserts identity equality before and after a role-scoped call.
- The role never appears as a JWT claim, a header forwarded to the gateway, or any wire field in
  phase 2; it is process-local only.

### R-4: Authority-provenance labeling on a role-staged mutation (ADR-0010 pattern)

When an `executor`-scoped agent stages a mutation, the platform records **which agent-role**
staged it, following ADR-0010's "provenance rides the signed fact, not an unsigned hint"
pattern. The mutation still parks on the existing HITL confirmation (SPEC-020/030/031) and, once
approved by a **distinct human**, dispatches through the signed at-most-one-dispatch worker
(SPEC-037/038/063). **No agent may approve another agent's mutation**; the executor cannot
self-approve. Phase 2 keeps this provenance **kernel-internal** (recorded on the confirmation /
parked record), adding **no field to `execution-request.schema.json`** — the wire/audit
projection of role provenance is deferred to phase 4 (audit) and phase 6 (contract).

Acceptance criteria:

- An executor-staged mutation produces a parked confirmation carrying the staging role; a
  `diagnostician` or `planner` context **cannot** stage a mutation at all (no mutating tool in
  its toolkit, R-2), asserted by a test.
- The staged mutation dispatches only through the existing signed path with a human decider
  distinct from the requester; the self-approval block (SPEC-030) still fires for a role-staged
  mutation.
- `execution-request.schema.json` is byte-unchanged in phase 2; a contract test asserts no new
  field is added.

### R-5: Fail-closed invariants and four-point-gate parity

A role-scoped agent **never widens** authority beyond the underlying token's `roles`; an
**unknown or absent** role fails closed to the most restrictive posture (no gateway tools /
read-only). The substrate preserves all four gate points: (1) tool-gateway remains the only
execution surface and deny-by-default policy is untouched in phase 2; (2) identity rides only
the delegated token (R-3); (3) the `diagnostician` read-only posture is enforced by toolkit
narrowing; (4) no agentscope type leaks (R-1). The substrate is **inert by default** — with no
orchestration caller, the deployed single-agent turn renders byte-identical to today.

Acceptance criteria:

- An absent/unrecognized role yields an empty-or-read-only toolkit, never a wider one; a test
  asserts the fail-closed posture.
- The full agent-platform suite and `make verify` pass with the substrate present but
  unexercised by any deployed path; the single-agent chat path shows no behavioral diff.
- A guard test asserts no role-scoped code path is reachable from the current
  `/api/v2/chat`/`/chat/stream` handlers (phase 2 wires no caller).

### R-6: Documentation and contract reconciliation

Record the substrate where it belongs at phase 2: the
[identity-and-authorization-design](../../agentic-aiops-platform/identity-and-authorization-design.md)
doc gains the role-scoped-narrowing-on-one-token model; ADR-0017's consequence ("unblocks the
phased SPEC series") is annotated that phase 2 is drafted; the roadmap multi-agent backlog row
and the specs index reflect SPEC-073 as `draft`. **No v2 contract schema changes** — any
additive, versioned multi-agent stream/schema change belongs to phase 6.

Acceptance criteria:

- The identity design doc states the role model, the same-token invariant, and the phase
  boundaries (what phases 3–6 own).
- No file under `shared/shared-contracts/schemas/` changes except (if an OQ resolves that way)
  an explicitly additive, versioned field with its own justification; `agent-stream-event.schema.json`
  is byte-unchanged.
- The specs index and roadmap row list SPEC-073 as `draft` with its phase-2 scope.

## Non-Goals

- **Policy role axis** (memo §4.2) — the agent-role dimension in the authorization matrix /
  policy-center and the gateway policy engine. Phase 3. Phase 2 narrows only the **toolkit**
  (what an agent sees), not the gateway **policy** evaluation (which stays keyed on the token's
  `roles`).
- **Multi-agent audit & attribution** (memo §4.3) — new audit dimensions/event types so member
  activity is reconstructable, and the SPEC-025 evidence / SPEC-039 transcript extensions.
  Phase 4.
- **Bounded autonomous diagnosis / the orchestration loop** (memo §5, ADR-0017 Decision 1) — the
  bounded read-only fan-out loop and its step budget. Phase 5. Phase 2 ships **no** caller.
- **The v2 multi-agent contract** (memo §4.5) — any additive, versioned stream/schema framing
  for member attribution or orchestration status. Phase 6, and only after phases 2–5 fix the
  semantics.
- **Autonomous resolve** — a self-approving mutation loop. Explicitly deferred by ADR-0017
  Decision 2 to a later, evidence-backed trust-model decision.
- **A2A external federation** and adopting `TeamPipeline`/`GoalPipeline`/`A2AAgent` as shipped —
  parked / kept out by ADR-0017 Decision 5.
- **Per-role broker identities** — rejected by ADR-0017 Decision 4 for this phase (revisit only
  if a role ever needs an independent credential).

## Impact

- products touched: `products/agent-platform` only — the `runtime_kernel.py` toolkit seam
  (`_ensure_toolkit`, `_filter_read_only`), `services/delegated_identity.py` (a role contextvar
  beside `DELEGATED_TOKEN`), and a new small agent-role module. **No** `tool-gateway`,
  `platform-gateway`, `identity-broker`, or portal change in phase 2 (the policy role axis is
  phase 3; the contract is phase 6).
- contracts touched: **none** in phase 2. `execution-request.schema.json` and
  `agent-stream-event.schema.json` stay byte-unchanged (R-4, R-6).
- identity / policy / audit / execution safety impact: **identity** — narrows authority per role
  on the *same* delegated token; no new principal, edge, claim, or broker mint (R-3).
  **policy** — none in phase 2 (toolkit-side narrowing only; gateway evaluation unchanged).
  **audit** — none in phase 2 (role provenance stays kernel-internal until phase 4).
  **execution safety** — unchanged: an executor-staged mutation still parks on HITL and
  dispatches through the signed at-most-one-dispatch worker with a distinct human approver
  (R-4); the substrate is inert (R-5).
- living state docs to update on delivery: `identity-and-authorization-design.md`, the ADR-0017
  consequence note, the roadmap multi-agent backlog row, and `docs/specs/README.md` (index).

## Open Questions

Unresolved points that block `approved`; must be empty before approval.

- **OQ-1 — role vocabulary.** Is the three-role set (`diagnostician`, `planner`/`orchestrator`,
  `executor`) the right phase-2 vocabulary, and is `planner` a distinct role from `orchestrator`
  or one combined role (ADR-0017 Decision 4 names them together as "`planner`/`orchestrator`")?
  Does phase 2 need an `approver`-facing role, or is the human approver never an agent (so no
  role)?
- **OQ-2 — where the role binds and its lifetime.** Does the role bind on a new
  agent-construction context carried in a contextvar beside `DELEGATED_TOKEN`, and must it
  survive a park/resume under the SPEC-017 snapshot (i.e., is a role part of resumable kernel
  state), or is it re-derived per turn from the (phase-5) orchestration frame?
- **OQ-3 — narrowing granularity.** Is read/write-tier narrowing (`_filter_read_only`)
  sufficient for `diagnostician`, or does a role need an explicit tool-family allowlist
  (observability / k8s / ServiceNow / log reads) beyond the tier? And is **toolkit-only**
  narrowing a sufficient phase-2 safety boundary given the gateway still enforces per the token's
  `roles` (with the policy role axis deferred to phase 3) — or must a minimal gateway-side role
  check land in phase 2 to avoid a toolkit-widening regression between phases?
- **OQ-4 — provenance shape.** Does the staging agent-role stay **kernel-internal** in phase 2
  (recorded on the confirmation/parked record only, no contract field), or does an OQ-3/phase-4
  dependency require an additive optional field on `execution-request.schema.json` now (the
  ADR-0010 `approval_kind` precedent)? This decides whether phase 2 touches a contract at all.
- **OQ-5 — inertness proof.** What is the acceptance evidence that the substrate is correct with
  no orchestration caller — unit/contract tests over the narrowing + identity-preservation seams
  (the SPEC-070 inert-substrate precedent) plus a `make verify` green with the deployed path
  byte-identical? Confirm no live-cluster or browser evidence is required at phase 2.
- **OQ-6 — executor staging mechanism.** Does the `executor` role's "may *stage* a mutation"
  reuse the existing HITL park + signed dispatch **entirely** (ADR-0017 Decision 2: no new
  enforcement machinery), so phase 2 adds zero new mutation-path code beyond the toolkit
  narrowing and the kernel-internal provenance label? Confirm no new gate, worker, or claim
  type is introduced.

## Changelog

- 2026-11-03: created as `draft` — phase 2 (role-scoped identity & authority) of the ADR-0017
  phased multi-agent series, opened on the operator's acceptance of ADR-0017 (2026-11-03) and
  direction to begin the program. Six Open Questions block `approved`; `plan.md` / `tasks.md`
  are authored on approval.
