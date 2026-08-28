# SPEC-041: Documents Readability and Digest Reference

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-08-28
- approved: 2026-08-28
- release slice: R5 — Hardening and External Consumption (third R5 slice)
- related ADRs: none (extends SPEC-039 operations document repository and SPEC-040 handover narrative)

## Summary

The v0.22.0 live test confirmed the document repository works but
surfaced four operator clarifications: the digest's vocabulary
(digest, frame, coverage tiers, handover) is nowhere explained to
operators; the drawer renders the digest as nested lists that are hard
to scan; the Digest and Prose blocks grow unbounded; and the document
list gives no glimpse of what each document contains. This spec adds
an **operator-facing digest reference**, **tabbed structured digest
rendering** in the document drawer, **bounded scrollable** digest and
prose panes, and a **deterministic counts-only summary line** computed
at creation time and shown with each document in the lists.

## Motivation

- **The vocabulary is undocumented.** Operator feedback on the v0.22.0
  live test (2026-08-28): "can you explain what a digest is? what is
  a frame? do we have a document explaining all these to our
  operators?" The portal user guide describes the workflow but never
  defines digest, evidence frame, coverage tiers, handover, or quiet
  for someone meeting them cold.
- **The digest reads as a wall of nested lists.** The drawer renders
  the digest through a generic recursive JSON tree. Coverage,
  confirmations, executions, evidence counts, and open items all
  stack vertically; a tabbed, table-shaped layout would be materially
  more scannable and compact.
- **Long blocks push everything off screen.** Digest and Prose are
  the two longest blocks in the 560px drawer and currently grow
  unbounded; bounded scroll keeps the drawer navigable.
- **The list is titles-only.** Mine/Published rows show label, state,
  owner, and timestamps but nothing about the shift's substance, so
  picking the right document means opening them one by one.
- Timing: SPEC-039/040 substrates are stable and the digest now
  carries the `handover` skeleton; the gap is purely readability and
  onboarding, squarely R5's "broader adoption" charter.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Operator digest and documents reference

The guides gain a dedicated reference that explains, in plain
operator language, every concept a reader meets in the Documents
view: what an operations document is, that the digest is the
deterministic artifact of record assembled without a model, each
digest section (session coverage entry with transcript counts and
evidence frame counts, confirmation decisions, execution receipts,
open items, handover including the `quiet` empty state), and the
vocabulary — evidence frame, owner vs foreign (metadata-only)
coverage tier, provenance anchoring, and the labeled narrative's
relationship to the digest facts.

Acceptance criteria:

- The reference covers every digest section and every vocabulary term
  above, each with an operator-readable explanation; nothing in it
  contradicts the shipped digest shape.
- The portal user guide's Documents section links to the reference,
  and the portal Documents view surfaces the same link (e.g. a "Learn
  more" affordance near the digest).
- The reference states the envelope-only listing posture (lists show
  metadata; full content is served by the audited single fetch).
- Digest shapes, routes, and export are unchanged by this
  requirement — documentation only.

### R-2: Tabbed, structured digest rendering in the drawer

The document drawer renders the digest as tabs with table-shaped
content instead of one recursive JSON tree: a **Handover** tab
(default), per-concern tabs for **sessions**, **confirmations**,
**executions**, **evidence & transcript counts**, and **open items**,
plus a **Raw JSON** tab. Rendering is tier-aware: foreign sessions
surface the metadata-only tier as such, never as empty fields that
read as missing data.

Acceptance criteria:

- Decisions render as rows with action, decision, decider, and
  timestamp; executions as rows with tool, receipt status, and
  completion time; the handover tab shows the shift-level counts,
  open items, and the honest quiet state.
- Foreign session entries never render owner-tier fields (title,
  transcript, evidence) — the metadata tier is labeled as metadata.
- The Raw JSON tab exposes the stored digest verbatim so the artifact
  of record remains inspectable; documents created before SPEC-040
  (no `handover`) degrade gracefully.
- Tabs are a rendering act only: the stored document, the audited
  single fetch, and the Markdown export (which continues to serialize
  the full digest) are unchanged.

### R-3: Bounded scrollable digest and prose panes

The digest area and the prose area in the drawer each render with a
bounded maximum height and internal scrolling when the content
overflows, with an affordance to expand to full height so no content
is ever trapped.

Acceptance criteria:

- At the standard drawer width, a long digest and a long narrative
  each scroll inside their own bounded region rather than stretching
  the drawer body.
- An expand/collapse affordance reveals the full content in place.
- Bounded rendering does not clip or alter content — everything
  remains reachable by scrolling or expanding.
- The export and the stored document are unaffected.

### R-4: Deterministic counts-only document summary in lists

The agent computes a deterministic one-line summary from the
document's own `handover` skeleton at creation time (no model
involvement), stores it on the document record, and the document
lists surface it under each row's label. The summary is counts-only —
covered-session counts, decision and execution counts, open-item
count, and the quiet phrasing — and never contains session titles,
record ids, decision outcomes, or narrative text.

