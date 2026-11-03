# SPEC-073 Tasks: Role-Scoped Agent Identity and Authority

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs. Phase 2 is
an **inert substrate** — every task is provable by unit/contract tests with no orchestration
caller and no change to the deployed single-agent path.

## R-1: A closed, platform-owned agent-role vocabulary

- [ ] Add `services/agent_role.py` with a closed `AgentRole` enum (`diagnostician`, `orchestrator`,
      `executor`), plain lowercase string values, no agentscope import
      (`products/agent-platform/src/agent_service/services/agent_role.py`)
- [ ] Add `AGENT_ROLE: ContextVar[AgentRole | None]` (default `None`) and a fail-closed
      `bind_agent_role(role)` that rejects an out-of-set value (`.../services/agent_role.py`)
- [ ] Test: out-of-set construction is rejected (fail-closed), not coerced; a bound role cannot be
      changed by any in-process API reachable from model/tool output; no agentscope type on any
      serialized role surface (`products/agent-platform/tests/...`)

## R-2: Per-role toolkit narrowing at the existing seam

- [ ] Extend `_ensure_toolkit`'s `cache_key` to append `::{role.value}` only when a role is bound;
      an unscoped turn keeps today's exact key and one cache entry
      (`products/agent-platform/src/agent_service/runtime_kernel.py`)
- [ ] Add `_narrow_for_role(definitions, role)`: `diagnostician` → `_filter_read_only`;
      `executor` → full set (mutating still parks on HITL); `orchestrator` → empty of gateway tools;
      subtractive-only (`.../runtime_kernel.py`)
- [ ] Test: per-role toolkit contents over a representative discovered-tool fixture; every role's
      toolkit ⊆ the unscoped toolkit for the same token; unscoped turn keeps one cache entry,
      byte-identical (`products/agent-platform/tests/...`)

## R-3: Same-token identity preservation ("on whose behalf")

- [ ] Set/reset `AGENT_ROLE` around a role-scoped turn mirroring the `DELEGATED_TOKEN` bracket;
      leave `DELEGATED_TOKEN` and `REQUESTER_IDENTITY`/`DECIDER_IDENTITY` untouched
      (`.../runtime_kernel.py`)
- [ ] Test: a member presents the **same** delegated token as its orchestrator; fails if the broker
      exchange is invoked more than once per user for a multi-role turn; requester `VerifiedHuman`
      (namespace/subject) unchanged across a delegation hop; role never a claim/header/wire field
      (`products/agent-platform/tests/...`)

## R-4: Authority-provenance labeling on a role-staged mutation

- [ ] Record the staging `AgentRole` on the kernel-internal parked/confirmation record when an
      `executor` stages a mutation; **no field added to `execution-request.schema.json`**
      (`.../runtime_kernel.py` park path)
- [ ] Test: an executor-staged mutation produces a parked record carrying the staging role; a
      `diagnostician`/`orchestrator` context cannot stage at all; the SPEC-030 self-approval block
      still fires for a role-staged mutation (`products/agent-platform/tests/...`)
- [ ] Contract test: `execution-request.schema.json` and `agent-stream-event.schema.json` are
      byte-unchanged (`shared/shared-contracts` validation)

## R-5: Fail-closed invariants and four-point-gate parity

- [ ] Absent/unrecognized role fails closed to the most restrictive posture (no gateway tools /
      read-only), never wider (`.../services/agent_role.py`, `.../runtime_kernel.py`)
- [ ] Guard test: no role-scoped code path is reachable from the deployed `/api/v2/chat` and
      `/chat/stream` handlers (phase 2 wires no caller) (`products/agent-platform/tests/...`)
- [ ] No-diff test: the single-agent turn is behaviorally identical with the substrate present but
      unexercised; full agent-platform suite + root `make verify` green

## R-6: Documentation and contract reconciliation

- [ ] Update `identity-and-authorization-design.md` with the role model, the same-token invariant,
      and the phase boundaries (what phases 3–6 own)
      (`docs/agentic-aiops-platform/identity-and-authorization-design.md`)
- [ ] Annotate ADR-0017's consequence note that phase 2 is delivered
      (`docs/adr/0017-bounded-read-only-multi-agent-orchestration.md`)
- [ ] Update the roadmap multi-agent backlog row and the specs index to `delivered`
      (`docs/agentic-aiops-platform/delivery-roadmap.md`, `docs/specs/README.md`)
- [ ] Verify no file under `shared/shared-contracts/schemas/` changed (none in phase 2)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (R-1…R-6)
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing SPEC-073
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
- [ ] confirm no orchestration caller wired, deployed single-agent path byte-identical, and no
      contract/gateway/policy change (phase-2 inertness)
