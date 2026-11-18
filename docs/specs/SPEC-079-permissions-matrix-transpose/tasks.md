# SPEC-079 Tasks: Permissions matrix transpose (roles across the top, permissions down the first column)

> **BINDING** — approved 2026-11-18. The operator ratified all three Open Questions in
> [`spec.md`](spec.md) **exactly as recommended**, so the tasks below are binding and the provisional
> banner is lifted. Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
> This is a **small, purely presentational** operator-portal change — **no** backend, gateway, policy,
> contract, schema, or authorization-model change; the `GET /api/v1/policy/matrix` payload, server-side
> row-scoping, `policy:read` gate, and the three cell states are preserved.

## R-1: Transpose the rendered orientation

- [ ] In `PermissionsView.tsx`, set `dataSource={actions.map((action) => ({ action }))}` and
      `rowKey="action"`
- [ ] Make the first column the permission name — `fixed: "left"`, header `permission` (OQ-1)
- [ ] Build the remaining columns from `roles.map((role) => ({ title: role, key: role, render }))`
- [ ] Drop the forced `scroll={{ x: "max-content" }}`; let the long permission list scroll with the page
      (OQ-2). If antd needs a `scroll` prop to honor `fixed: "left"`, use a bounded `scroll={{ y: … }}`,
      not a forced horizontal `x`
- [ ] Re-order the footer to `{actions} permissions × {roles} roles · evaluated from the enforced bundle`
      (OQ-1); keep the page title + bundle-version line
- [ ] Update the component header comment to describe the transposed orientation

## R-2: Preserve semantics, scoping, and the payload contract

- [ ] Each role column's `render(_, row: { action })` resolves the same lookups —
      `approval_requirements[role][row.action]` then `matrix[role][row.action]` — so all three cell states
      (allow/deny/require_approval with the tier label + `deciders:` tooltip) render identically
- [ ] Leave the `useEffect` fetch, `PolicyMatrixPayload`, and `ApprovalRequirement` interfaces
      byte-unchanged; add **no** client-side scoping (columns stay server-scoped)
- [ ] Confirm **no** backend, gateway, policy, schema, or contract artifact is touched

## R-3: Tests + living docs

- [ ] Add `views/control/__tests__/PermissionsView.test.tsx` (currently absent), mirroring
      `ApprovalsView.test.tsx`: mock `requestJson` (`../../../api/client`) with a small payload (allow +
      deny + require_approval cells), shim `window.matchMedia`, `cleanup()` in `afterEach`
- [ ] Assert: roles render as column headers; actions render as first-column row labels; all three cell
      states render (incl. the deciders tooltip); the footer reads `{actions} permissions × {roles} roles`
- [ ] Docs: `docs/specs/README.md` index (this row) + `CHANGELOG.md`; sweep the guides for any orientation
      claim (none expected)
- [ ] Operator-portal suite + root `make verify` green

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (R-1…R-3)
- [ ] all three Open Questions ratified by the operator **exactly as recommended** (2026-11-18); the
      `plan.md` / `tasks.md` PROVISIONAL banners lifted (binding)
- [ ] confirm: the `GET /api/v1/policy/matrix` request/payload is byte-unchanged; server-side row-scoping
      and the `policy:read` gate are unchanged; the three cell states render identically; **no**
      backend/gateway/policy/schema/contract change; the transpose is presentational only
- [ ] living docs updated; `CHANGELOG.md` entry added referencing SPEC-079
- [ ] spec index in `docs/specs/README.md` updated; spec status set to `delivered` (done at the release
      gate — the `delivered` flip is version-stamped `as v0.60.0`, shared with SPEC-078)
- [ ] version bump to **v0.60.0** at the release gate (shared with SPEC-078; `VERSION` + products + portal
      lockstep, proven by `validate-version`)
