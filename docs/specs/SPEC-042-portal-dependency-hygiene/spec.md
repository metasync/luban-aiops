# SPEC-042: Portal Dependency Hygiene — antd v6 API Migration and Managed Component Refresh

## Status

- status: `draft`
- owner: luban-platform-team
- created: 2026-08-28
- approved: —
- delivered: —
- release slice: R5 — Hardening and External Consumption (fourth R5 slice)
- related ADRs: none (extends the SPEC-023 portal framework rebuild's
  technology choices)

## Summary

The v0.23.2 delivery train confirmed the portal is functionally stable
but surfaced two maintainability signals: the vitest suite prints 53
antd deprecation warnings (48× `Drawer width`, 5× `Alert message`),
and the 2026-08-28 upgrade check found the portal's major components
several majors behind their upstreams (vite 6 vs 8, vitest 3 vs 4,
TypeScript 5.6 vs 5.9, React 18 vs 19, jsdom 25 vs 30). This spec
migrates the portal off every deprecated antd v6 API it uses, adds a
deprecation regression guard so warnings can never accumulate again,
and applies a managed refresh of the major components with every
decision recorded below. Portal-only: no backend, contract, policy,
or audit change.

## Motivation

- **Deprecation warnings are compounding debt.** The v0.23.2 train
  observed `[antd: Drawer] width is deprecated` (48 occurrences) and
  `[antd: Alert] message is deprecated` (5 occurrences) across the
  vitest run. Each antd major eventually removes deprecated props;
  warnings left in the suite mask new ones and erode the signal.
- **The upgrade window widens every release.** The 2026-08-28 check
  found: antd locked at 6.6.1 (6.6.2 out), TypeScript 5.6.3 (5.9.3
  out, 7.x native line already published), vite 6.4.3 (8.x out),
  vitest 3.2.7 (4.x out), jsdom 25.0.1 (30.x out), React 18.3.1
  (19.x out with every portal peer dependency already declaring
  support). Small, regular refreshes stay cheap; deferred ones
  compound into risky migrations.
- **The deprecation cleanup and the refresh are one job.** antd 6.6.x
  is already the locked resolution, so the warnings describe the
  current API posture — the fix is code migration, not pinning. Doing
  it alongside the component refresh means one regression pass
  (suite + tsc + build + live walkthrough) covers both.
- Timing: three R5 documents slices are delivered and live-checked;
  dependency hygiene is squarely R5's "reliability and operability"
  charter, and the portal surface is quiet enough to absorb a
  toolchain refresh safely.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Migration off deprecated antd v6 APIs

Every antd API the portal uses migrates to its non-deprecated v6
form. The 2026-08-28 inventory is exhaustive: three `Drawer` usages
passing `width` (`App.tsx` navigation drawers at 230px and 260px,
`DocumentsView.tsx` document drawer at 560px) and fifteen `Alert`
usages passing `message` across nine view files. `Alert description`
is not flagged and stays.

Acceptance criteria:

- `Drawer` usages render at their current pixel widths through the
  non-deprecated API; navigation layout and the document drawer are
  visually unchanged.
- `Alert` usages keep identical rendered content (title and
  description text, type, icon) through the non-deprecated API.
- The vitest suite emits zero antd deprecation warnings.
- No other antd prop usage changes; no visual, routing, or state
  behavior changes.

### R-2: Deprecation regression guard

The vitest setup fails the suite when any antd deprecation warning
appears in test output, so future deprecations surface at the pull
that introduces them instead of accumulating silently.

Acceptance criteria:

- A test-run that emits an `[antd: …] … is deprecated` console
  warning fails the suite with a pointer to the offending warning.
- The guard does not fail on non-deprecation console output and does
  not alter existing test assertions.

### R-3: Managed component refresh

The portal's dependencies move to the recorded adopt set below; every
check finding resolves to either an adopted bump or a parked
decision with a recorded reason. `package.json` ranges and
`package-lock.json` stay consistent, and the Docker image build
(`tsc --noEmit && vite build` on the node base image) stays green.

Adopt set (2026-08-28 check):

