# SPEC-050 Tasks

## Implementation Order

The tasks are ordered to build incrementally: core tools first, then
restructuring, then documentation. Each task is independently testable.

## Wave 1: Write-tier tools (inherit `_WebInteractionTool`)

These tools follow the exact same pattern as `web.click` and `web.type`,
so they're the fastest to implement and test.

- [x] **t1**: `web.select` — dropdown selection
- [x] **t4**: `web.press_key` — keyboard input
- [x] **t8**: `web.upload_file` — file upload with path allowlisting

## Wave 2: Read-tier tools (use `gate_capture`)

These tools follow the pattern of `web.snapshot` and `web.screenshot`:
read-tier, origin re-check, no step budget consumption.

- [x] **t2**: `web.extract` — structured data extraction
- [x] **t3**: `web.wait_for` — element state wait
- [x] **t5**: `web.hover` — element hover
- [x] **t6**: `web.evaluate` — JavaScript evaluation
- [x] **t7**: `web.scroll` — page scrolling
- [x] **t9**: `web.switch_frame` — iframe traversal

## Wave 3: Test infrastructure

- [x] **t10**: Update FakePage/FakeElementHandle with new methods
  (`select_option`, `hover`, `press`, `set_input_files`,
  `wait_for_selector`, `mouse.wheel`, frame traversal)

## Wave 4: Samples restructuring

- [x] **t11**: Create `samples/` directory structure
- [x] **t12**: Update references and clean up old locations
- [x] **t13**: Update `make verify` and demo scripts

## Wave 5: Documentation

- [x] **t14**: Update documentation (CHANGELOG, spec index, tool docs)

## Estimation

| Wave | Tasks | Estimated effort |
|------|-------|-----------------|
| 1 | 3 write-tier tools | ~2 hours |
| 2 | 6 read-tier tools | ~3 hours |
| 3 | Test infrastructure | ~1 hour |
| 4 | Samples restructuring | ~1.5 hours |
| 5 | Documentation | ~0.5 hours |
| **Total** | **14 tasks** | **~8 hours** |

## Dependencies

- Wave 3 (test infrastructure) should be done alongside or before Waves 1-2
  so each tool can be tested as it's implemented.
- Wave 4 (restructuring) is independent of Waves 1-3 and could be done in
  parallel by a second implementer.
- Wave 5 (documentation) depends on Waves 1-4 being complete.

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] `make verify` green at 0.32.0 (tests + all four overlays + policy
  validation + scenario guard + version lockstep)
- [x] live `dev-k8s` check: `make deploy-samples` ingested
  `samples/password-reset-resetuserpassword`, `demo.sh` ran all five legs,
  `make undeploy-samples` / re-deploy lifecycle confirmed
- [x] `CHANGELOG.md` closed into the `0.32.0 — 2026-09-04` section
- [x] release note + release-notes index entry added
- [x] spec index in `docs/specs/README.md` updated
- [x] delivery-roadmap backlog row updated
- [x] spec status set to `delivered` (delivered: 2026-09-04)
