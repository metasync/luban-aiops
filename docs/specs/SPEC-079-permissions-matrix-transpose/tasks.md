# SPEC-079 Tasks: Permissions matrix transpose (roles across the top, permissions down the first column)

> **BINDING** — approved 2026-11-18. The operator ratified all three Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the tasks below are binding and the provisional
> banner is lifted. Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
> This is a **small, purely presentational** operator-portal change — **no** backend, gateway, policy,
> contract, schema, or authorization-model change; the `GET /api/v1/policy/matrix` payload, server-side
> row-scoping, `policy:read` gate, and the three cell states are preserved.

## R-1: Transpose the rendered orientation

- [x] In `PermissionsView.tsx`, set `dataSource={actions.map((action) => ({ action }))}` and
      `rowKey="action"`
- [x] Make the first column the permission name — `fixed: "left"`, header `permission` (OQ-1)
- [x] Build the remaining columns from `roles.map((role) => ({ title: role, key: role, render }))`
- [x] Drop the forced `scroll={{ x: "max-content" }}`; let the long permission list scroll with the page
      (OQ-2). No bounded body scroll or pagination added; the 40-row DOM fixture retains every label.
- [x] Re-order the footer to `{actions} permissions × {roles} roles · evaluated from the enforced bundle`
      (OQ-1); keep the page title + bundle-version line and existing singular `role` wording
- [x] Update the component header comment to describe the transposed orientation

## R-2: Preserve semantics, scoping, and the payload contract

- [x] Each role column's `render(_, row: { action })` resolves the same lookups —
      `approval_requirements[role][row.action]` then `matrix[role][row.action]` — so all three cell states
      (allow/deny/require_approval with the tier label + `deciders:` tooltip) render identically
- [x] Leave the `useEffect` fetch, `PolicyMatrixPayload`, and `ApprovalRequirement` interfaces
      byte-unchanged; add **no** client-side scoping (columns stay server-scoped)
- [x] Confirm **no** backend, gateway, policy, schema, or contract artifact is touched by SPEC-079
      (the separately committed SPEC-078 parking correction, `b98de18d`, is not part of this change)

## R-3: Tests + living docs

- [x] Add `views/control/__tests__/PermissionsView.test.tsx`, mirroring
      `ApprovalsView.test.tsx`: mock `requestJson` (`../../../api/client`) with a small payload (allow +
      deny + require_approval cells), reuse the shared `window.matchMedia` shim, `cleanup()` in `afterEach`
- [x] Assert: roles render as column headers; actions render as first-column row labels; all three cell
      states render (incl. both tier labels and deciders tooltips); the footer matches the visual order.
      **Failure-first: 5 failed / 4 passed** before the transpose; **9 passed** afterward. Also covers
      exact cell coordinates/colors, server-scoped columns, absent approval metadata, 40 permission
      rows without pagination/forced x-scroll, empty data, and 403/502 error display.
- [x] Docs: `docs/specs/README.md` index (in-progress) + `CHANGELOG.md` Unreleased entry;
      corrected four living surfaces: portal README, portal-user-guide, user-and-role-administration,
      and architecture-overview. No orientation change needed in authorization-matrix.md.
- [x] Updated operator-portal suite and production build green: `make portal-test` — **555 passed**
      across 41 files, including the nine new cases; `tsc --noEmit` and Vite build passed.
      The first build caught an unsupported `getByRole` `exact` option in the new test helper;
      removed it (string names already match exactly) and reran the whole portal gate successfully.
- [x] `make docs-check validate-version` and staged/unstaged `git diff --check` passed.
      Version remains **0.60.0**; existing frozen-spec link/version warnings are nonfatal.
- [x] Root `make verify` green (2026-11-19): every leg passed; the final execution-failure campaign
      finished **795 passed, 2 deselected, exit 0** in **0:45:17** (complete root run **50m33s**).
      Its portal leg ran before SPEC-079: **546 passed** + build. The separate **555-test** portal
      gate above covers the final SPEC-079 code; unchanged backend legs were not restarted.
      At the implementation gate, browser geometry was not verified and the optional live/manual
      check had not run; subsequent local deployment and browser verification are now authorized.
- [x] Operator-requested code and documentation review passed with no blocking findings across
      SPEC-079 and the separate parking correction `b98de18d`. The review confirmed scope,
      semantics, regression coverage, and living-doc accuracy. It retained two evidence limits:
      browser geometry awaits the post-deploy check; the earlier paid parking run was not a clean
      end-to-end harness exit (its card was subsequently safely denied/deleted).

The operator authorized commit/push, local rebuild/redeploy, and then browser visual verification
following a clear review. Version bump and the `delivered` release closure remain separate gates.

### Authorized handoff progress

- [x] Code/doc review and L3 security review passed; parking correction `b98de18d` and
      SPEC-079 `d32f79b0` committed and pushed to `origin/main`.
- [x] Coordinated build completed: all nine product images and `.images.env` use
      `0.60.0-dev-k8s-d32f79b0` (no version bump).
- [x] `make deploy` completed with exit 0, including final realm and browser-client reconciliation.
      OpenObserve credential provisioning was skipped because bootstrap credentials were absent.
- [x] Complete `make deploy-sample-app` and final cluster health verification. Initial follow-up
      hit Kubernetes TLS/Docker timeouts; the operator authorized an OrbStack restart. All 15
      namespace pods recovered to Ready; the sample deploy then exited 0 with health, authentication,
      credential-set, and network-policy checks passing. Product/sample images match the built tag.