| Package | Locked | Target | Note |
|---|---|---|---|
| antd | 6.6.1 | latest 6.x | patch refresh; R-1 migrates its deprecations |
| @ant-design/x | 2.9.0 | unchanged | already latest |
| @ant-design/icons | 6.3.2 | unchanged | already latest |
| dayjs | 1.11.23 | unchanged | already latest |
| @testing-library/react | 16.3.2 | latest 16.x | patch refresh |
| @testing-library/dom | 10.4.0 | latest 10.x | patch refresh |
| typescript | 5.6.3 | 5.9.x | 7.x parked (see Design Decisions) |
| vite | 6.4.3 | latest 8.x | paired with plugin-react 6 |
| @vitejs/plugin-react | 4.7.0 | latest 6.x | requires vite ^8 |
| vitest | 3.2.7 | latest 4.x | compatible with vite 6/7/8 |
| jsdom | 25.0.1 | latest 30.x | requires node ≥22.22.2 |
| @types/node | ^22.10.0 | latest ^22.x | stays on the node 22 line |

Acceptance criteria:

- Every adopt-set package resolves at its target in
  `package-lock.json`; no adopt-set package remains behind its
  recorded target.
- `engines.node` in `package.json` reflects the strictest adopted
  requirement (jsdom 30's `>=22.22.2`) and the Dockerfile's node
  base image satisfies it.
- `tsc --noEmit`, the vitest suite, and the production build all
  pass on the refreshed set.
- Parked majors are recorded in Design Decisions with reasons —
  nothing is silently skipped.

### R-4: React 19 migration

React and React DOM move from 18.3.1 to the current 19.x line. The
2026-08-28 peer check recorded that every portal consumer already
declares React 19 support (antd `>=18.0.0`, @ant-design/x
`>=18.0.0`, @testing-library/react `^18 || ^19`), so the migration
is gated on behavior, not compatibility.

Acceptance criteria:

- `react`, `react-dom`, `@types/react`, and `@types/react-dom`
  resolve on the 19.x line with no peer-dependency warnings.
- The full vitest suite, `tsc --noEmit`, and the production build
  pass unchanged.
- A live browser walkthrough covers sign-in, chat (including a
  streamed turn), the session panel, Approvals, and the Documents
  drawer with no rendering or interaction regressions.
- Any code changes forced by React 19 (e.g. removed legacy APIs or
  type tightening) are listed in the delivery commit; none alter
  portal behavior.

## Design Decisions

- **Code migration, not version pinning.** antd already resolves to
  6.6.x in the lockfile — the warnings describe the current API, so
  pinning backwards would fight the lockstep refresh. Migrating the
  three `width` and fifteen `message` sites is small, bounded, and
  permanent; the R-2 guard keeps it permanent.
- **TypeScript stays on the 5.x line.** TypeScript 7 is the native
  (tsgo) port line; it is too new for a safety-critical portal build
  gate in this window. 5.9.3 captures every current 5.x fix and
  leaves the 7.x move as a future hygiene slice with its own check.
- **vite and plugin-react move together.** @vitejs/plugin-react 6
  requires vite ^8, so they bump as a pair; the portal's vite config
  (version injection, api proxy, hash output) uses no plugin-react 4
  internals, so the pair move carries no config rewrite risk.
- **React 19 is adopted now because the peer surface is ready.** All
  three framework peers declare React 19 support today; deferring
  would only widen the gap. The gate is behavioral (suite + build +
  walkthrough), not declarative.
- **No deprecation snapshot allow-list.** The R-2 guard is
  zero-tolerance rather than an allow-list: the portal's antd
  surface is small enough that every new deprecation deserves a
  decision, not a grandfather.

## Non-Goals

- TypeScript 7.x (native port line) — parked per Design Decisions.
- Node engine moves beyond the strictest adopted requirement; the
  portal stays on the node 22 line in both `engines` and the
  Dockerfile.
- Any backend service, shared contract, policy, audit, or execution
  change — this spec is portal-only.
- Design-token, theme, or layout changes beyond preserving the exact
  current rendering.
- Migrating antd APIs that are not flagged as deprecated.
- Package-manager or workspace-tooling changes (npm stays).
- The numbered-list continuation renderer item (backlog) — unrelated
  to dependency hygiene.

## Impact

- products touched: `products/operator-portal` only (web-ui app and
  its Dockerfile node base pin check)
- contracts touched: none
- identity / policy / audit / execution safety impact: none — no
  routes, actions, event types, or execution paths change
- living state docs to update on delivery: CHANGELOG, release notes
  + index, `docs/guides/configuration-reference.md` only if the node
  floor wording changes, spec index, delivery-roadmap

## Open Questions

- none recorded — every upgrade check finding resolves to an adopt
  or a parked decision in Design Decisions.

## Changelog

- 2026-08-28: created as `draft`. Drafted directly from the v0.23.2
  delivery-train observations (antd deprecation warnings in the
  vitest output) plus the same-day upgrade check recorded above —
  the same memo-free evidence-base departure as SPEC-031/032, since
  the check itself is the evidence base.
