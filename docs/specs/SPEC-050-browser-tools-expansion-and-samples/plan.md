# SPEC-050 Implementation Plan

## Overview

SPEC-050 delivers two workstreams:
1. **Browser Tools Expansion**: 9 new `web.*` tools (15 total)
2. **Samples Reorganization**: Self-contained `samples/` directory

Target version: **v0.32.0**

## Implementation Strategy

### Phase 1: Write-tier tools (t1, t4, t8)

These extend `_WebInteractionTool` and follow the exact pattern of `web.click`
and `web.type`. Each tool:
- Subclasses `_WebInteractionTool`
- Sets `tool_name` and `risk_level = "write"`
- Implements `definition` property with parameters schema
- Implements `execute` method with deviation guard + ref resolution + action
- Registers in `BrowserConnector.register_tools`
- Gets unit tests covering success, invalid ref, flow-not-bound paths

**Files to modify:**
- `products/tool-gateway/src/tool_gateway/tools/browser_connector.py`
- `products/tool-gateway/tests/test_browser_connector.py`

### Phase 2: Read-tier tools (t2, t3, t5, t6, t7, t9)

These extend `BaseTool` and follow the pattern of `web.snapshot`/`web.screenshot`.
Each tool:
- Subclasses `BaseTool`
- Sets `risk_level = "read"`
- Implements `definition` property
- Implements `execute` method with `gate_capture` origin re-check
- Gets unit tests

**Special cases:**
- `web.extract`: Needs CSS selector query + result bounding logic
- `web.wait_for`: Needs timeout cap enforcement
- `web.evaluate`: Needs result serialization + size bounding
- `web.switch_frame`: Needs frame tracking in `BrowserSessionEntry`

**Files to modify:**
- `products/tool-gateway/src/tool_gateway/tools/browser_connector.py`
- `products/tool-gateway/src/tool_gateway/tools/browser_sessions.py` (for frame tracking)
- `products/tool-gateway/tests/test_browser_connector.py`

### Phase 3: Test infrastructure (t10)

Update the fake Playwright layer to support the new operations:
- `FakeElementHandle.select_option(value)`
- `FakeElementHandle.hover()`
- `FakePage.keyboard.press(key)`
- `FakeElementHandle.set_input_files(files)`
- `FakePage.wait_for_selector(selector, state, timeout)`
- `FakePage.mouse.wheel(delta_x, delta_y)`
- `FakePage.frame(selector)` / `FakeFrame` class

This phase should be done alongside Phases 1-2 so each tool can be tested
as it's implemented.

### Phase 4: Samples restructuring (t11, t12, t13)

**Final directory structure** (tutorial-specific artifacts only; see R-11 for
the separation principle — dependency arrow is always tutorial → platform):
```
samples/
├── README.md                    # overview + `make deploy-samples` guide
├── deploy-samples.sh            # installs sample skills into a cluster
└── web-checks/
    └── password-reset/
        ├── README.md
        ├── WALKTHROUGH.md
        ├── skill/
        │   └── ResetUserPassword.md
        └── demo/
            └── demo.sh
```

**Single-source the skill (no deployed platform copy):**
- `samples/web-checks/password-reset/skill/ResetUserPassword.md` is the one
  home, reconciled to the richer v1.1 content.
- Remove `shared/platform-ops/skills/platform-runbooks/web-checks/ResetUserPassword.md`.
- Remove `shared/platform-ops/e2e/password-reset-demo.sh` (superseded by the
  samples demo).

**Shared infrastructure stays in platform space** (also used by the SPEC-049
`browser-check-demo.sh` smoke test) and is *referenced*, not moved:
- `runtime-profiles/browser-dev/browser-check-target-pages.yaml` (admin pages)
- `runtime-profiles/browser-dev/browser-check-target-deployment.yaml`
- `runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml`
- `sync-browser-credentials.sh` (the `admin-portal` credential set)

**Generic `samples` skill source** (the base overlay names no specific sample):
- `dev-k8s/base/kustomization.yaml`: drop the ResetUserPassword ConfigMap entry.
- `dev-k8s/base/skills-hub/skills-hub-deployment.yaml`: drop the
  ResetUserPassword volume item; add an optional `skills-samples` ConfigMap
  volume mounted read-only at `/skills/samples`.
- `dev-k8s/base/skills-hub/runtime-config.env`: add a `samples` local source
  entry to `SKILLS_SOURCES`.
- Root `Makefile`: add `deploy-samples` / `undeploy-samples` targets wrapping
  `samples/deploy-samples.sh`, which packs selected `skill/*.md` into the
  `skills-samples` ConfigMap and restarts skills-hub.

### Phase 5: Documentation (t14)

- Update `CHANGELOG.md` with v0.32.0 entry listing all 9 new tools
- Add SPEC-050 to `docs/specs/README.md` index
- Update any browser tool documentation
- Create `samples/README.md` with overview of available samples

## Verification Plan

### Unit tests
- Each new tool gets unit tests in `test_browser_connector.py`
- Tests use the fake Playwright layer (no real browser needed)
- Cover success, error, and enforcement paths

### Integration tests
- `make verify` passes (existing 273+ tests + new tool tests)
- `browser-check-demo.sh` passes (no regression)
- `samples/web-checks/password-reset/demo.sh` passes from new location

### Manual verification
- Deploy to dev-k8s overlay
- Verify all 15 tools appear in tool registry
- Run password-reset demo end-to-end
- Verify write-tier tools require HITL confirmation

## Risk Mitigation

### Risk: Fake Playwright layer complexity
**Mitigation**: Each fake method is simple (increment counter, store value).
The fake layer is already proven for `click`, `fill`, `evaluate`, `screenshot`.

### Risk: `web.evaluate` security
**Mitigation**: Origin allowlist + flow binding ensure the expression runs
only on approved pages. Result bounding prevents data exfiltration.

### Risk: `web.upload_file` path traversal
**Mitigation**: Path resolution uses `os.path.commonpath` to verify the
resolved path is under `GATEWAY_BROWSER_UPLOAD_DIR`. Symlinks are resolved
before checking.

### Risk: `web.switch_frame` cross-origin
**Mitigation**: Frame origin is checked against flow's bound origin. Cross-origin
frames are denied with `BROWSER_FRAME_ORIGIN_MISMATCH`.

## Rollback Plan

If SPEC-050 causes issues in production:
1. Set `GATEWAY_BROWSER_ENABLED=false` to disable all browser tools
2. Revert the deployment to the previous image
3. The samples restructuring is purely organizational and can be reverted
   independently

## Success Criteria

- All 9 new tools implemented and tested
- `samples/web-checks/password-reset/` is self-contained and documented
- `make verify` passes with no regressions
- Both demo scripts pass
- Documentation updated
