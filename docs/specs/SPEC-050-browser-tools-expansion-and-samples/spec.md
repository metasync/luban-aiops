# SPEC-050: Browser Tools Expansion and Samples Reorganization

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-03
- approved: 2026-09-03
- delivered: 2026-09-04
- release slice: R5 — Hardening and External Consumption (target v0.32.0)
- related ADRs: none (lineage: extends SPEC-049 browser web-check tools,
  SPEC-007 read-only tool execution framework, SPEC-014 skills and
  grounded guidance, SPEC-020 HITL confirmation bridging, SPEC-021
  bounded mutating actions)

## Summary

SPEC-049 delivered a six-tool browser surface (`web.navigate`, `web.snapshot`,
`web.screenshot`, `web.fill_credential`, `web.click`, `web.type`) that covers
basic login-and-inspect flows. This spec expands the surface by nine tools to
cover the interactions real-world admin panels and dashboards actually require
(dropdowns, structured data extraction, async waits, keyboard shortcuts, hover
menus, JavaScript evaluation, scrolling, file uploads, and iframe traversal).
It also reorganizes tutorial demo content into a top-level `samples/` directory
so each sample is self-contained — skill, target pages, credentials, demo
script, and deployment wiring — rather than scattered across four directories.

## Motivation

- The six-tool MVP covers the happy path (navigate, snapshot, click, type) but
  real admin panels use `<select>` dropdowns, load data asynchronously, embed
  dashboards in iframes, and hide actions behind hover menus. Without these
  tools, the agent cannot automate the majority of operator web-check skills.
- The password-reset demo pieces currently live in four separate directories
  (`skills/`, `e2e/`, `gitops/runtime-profiles/browser-dev/`,
  `gitops/sync-browser-credentials.sh`), making it hard for a new user to
  discover the full picture or adapt the demo for their own target.
- The existing tool patterns (`_WebInteractionTool`, `gate_capture`,
  `gate_interaction`, `FlowState`) generalize cleanly to the new tools — the
  HITL confirmation, deviation guard, origin allowlist, and credential masking
  machinery carries over for free.

## Requirements

### R-1: `web.select` — dropdown selection (write tier)

