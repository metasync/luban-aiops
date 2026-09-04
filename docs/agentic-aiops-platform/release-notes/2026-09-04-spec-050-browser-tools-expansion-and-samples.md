# SPEC-050: Browser Tools Expansion and Samples Reorganization (v0.32.0)

**Date:** 2026-09-04
**Slice:** R5 — Hardening and External Consumption (twelfth R5 slice)
**Spec:** `docs/specs/SPEC-050-browser-tools-expansion-and-samples/`

## What shipped

SPEC-049 gave the agent a six-tool browser surface covering the
login-and-inspect happy path (navigate, snapshot, screenshot,
fill_credential, click, type). Real admin panels and dashboards need
more than that: they use `<select>` dropdowns, load data asynchronously,
hide actions behind hover menus, embed sub-applications in iframes, and
occasionally expose state only reachable through JavaScript. SPEC-050
expands the surface by nine tools to cover those interactions — every one
inheriting the SPEC-049 server-side guards (origin allowlist, flow
binding, deviation guard, HITL gate, credential masking) — and
reorganizes the tutorial demo content into a self-contained top-level
`samples/` tree:

1. **Nine new `web.*` tools (R-1…R-9).** The surface grows from six to
   fifteen tools. Four are write tier and inherit the
   `_WebInteractionTool` pattern (deviation guard, ref resolution, step
   counting, HITL confirmation via the existing SPEC-020/037 path):
   `web.select` (dropdown selection by snapshot ref, value or label),
   `web.press_key` (keyboard key or combination with optional element
   focus), `web.upload_file` (file input upload), and `web.evaluate`
   (JavaScript evaluation). Five are read tier and use the `gate_capture`
   origin re-check without consuming step budget: `web.extract`
   (structured table/list data by CSS selector), `web.wait_for` (element
   state wait — attached/detached/visible/hidden), `web.hover` (reveal
   tooltips and menus), `web.scroll` (pixel-delta wheel scroll), and
   `web.switch_frame` (iframe traversal).
2. **Bounded, gated JavaScript evaluation (R-6, D-3).** `web.evaluate`
   is the escape hatch for data the accessibility tree does not capture
   (chart data, computed state). Because arbitrary JS can mutate the DOM
   and read back masked credential values, it is **write tier**: every
   call parks for HITL confirmation, is never auto-allowed, and still
   rides the origin allowlist and flow-origin re-check. Results are
   bounded (16 000 chars, 100 array elements, non-serializable values
   rejected). A pre-execution mutation guard
   (`BROWSER_EVAL_MUTATION_BLOCKED`) rejects known state-changing DOM
   APIs as **defense-in-depth only** — it steers the agent to the
   dedicated ref-addressed write tools, but the HITL gate, not the regex
   denylist, is the security boundary. The expression runs in the page's
   main world, on an origin the operator already approved.
3. **Upload path allowlisting (R-8, D-4).** `web.upload_file` resolves
   the requested filename against `GATEWAY_BROWSER_UPLOAD_DIR` (new
   config knob, default `/tmp/browser-uploads`) and denies any path that
   escapes it (`../` segments, symlinks out) with
   `BROWSER_UPLOAD_PATH_NOT_ALLOWED`; a ref that is not an
   `<input type="file">` returns `BROWSER_UPLOAD_NOT_A_FILE_INPUT`.
4. **Cross-origin frame denial (R-9, D-5).** `web.switch_frame` checks
   the target frame's origin against the flow's bound origin and denies
   cross-origin frames (`BROWSER_FRAME_ORIGIN_MISMATCH`), so a flow bound
   to `https://admin.internal` cannot be steered into an iframe served
   from an external origin. A subsequent `web.navigate` resets the
   context to the main frame; `web.scroll` centers the cursor over the
   active frame before wheeling so the frame, not the top-level page,
   scrolls.
5. **Registration and discovery (R-10).** All fifteen tools register
   with the `ToolRegistry` only when `GATEWAY_BROWSER_ENABLED=true`; the
   four write-tier tools are additionally subject to the existing
   `GATEWAY_MUTATING_TOOLS_ENABLED` gate and are absent from discovery
   when it is off. The agent-platform auto-allow invariant continues to
   pin that the write-class web tools can never satisfy the read-only
   auto-allow contract, even if force-listed.
6. **Self-contained samples tree (R-11).** Tutorial content moves into a
   top-level `samples/` directory under a strict **tutorial → platform**
   dependency arrow: `samples/web-checks/password-reset/` bundles the
   skill document, demo script, README, and WALKTHROUGH, and *references*
   — never duplicates — the shared browser target pages, credential
   secret, and NetworkPolicy that stay in `shared/platform-ops/gitops/`
   (also used by the SPEC-049 `browser-check-demo.sh` smoke test). Sample
   skills install **out-of-band**, not by `make deploy`: the base overlay
   declares one *generic* `samples` local source — an optional
   `skills-samples` ConfigMap mounted read-only at `/skills/samples` —
   that ingests nothing until `make deploy-samples` packs the selected
   samples' `skill/*.md` into it (and `make undeploy-samples` removes
   them). The skill lands as `samples/password-reset-resetuserpassword`,
   keeping tutorials removable leaves with zero system → tutorial
   coupling. The former
   `platform-runbooks/web-checks/ResetUserPassword.md` copy and its
   base-overlay ConfigMap/mount wiring are removed; the base overlay
   deploys cleanly with zero samples installed.
7. **Backward compatibility (R-12).** The six SPEC-049 tools retain their
   signatures, risk tiers, and enforcement; the new tools are purely
   additive. The existing `test_browser_connector.py` suite and
   `browser-check-demo.sh` pass unchanged.

## Validation

- `make verify` green at 0.32.0: all product suites — including the new
  tool-gateway browser-tool tests (select/extract/wait/press/hover/
  evaluate/scroll/upload/switch_frame, the mutation guard, upload path
  traversal, cross-origin frame denial, result bounding) and the
  agent-platform auto-allow invariant — all four overlays (including
  `runtime-profiles/browser-dev`), policy validation, scenario guard, and
  version lockstep.
- Live on the canonical `dev-k8s` deployment: `make deploy-samples`
  packed the password-reset skill into the `skills-samples` ConfigMap,
  the overlay re-apply mounted `/skills/samples`, and skills-hub ingested
  `samples/password-reset-resetuserpassword` (version 1.1, `web_target`
  and `risk_class` present, HTTP 200 on the authenticated query path).
- `samples/web-checks/password-reset/demo/demo.sh` ran all five
  deterministic legs green from its new location against the live
  identity broker; `make undeploy-samples` pruned the skill (query total
  → 0) and a re-deploy restored it (total → 1), confirming the
  out-of-band install/remove lifecycle.

## Parked

The SPEC-049 boundaries still hold and bound this slice: real production
browser pools, multi-step form flows beyond one sign-in gate, and
non-HTML target types remain outside the surface. SPEC-050 adds no
sandboxed JS evaluation context (the expression runs in the page main
world on an operator-approved origin, gated by HITL rather than
isolation), no nested multi-level frame tree beyond the one-level
cross-origin-checked traversal, and no sample-specific platform wiring by
design — the base overlay names no specific sample, and any shared
infrastructure a future sample needs stays in platform space and is
referenced, never embedded.
