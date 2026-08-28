# v0.24.1 — Post-Release Review Remediation

Date: 2026-08-28
Release type: patch (same-day follow-up to the v0.24.0 code & doc
review; test and documentation polish only — no runtime behavior,
routes, actions, event types, or dependency versions change)

## Summary

The post-release review of v0.24.0 (SPEC-042 dependency hygiene)
returned approve-with-minor: one Minor finding in the zero-tolerance
vitest deprecation guard and three documentation Nits. This patch
remediates all four without touching any runtime path.

## The guard hardening (the Minor finding)

The R-2 guard's pattern `/\[antd: .+\].*deprecated/i` matched antd's
standard per-component emission (`Warning: [antd: Alert] \`message\`
is deprecated …`) but not the second emission mode: when a
`ConfigProvider` sets `warning={{ strict: false }}`, antd batches
deprecations into a single `console.warn('[antd] There exists
deprecated usage in your code:', …)` — no component bracket, so the
guard would let it pass and silently defeat the zero-tolerance gate.

The portal does not use `strict: false` today, so the gap was latent,
not live. The pattern broadens to `/\[antd(?:: .+)?\].*deprecated/i`,
making the component segment optional and closing the strict-mode
escape hatch. Verification:

- pattern unit-checked against both emission forms plus non-antd
  decoys (matches both antd forms only);
- guard re-proven end-to-end: deliberately re-introducing a
  deprecated `Alert message` prop fails the suite at teardown with
  the offending warning text, reverting returns it to green
  (18 files / 184 tests).

## Documentation Nits

1. **R-3 adopt-set table accuracy** — the `@testing-library/dom` and
   `@types/node` rows cited declared ranges as "From" values even
   though the pre-release lockfile already resolved 10.4.1 and
   22.20.1; both rows are now marked as range-only bumps
   (`^10.4.0` → `^10.4.1`, `^22.10.0` → `^22.20.1`).
2. **`engines.node` precision** — the note now states jsdom 30's
   full engine expression (`^22.22.2 || ^24.15.0 || >=26.0.0`)
   rather than the simplified "jsdom 30's floor"; the `node:22-alpine`
   Dockerfile base satisfies it.
3. **SPEC-042 tasks.md reality** — the checked R-1 lines now record
   the delivered truth: one `Drawer` in App.tsx (260px; the 230px
   draft-inventory figure is a `Layout.Sider` width, not deprecated)
   and twenty Alert sites across ten view files (the approved
   inventory counted fifteen before v0.23.x views landed).

## What does not change

- No dependency version moves; the v0.24.0 locks stand as shipped.
- No route, action, event type, approval path, or audit change.
- Version lockstep only: every product and the portal report 0.24.1.

## Verification

- Portal: `tsc --noEmit` and the full vitest suite green under the
  hardened guard.
- House train: `make build`, `make verify`, `make deploy`, and a live
  version check on the dev-k8s cluster.
