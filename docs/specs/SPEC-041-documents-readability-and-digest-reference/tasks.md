# SPEC-041 Tasks: Documents Readability and Digest Reference

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-4: Deterministic counts-only document summary in lists

- [x] Compute the summary from `digest["handover"]` in the create path; store as the document record's top-level `summary` field (`products/agent-platform`)
- [x] Contract note: description-only `summary` note in `operation-document.schema.json` (`shared/shared-contracts`)
- [x] Tests: determinism, quiet phrasing, open-item suffix, counts-only posture, envelope carries summary with digest/prose stripped, legacy degradation (`products/agent-platform/tests/test_documents.py`)
- [x] Portal list rows render the summary line; legacy rows degrade to label-only (`products/operator-portal/.../DocumentsView.tsx` + test)

## R-2: Tabbed, structured digest rendering in the drawer

- [x] Restructure `DigestPanel` into tabs: Handover (default), Sessions, Confirmations, Executions, Evidence & transcript, Open items, Raw JSON (`products/operator-portal/.../DocumentsView.tsx`)
- [x] Decision/execution tables with stable columns; quiet state on the handover tab (`products/operator-portal`)
- [x] Tier-aware rendering: foreign sessions labeled as metadata tier, never empty owner-tier fields (`products/operator-portal`)
- [x] Tests: tab presence, foreign-tier rendering, pre-SPEC-040 degradation, raw JSON intact (`products/operator-portal/.../__tests__/DocumentsView.test.tsx`)

## R-3: Bounded scrollable digest and prose panes

- [x] Bounded maxHeight + internal scroll + expand/collapse affordance on digest and prose panes (`products/operator-portal`)
- [x] Test: expand affordance renders; export unaffected (`products/operator-portal`)

## R-1: Operator digest and documents reference

- [x] New `docs/guides/documents-digest-reference.md` covering every digest section and vocabulary term (`docs/guides`)
- [x] Portal user guide Documents section links to the reference (`docs/guides/portal-user-guide.md`)
- [x] Portal Documents view Learn more link to the reference page (`products/operator-portal`)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
