# SPEC-079: Permissions matrix transpose (roles across the top, permissions down the first column)

## Status

- status: `in-progress`
- owner: chi
- created: 2026-11-18
- approved: **2026-11-18** — the operator ratified all three Open Questions **exactly as
  recommended** (`draft → approved`), and the binding [plan](plan.md) / [tasks](tasks.md) are
  authored. Approval authorizes implementation to *begin* — **not** to merge, commit/push,
  deploy, or version-bump (each a separate gate).
- origin: **operator feedback from a local-cluster trial** of the operator portal. The
  Permissions page renders the live role × action matrix in
  `products/operator-portal/web-ui/app/src/views/control/PermissionsView.tsx` with the
  **permissions (actions) as columns** and the **roles as rows**, so the long action list
  forces a wide, horizontally-scrolling table that is hard to scan. The operator asked to
  **transpose** it — **roles across the top header row** and **permissions down the first
  column** — because the permission list is long and reads/browses better vertically.
- scope: a **small, purely presentational** operator-portal UX change. **No** backend,
  policy, contract, schema, or authorization-model change: the `GET /api/v1/policy/matrix`
  request and payload, the server-side row-scoping, the `policy:read` gate, and the three
  cell states are all preserved verbatim. Only the **orientation** of the rendered matrix
  changes, never its meaning.
- release slice: the **operator portal** Permissions view. Independent of
  [SPEC-078](../SPEC-078-conversational-agentic-remediation/spec.md) — that spec is a
  backend composition + entry change whose boundary explicitly adds **no** portal view.
  **Release reconciliation 2026-11-19:** v0.60.0 shipped with SPEC-078 before this implementation.
  SPEC-079 therefore moves to a subsequent release; the exact version is chosen at its separate
  release gate. The original shared-v0.60.0 approval remains recorded in OQ-3 and the changelog,
  superseded only for release scheduling. No version bump is part of this implementation.
- extends / provenance: [SPEC-019](../SPEC-019-portal-transparency-navigation/spec.md) R-3
  (the role × action policy-matrix view), [SPEC-023](../SPEC-023-portal-framework-rebuild/spec.md)
  R-5 (the rebuilt control view), and [SPEC-030](../SPEC-030-require-approval-policy-semantics/spec.md)
  R-5 (the additive third cell state — `require_approval` with its tier + designated deciders).

## Problem

