# SPEC-041 Tasks: Documents Readability and Digest Reference

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-4: Deterministic counts-only document summary in lists

- [ ] Compute the summary from `digest["handover"]` in the create path; store as the document record's top-level `summary` field (`products/agent-platform`)
- [ ] Contract note: description-only `summary` note in `operation-document.schema.json` (`shared/shared-contracts`)
- [ ] Tests: determinism, quiet phrasing, open-item suffix, counts-only posture, envelope carries summary with digest/prose stripped, legacy degradation (`products/agent-platform/tests/test_documents.py`)
- [ ] Portal list rows render the summary line; legacy rows degrade to label-only (`products/operator-portal/.../DocumentsView.tsx` + test)

## R-2: Tabbed, structured digest rendering in the drawer

- [ ] Restructure `DigestPanel` into tabs: Handover (default), Sessions, Confirmations, Executions, Evidence & transcript, Open items, Raw JSON (`products/operator-portal/.../DocumentsView.tsx`)
- [ ] Decision/execution tables with stable columns; quiet state on the handover tab (`products/operator-portal`)
- [ ] Tier-aware rendering: foreign sessions labeled as metadata tier, never empty owner-tier fields (`products/operator-portal`)
- [ ] Tests: tab presence, foreign-tier rendering, pre-SPEC-040 degradation, raw JSON intact (`products/operator-portal/.../__tests__/DocumentsView.test.tsx`)

## R-3: Bounded scrollable digest and prose panes

- [ ] Bounded maxHeight + internal scroll + expand/collapse affordance on digest and prose panes (`products/operator-portal`)
- [ ] Test: expand affordance renders; export unaffected (`products/operator-portal`)

## R-1: Operator digest and documents reference

- [ ] New `docs/guides/documents-digest-reference.md` covering every digest section and vocabulary term (`docs/guides`)
- [ ] Portal user guide Documents section links to the reference (`docs/guides/portal-user-guide.md`)
- [ ] Portal Documents view Learn more link to the reference page (`products/operator-portal`)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
