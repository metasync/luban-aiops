# SPEC-040 Implementation Plan

## Approach

Extend the delivered SPEC-039 substrate in place — no new services, no
new policy actions, no new audit event types. The agent gains a
deterministic `handover` digest section and a prose-default flip with a
tighter prompt contract; the portal gains a nav move, a relabeled prose
panel, and a client-side Markdown export. Version lockstep to 0.22.0.

## Workstreams

### W-1: Handover digest section (agent-platform)

- `services/shift_summary.py`: new `_handover(entries)` pass inside
  `build_digest`, computed from the per-session entries after assembly:
  - `covered_session_count`, `own_session_count`,
    `foreign_session_count`
  - `decisions` — own-coverage confirmations only: `session_id`,
    `confirm_id`, `action`, `decision`, `decider_user_id`,
    `decided_at`; sorted by `(decided_at or parked_at, confirm_id)`
  - `executions` — own-coverage executions only: `session_id`,
    `execution_id`, `tool_name`, `receipt_status`, `completed_at`;
    sorted by `(completed_at, execution_id)`
  - `decision_count` / `execution_count` — decided confirmations and
    recorded executions across **all** covered sessions (foreign
    records contribute counts only, never details)
  - `open_items` — summed pending confirmations and requested
    executions; `open_sessions` — own-coverage session ids carrying
    any open item
  - `quiet` — true when no decisions and no executions exist anywhere
    in the shift (the honest empty state)
  - Unavailable sources contribute nothing (degrade with the session
    section); assembly stays side-effect-free and deterministic.
- `shared/shared-contracts/schemas/operation-document.schema.json`:
  description-only note on the `digest` property for the `handover`
  section (digest stays an open object — no shape break).
- Tests (`tests/test_shift_summary.py` + `tests/test_documents.py`):
  determinism (two assemblies byte-identical), two-tier posture
  (foreign never leaks details), quiet shift, open items,
  `handover` present on created documents via the route.

### W-2: Prose as default, anchored narrative (agent-platform + portal)

- `schemas/v2.py` `DocumentCreateRequest.include_prose`: default
  flips `False → True` (omitted requests now generate prose);
  docstring updated.
- `services/document_prose.py`: prompt contract gains the anchoring
  rules — render only facts present in the digest, reference the
  digest sections facts come from (including the new `handover`
  section), never introduce record ids, causes, or recommendations
  absent from the input; digest-only input invariant unchanged.
- Portal `DocumentsView` create dialog: prose switch defaults on
  (explicit opt-out preserved); prose panel label becomes
  "AI-generated narrative (from this document's digest facts)".
- Tests: create with omitted `include_prose` requests prose
  (monkeypatched generator); explicit false keeps `not_requested`;
  existing create tests pin `include_prose: false` where they assert
  `not_requested`.

### W-3: Documents moves to Workspace (portal)

- `App.tsx`: the Documents menu item moves from the Control group to
  the Workspace group (first Workspace entry); its `documents:read`
  role mirror moves with it into the workspace visibility block;
  Control rendering unchanged for roles seeing only other surfaces.
- View file moves `views/control/DocumentsView.tsx →
  views/workspace/DocumentsView.tsx` with its test; import paths
  updated (App.tsx, test file).
- Guide: portal-user-guide navigation references updated.

### W-4: Markdown export (portal)

- New `src/documents/exportDocument.ts`:
  `renderDocumentMarkdown(document)` — self-contained Markdown:
  title/label, metadata table (type, state, owner, created/published,
  document id), provenance table (session ids, coverage, cited record
  ids), handover section (when present), digest sections, labeled
  prose (when `included`; failure noted when `failed`), and an export
  footer (document id + UTC export time).
  `downloadDocumentMarkdown(document)` — Blob download, filename
  `<label-slug>-<document-id short>.md` (label slugified, capped;
  id short = `doc-` + first six hex chars).
- Drawer gains an **Export** button beside the header meta; export
  uses the already-fetched full document — no network call.
- Unit test for the renderer (metadata/provenance/prose posture,
  quiet handover, failed prose note).

## Verification

- agent-platform + platform-gateway suites green; portal `tsc` build
  and unit tests green; `make verify` green at 0.22.0.
- Live check: `documents-demo.sh` extended — created document carries
  `handover` (quiet shape on the demo session), and the created-via-
  default request flows prose generation posture; browser walkthrough
  covers nav placement, default prose switch, handover rendering, and
  the export download.

## Release

0.22.0 (minor) through the full train: version lockstep, living-state
docs, live check, feat commit, scan gate, annotated tag, push,
repowiki refresh as a separate docs commit.
