# SPEC-039: Operations Document Repository (Phase 1: Shift Summaries)

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-08-27
- release slice: R5 — Hardening and External Consumption (first R5 slice)
- related ADRs: none (spike memo: `docs/workspace/session-handover-spike.md`)

## Summary

Operators gain a platform-owned **operations document repository**: a
typed-document substrate where team members generate durable documents
from the platform's own records and colleagues access them **by role,
not by per-document permission grants**. Phase 1 ships the substrate —
typed store, draft→publish lifecycle, role-based access matrix,
provenance anchoring, audit, portal Documents view — with the
**shift summary** as the first document type: a deterministic digest of
sessions, confirmation decisions, execution receipts, and evidence
counts, with an optional clearly-labeled prose layer generated from the
digest alone. Two session-workspace add-ons support the sharing
workflow: owner session rename and copy-session-id. Skill authoring
(troubleshooting → skill markdown for the team's Git skills repo) is
recorded as a follow-on candidate, deliberately *not* a document type.

## Motivation

- **Operators need to produce documents, not just chat.** Three
  recorded operational needs share one substrate: end-of-shift
  handover summaries (SPEC-035 open question, SPEC-036 restatement),
  incident reports with gathered evidence and taken actions (incident
  review), and reusable guidance distilled from troubleshooting
  (handled separately as a skills export — see Non-Goals). The
  2026-08-27 operator review generalized the spike memo's shift-only
  recommendation into a typed repository with role-based access.
- **Role-based access beats per-document grants.** Authorization is
  policy-driven everywhere else (inbox, tools, mutations); documents
  being the one ACL-managed surface would be the anomaly. A role ×
  type matrix means requesters never manage sharing: publishing moves
  a document into the role-visible space, and that is the end of the
  access conversation.
- **The facts are already durable; only assembly is missing.** A
  session's story is reconstructable from four stores — the kernel
  state snapshot, `session_evidence` (SPEC-025),
  `confirmation_records` (SPEC-031/033), and `execution_records`
  (SPEC-037). What colleagues need is a bounded, attributed recap,
  not raw-transcript exposure.
- **Provenance is the safety property.** Documents are immutable
  digests *copied* from durable records with record-id anchors — not
  live session exposure. Role-wide visibility never opens a session:
  readers see facts with traceable sources, and cross-owner reads are
  audited.

## Requirements

Each requirement is stable once the spec is `approved` and carries
testable acceptance criteria.

### R-1: The typed document substrate

A document repository in agent-platform persists typed documents with
a draft→published lifecycle. Documents are immutable snapshots — the
assembly copies facts, so a document never depends on its source
records' lifetimes; record ids are provenance anchors, not live
references.

Acceptance criteria:

- Documents carry `document_type` (`shift_summary` in Phase 1),
  `state` (`draft` | `published`), owner attribution, label, created
  and published timestamps, and a provenance block listing covered
  session ids and cited record ids.
- Publishing is a one-way owner action (`draft` → `published`); a
  published document can be deleted by its owner but not edited.
- The store follows the SPEC-031/037 record-store conventions: memory
  and Postgres backends behind one interface on the existing
  `AGENT_STATE_STORE_BACKEND`/`AGENT_STATE_DB_URL` knobs, idempotent
  DDL, per-owner cap (20 documents) with oldest-eviction, 30-day TTL
  with opportunistic sweep (aligned with the inbox history window;
  per-type retention tuning is future work with the next document
  type).
- Digest values in every document are copied verbatim from the
  durable stores; no model output appears outside the labeled prose
  section.

### R-2: Role-based access matrix (no per-document ACLs)

Access is policy-driven: a new `documents:create` action gates
creation, publishing, and deletion of one's own documents; a
`documents:read` action gates listing/getting. The default bundle
grants both to `operator`, `approver`, and `platform-admin`; the
agent-service layer enforces the visibility matrix.

Acceptance criteria:

- Drafts are visible only to their owner (every list/get filters
  drafts out for non-owners, including admins).
- Published documents are visible to all holders of `documents:read`;
  the list surface offers an owner scope (`mine`) and a team scope
  (`all published`).
- There is no per-document grant surface: no grant records, no
  share links with tokens, no ACL management.
- Callers without the actions receive the gateway's structured
  denial with the audited block, identical in shape to existing
  policy denials.

### R-3: Shift summary assembly (first document type)

A shift-summary assembler builds the `shift_summary` digest
mechanically from the durable stores, with two-tier coverage by
session ownership:

- **Owner-covered sessions** contribute the full digest: title, turn
  counts, evidence counts per turn, confirmation cards with
  decision/decider/timestamps, executions with receipt status, and
  still-pending items.
- **Foreign sessions** (owner ≠ requester) contribute a
  metadata-level digest only, and only when the requester holds
  `approvals:list`: confirmation decisions, execution receipts, and
  record counts — never titles, transcript excerpts, or evidence
  content (the SPEC-030 Q-1 metadata-only posture, extended). Foreign
  session ids are caller-supplied; foreign enumeration stays
  impossible.

Acceptance criteria:

- Generation requests validate bounded input (≤20 session ids, label
  cap) and reject unknown ids structurally without revealing
  ownership.
- A foreign session without `approvals:list` is rejected before
  assembly; with `approvals:list` it appears metadata-only.
- Missing or unreadable secondary stores degrade per-source (the
  affected digest section reports `unavailable`), never a 500.

### R-4: Optional clearly-labeled prose layer

When requested, an LLM narrative accompanies the digest. The prompt
contract feeds the model the digest JSON only — never raw transcripts
— so the prose can only paraphrase verified facts; the document marks
the section as generated, and generation failure degrades to
digest-only.

Acceptance criteria:

- Prose is generated from the assembled digest alone; no transcript
  text, evidence payload, or argument body reaches the prompt.
- The document carries `prose_status` (`included` | `failed` |
  `not_requested`); the portal renders prose only in a clearly
  labeled "Generated narrative" panel beneath the digest.
- A model error or timeout yields `prose_status=failed` and a
  digest-only document; generation itself succeeds.
- The narrative uses the requester's default catalog model; no
  per-document model selection surface ships.

### R-5: Audit events

The repository emits events through the canonical fire-and-forget
emitter, correlated via forwarded `x-request-id` (SPEC-029
convention): `document_created` (requester, type, covered ids split
own/foreign, per-source counts, prose status), `document_published`
(owner, type, document id), and `document_read` for cross-owner reads
of published documents (reader, owner, document id, type).

Acceptance criteria:

- Reads of one's own documents are not audited; cross-owner reads of
  published documents always are.
- Audit emission failure never blocks the document operation
  (fire-and-forget).

### R-6: Portal Documents view

The operator portal gains a Documents view beside Approvals: create,
manage, publish, and read documents.

Acceptance criteria:

- Creation dialog for shift summaries: own-session picker (from the
  session list surface), explicit foreign-session-id input, label,
  prose toggle.
- The list shows a Mine / Published split with type badges; drafts
  carry a Publish action; the document page renders the digest as the
  primary surface (sessions, decisions, executions, open items) with
  the prose panel collapsed by default and unmistakably labeled.
- Cross-owner reads show owner attribution prominently ("created by
  …"), and the view follows the existing dark-theme antd conventions.

### R-7 (add-on): Session rename

Session titles become owner-editable: a new owner-only rename surface
supersedes the SPEC-022 server-minted set-once title.

Acceptance criteria:

- `PATCH /api/v2/sessions/{session_id}/title` accepts an owner-supplied
  title (1–80 chars, trimmed); foreign or unknown ids answer `404`
  per the anti-enumeration convention.
- The gateway gates the route behind a new `session:update` action
  granted alongside `session:list`; the session list and detail
  surfaces reflect the new title.
- The portal session panel and session list offer inline rename.
- Renames are not audited (owner-side cosmetic act on one's own
  record; recorded design decision).

### R-8 (add-on): Session id reveal and copy

The portal surfaces the session id next to the title wherever sessions
are listed or open, with one-click copy to the clipboard — so
operators can hand a teammate a session id to reference (e.g., as
foreign coverage in their own shift summary).

Acceptance criteria:

- The session list items and the open-session header display the
  session id (truncated with full value on hover) and a copy action
  using `navigator.clipboard` with a visible confirmation state.
- No backend or contract changes; the id is already carried by the
  existing session surfaces.

## Design Decisions (spike Q-1 through Q-4, re-resolved for the repository)

- **Q-1 ownership/audience** → generalized: the requester owns the
  document; publishing exposes it to every `documents:read` holder —
  no per-document grants anywhere. Foreign *coverage* during assembly
  keeps the spike's two-tier posture (foreign facts only at the
  inbox's metadata-only level behind `approvals:list`).
- **Q-2 audit posture** → generalized: creation and publishing audit;
  cross-owner reads audit (the repository intentionally introduces a
  role-wide read path, so reads of others' documents are the
  policed surface); own reads/deletes/renames stay unaudited.
- **Q-3 prose guardrails** → unchanged: digest-only prompt contract,
  labeled rendering, fail-soft degradation.
- **Q-4 retention** → unchanged for Phase 1: immutable snapshots,
  cap 20 per owner, 30-day TTL aligned with the inbox history window;
  per-type retention tuning travels with the next document type.

## Non-Goals

- **Incident reports** (`incident_report` type) — next slice
  (SPEC-040 candidate); its assembly additionally reaches
  incident-service data and earns its own vertical slice.
- **Skill/knowledge authoring export** — session triage → skill
  markdown that the operator contributes to their own team's Git
  skills repo (ingested by skills-hub's existing federated sources).
  Skills are deliberately *not* a document type: the artifact of
  record stays in Git-managed team knowledge (SPEC-014 lineage).
  Tracked on the exploration backlog.
- Cross-owner raw session review — parked behind its recorded trigger;
  the document's provenance index is its future entry point.
- Session inheritance or transferring parked confirmations — rejected
  (SPEC-035 lineage).
- Agent-tool access to repository documents — future candidate.
- Scheduled/automatic generation, document versioning/editing,
  comments — out of scope.

## Impact

- products touched: `products/agent-platform` (document substrate,
  shift-summary assembler, prose, store, routes, session rename
  route, tests), `products/platform-gateway` (pass-through routes,
  `documents:create`/`documents:read`/`session:update` wiring,
  schema mirror, tests), `products/operator-portal` (Documents view,
  session rename + id-copy)
- contracts touched: new `shared/shared-contracts/schemas/operation-document.schema.json`;
  `shared/shared-contracts/policies/policy-default.yaml` gains
  `documents:create`, `documents:read`, `session:update` (`make
  sync-policy` to consumers)
- identity / policy / audit / execution safety impact: three new
  policy actions with role grants; foreign coverage capped at the
  inbox's metadata-only posture; three new audit event types; no
  execution-path changes (read-only spec — no mutating tools, no HITL
  interaction)
- living state docs to update on delivery: `docs/guides/portal-user-guide.md`,
  `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/guides/configuration-reference.md`, `CHANGELOG.md`, release
  note + index

## Open Questions

- none — the spike memo's Q-1 through Q-4 are re-resolved for the
  repository in Design Decisions; approval can proceed on operator
  review of those resolutions.

## Changelog

- 2026-08-27: created as `draft` (`SPEC-039: Shift-Summary Artifacts`)
  from the session-handover spike memo after operator sign-off.
- 2026-08-27: retargeted to the operations document repository after
  the operator review generalized the scope (typed substrate, role
  × type access matrix replacing per-document grants, draft→publish
  lifecycle); shift summary becomes the first document type; session
  rename (R-7) and session-id copy (R-8) added as add-ons; skill
  authoring export recorded as a backlog candidate, explicitly not a
  document type.
- 2026-08-27: approved by the operator with no recorded conditions;
  implementation proceeds as the first R5 slice.
