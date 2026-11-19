# SPEC-079 Plan: Permissions matrix transpose (roles across the top, permissions down the first column)

> **BINDING** — approved 2026-11-18. The operator ratified all three Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the design below is binding and the provisional
> banner is lifted (the SPEC-066/069/076/077/078 pattern). Approval authorizes implementation to
> *begin* — **not** to merge, commit/push, deploy, or version-bump (separate gates). This is a
> **small, purely presentational** operator-portal change: **no** backend, gateway, policy, contract,
> schema, or authorization-model change. Release reconciliation 2026-11-19: v0.60.0 already shipped
> with SPEC-078; SPEC-079 targets a subsequent release, with its version chosen at the release gate.

## Approach

Transpose the rendering in
`products/operator-portal/web-ui/app/src/views/control/PermissionsView.tsx` and change nothing else.
The `GET /api/v1/policy/matrix` request, its payload shape, the server-side row-scoping, and the
`policy:read` gate are untouched; the view simply addresses the same payload by **(row = action,
column = role)** instead of **(row = role, column = action)**. All three cell states (`allow` / `deny`
/ `require_approval` with the tier + deciders tooltip, SPEC-030 R-5) render identically. The work is
three small stages mirroring R-1…R-3.

## Design Per Requirement

### R-1: Transpose the rendered orientation (permissions as rows, roles as columns)

- affected file: `PermissionsView.tsx` only.
- chosen approach:
  - `dataSource` becomes the actions (`actions.map((action) => ({ action }))`); `rowKey="action"`.
  - the first column is the permission name, `fixed: "left"`, header **`permission`** (OQ-1).
  - the remaining columns are the roles: `...roles.map((role) => ({ title: role, key: role, render }))`.
  - each role column's `render(_, row: { action: string })` resolves the **same** lookups as today —
    `approval_requirements[role][row.action]` for the require_approval state, else
    `matrix[role][row.action]` for allow/deny — so the cell semantics are unchanged.
  - the footer re-orders to `{actions} permissions × {roles} roles · evaluated from the enforced
    bundle` (OQ-1); the page title and the bundle-version line stay.
  - scroll (OQ-2): drop the forced `scroll={{ x: "max-content" }}` and let the long permission list
    scroll **with the page**. Note the antd constraint that a `fixed` column normally wants a `scroll`
    prop — keep the permission column `fixed: "left"` and, if antd needs a `scroll` to honor it, use a
    bounded `scroll={{ y: … }}` (fixed-height body, page still scrolls) rather than re-introducing a
    forced horizontal `x`; with only a handful of role columns the table should not overflow
    horizontally. The test asserts the first-column labels stay visible.
- alternatives rejected: transposing server-side (the payload is unchanged and other consumers rely on
  its shape); keeping roles-as-rows with a wider scroll (that is the papercut the operator raised).

### R-2: Preserve semantics, scoping, and the payload contract (presentational only)

- affected files: none beyond the component's render path.
- chosen approach: the `useEffect` fetch of `GET /api/v1/policy/matrix`, the `PolicyMatrixPayload`
  interface, and the `ApprovalRequirement` interface stay **byte-identical**; only the `columns` /
  `dataSource` construction changes. A scoped caller (non-`platform-admin`) still receives only their
  own roles from the gateway, now rendered as a subset of the columns — **no** client-side scoping is
  added. No backend, gateway, policy, schema, or contract artifact is touched.
- alternatives rejected: any change to the endpoint, payload, or scoping (out of scope — this is a
  presentational transpose).

### R-3: Tests + living docs

- affected files: a **new**
  `products/operator-portal/web-ui/app/src/views/control/__tests__/PermissionsView.test.tsx`
  (absent at approval), mirroring the sibling control-view tests (`ApprovalsView.test.tsx`,
  `SettingsView.test.tsx`, `SkillsView.test.tsx`); `docs/specs/README.md` (this row), `CHANGELOG.md`,
  and the four living surfaces with roles-as-rows wording (portal README; portal-user-guide,
  user-and-role-administration, and architecture-overview).
- chosen approach: mock `requestJson` from `../../../api/client` to return a small fixed
  `PolicyMatrixPayload` (a few roles × a few actions, including one `allow`, one `deny`, and one
  `require_approval` with `decided_by_roles`), shim `window.matchMedia` (antd probes it), render
  `<PermissionsView />`, and assert: (a) each **role** appears as a **column header**; (b) each
  **action** appears in the **first column** as a row label; (c) all three cell states render (`allow`
  / `deny` / the `self-approval` or `approver required` tag with the deciders tooltip); (d) the footer
  reads `{actions} permissions × {roles} roles`. Sweep the guides for any orientation claim (none found
  in `authorization-matrix.md`).
- alternatives rejected: leaving the view untested (every sibling control view has a test, and the
  transpose is exactly what a DOM assertion guards).

## Sequencing And Dependencies

1. **Stage 1 — transpose the component (R-1, R-2)** — swap `columns`/`dataSource`, keep the fetch +
   payload + cell lookups unchanged, drop the forced horizontal scroll. Depends on nothing.
2. **Stage 2 — the test (R-3)** — add `PermissionsView.test.tsx` asserting the transposed orientation +
   the three cell states + the footer. Depends on Stage 1.
3. **Stage 3 — docs + verify (R-3)** — the spec-index row, `CHANGELOG.md`, and `make verify` (portal
   suite) green. Depends on Stages 1–2.

## Test Strategy

- DOM/unit: the transposed orientation (roles as column headers, permissions as first-column rows), the
  three cell states, and the footer wording, via `PermissionsView.test.tsx` with a mocked `requestJson`
  payload.
- regression: the operator-portal suite stays green; root `make verify` green (the portal leg).
- manual/live (optional, at the operator's discretion): reload the Permissions page on the local cluster
  and confirm the transposed layout reads well with the full action list.

## Rollout And Migration

- portal-only, presentational: **no** migration, **no** config knob, **no** contract or policy change.
- rollback: revert `PermissionsView.tsx` (and its test) to the roles-as-rows orientation; nothing else is
  affected.
- release: a subsequent release after **v0.60.0**, which already shipped with SPEC-078. The exact
  version, `VERSION` bump, and spec-index `delivered` flip remain separate release-gate decisions;
  the original shared-train target is superseded for scheduling only (2026-11-19).
