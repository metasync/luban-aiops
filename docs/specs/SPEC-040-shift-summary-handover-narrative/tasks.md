# SPEC-040 Tasks

Derived from `plan.md`; each requirement maps to its workstream.

## R-1 — Deterministic handover digest section

- [ ] Add `_handover(entries)` assembly to `shift_summary.py`
      (counts, own-only decisions/executions details with stable
      sorting, open items, open sessions, quiet flag)
- [ ] Wire `handover` into `build_digest` output; unavailable
      sources degrade per session as today
- [ ] Contract note: `operation-document.schema.json` digest
      description documents the `handover` section
- [ ] Tests: determinism, two-tier foreign counts-only posture,
      quiet shift, open items, route-created document carries
      `handover`

## R-2 — Prose as the default, digest-anchored narrative

- [ ] Flip `DocumentCreateRequest.include_prose` default to `True`;
      docstring updated
- [ ] Extend the prose prompt contract with the anchoring rules
      (digest sections referenced; no new record ids/facts)
- [ ] Portal: create dialog prose switch defaults on (opt-out kept);
      prose panel relabeled "AI-generated narrative (from this
      document's digest facts)"
- [ ] Tests: omitted `include_prose` requests prose (monkeypatched
      generator); explicit false stays `not_requested`; existing
      create tests pinned accordingly

## R-3 — Documents moves from Control to Workspace

- [ ] `App.tsx`: Documents entry moves to the Workspace group (first
      entry); visibility mirror moves with it
- [ ] Move `views/control/DocumentsView.tsx` (+ test) to
      `views/workspace/`; imports updated
- [ ] Portal guide navigation wording updated

## R-4 — Offline Markdown export

- [ ] `exportDocument.ts`: `renderDocumentMarkdown` (metadata table,
      provenance table, handover, digest sections, labeled prose /
      failure note, attributed footer)
- [ ] `downloadDocumentMarkdown`: Blob download,
      `<label-slug>-doc-<6-hex>.md` filename
- [ ] Drawer Export button; export uses the already-fetched document
      (no network call)
- [ ] Renderer unit test (metadata/provenance/prose posture, quiet
      handover, failed-prose note)

## Release train

- [ ] Version lockstep 0.22.0 (VERSION, pyprojects, metadata
      surfaces, uv.locks)
- [ ] Living-state docs: CHANGELOG Unreleased entry, release note +
      index, portal-user-guide (placement, handover, export
      walkthrough), authorization-matrix note if needed, spec status
      flip, specs README, roadmap row
- [ ] `make verify` green
- [ ] Live check: extend `documents-demo.sh` (handover present on
      created document, quiet shape), rebuild + deploy + run
- [ ] Browser walkthrough: nav placement, default prose switch,
      handover rendering, export download
- [ ] Feat commit, scan gate, annotated tag v0.22.0, push, repowiki
      refresh as separate docs commit
