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
- [ ] Complete deployed horizontal-overflow and wide-viewport verification. Initial fixture
      screenshot/interaction checks were incomplete: browser capture was blocked
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
pending horizontal-overflow/wide-viewport check above or the separate version/release gates below.

### Correction handoff and deployed verification

- [x] Correction `b046f143` committed and pushed after the authorized L3 security review passed.
      All nine product images and the sample application rebuilt at `0.60.0-dev-k8s-b046f143`.
      The initial deploy stopped on a same-second `tool-gateway` rollout-restart collision after
      applying the Ansible credential Secrets. Resuming the missing restarts and remaining stages
      completed deployment; sample checks passed, all 15 pods were Ready, and gateway/agent health
      returned 200. This was a recovered deployment, not a clean initial `make deploy` exit.
- [x] Subsequently authorized OpenObserve credential provisioning from the namespace Secret
      completed for all eight Python services; authenticated streams API returned 200 and all
      15 pods remained Ready. This proves configuration and API authentication, not end-to-end
      telemetry ingestion. No credential values were printed or recorded here.
- [x] Deployed authenticated browser check after manual sign-in (2026-11-21): `luban-admin`,
      `platform-admin`, full scope; expected assets `index-CMis_fPs.js` and `index-B4S1aXRs.css`.
      Actual viewport **945 × 535 CSS pixels**, DPR 2. Confirmed 27 permissions × six roles,
      allow/deny/approval colors, and hover tooltip `deciders: approver, platform-admin`.
      Real Tab focused the named matrix region with a visible cyan 2px outline. Page-level vertical
      scrolling reached the final row and footer; no fixed-height table body. No console errors or
      warnings; the matrix GET and subsequent observed requests returned 200.
      Document client/scroll width was 945/945px, main 881/881px, matrix 833/833px. Main height was
      535/1286px and bottom scrollTop 750.5px; matrix height was 1150/1151px with no max-height.
      Evidence: `.qoder/spec079-fix-deployed-narrow-left.png`,
      `.qoder/spec079-fix-deployed-focus.png`, `.qoder/spec079-fix-deployed-tooltip.png`, and
      `.qoder/spec079-fix-deployed-footer.png`. These are actual 945px captures despite the
      historical `narrow-left` filename; no 830px viewport is claimed.
- [ ] Verify horizontal keyboard scrolling, pinned permission column, and stationary page chrome
      during actual matrix overflow, plus a genuine wide viewport. The matrix fit at 945px, so
      ArrowRight/Left left scrollLeft at zero; unchanged x positions do not prove containment.
      Browser resize requests did not change the actual viewport. Opening navigation produced a
      260px overlay drawer, not narrower content; matrix width stayed 833px. The `narrow-right-attempt`
      and `expanded-left` screenshots document these limits, not successful horizontal scrolling.
      Earlier local-fixture geometry remains separate evidence. Other deployed role scopes were
      not tested. The authenticated session was preserved; no model requests, mutations, or
      production DOM/CSS fixtures were used. Full visual verification remains open.
      A further operator-ready retry still measured 945 × 535 and matrix width 833/833px;
      ArrowRight left scrollLeft at zero. Genuine keyboard focus and ordinary footer reach passed
      again (`.qoder/spec079-fix-deployed-resized-focus.png` and
      `.qoder/spec079-fix-deployed-resized-footer.png`), but these filenames do not imply a changed
      viewport. Page-specific browser zoom was unavailable; no global IDE zoom or settings were
      changed. No console messages were observed; all 102 recorded requests returned 200.

### Duplicate vertical scrollbar follow-up

- [x] Reproduced the operator-reported nested vertical scrolling. The earlier 1px range was a
      defect, not harmless rounding: Ant's `.ant-table-container::after` has `bottom: -1px`,
      extending its generated box below the borderless table. `overflow-x: auto` makes the
      matrix's Y overflow compute to `auto`. The first PageDown moved the matrix 0→1px while
      the page stayed at zero; only the second PageDown moved the page. Ordinary footer reach
      therefore did not prove the intended single vertical scroll owner.
- [x] Scoped `bottom: 0` to both table-container shadow pseudo-elements inside
      `.permissions-matrix-scroll`. No scrollbar hiding, height constraint, table markup,
      payload, authorization, or shared-table change. New CSS-rule regression failed before
      the fix (one failed, ten passed). The first post-fix run exposed CSSOM's `0px` normalization;
      corrected the assertion from `0` to `0px`, then the complete gate passed.
- [x] Final affected-scope gate: **557 tests across 41 files**, TypeScript, Vite build, docs-check,
      and version lockstep passed. All eleven matrix tests pass. Backend root-gate evidence
      remains historical; no new full-root run or release/version change is claimed.
- [x] Browser A/B diagnostic using the exact temporary CSS rule at 945 × 535: matrix
      client/scroll height changed 1150/1151→1150/1150px. Real Tab focus remained visible;
      the first PageDown moved the page 0→515px while matrix scrollTop stayed zero. Subsequent
      PageDown reached the final row/footer. This confirms removal of the matrix's extra range,
      not all document/body geometric excess. Both scrollbar thumbs were not visible in captures.
- [x] Separate synthetic-width diagnostic: temporarily constrained only the matrix to 720px,
      giving 830px scroll width. Real ArrowRight/Left moved 0→40→0px and reached the 110px
      rightmost offset. All first-column cells, title, metadata, and footer stayed at x=88px;
      main/document had no horizontal overflow and the matrix had no vertical range. Actual
      browser viewport remained 945 × 535; this is not responsive-viewport acceptance.
      Labeled evidence: `.qoder/spec079-shadow-fix-diagnostic-focus.png`,
      `.qoder/spec079-shadow-fix-diagnostic-footer.png`, and
      `.qoder/spec079-shadow-fix-diagnostic-right.png`. All temporary CSS/labels were removed
      and original scroll/focus restored; the deployed baseline was remeasured unchanged.
