---
kind: external_dependency
name: Browser automation driver via CDP sidecar
slug: playwright
category: external_dependency
category_hints:
    - framework_behavior
    - sdk_real_api
scope:
    - '**'
source_files:
    - products/tool-gateway/src/tool_gateway/tools/browser_connector.py
    - products/tool-gateway/src/tool_gateway/tools/browser_sessions.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/tool-gateway-browser-sidecar.yaml
---

### Role
Python Playwright drives a headless browser running in a **sidecar container** inside the `tool-gateway` pod. The connector connects over CDP (`connect_over_cdp`) to `ws://localhost:9222`; the gateway image itself carries only the Playwright Python dependency — no browser binary.

### Integration points
- `browser_connector.py` registers the 15 `web.*` tools (`web.navigate`, `web.snapshot`, `web.screenshot`, `web.click`, `web.type`, `web.fill_credential`, plus the 9 SPEC-050 additions: `web.select`, `web.press_key`, `web.upload_file`, `web.extract`, `web.wait_for`, `web.hover`, `web.evaluate`, `web.scroll`, `web.switch_frame`).
- `browser_sessions.py` manages per-session contexts on one warm browser process; sessions track a frame stack for `web.switch_frame`.
- `config.py` exposes `GATEWAY_BROWSER_CDP_ENDPOINT` (default `ws://localhost:9222`) and `GATEWAY_BROWSER_UPLOAD_DIR`.

### Stable usage model
- Write-tier tools inherit `_WebInteractionTool` → automatic HITL confirmation card in the operator portal.
- `web.evaluate` results are bounded (16K chars, 100 array elements); `web.upload_file` is restricted to an allowlisted directory.
- Frame traversal (`web.switch_frame`) checks frame origin against the flow's bound origin.

### Known constraints
- The sidecar port drifts between 9222/9223 depending on the `:stable` tag; pin both address and port explicitly.
- Origin allowlist is re-checked at `web.navigate` post-`goto`; snapshot/screenshot must additionally re-check after page load to guard against client-side redirects.