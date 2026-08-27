# SPEC-039: Shift-Summary Artifacts

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-27
- release slice: R5 — Hardening and External Consumption (first R5 slice)
- related ADRs: none (spike memo: `docs/workspace/session-handover-spike.md`)

## Summary

Operators gain a durable shift-summary artifact for incident review and
7x24 roster handover: on request, the platform assembles a
**deterministic digest** of what happened across a set of sessions —
mechanically from the durable records (session metadata, confirmation
decisions, execution receipts, evidence counts), never from prose — and
persists it as an immutable, owner-scoped record with provenance
anchoring. An **optional, clearly-labeled** LLM narrative may ride
alongside the digest, generated from the digest alone so it can only
paraphrase verified facts. Raw cross-owner session review stays parked
on the backlog behind its recorded trigger.

## Motivation

- **The operational ask is real and twice-recorded.** The v0.16.0 live
  approval test raised shift handoff / reviewing other users' sessions
  (SPEC-035 open question); SPEC-036 re-stated it. Incident review and
  7x24 roster handover need context from work done by another operator.
- **The facts are already durable; only the assembly is missing.** A
  session's story is reconstructable today from four stores — the
  kernel state snapshot (transcript), `session_evidence` (SPEC-025),
  `confirmation_records` (SPEC-031/033), and `execution_records`
  (SPEC-037) — and the owner transcript view already merges all four.
  What a relieving operator needs is a bounded, attributed recap, not a
  raw-transcript exposure decision.
- **The spike memo settled the direction.** The paired spike
  (`docs/workspace/session-handover-spike.md`, operator sign-off
  2026-08-27) recommends the shift-summary artifact first — digest
  first, prose optional and labeled — and parks cross-owner session
  review behind a recorded trigger. This spec resolves the memo's Q-1
  through Q-4 in the draft (see Design Decisions).

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance criteria.

### R-1: Deterministic digest assembly

A shift-summary service in agent-platform assembles the artifact's
trusted core mechanically from the durable stores — sessions,
`confirmation_records`, `execution_records`, and evidence counts — so
nothing in the digest can be fabricated; every covered session and
record id rides as a provenance anchor.

Coverage is two-tiered by ownership:

- **Requester-owned sessions** contribute the full digest: title,
  turn counts, evidence counts per turn, confirmation cards with
  decision/decider/timestamps, executions with receipt status, and
  still-pending items.
- **Foreign sessions** (owner ≠ requester) contribute a
  metadata-level digest only, and only when the requester holds
  `approvals:list`: confirmation decisions, execution receipts, and
  record counts — never titles, transcript excerpts, or evidence
  content (the SPEC-030 Q-1 metadata-only posture, extended).

Acceptance criteria:

- A generated digest's trusted section contains only values copied
  verbatim from the durable stores; no model output appears in it.
- Each covered session carries its `session_id` and the record ids
  (confirm ids, execution ids) it cites.
- A foreign session without `approvals:list` is rejected with a
  structured error before generation; with `approvals:list` it
  appears metadata-only (no title, no transcript text).
- Foreign session enumeration stays impossible: there is no endpoint
  listing another owner's sessions; foreign coverage is by
  caller-supplied id only.
- Missing or unreadable secondary stores degrade per-source (the
  affected digest section reports `unavailable`), never a 500.

### R-2: Policy-gated generation API

Generation is a policy-gated action: agent-platform serves
`POST /api/v2/shift-summaries` and platform-gateway passes it through
behind a new `shifts:summarize` action (granted to `operator`,
`approver`, `platform-admin` in the default bundle).

Acceptance criteria:

- The request body supplies a bounded session-id list (cap 20), an
  optional prose flag, and an optional label; unknown session ids
  produce a structured `404`-family rejection naming nothing about
  ownership.
- A caller without `shifts:summarize` receives the gateway's
  structured denial with the audited block, identical in shape to the
  existing policy denials.
- Successful generation returns the artifact id and the full artifact
  body; the response mirrors a new `shift-summary.schema.json`
  contract in shared-contracts.
- A per-requester generation cap and bounded input keep the endpoint
  bounded (no unbounded scans over the session store).

### R-3: Durable artifact store

Artifacts persist in a new `shift_summaries` store on the shared
Postgres posture (memory backend for development), following the
SPEC-031/037 record-store conventions. Artifacts are immutable
snapshots — the digest copies facts, so an artifact never depends on
its source records' lifetimes; record ids are provenance anchors, not
live references.

Acceptance criteria:

- `GET /api/v2/shift-summaries` lists the requester's own artifacts
  (most recent first); `GET /api/v2/shift-summaries/{id}` returns one;
  `DELETE /api/v2/shift-summaries/{id}` removes it. Foreign or
  unknown ids answer `404` (anti-enumeration house convention).