Acceptance criteria:

- Every newly created shift summary carries the summary; two
  creations over identical records yield identical summary strings.
- A quiet shift's summary says plainly that nothing was decided or
  executed; a busy shift's summary reports counts only.
- The list endpoint returns the summary on both `mine` and
  `published` rows while continuing to strip `digest` and `prose`;
  the detail fetch, `document_read` audit posture, and all other
  authorization behavior are unchanged.
- Documents created before SPEC-041 carry no summary; lists and any
  consumer degrade gracefully (label-only rows).
- No new audit event types and no new policy actions are introduced.

## Design Decisions

- **The summary is metadata, not content.** The envelope-only listing
  posture (v0.21.1) keeps full content behind the audited single
  fetch. The summary stays within that posture because it discloses
  only counts and the quiet state — never titles, record ids,
  decision outcomes, or prose; a list reader learns "how much
  happened", not "what". AI-derived list summaries (e.g. the
  narrative's first sentence) were rejected for this reason: they
  would surface model text on the un-audited surface.
- **Computed at creation, not render.** Documents are immutable
  snapshots; deriving the summary when the digest is assembled keeps
  it deterministic, keeps pre-SPEC-041 documents untouched, and
  avoids re-deriving from handover on every list render.
- **Tabs are rendering, Raw JSON stays.** The structured tabs improve
  scanning; the Raw JSON tab keeps the artifact of record verifiable
  in place, and the Markdown export keeps serializing the full digest
  JSON so offline copies remain faithful.
- **Reference as a dedicated guide page.** A standalone page under
  `docs/guides/` keeps the portal user guide workflow-focused and
  gives the portal a stable link target.

## Non-Goals

- Narrative-derived or model-generated summaries anywhere in the
  document surface.
- Summaries or tab layouts for future document types (incident
  reports define their own shapes when promoted).
- Backfilling summaries onto pre-SPEC-041 stored documents —
  documents remain immutable snapshots.
- Evidence or transcript **content** in the digest, tabs, or lists —
  counts only, as shipped.
- Cross-owner session review (parked backlog item) — foreign coverage
  stays metadata-only everywhere this spec renders it.

## Impact

- products touched: `products/agent-platform` (creation-time summary
  computation and document record field), `products/operator-portal`
  (tabbed digest panel, bounded scroll panes, list summary rows,
  Learn more link), `products/platform-gateway` (pass-through only —
  no new routes)
- contracts touched: `shared/shared-contracts/schemas/operation-document.schema.json`
  (description-only note for the `summary` field; document stays an
  open object — no shape break)
- identity / policy / audit / execution safety impact: none — no new
  policy actions, no new audit event types, no execution-path change;
  the list envelope gains a counts-only field within the existing
  envelope posture
- living state docs to update on delivery: CHANGELOG, release notes +
  index, portal-user-guide (Documents section + reference link),
  new `docs/guides` reference page, spec index, delivery-roadmap

## Open Questions

- none recorded — the list-summary audit posture was resolved in
  Design Decisions (counts-only metadata).

## Changelog

- 2026-08-28: created as `draft` from operator live-test feedback on
  v0.22.0 (digest vocabulary documentation, tabbed/compact digest
  rendering, bounded scroll, list summaries).
- 2026-08-28: approved by the operator after the R-4 summary design
  (creation-time counts-only string in the list envelope) was
  confirmed; implementation proceeds as the third R5 slice (v0.23.0).
