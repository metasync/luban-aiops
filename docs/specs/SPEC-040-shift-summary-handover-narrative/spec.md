# SPEC-040: Shift-Summary Handover Narrative and Export

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-28
- release slice: R5 — Hardening and External Consumption (second R5 slice)
- related ADRs: none (extends SPEC-039 operations document repository)

## Summary

Shift summaries today satisfy the integrity posture (deterministic
digest, provenance anchors, no model output outside labeled prose) but
underserve their actual job: telling the next operator **what happened
and what they are inheriting**. This spec adds a deterministic
**handover** section to the shift-summary digest (decisions made,
executions and their outcomes, items still open — facts only, assembled
from the same durable records), repositions the prose layer as the
**default, digest-anchored narrative**, moves the portal Documents entry
from Control into **Workspace** where the daily handover workflow lives,
and adds a client-side **Markdown export** so a summary can be taken
offline.

## Motivation

- **The artifact of record is a pile of receipts.** The shipped digest
  (SPEC-039 R-3) carries per-session confirmations, execution entries,
  evidence counts, and open-item counts — provable facts, but the next
  operator must reconstruct the narrative themselves. Operator feedback
  on v0.21.0/0.21.1 (2026-08-28): "without a facts summary, the next
  operator doesn't know anything."
- **The prose layer cannot currently carry the story.** It is declined
  by default, fail-soft, and labeled "may omit facts" — so it is never
  the thing a relieving operator can rely on. The anti-hallucination
  posture was right; the default posture was wrong.
- **Documents live under Control.** The nav grouping put Documents with
  oversight surfaces (Incidents, Approvals, Audit trail) because the
  section already had role-mirror visibility logic; semantically a
  shift summary is a daily workflow artifact and belongs in Workspace
  (Tools, Skills, Settings).
- **No offline path.** A relieving operator on a call, in a paging
  review, or outside the portal has no way to take the summary with
  them.
- Timing: SPEC-039's substrate, audit-integrity hardening (v0.21.1
  envelope-only listings), and portal view are all stable; the gap is
  now purely artifact quality and ergonomics, which is exactly R5's
  "broader adoption and stable reuse" charter.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Deterministic handover section in the shift-summary digest

Every shift summary digest gains a top-level `handover` object assembled
deterministically from the same durable records the digest already reads
(no model involvement): shift-level counts, per confirmation decision
(outcome, tool, redacted argument digest, confirmer, timestamp), per
execution (result status, tool, timestamp), the open items a reliever
inherits, and which covered sessions still hold open threads.

Acceptance criteria:

- `handover` is present on every newly created shift summary and is
  fully determined by the durable records: two assemblies over the same
  records yield byte-identical `handover` objects.
- Own-covered sessions contribute decision/execution details; foreign
  sessions contribute counts only (the metadata-only tier — never
  titles, arguments, or confirmers), mirroring the two-tier coverage of
  the existing digest sections.
- `handover.open_items` reports pending confirmations and
  requested-but-unsettled executions across covered sessions;
  `handover.open_sessions` lists covered session ids with any open
  thread (own coverage only).
- A shift with no confirmations or executions yields an honest empty
  handover (`"quiet shift"` empty-state data, never fabricated items).
- Digest sections shipped in SPEC-039 are unchanged; existing stored
  documents keep their old shape and consumers degrade gracefully when
  `handover` is absent.

### R-2: Prose as the default, digest-anchored narrative

For the shift-summary type, prose is **requested by default** (the
create dialog offers an explicit opt-out) and the generation contract
gains anchoring: prose is produced from the digest JSON alone and must
render only facts present in it. The portal label changes from
"AI-generated prose (digest-only, may omit facts)" to
"AI-generated narrative — from this document's digest facts". Fail-soft
behavior is preserved: a generation failure still yields
`prose_status: failed` and a digest-only document.

Acceptance criteria:

- The create request defaults `include_prose` to true when the field is
  omitted; the portal dialog shows the prose switch on by default with a
  working opt-out.
- The prose prompt contract requires sentence-level references to digest
  sections (e.g. session entries, decisions, executions) and forbids
  introducing record ids or facts absent from the digest input.
- `prose_status` semantics are unchanged (`included|failed|
  not_requested`); a declined or failed generation leaves the digest —
  including the new `handover` section — as the complete record.