The Permissions view is the operator's window into the enforced policy bundle: it fetches
`GET /api/v1/policy/matrix` (already scoped server-side — the full matrix for a
`platform-admin`, the caller's own roles otherwise) and renders one cell per
(role, action) pair. Today the table is oriented **roles-as-rows × actions-as-columns**:

- the first fixed column is the role (`rowKey="role"`, header `"role"`);
- every action becomes a column (`...actions.map(...)`), and the table scrolls horizontally
  (`scroll={{ x: "max-content" }}`).

The **action list is long** (the deny-by-default vocabulary keeps growing — `chat`,
`policy:read`, `runtime:flags`, `remediate:stage`, the tool families, …) while the **role set
is short** (`platform-admin`, `operator`, `approver`, `developer`, `read-only-observer`,
`auditor`). Putting the long axis on the columns forces a wide table that must be scrolled
sideways to compare two roles, and the row headers (the few roles) are the *short* dimension.
Transposing — the **long permission list down the first column** (a vertical read, the natural
scrolling axis of a page) and the **few roles across the top** — makes the matrix far easier to
browse and to compare role-by-role at a glance.

## Approach

Transpose the rendering in `PermissionsView.tsx`, with scoped CSS for matrix-only overflow.
Change only presentation. The payload keeps its shape (`actions[]`, `roles[]`, `matrix: Record<role, Record<action, boolean>>`, and the optional
`approval_requirements: Record<role, Record<action, {tier, decided_by_roles, rule_id}>>`); the
view simply addresses it by **(row = action, column = role)** instead of **(row = role, column =
action)**:

- `dataSource` becomes the actions (`actions.map((action) => ({ action }))`), `rowKey="action"`;
- the first **fixed** column is the permission name (header per OQ-1);
- the remaining columns are the roles (`...roles.map((role) => ({ title: role, key: role, ... }))`);
- each cell resolves the **same** lookups as today — `approval_requirements[role][action]` for the
  `require_approval` state, else `matrix[role][action]` for allow/deny — so all three cell states
  (and the tier + deciders tooltip) render identically;
- the scroll axis flips: the permission column stays `fixed: "left"` and the long permission list
  scrolls vertically (per OQ-2). If role columns exceed the available width, only the matrix scrolls
  horizontally; the title, bundle metadata, and footer stay outside that scroll region.

This is a **presentational** change only: the request, the payload contract, the server-side
row-scoping, and the gateway's `policy:read` re-enforcement are untouched, and no backend,
policy, or authorization-model artifact changes.

## Requirements

> Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.
> Every requirement preserves the payload contract, the server-side scoping, and the three cell
> states exactly as delivered by SPEC-019 R-3 / SPEC-023 R-5 / SPEC-030 R-5.

### R-1: Transpose the rendered orientation (permissions as rows, roles as columns)

Render the matrix with the **permissions (actions) down the first column** as the rows and the
**roles across the top header row** as the columns. The first column (the permission name) is
`fixed: "left"`; the role columns follow. The page title, the policy-bundle version line, and the
footer summary stay (footer wording per OQ-1).

- **Acceptance:** the top header row lists the role names; the first fixed column lists the
  permission/action names; the same set of (role, action) cells renders as before the transpose
  (no cell added, dropped, or re-valued); a long permission list scrolls vertically without
  losing the first-column labels.

### R-2: Preserve semantics, scoping, and the payload contract (presentational only)

The transpose changes **no** data path. The view still fetches `GET /api/v1/policy/matrix` and
renders whatever the gateway returns (already scoped server-side); all **three cell states** render
identically — `allow` (success), `deny` (error), and `require_approval` (warning: `self-approval`
for `tier_1`, otherwise `approver required`, with the `deciders: …` tooltip from
`decided_by_roles`). `agent-stream-event`/`execution-request` and every policy/authorization
artifact are unaffected; the `policy:read` gate and the row-scoping are unchanged.

- **Acceptance:** the `GET /api/v1/policy/matrix` request and its payload shape are byte-unchanged;
  each cell resolves the same `matrix[role][action]` / `approval_requirements[role][action]` lookups
  as before; a scoped caller (non-`platform-admin`) still sees only their own roles (now as a subset
  of the columns); no backend, gateway, policy, schema, or contract change is made.

### R-3: Tests + living docs

Add the **currently absent** `PermissionsView.test.tsx`, mirroring the sibling control-view tests
(`ApprovalsView.test.tsx`, `SettingsView.test.tsx`, `SkillsView.test.tsx` — `@testing-library/react`
+ `vitest`, mocking `requestJson` from the api client, with the antd `matchMedia` shim), asserting the
transposed orientation and the three cell states. Reconcile the living docs: this spec index row and
`CHANGELOG.md`. The implementation sweep found stale roles-as-rows wording in the portal,
role-administration, and architecture guides plus the portal README; update those living surfaces.
The authorization-matrix reference itself needs no orientation change.

- **Acceptance:** `PermissionsView.test.tsx` asserts roles render as column headers, permissions as
  the first-column rows, and all three cell states (allow/deny/require_approval with the deciders
  tooltip) render; the operator-portal suite and root `make verify` stay green; the spec index and
  `CHANGELOG.md` are updated.

## Non-Goals

- **No backend, gateway, policy, contract, schema, or authorization-model change** — the matrix
  content and how it is evaluated are unchanged; only the rendered orientation changes.
- **No new permission, role, action, or cell state**, and no change to the three existing states'
  meaning (SPEC-030 R-5).
- **No change to server-side row-scoping or the `policy:read` gate** — the view still renders
  whatever the gateway returns.
- **Not bundled into [SPEC-078](../SPEC-078-conversational-agentic-remediation/spec.md)** — that
  spec adds **no** portal view; the transpose ships independently in a subsequent release.
- **No redesign** of the Permissions page beyond the table orientation (the title, bundle-version
  line, and footer stay, subject only to the OQ-1 wording).

## Open Questions

> Each question was **ratified by the operator exactly as recommended 2026-11-18** (`draft →
> approved`), on which the binding [plan](plan.md) / [tasks](tasks.md) were authored.

- **OQ-1 — First-column header + footer wording.** The transposed first column holds the payload's
  `actions[]`, which the operator calls "permissions." **Resolved (ratified 2026-11-18):** title
  the first column
  **`permission`** (the operator's user-facing term) and re-order the footer to
  **`{actions} permissions × {roles} roles · evaluated from the enforced bundle`** so the summary
  matches the new visual order. Alternative: keep `action` for literal payload-field fidelity.
- **OQ-2 — Scroll / sticky behavior for the now-long row list.** With roles on the (few) columns and
  permissions on the (many) rows, the horizontal `x`-scroll is no longer needed. **Resolved
  (ratified 2026-11-18):** keep the permission column `fixed: "left"`, drop `scroll={{ x:
  "max-content" }}`, and let the long permission list scroll **with the page** (the natural
  vertical axis); a bounded `scroll={{ y: … }}` stays an implementation-detail fallback if a
  fixed-height viewport proves preferable.
  **Narrow-layout correction authorized 2026-11-20:** the live 830px check showed that six roles
  can still overflow. Keep the removed forced width and page-level vertical scrolling; contain
  conditional horizontal overflow in a keyboard-focusable matrix-only region so page chrome
  does not slide or clip. This does not change the request, scope, or cell semantics.
- **OQ-3 — Test coverage + target version.** **Resolved (ratified 2026-11-18):** add the missing
  `PermissionsView.test.tsx` **now** (the transpose is exactly what a DOM assertion guards, and
  every sibling control view already has one); target version pinned **v0.60.0** — the operator
  chose to ride the shared release train with
  [SPEC-078](../SPEC-078-conversational-agentic-remediation/spec.md) rather than a separate
  PATCH/MINOR, so SPEC-079 could have been delivered within v0.60.0.
  **Scheduling supersession 2026-11-19:** v0.60.0 shipped without SPEC-079; its implementation
  remains approved, but it now targets a subsequent release selected at the release gate.

## Changelog

- 2026-11-18 — created as `draft` from operator local-cluster trial feedback: transpose the operator
  portal Permissions matrix so **roles run across the top** and **permissions run down the first
  column** (the long permission list browses better vertically). A **purely presentational**
  operator-portal change — the `GET /api/v1/policy/matrix` payload, server-side row-scoping, the
  `policy:read` gate, and the three cell states (SPEC-019 R-3 / SPEC-023 R-5 / SPEC-030 R-5) are all
  preserved. Raises three Open Questions (header/footer wording; scroll behavior; test + target
  version), each recommended and pending formal ratification. Kept **out of** SPEC-078 (a backend
  composition + entry change with no portal view) so it can ship independently. No implementation,
  merge, commit/push, deployment, or version bump authorized by this draft.
- 2026-11-18 — **approved** (`draft → approved`): the operator ratified all three Open Questions
  **exactly as recommended** — OQ-1 the first column is titled `permission` and the footer
  re-orders to `{actions} permissions × {roles} roles`; OQ-2 the permission column stays
  `fixed: "left"`, the horizontal `x`-scroll is dropped, and the long list scrolls with the page;
  OQ-3 add `PermissionsView.test.tsx` now and pin target version **v0.60.0** (riding the shared
  release train with SPEC-078 rather than a separate PATCH/MINOR). The binding [plan](plan.md) /
  [tasks](tasks.md) are authored. Approval authorizes implementation to *begin* — not to merge,
  commit/push, deploy, or version-bump (each a separate gate).
- 2026-11-19 — implementation started (`approved → in-progress`) on the operator's go-ahead.
  Reconciled the release schedule: v0.60.0 already shipped with SPEC-078, so SPEC-079 moves to a
  subsequent release whose version is chosen at the separate release gate. R-1…R-3 scope and the
  approved presentation/semantics decisions are unchanged. The living-doc sweep found four stale
  roles-as-rows claims, correcting the earlier expectation of a no-op guide sweep. Added failure-first
  DOM coverage (five failures before the transpose, all nine cases passing afterward); verification
  and release-gate state are tracked in [tasks](tasks.md).
- 2026-11-20 — operator authorized the narrow-layout correction after browser verification found
  whole-page horizontal overflow. Contain overflow in a focusable matrix-only region while keeping
  the permission column pinned and the long list at page height. Added a failure-first containment
  regression and updated the operator guide; verification limits remain explicit in [tasks](tasks.md).