Select an `<option>` from a `<select>` element by snapshot ref. The tool
accepts a ref and a value (the option's `value` attribute) or visible text.

- Follows the `_WebInteractionTool` pattern: deviation guard, ref resolution,
  step counting, HITL confirmation via the existing SPEC-020/037 path.
- Uses Playwright's `select_option()` with `value` or `label` matching.
- Returns the selected option's text and value in the result data.

Acceptance criteria:
- `web.select` with a valid ref and matching value succeeds and increments
  `flow.steps_used`.
- `web.select` with a ref that is not a `<select>` element returns
  `BROWSER_SELECT_NOT_A_SELECT`.
- `web.select` with a value not present in the dropdown returns
  `BROWSER_SELECT_OPTION_NOT_FOUND`.
- Write-tier enforcement: requires bound write-class flow, HITL approval.
- Unit test covers success, wrong-element-type, missing-option, and
  flow-not-bound paths.

### R-2: `web.extract` — structured data extraction (read tier)

Extract structured data from DOM elements matching a CSS selector. Returns
rows of key-value pairs from table rows, list items, or repeating elements.

- Read tier: no HITL gate, but requires a bound flow and origin re-check
  via `gate_capture`.
- Accepts a `selector` (CSS selector) and optional `max_rows` (default 100,
  hard cap 500).
- For `<table>` elements: extracts header row as keys, data rows as values.
- For other elements: extracts text content of each matched element.
- Result is bounded: max 500 rows, max 50 columns, text cells truncated to
  200 chars.

Acceptance criteria:
- `web.extract` with a table selector returns `{headers: [...], rows: [[...]]}`.
- `web.extract` with a non-table selector returns `{items: ["..."]}`.
- `web.extract` with no matching elements returns `{items: []}`.
- Origin re-check via `gate_capture` blocks off-flow extraction.
- Result size is bounded (max_rows cap honored).
- Unit test covers table extraction, list extraction, empty result, origin
  deviation, and cap enforcement.

### R-3: `web.wait_for` — element state wait (read tier)

Wait for an element to appear, disappear, or reach a specific state. Essential
for pages that load data asynchronously after navigation.

- Read tier: no HITL gate, requires bound flow and origin re-check.
- Accepts a `selector` (CSS selector), `state` (one of `attached`, `detached`,
  `visible`, `hidden`), and optional `timeout_ms` (default 5000, hard cap
  30000).
- Uses Playwright's `wait_for_selector()` with the given state.
- Returns the matched element's tag and text content (bounded to 200 chars).

Acceptance criteria:
- `web.wait_for` with `state=visible` succeeds when the element appears within
  the timeout.
- `web.wait_for` with `state=detached` succeeds when the element disappears.
- `web.wait_for` that exceeds the timeout returns `BROWSER_WAIT_TIMEOUT`.
- Timeout is capped at 30000ms server-side regardless of caller input.
- Origin re-check blocks off-flow waits.
- Unit test covers visible/detached/timeout/cap paths.

### R-4: `web.press_key` — keyboard input (write tier)

Press a keyboard key or key combination. Useful for search fields (Enter),
closing dialogs (Escape), and keyboard shortcuts.

- Follows the `_WebInteractionTool` pattern: deviation guard, ref resolution,
  step counting, HITL confirmation.
- Accepts a `key` (Playwright key name, e.g. `Enter`, `Escape`, `Tab`,
  `Control+a`) and optional `ref` (if omitted, presses on the page body).
- Uses Playwright's `keyboard.press()`.

Acceptance criteria:
- `web.press_key` with a valid key succeeds and increments `flow.steps_used`.
- `web.press_key` with a ref focuses the element first, then presses.
- Write-tier enforcement: requires bound write-class flow, HITL approval.
- Unit test covers key press with and without ref, flow-not-bound path.

### R-5: `web.hover` — element hover (read tier)

Hover over an element to reveal tooltips, dropdown menus, or popover actions.

- Read tier: no HITL gate, requires bound flow and origin re-check.
- Accepts a `ref` (snapshot element reference).
- Uses Playwright's `hover()` on the resolved element handle.
- Returns the element's tag and any tooltip text revealed.

Acceptance criteria:
- `web.hover` with a valid ref succeeds and returns element info.
- `web.hover` with an invalid ref returns `BROWSER_REF_UNKNOWN`.
- Origin re-check blocks off-flow hovers.
- Unit test covers success, invalid ref, origin deviation.

### R-6: `web.evaluate` — JavaScript evaluation (write tier)

Execute JavaScript in the page context and return the result. Escape hatch for
data the accessibility tree doesn't capture (chart data, computed state).

- Write tier: arbitrary JS can mutate the DOM and read back masked credential
  values, so every invocation inherits the SPEC-020/037 HITL gate (the operator
  confirms before any script runs) and is never auto-allowed; the gateway still
  enforces the origin allowlist and the flow-origin re-check on every call.
- A pre-execution mutation guard rejects expressions containing known
  state-changing DOM APIs (`BROWSER_EVAL_MUTATION_BLOCKED`) as defense-in-depth
  only — it steers the agent to the dedicated ref-addressed write tools, but the
  HITL gate, not the regex denylist, is the security boundary.
- Accepts `expression` (JavaScript expression string).
- Result is serialized to JSON; non-serializable values return an error.
- Result size bounded: max 16000 chars, max 100 array elements.
- The expression runs in the page's main world (not an isolated context).

Acceptance criteria:
- `web.evaluate` with a simple expression (`document.title`) returns the value.
- `web.evaluate` with a non-serializable result (function, symbol) returns
  `BROWSER_EVAL_NOT_SERIALIZABLE`.
- `web.evaluate` with a result exceeding the size cap returns
  `BROWSER_EVAL_RESULT_TOO_LARGE`.
- `web.evaluate` with a mutating expression (`.click()`, `.submit()`) returns
  `BROWSER_EVAL_MUTATION_BLOCKED`.
- Origin re-check blocks off-flow evaluation.
- `web.evaluate` declares risk tier `write` and is absent from the kernel
  auto-allow set, so it always parks for HITL confirmation.
- Unit test covers success, serialization failure, size cap, origin deviation,
  and the mutation guard.

### R-7: `web.scroll` — page scrolling (read tier)

Scroll the page or a specific element by a delta. Lets the agent see content
below the fold.

- Read tier: no HITL gate; the gateway enforces the origin allowlist and the
  flow-origin re-check on every call.
- Accepts `delta_x` and `delta_y` (pixel offsets, signed integers; default
  `0`/`300`).
- Dispatches a Page-level `mouse.wheel(delta_x, delta_y)`. When an iframe is
  the active target, the cursor is first moved to the frame's center so the
  wheel scrolls the frame rather than the top-level page.
- Returns the active target's `url` and the applied `delta_x`/`delta_y`.

Acceptance criteria:
- `web.scroll` with valid deltas succeeds and returns the applied deltas + url.
- `web.scroll` with non-integer deltas returns `INVALID_PARAMETERS`.
- Origin re-check blocks off-flow scrolls.
- With an active frame, the cursor is centered over the frame before wheeling.
- Unit test covers success, defaults, invalid parameters, origin deviation, and
  frame-centering.

### R-8: `web.upload_file` — file upload (write tier)

Upload a file via an `<input type="file">` element. Needed for workflows like
"upload a configuration file" or "import a CSV."

- Follows the `_WebInteractionTool` pattern: deviation guard, ref resolution,
  step counting, HITL confirmation.
- Accepts a `ref` (must be an `<input type="file">`) and `filename` (the name
  of a file from an allowlisted upload directory).
- File paths are resolved against `GATEWAY_BROWSER_UPLOAD_DIR` (default
  `/tmp/browser-uploads`); only files under this directory are accessible.
- Uses Playwright's `set_input_files()`.

Acceptance criteria:
- `web.upload_file` with a valid file ref and allowlisted filename succeeds.
- `web.upload_file` with a path outside the upload dir returns
  `BROWSER_UPLOAD_PATH_NOT_ALLOWED`.
- `web.upload_file` with a ref that is not `<input type="file">` returns
  `BROWSER_UPLOAD_NOT_A_FILE_INPUT`.
- Write-tier enforcement: requires bound write-class flow, HITL approval.
- Unit test covers success, path traversal attempt, wrong element type.

### R-9: `web.switch_frame` — iframe traversal (read tier)

Switch the page context into an iframe. Some admin panels embed monitoring
dashboards or sub-applications in iframes.

- Read tier: no HITL gate, requires bound flow and origin re-check.
- Accepts a `selector` (CSS selector for the iframe element) or `ref`.
- After switching, subsequent operations target the iframe's document.
- The frame's origin is checked against the flow's bound origin; frames from
  different origins are denied.
- A `web.navigate` call resets back to the main frame.

Acceptance criteria:
- `web.switch_frame` with a valid iframe selector succeeds.
- `web.switch_frame` with a cross-origin iframe returns
  `BROWSER_FRAME_ORIGIN_MISMATCH`.
- `web.switch_frame` with no matching element returns `BROWSER_FRAME_NOT_FOUND`.
- After `web.navigate`, the context returns to the main frame.
- Unit test covers success, cross-origin denial, not-found, reset on navigate.

### R-10: Tool registration and discovery

All nine new tools register with the `ToolRegistry` when the browser connector
is enabled (`GATEWAY_BROWSER_ENABLED=true`). The write-tier tools
(`web.select`, `web.press_key`, `web.upload_file`) are subject to the existing
`GATEWAY_MUTATING_TOOLS_ENABLED` gate.

Acceptance criteria:
- `register_tools` registers all 15 tools (6 existing + 9 new).
- Write-tier tools are absent from the registry when
  `GATEWAY_MUTATING_TOOLS_ENABLED=false`.
- The system prompt tool list includes the new tools with their descriptions.

### R-11: Samples directory structure

Tutorial content lives in a self-contained `samples/` directory at the
repository root. Each sample bundles the artifacts a tutorial reader has to
reason about:

- `skill/` — the skill document(s), installed into a cluster by
  `make deploy-samples`
- `demo/` — standalone demo script(s)
- `README.md` — tutorial walkthrough (plus an optional `WALKTHROUGH.md`)
- `target/` — sample-specific target infrastructure (optional)

Separation principle: the dependency arrow is always **tutorial → platform**.
A sample owns its tutorial-specific artifacts and *references* shared
infrastructure; it never embeds platform internals, and platform GitOps never
names a specific sample. Infrastructure shared with the platform or other
samples — the browser target pages, credential secret, and NetworkPolicy
(also used by the SPEC-049 `browser-check-demo.sh` smoke test) — therefore
stays in `shared/platform-ops/gitops/` and is referenced from the sample.

Sample skills are installed out-of-band, not by `make deploy`: the base
overlay declares one *generic* `samples` local source (an optional
`skills-samples` ConfigMap mounted read-only at `/skills/samples`) that
ingests nothing until `make deploy-samples` packs the selected samples'
`skill/*.md` into it. This keeps tutorials removable leaves with zero
system → tutorial coupling, and avoids duplicating a skill between a deployed
platform copy and a tutorial copy.

Acceptance criteria:
- `samples/web-checks/password-reset/` contains the tutorial-specific pieces
  (skill, demo, README/WALKTHROUGH) and references — not duplicates — the
  shared browser infrastructure.
- `shared/platform-ops/e2e/password-reset-demo.sh` is removed (replaced by
  `samples/web-checks/password-reset/demo/demo.sh`).
- The ResetUserPassword skill has a single home under
  `samples/web-checks/password-reset/skill/`; the former
  `shared/platform-ops/skills/platform-runbooks/web-checks/ResetUserPassword.md`
  copy and its base-overlay ConfigMap/mount wiring are removed.
- `make deploy-samples` installs the skill into the `samples` source
  (`skill_id samples/password-reset-resetuserpassword`) and `make
  undeploy-samples` removes it; the base overlay deploys cleanly with zero
  samples installed.
- `make verify` passes with the new layout.
- The demo script runs successfully from the new location.

### R-12: Backward compatibility

No existing tool behavior changes. The six SPEC-049 tools retain their
signatures, risk tiers, and enforcement. The new tools are additive.

Acceptance criteria:
- All existing `test_browser_connector.py` tests pass unchanged.
- `browser-check-demo.sh` passes with no modifications.
- The password-reset demo script works from its new location.

## Design Notes

### D-1: Read-tier tools use `gate_capture`, not `gate_interaction`

The read-tier tools (`web.extract`, `web.wait_for`, `web.hover`,
`web.evaluate`, `web.scroll`, `web.switch_frame`) perform captures or
observations, not mutations. They use `gate_capture` (the same origin re-check
as `web.snapshot` and `web.screenshot`) rather than `gate_interaction` (which
checks flow binding, risk class, and step budget). This is consistent with the
SPEC-049 design where reads don't consume step budget.

Exception: `web.wait_for` can be argued to be a "setup" action that doesn't
consume a step (it waits for the page to reach a state, then the agent takes
an action). It uses `gate_capture` for this reason.

### D-2: Write-tier tools inherit `_WebInteractionTool`

The write-tier tools (`web.select`, `web.press_key`, `web.upload_file`) extend
`_WebInteractionTool` and inherit the deviation guard, ref resolution, step
counting, and HITL confirmation flow. This is the same pattern as `web.click`
and `web.type`.

### D-3: `web.evaluate` result bounding

JavaScript evaluation is a powerful escape hatch but carries risk: a malicious
or careless expression could return gigabytes of data. The result is bounded:
- Max 16000 chars (same as `SNAPSHOT_MAX_CHARS`).
- Max 100 array elements (arrays beyond this are truncated with a note).
- Non-serializable values (functions, symbols, circular refs) return an error.

The expression itself is not sandboxed beyond the page's own origin — the
deviation guard ensures the page is on the flow's allowed origin, so the
expression runs in a context the operator already approved.

### D-4: `web.upload_file` path allowlisting

File uploads are a vector for path traversal attacks. The tool resolves the
filename against `GATEWAY_BROWSER_UPLOAD_DIR` and denies any path that escapes
it (including `../` segments, symlinks to outside, etc.). The upload directory
defaults to `/tmp/browser-uploads` and is operator-configurable.

### D-5: `web.switch_frame` origin check

Frames can load content from different origins. The tool checks the frame's
origin against the flow's bound origin and denies cross-origin frames. This
prevents a flow bound to `https://admin.internal` from interacting with an
iframe loaded from `https://ads.external.com`.

### D-6: Tool count and system prompt

With 15 browser tools, the system prompt's tool list grows. The descriptions
should be concise (one line each) and grouped by tier. The agent-platform's
system prompt builder already handles this for other tool categories.

## Tasks

### t1: Implement `web.select` tool

- Add `WebSelectTool` class extending `_WebInteractionTool`.
- Implement `select_option()` with value/label matching.
- Add error codes: `BROWSER_SELECT_NOT_A_SELECT`,
  `BROWSER_SELECT_OPTION_NOT_FOUND`.
- Register in `BrowserConnector.register_tools`.
- Unit tests.

### t2: Implement `web.extract` tool

- Add `WebExtractTool` class extending `BaseTool`.
- Implement CSS selector query, table extraction, list extraction.
- Add result bounding (max_rows, max_cols, cell truncation).
- Use `gate_capture` for origin re-check.
- Unit tests.

### t3: Implement `web.wait_for` tool

- Add `WebWaitForTool` class extending `BaseTool`.
- Implement `wait_for_selector()` with state and timeout.
- Add timeout cap (30000ms).
- Use `gate_capture` for origin re-check.
- Unit tests.

### t4: Implement `web.press_key` tool

- Add `WebPressKeyTool` class extending `_WebInteractionTool`.
- Implement `keyboard.press()` with optional ref focus.
- Register in `BrowserConnector.register_tools`.
- Unit tests.

### t5: Implement `web.hover` tool

- Add `WebHoverTool` class extending `BaseTool`.
- Implement `hover()` on resolved element handle.
- Use `gate_capture` for origin re-check.
- Unit tests.

### t6: Implement `web.evaluate` tool

- Add `WebEvaluateTool` class extending `BaseTool`.
- Implement `page.evaluate()` with result serialization and bounding.
- Add error codes: `BROWSER_EVAL_NOT_SERIALIZABLE`,
  `BROWSER_EVAL_RESULT_TOO_LARGE`.
- Use `gate_capture` for origin re-check.
- Unit tests.

### t7: Implement `web.scroll` tool

- Add `WebScrollTool` class extending `BaseTool`.
- Implement `mouse.wheel()` with delta parameters.
- Use `gate_capture` for origin re-check.
- Unit tests.

### t8: Implement `web.upload_file` tool

- Add `WebUploadFileTool` class extending `_WebInteractionTool`.
- Implement `set_input_files()` with path allowlisting.
- Add `GATEWAY_BROWSER_UPLOAD_DIR` config.
- Add error codes: `BROWSER_UPLOAD_PATH_NOT_ALLOWED`,
  `BROWSER_UPLOAD_NOT_A_FILE_INPUT`.
- Register in `BrowserConnector.register_tools`.
- Unit tests.

### t9: Implement `web.switch_frame` tool

- Add `WebSwitchFrameTool` class extending `BaseTool`.
- Implement frame traversal with origin check.
- Add frame tracking to `BrowserSessionEntry`.
- Reset to main frame on `web.navigate`.
- Use `gate_capture` for origin re-check.
- Unit tests.

### t10: Update FakePage/FakeElementHandle for new tools

- Add `select_option()`, `hover()`, `press()`, `set_input_files()`,
  `wait_for_selector()`, `evaluate()` (for general JS), `mouse.wheel()`
  to the fake Playwright layer.
- Update existing tests to cover the new fake methods.

### t11: Create `samples/` directory structure

- Create `samples/web-checks/password-reset/` with `skill/`, `demo/`, and docs.
- Single-source `ResetUserPassword.md` into `samples/.../skill/`, reconciled to
  the richer v1.1 content (it is tutorial-specific, not a platform runbook).
- Move the demo script to `samples/.../demo/demo.sh`.
- Write `samples/.../README.md` (+ `WALKTHROUGH.md`) tutorial walkthrough.
- Leave shared browser infrastructure (admin target pages, credential secret,
  NetworkPolicy) in `shared/platform-ops/gitops/`; the sample references it.

### t12: Update references and clean up old locations

- Remove `shared/platform-ops/e2e/password-reset-demo.sh` (superseded by the
  samples demo).
- Remove `shared/platform-ops/skills/.../web-checks/ResetUserPassword.md` and
  drop its entries from the base `kustomization.yaml` ConfigMap generator and
  the `skills-hub-deployment.yaml` volume items.
- Add a generic `samples` local source to skills-hub: an optional
  `skills-samples` ConfigMap mounted at `/skills/samples` plus a `samples`
  entry in `SKILLS_SOURCES`. The base names no specific sample.
- Add `make deploy-samples` / `make undeploy-samples` (via
  `samples/deploy-samples.sh`) to install/remove sample skills out-of-band.
- Keep `sync-browser-credentials.sh`, `browser-check-target-deployment.yaml`,
  and `browser-sidecar-network-policy.yaml` in platform space (shared with the
  SPEC-049 smoke test); the sample references them.

### t13: Update `make verify` and demo scripts

- Ensure `make verify` passes with new layout.
- Ensure `browser-check-demo.sh` still passes (assertions unchanged).
- Ensure `samples/.../demo.sh` runs from its new location after
  `make deploy-samples` (its skill-ingestion leg reads `/skills/samples/`).
- Update any CI scripts that reference old paths.

### t14: Update documentation

- Update `CHANGELOG.md` with v0.32.0 entry.
- Update `docs/specs/` index with SPEC-050.
- Update browser tool documentation (if any) with new tools.
- Update `samples/README.md` with overview of available samples.

## Acceptance Criteria Summary

- All 9 new tools implemented with correct tier assignment.
- Write-tier tools (`web.select`, `web.press_key`, `web.upload_file`) require
  HITL confirmation and consume step budget.
- Read-tier tools use `gate_capture` for origin re-check.
- All tools respect the origin allowlist and flow-binding enforcement.
- `samples/web-checks/password-reset/` is self-contained and documented.
- Old scattered locations are cleaned up.
- `make verify` passes (existing tests + new tool tests).
- Both demo scripts (`browser-check-demo.sh`, `samples/.../demo.sh`) pass.