- Per-requester cap of 20 artifacts: creating beyond the cap evicts
  the oldest artifact of that requester.
- Retention is 30 days with an opportunistic sweep (startup +
  access), aligned with the inbox history window; expiry deletes the
  artifact outright.
- Postgres DDL initialization is idempotent; the memory backend keeps
  parity for tests and dev.

### R-4: Optional clearly-labeled prose layer

When requested, an LLM narrative accompanies the digest. The prompt
contract feeds the model the digest JSON only — never raw transcripts
— so the prose can only paraphrase verified facts; the artifact marks
the section as generated, and generation failure degrades to
digest-only.

Acceptance criteria:

- Prose is generated from the assembled digest alone; no transcript
  text, evidence payload, or argument body reaches the prompt.
- The artifact carries `prose_status` (`included` | `failed` |
  `not_requested`) and the portal renders prose only in a clearly
  labeled "Generated narrative" panel beneath the digest.
- A model error or timeout yields `prose_status=failed` and a
  digest-only artifact — the generation request itself succeeds.
- The narrative uses the requester's default catalog model; no
  per-artifact model selection surface ships.

### R-5: Audit event

Generation emits one `shift_summary_generated` audit event through
the canonical fire-and-forget emitter, correlating via the forwarded
`x-request-id` (SPEC-029 convention).

Acceptance criteria:

- The event names the requester, covered session ids split by
  ownership (own/foreign), per-source record counts, and the prose
  status.
- Artifact reads and owner deletes are not audited: the artifact is
  the requester's own record (recorded design decision, Q-2).
- Audit emission failure never blocks generation (fire-and-forget).

### R-6: Portal shift-summaries view

The operator portal gains a Shift summaries view: request an artifact
with a session picker, list owned artifacts, and render one
digest-first.

Acceptance criteria:

- The session picker offers the requester's own recent sessions;
  foreign session ids are entered explicitly (handover/incident
  links), never listed.
- The artifact page renders the digest as the primary surface
  (sessions, decisions, executions, open items) with the prose panel
  collapsed by default and unmistakably labeled.
- The view follows the existing portal dark-theme antd conventions
  and the sticky-banner/navigation patterns.

## Design Decisions (spike Q-1 through Q-4 resolved)

- **Q-1 ownership/audience.** The requester owns the artifact; the
  two-tier coverage posture grants foreign facts only where the
  requester already holds `approvals:list`, mirroring the inbox's
  metadata-only stance. No cross-user artifact reads ship.
- **Q-2 audit posture.** One `shift_summary_generated` event per
  generation; reads/deletes of one's own artifact stay unaudited
  because no cross-user surface exists to police.
- **Q-3 prose guardrails.** Digest-only prompt contract bounds the
  hallucination surface to paraphrase of verified facts; labeled
  rendering and fail-soft degradation keep the digest authoritative.
- **Q-4 retention.** Immutable snapshot + 30-day TTL + cap 20. Because
  the digest copies facts, the artifact can never dangle on aged-out
  source records — retention aligns with the inbox history window for
  operational coherence, not referential necessity.

## Non-Goals

- Cross-owner raw session review (transcript/evidence exposure) —
  parked on the backlog behind its recorded trigger; the artifact's
  provenance index is its future entry point.
- Session inheritance or transferring parked confirmations — rejected
  by the spike memo (SPEC-035 lineage).
- Scheduled/automatic shift-close generation — on-demand only.
- Cross-user artifact sharing or team-scoped artifacts — revisit if a
  concrete ask appears.
- Edit/versioning of artifacts — immutable by construction.

## Impact

- products touched: `products/agent-platform` (digest service, store,
  routes, settings, tests), `products/platform-gateway` (pass-through
  route, policy action wiring, schema mirror, tests),
  `products/operator-portal` (Shift summaries view)
- contracts touched: new `shared/shared-contracts/schemas/shift-summary.schema.json`;
  `shared/shared-contracts/policies/policy-default.yaml` gains the
  `shifts:summarize` action (`make sync-policy` to consumers)
- identity / policy / audit / execution safety impact: new policy
  action with role grants; foreign coverage is capped at the inbox's
  metadata-only posture; one new audit event; no execution-path
  changes (read-only spec — no mutating tools, no HITL interaction)
- living state docs to update on delivery: `docs/guides/portal-user-guide.md`,
  `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/guides/configuration-reference.md`, `CHANGELOG.md`, release
  note + index

## Open Questions

- none — the spike memo's Q-1 through Q-4 are resolved in Design
  Decisions; approval can proceed on operator review of those
  resolutions.

## Changelog

- 2026-08-27: created as `draft` from the session-handover spike memo
  after operator sign-off (2026-08-27).