- [x] Browser visual check performed using the operator-authenticated `luban-admin` session
      (`platform-admin`, full scope), at 830 × 535 CSS pixels. Confirmed 27 permission rows,
      six role columns, allow/deny/approval colors, `deciders: approver, platform-admin` tooltip,
      and `27 permissions × 6 roles` footer. No console warnings/errors; all 24 observed fetch/XHR
      requests returned 200. Preserved the signed-in session; no chat/model or mutation actions.
      Local evidence: `.qoder/spec079-permissions-viewport.png`,
      `.qoder/spec079-permissions-approval-tooltip-footer.png`, and
      `.qoder/spec079-permissions-bottom-right.png`.
      **Visual concern:** at this width the observer column is initially offscreen. Horizontal
      scrolling (88 px) reveals it and keeps the permission column pinned, but scrolls the whole
      content region, clipping the heading/footer on the left. This is not a clean visual pass.
      Other role scopes and wider viewports remain untested; browser resizing was unavailable.
      The full-page screenshot does not capture the entire internally scrolling matrix.

### Narrow-layout correction (operator authorized 2026-11-20)

- [x] Wrap only the matrix in a named, focusable region. Scoped `overflow-x: auto` and
      `max-width: 100%` keep the heading, metadata, and footer out of horizontal scrolling.
      Preserve `fixed: "left"`, natural table width, page-level vertical scrolling, and all data paths.
- [x] Failure-first regression: the new region test failed with the nine existing cases passing;
      after the fix all ten pass. It checks keyboard focusability, chrome outside the region,
      the real CSS containment rules, and absence of a fixed-height table body.
- [x] Final `make portal-test docs-check validate-version` and `git diff --check` passed:
      **556 tests across 41 files**, including all ten matrix cases with the final CSS-rule assertions;
      TypeScript and Vite production build passed. Docs remain link-clean; version remains 0.60.0.
      The first run had all assertions passing but exited on the existing React/jsdom
      `window is not defined` teardown race; subsequent full runs passed without changing shared
      test setup. CSS is read directly because Vitest stubs CSS imports, including query imports.
- [x] Local browser fixture measurements: real component/theme/CSS, six roles and 36 actions
      (including four synthetic long labels), 845 × 535 viewport. Main client/scroll width both
      781px; matrix 733px client / 900px scroll width. Horizontal scrolling reached the last role
      while the permission column, heading, and footer stayed at x=88px. No production DOM,
      authentication, or deployment changes were used for the fixture.
- [ ] Complete screenshot/interaction and wide-viewport verification. Browser capture was blocked
      by a hidden/detached view; hover timed out and arrow-key scrolling was inconclusive. The
      wrapper had a 1px vertical scroll range despite no imposed height; main-page vertical range
      was 1106px, but bottom reach was not verified. This is partial geometry evidence, not a full
      visual pass or a deployed-fix check.
      Operator-requested full visual retry on 2026-11-20 remained blocked, including after the
      operator opened/focused the Browser view and confirmed readiness. Screenshot capture still
      returned `NATIVE_BROWSER_VIEWPORT_UNAVAILABLE` (`visible=false`, `attached=false`,
      `visibilityState=hidden`) after supported page activation. No new screenshots or layout/
      interaction results were obtained; the production page and signed-in session were unchanged.
- [x] Reconcile the spec/plan narrow-width assumption, operator guide, and Unreleased changelog.
      Version and release closure are unchanged.
- [x] Pre-handoff recheck (2026-11-20): **556 tests across 41 files**, TypeScript, Vite build,
      docs-check, and version lockstep passed again. The unchanged backend retains the full
      2026-11-19 root-gate evidence above; this is affected-scope re-verification, not a new full run.
      A first retry was terminated by the terminal tool's one-second execution timeout; the
      complete rerun passed with a sufficient timeout and no code changes.

The operator subsequently authorized committing/pushing this correction, a coordinated local
rebuild/redeploy, and renewed browser testing (2026-11-20). This authorization does not close the
pending screenshot/interaction check above or the separate version/release gates below.

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-3):
      R-1 → exact headers/row-key/cell coordinates, footer, and 40-row DOM cases;
      R-2 → request equality, scoped-role columns, all cell colors/tier tooltips, boolean fallback,
      and render-only diff confirming unchanged fetch/interfaces/backend;
      R-3 → the nine regression cases, green portal/root gates, and reconciled living docs.
- [x] all three Open Questions ratified by the operator **exactly as recommended** (2026-11-18); the
      `plan.md` / `tasks.md` PROVISIONAL banners lifted (binding). Release scheduling superseded
      2026-11-19 only: v0.60.0 already shipped, so a subsequent release is required.
- [x] confirm: the `GET /api/v1/policy/matrix` request/payload is byte-unchanged; server-side row-scoping
      and the `policy:read` gate are unchanged; the three cell states render identically; **no**
      backend/gateway/policy/schema/contract change; the transpose is presentational only
- [x] living docs updated; `CHANGELOG.md` entry added referencing SPEC-079
- [ ] spec index and spec status set to `delivered` at the separate release gate, version-stamped
      with the subsequent release selected by the operator (not the already-shipped v0.60.0)
- [ ] version selected and bumped at the separate release gate (`VERSION` + products + portal
      lockstep, proven by `validate-version`); no version bump authorized by implementation approval
