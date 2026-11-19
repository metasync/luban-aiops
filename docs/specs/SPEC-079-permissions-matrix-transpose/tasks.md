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