- [x] Commit and redeploy the shadow correction: `58a5a473`, with L3 security review passed.
      After terminal-dispatch and Docker sandbox failures were resolved, all nine product images
      built at `0.60.0-dev-k8s-58a5a473`; product/sample deployment and sample assertions passed.
      All 15 namespace pods were Ready; gateway/agent health returned 200. OpenObserve credential
      provisioning completed for eight services without exposing credentials. No Git push,
      version bump, release tag, or delivered-status change occurred in this handoff.
- [x] Authenticated check of the unmodified deployed shadow correction at **945 × 535**:
      assets `index-ITcYrYZh.js` / `index-kD13PatA.css`; matrix height **1150/1150px** and
      width **833/833px**, pseudo-element bottoms `0px`. First PageDown moved main scrollTop
      **0→515px**, then **750.5px** at the final row/footer; matrix/document remained at zero.
      Visible 2px focus outline and approval tooltip passed. No relevant console errors/warnings;
      observed requests returned 200. Evidence: `.qoder/spec079-shadow-deployed-focus.png` and
      `.qoder/spec079-shadow-deployed-footer.png`. The matrix fit at this actual viewport, so
      genuine narrow/wide horizontal-overflow acceptance remains open.
      **Separate defect:** focusing sidebar Sign out moved document scrollTop **0→80px**
      (document height 535/615px). The matrix fix did not resolve sidebar content overflow.

### Sidebar focus-containment follow-up (operator authorized 2026-11-21)

- [x] Bound shared `SidebarContent` in `App.tsx` to the available height. Keep the brand/spacer
      outside a named `Primary navigation` region containing the menu and account controls.
      Scoped CSS gives this region shrinkable vertical scrolling and prevents menu/footer
      shrinkage. The inline expanded/collapsed sidebar and Drawer reuse the same structure;
      main content and matrix scrolling stay separate. Role gates, authentication handlers,
      navigation behavior, backend, policy, and payloads are unchanged.
- [x] Six failure-first cases in `App.studio.test.tsx`: expanded/collapsed × signed-in/out,
      Drawer containment/navigation close, and authentication-error placement. All six failed
      before the fix while the existing 25 passed; all 31 passed afterward. Tests load the real
      CSS and assert structure, focusability, and scroll rules; jsdom does not prove geometry.
- [x] Affected-scope verification before the final assertion refinement: **563 tests across
      41 files**, TypeScript, Vite production build, docs-check, version lockstep, and whitespace
      checks passed. No new full-root backend run is claimed; version remains **0.60.0**.
- [x] Isolated local fixture used the real App/bootstrap/theme with mocked identity and read-only
      API responses, not the deployed portal. Actual iframe CSS viewports were **390×535,
      830×535, 945×535, 1440×800, and 1440×320**. Document/body/root had zero scroll ranges;
      programmatic Sign out focus moved only navigation (80px at the three narrow sizes,
      322px at 1440×320, zero at 1440×800), leaving document and main scroll positions unchanged.
      Narrow Drawer DOM checks likewise moved only its navigation (164px). Matrix Y range was
      zero throughout. No auth control was activated and no model/remediation calls were made.
- [ ] Complete visible real-keyboard and settled narrow/wide acceptance. The native browser view
      was hidden/detached, preventing screenshots and real-keypress proof. Transitions stayed
      frozen: narrow Sider state/inline width was collapsed/64px but rendered width remained
      230px; the Drawer stayed translated offscreen. Programmatic matrix scrolling preserved
      the first-column x position at 830/945px, but not at 390px where the frozen sidebar left
      only 112px for the matrix. These measurements are **partial DOM evidence**, not a responsive
      pass or proof of a settled-production defect. No new sidebar screenshots were captured.
      Live portal and Kubernetes API checks returned connection refused during this follow-up;
      earlier deployment health is historical, not current availability. Infrastructure/IDE
      recovery was not attempted. Temporary fixture data was cleared and its HTML file removed.
- [x] Final affected-scope recheck after strengthening the main-content exclusion assertion:
      **563 tests across 41 files**, TypeScript/Vite build, docs-check, version lockstep, and
      whitespace checks passed. The first attempt passed all assertions but exited on the
      previously observed React/jsdom `window is not defined` teardown error (reported from
      `DraftAsSkillButton.test.tsx`); an unchanged full rerun passed. No shared test setup change.
- [x] Code/doc review of the seven-file sidebar follow-up completed with **no blocking findings**.
      Review confirmed scroll boundaries, unchanged auth/role/navigation behavior, regression
      coverage, and explicit evidence limits. Local commit is authorized. A new push/redeploy,
      release/version change, and deployed sidebar verification remain separate gates outside
      this authorization.
- [x] Temporary fixture cleanup complete: session data cleared, HTML removed, owned Vite server
      stopped, and no listener remains on localhost:5173. Shutdown required a background retry
      after terminal-dispatch failures; no unrelated process or service was stopped.

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
- [x] spec index and spec status set to `delivered` at the separate release gate, version-stamped
      with the subsequent release selected by the operator (not the already-shipped v0.60.0)
- [x] version selected and bumped at the separate release gate (`VERSION` + products + portal
      lockstep, proven by `validate-version`); no version bump authorized by implementation approval