- The audit `document_created` details keep carrying `prose_status`; no
  new event types are introduced.

### R-3: Portal Documents moves from Control to Workspace

The Documents navigation entry moves from the **Control** group to the
**Workspace** group. Its role gating (`documents:read` mirror) is
unchanged; only the grouping moves.

Acceptance criteria:

- Signed-in users holding a document role see **Documents** under
  Workspace (after Tools/Skills ordering conventions); users without
  the grant do not see it at all.
- Control still renders correctly when Documents was its trigger for
  visibility edge cases (e.g. a role seeing only Audit trail).
- The portal user guide and navigation screenshots reflect the new
  placement.

### R-4 (add-on): Offline export of a document

The portal offers an **Export** action on the document drawer that
serializes the full document — metadata, attribution, provenance,
digest (including `handover`), and prose when present — into a
Markdown file downloaded in the browser. Export is client-side: it
serializes the document already retrieved through the audited single
fetch, so there is no new API surface, policy action, or audit event.

Acceptance criteria:

- Export is available on any document the user can open (own and
  published-by-others) and produces a self-contained Markdown file:
  label, document id, type, state, owner attribution, created/published
  timestamps, provenance (session ids, coverage, cited record ids), the
  digest rendered as structured Markdown, and the labeled prose section
  when `prose_status` is `included`.
- Filename is deterministic and traceable: a slug of the label plus the
  document id (e.g. `night-shift-2026-08-28-doc-3f2a91.md`).
- The exported prose carries the same "AI-generated narrative" label as
  the portal; the export footer states the document id and export time
  so the offline copy stays attributable.
- No request leaves the browser during export (no gateway call, no new
  endpoint); a document with `prose_status: failed` exports the digest
  alone with the failure noted.

## Design Decisions

- **Facts guaranteed by the skeleton, readability by the narrative.**
  The deterministic `handover` section (R-1) means the handover story
  survives even when prose fails or is declined; prose (R-2) becomes
  the readable letter on top. This keeps SPEC-039's core invariant —
  no model output outside the labeled prose — while closing the
  "receipts without a story" gap.
- **Export is a rendering concern, not a read path.** Content reaches
  the browser only through the audited single fetch (v0.21.1); export
  merely serializes what was already served. A server-side export
  endpoint was rejected: it would add a second, separately-policed and
  separately-audited content path for zero capability gain.
- **No `document_exported` audit event.** Exporting adds no information
  access beyond the fetch that preceded it; the cross-owner
  `document_read` already attributes the content access.
- **Additive digest evolution.** `handover` is a new top-level digest
  key; the digest remains typed-but-open, so no schema break for
  existing consumers, and the contract schema gains a description-only
  note (the `digest` property stays an open object).

## Non-Goals

- PDF / HTML / email export formats and bulk export of multiple
  documents — Markdown single-document export only in this slice.
- Server-side export endpoints, export tokens, or offline re-sync of
  exported copies.
- Handover sections or export for future document types (incident
  reports and others define their own shapes when promoted).
- Cross-owner session review (the SPEC-035 backlog question) — foreign
  sessions stay metadata-only inside `handover`, exactly as in the
  existing digest.
- Translating or re-summarizing existing stored documents: documents
  remain immutable snapshots; pre-SPEC-040 documents keep their
  original digest shape.

## Impact

- products touched: `products/agent-platform` (shift-summary assembly,
  prose prompt contract, create-default handling),
  `products/operator-portal` (Documents nav placement, drawer Export,
  prose label, create dialog default), `products/platform-gateway`
  (pass-through only — no new routes)
- contracts touched: `shared/shared-contracts/schemas/operation-document.schema.json`
  (description-only note for the `handover` digest section)
- identity / policy / audit / execution safety impact: none — no new
  policy actions, no new audit event types, no execution-path change;
  authorization posture inherits SPEC-039 unchanged
- living state docs to update on delivery: CHANGELOG, release notes +
  index, portal-user-guide (Documents placement, handover/export
  walkthrough), authorization-matrix (note only if wording needs it),
  spec index, delivery-roadmap

## Open Questions

- none recorded yet — pending operator review of the draft.

## Changelog

- 2026-08-28: created as `draft` following operator feedback on the
  v0.21.0/0.21.1 shift-summary delivery (readability gap, Documents
  placement, offline export).
