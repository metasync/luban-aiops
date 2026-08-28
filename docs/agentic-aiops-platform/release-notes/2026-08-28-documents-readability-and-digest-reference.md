# v0.23.0 — Documents Readability and Digest Reference (SPEC-041)

Date: 2026-08-28
Release type: feature (third R5 slice, extending the SPEC-039/040
document repository; no new policy actions, no new audit event types)

## Summary

The v0.22.0 live test confirmed the document repository works but
surfaced four operator clarifications: the digest vocabulary (digest,
frame, coverage tiers, handover, quiet) is nowhere explained to
operators; the drawer renders the digest as one wall of nested lists;
the Digest and Prose blocks grow unbounded in the 560px drawer; and
the document lists give no glimpse of what each document contains.
v0.23.0 delivers SPEC-041: an operator-facing digest reference guide,
tabbed table-shaped digest rendering, bounded scrollable digest and
prose panes, and a deterministic counts-only summary line computed at
creation time and shown with each document in the lists.

## What Changed

### Operator digest reference (docs + portal, R-1)

- New `docs/guides/documents-digest-reference.md` explains, in plain
  operator language, what an operations document is, that the digest is
  the deterministic artifact of record assembled without a model, every
  digest section (session entries with transcript counts and evidence
  frame counts, confirmation decisions, execution receipts, open items,
  the handover skeleton including the honest `quiet` state), and the
  vocabulary: evidence frame, owner vs foreign (metadata-only) coverage
  tier, provenance anchoring, the narrative's relationship to the
  digest facts, and the envelope-only listing posture.
- The portal user guide's Documents section links the reference, and
  the portal document drawer surfaces a **Learn more** link beside the
  Digest title. Documentation only — digest shapes, routes, and export
  are unchanged by this requirement.

### Tabbed, structured digest rendering (portal, R-2)

- The drawer renders the digest as tabs instead of one recursive JSON
  tree: **Handover** (default when present) with the shift-level
  counts, open items, and quiet state; **Sessions** with one card per
  covered session; **Confirmations** with decision rows (action,
  status, decision, decider, decided time); **Executions** with receipt
  rows (tool, status, receipt, completion time); **Evidence &
  transcript** with per-session counts; **Open items**; and **Raw
  JSON** exposing the stored digest verbatim so the artifact of record
  stays inspectable.
- Rendering is tier-aware: foreign sessions are labeled *metadata
  only* with their record counts — never empty owner-tier fields that
  read as missing data — and `unavailable` store sections surface as
  tags. Documents created before SPEC-040 (no `handover`) degrade
  gracefully to the remaining tabs. Tabs are a rendering act only:
  the stored document, the audited single fetch, and the Markdown
  export are unchanged.

### Bounded scrollable panes (portal, R-3)

- The digest and prose regions in the drawer each render bounded with
  internal scrolling when the content overflows, plus an expand
  affordance that reveals the full content in place — nothing is ever
  trapped off screen, and the export and stored document are
  unaffected.

### Deterministic counts-only list summaries (agent + portal, R-4)

- The agent computes a one-line summary from the document's own
  `handover` skeleton at creation time (no model involvement) and
  stores it on the document record: *2 sessions · 3 decisions · 1
  execution · 1 open item* for busy shifts, *Quiet shift — no recorded
  decisions or executions.* for quiet ones. The summary is counts-only
  — never session titles, record ids, decision outcomes, or narrative
  text — so it flows through the envelope-only listing without breaking
  the audited single-read posture.
- Both `mine` and `published` list rows surface the summary under the
  label; pre-SPEC-041 documents degrade to label-only rows. The detail
  fetch, `document_read` audit posture, and all authorization behavior
  are unchanged; no new audit event types or policy actions.

## Storage and Contracts

- `operation_documents` gains an additive nullable `summary TEXT`
  column (Postgres: `ADD COLUMN IF NOT EXISTS` migration; legacy rows
  NULL). The in-memory store passes the field through unchanged.
- `operation-document.schema.json` gains an additive `summary`
  property (`["string", "null"]`, not required) — the document stays
  an open object, no shape break.

## Verification

- New `TestDocumentSummary` suites pin the summary wording contract
  (busy counts, open-item suffix, quiet phrasing, determinism,
  legacy/degraded `None`), the creation-time storage and envelope flow
  (mine + published), and the label-only legacy degrade; portal suites
  cover the tab layout, tier-aware foreign rendering, legacy degrade,
  list summary rows, and the bounded-pane expand affordance
  (agent-platform tests green; portal 179 tests green).
- `make verify` green at 0.23.0.
- Live check: rebuilt and redeployed to the dev cluster;
  `shared/platform-ops/e2e/documents-demo.sh` passes with the summary
  assertions, plus the browser walkthrough of the tabbed digest,
  bounded panes, list summaries, and the Learn more link.
