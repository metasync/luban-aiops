# SPEC-041 Implementation Plan

## Approach

Extend the delivered SPEC-039/040 surfaces in place — no new services,
no new policy actions, no new audit event types. The agent gains a
deterministic creation-time summary field on the document record; the
portal gains a tabbed digest panel, bounded scroll panes, list summary
rows, and a Learn more link; the guides gain a dedicated digest
reference page. Version lockstep to 0.23.0.

## Workstreams

### W-1: Creation-time document summary (agent-platform)

- `api/v2/routes.py` document-create path (or the adjacent documents
  service module): after `build_digest` returns, derive a one-line
  summary from `digest["handover"]`:
  - busy shift: `"{covered_session_count} sessions ·
    {decision_count} decisions · {execution_count} executions"` with
    ` · {open} open` appended when pending confirmations plus
    requested executions is nonzero
  - quiet shift (`quiet: true`): the plain "quiet shift — no recorded
    decisions or executions" phrasing
  - no model involvement; fully determined by the handover skeleton.
- Store the string as the document record's top-level `summary`
  field beside `label`/`state`; `list_documents` already strips only
  `digest`/`prose`, so the summary flows into both `mine` and
  `published` envelopes with no route change.
- `shared/shared-contracts/schemas/operation-document.schema.json`:
  description-only note for the new `summary` property (open object
  posture unchanged).
- Tests (`tests/test_documents.py`, `tests/test_shift_summary.py`):
  determinism (identical records → identical string), quiet phrasing,
  open-item suffix, counts-only (never titles/ids/outcomes), envelope
  carries `summary` while digest/prose stay stripped, missing summary
  on legacy records degrades.

### W-2: Tabbed structured digest panel (portal)

- `views/workspace/DocumentsView.tsx`: restructure `DigestPanel` from
  the recursive JSON tree into an antd `Tabs` layout:
  - **Handover** (default) — shift counts, open items, quiet state,
    decision and execution tables
  - **Sessions** — one row per covered session: title (owner tier),
    coverage tag, transcript counts, evidence frame counts
  - **Confirmations** — rows: session, action, status/decision,
    decider, decided_at
  - **Executions** — rows: session, tool, receipt status,
    completed_at
  - **Open items** — per-session pending/requested breakdown
  - **Raw JSON** — the stored digest verbatim (existing tree renderer
    stays here)
- Foreign entries render as a labeled metadata tier (counts and
  decisions only), never as empty owner-tier fields.
- Pre-SPEC-040 documents (no `handover`) hide the handover tab and
  keep the Raw JSON tab.
- Unit tests: tab presence, foreign-tier rendering, legacy
  degradation, raw JSON intact.

### W-3: Bounded scroll panes (portal)

- Drawer digest and prose areas get a bounded `maxHeight` with
  internal scroll (`overflow: auto`) plus an expand/collapse
  affordance that releases the bound in place.
- Unit test: pane renders the expand affordance; export unchanged.

### W-4: List summary rows (portal)

- `DocumentsView` Mine/Published list rows render the envelope's
  `summary` as a secondary line under the label; rows without a
  summary (legacy documents) stay label-only.
- Unit test: summary line renders; legacy row degrades.

### W-5: Digest reference documentation (docs + portal link)

- New `docs/guides/documents-digest-reference.md`: what an operations
  document is; the digest as the deterministic artifact of record; a
  section-by-section explanation (session entries with transcript
  counts and evidence frame counts, confirmations, executions, open
  items, handover incl. `quiet`); vocabulary — evidence frame,
  owner/foreign coverage tiers, provenance anchoring, labeled
  narrative; the envelope-only listing posture.
- `docs/guides/portal-user-guide.md` Documents section links to the
  reference.
- Portal Documents view gains the Learn more link to the same page.

## Verification

- agent-platform suite green (new summary tests + existing document
  suites); portal `tsc` build and unit tests green; `make verify`
  green at 0.23.0.
- Live check: `documents-demo.sh` extended — created document carries
  the deterministic `summary` and the list endpoint returns it with
  digest/prose still stripped; browser walkthrough covers the tabbed
  drawer, bounded scroll, list summary lines, and the Learn more
  link.

## Release

0.23.0 (minor) through the full train: version lockstep, living-state
docs, live check, feat commit, scan gate, annotated tag, push,
repowiki refresh as a separate docs commit.
