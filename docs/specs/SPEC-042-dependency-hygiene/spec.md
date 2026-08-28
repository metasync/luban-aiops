# SPEC-042: Portal and Backend Dependency Hygiene

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-08-28
- approved: 2026-08-28
- delivered: —
- release slice: R5 — Hardening and External Consumption (fourth R5 slice)
- related ADRs: none (extends the SPEC-023 portal framework rebuild's
  technology choices; honors ADR-0002's AgentScope kernel position in
  R-5's verification posture)

## Summary

The v0.23.2 delivery train confirmed the platform is functionally
stable but surfaced two maintainability signals. The portal's vitest
suite prints 53 antd deprecation warnings (48× `Drawer width`, 5×
`Alert message`), and the 2026-08-28 upgrade check found the portal's
major components several majors behind their upstreams (vite 6 vs 8,
vitest 3 vs 4, TypeScript 5.6 vs 5.9, React 18 vs 19, jsdom 25 vs
30). The same check over the backend lockfiles found them close to
current — the work there is a stable-channel re-lock (agentscope
2.0.6 → 2.0.7.post1, fastapi and uvicorn minors) plus three
adjudicated range decisions. This spec migrates the portal off every
deprecated antd v6 API it uses, adds a deprecation regression guard,
applies a managed portal refresh, and re-locks every backend product
inside its declared ranges — **adopting latest stable versions only**.

## Motivation

- **Deprecation warnings are compounding debt.** The v0.23.2 train
  observed `[antd: Drawer] width is deprecated` (48 occurrences) and
  `[antd: Alert] message is deprecated` (5 occurrences) across the
  vitest run. Each antd major eventually removes deprecated props;
  warnings left in the suite mask new ones and erode the signal.
- **The portal upgrade window widens every release.** The 2026-08-28
  check found: antd locked at 6.6.1 (6.6.2 out), TypeScript 5.6.3
  (5.9.3 out, the 7.x native line already published), vite 6.4.3
  (8.x out), vitest 3.2.7 (4.x out), jsdom 25.0.1 (30.x out), React
  18.3.1 (19.x out with every portal peer dependency already
  declaring support). Small, regular refreshes stay cheap; deferred
  ones compound into risky migrations.
- **The backend is close to current but not checked in.** Caret-capped
  ranges have kept lockfiles near upstream, yet no re-lock has run
  since the last spec train: agentscope sits one patch behind
  (2.0.6 vs 2.0.7.post1), fastapi two minors behind (0.139.2 vs
  0.141.1), uvicorn one minor behind (0.51.0 vs 0.52.4), and six
  products cap cryptography at `<45.0` while the ecosystem ships
  50.x. A deliberate re-lock with adjudicated caps keeps the
  backend's frozen-sync posture honest.
- **The deprecation cleanup and the refreshes are one job.** antd
  6.6.x is already the locked resolution, so the warnings describe
  the current API posture — the fix is code migration, not pinning.
  Doing it alongside the component refreshes means one consolidated
  regression pass covers both.
- Timing: three R5 documents slices are delivered and live-checked;
  dependency hygiene is squarely R5's "reliability and operability"
  charter, and both surfaces are quiet enough to absorb a refresh
  safely.

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

### R-3: Managed portal component refresh

The portal's dependencies move to the recorded adopt set below; every
check finding resolves to either an adopted bump or a parked
decision with a recorded reason. All adopted versions are **latest
stable** (no alpha, beta, release candidate, or dev builds).
`package.json` ranges and `package-lock.json` stay consistent, and
the Docker image build (`tsc --noEmit && vite build` on the node base
image) stays green.

Adopt set (2026-08-28 check, stable channel):

| Package | Locked | Target | Note |
|---|---|---|---|
| antd | 6.6.1 | latest stable 6.x | patch refresh; R-1 migrates its deprecations |
| @ant-design/x | 2.9.0 | unchanged | already latest stable |
| @ant-design/icons | 6.3.2 | unchanged | already latest stable |
| dayjs | 1.11.23 | unchanged | already latest stable |
| @testing-library/react | 16.3.2 | latest stable 16.x | patch refresh |
| @testing-library/dom | 10.4.0 | latest stable 10.x | patch refresh |
| typescript | 5.6.3 | 5.9.x | latest stable 5.x; the 7.x line is parked (see Design Decisions) |
| vite | 6.4.3 | latest stable 8.x | paired with plugin-react 6 |
| @vitejs/plugin-react | 4.7.0 | latest stable 6.x | requires vite ^8 |
| vitest | 3.2.7 | latest stable 4.x | compatible with vite 6/7/8 |
| jsdom | 25.0.1 | latest stable 30.x | requires node ≥22.22.2 |
| @types/node | ^22.10.0 | latest stable ^22.x | stays on the node 22 line |

Acceptance criteria:

- Every adopt-set package resolves at its target in
  `package-lock.json`; no adopt-set package remains behind its
  recorded target, and no resolved version is a prerelease.
- `engines.node` in `package.json` reflects the strictest adopted
  requirement (jsdom 30's `>=22.22.2`) and the Dockerfile's node
  base image satisfies it.
- `tsc --noEmit`, the vitest suite, and the production build all
  pass on the refreshed set.
- Parked majors are recorded in Design Decisions with reasons —
  nothing is silently skipped.

### R-4: React 19 migration

React and React DOM move from 18.3.1 to the latest stable 19.x line.
The 2026-08-28 peer check recorded that every portal consumer
already declares React 19 support (antd `>=18.0.0`, @ant-design/x
`>=18.0.0`, @testing-library/react `^18 || ^19`), so the migration
is gated on behavior, not compatibility.

Acceptance criteria:

- `react`, `react-dom`, `@types/react`, and `@types/react-dom`
  resolve on the stable 19.x line with no peer-dependency warnings.
- The full vitest suite, `tsc --noEmit`, and the production build
  pass unchanged.
- A live browser walkthrough covers sign-in, chat (including a
  streamed turn), the session panel, Approvals, and the Documents
  drawer with no rendering or interaction regressions.
- Any code changes forced by React 19 (e.g. removed legacy APIs or
  type tightening) are listed in the delivery commit; none alter
  portal behavior.

### R-5: Backend stable-channel lockfile refresh

Every backend product re-locks inside its declared ranges so each
`uv.lock` carries the latest stable version its range allows; the
three lagging range caps are adjudicated explicitly. No prerelease,
beta, or release-candidate version is adopted anywhere.

Re-lock findings and adjudications (2026-08-28 check):

| Component | Locked | Latest stable | Disposition |
|---|---|---|---|
| agentscope | 2.0.6 | 2.0.7.post1 | adopt — in range `>=2.0.4,<3.0`; a PEP 440 post-release is a final stable release |
| agentscope-runtime | 1.1.6.post2 | 1.1.6.post2 | already current |
| fastapi | 0.139.2 | 0.141.1 | adopt — in range |
| uvicorn | 0.51.0 | 0.52.4 | adopt — in range |
| pydantic, httpx, kubernetes, psycopg, pyjwt, pyyaml, prometheus-client, OTel sdk/api/exporter | — | — | already latest stable |
| cryptography | capped `<45.0` in six products | 50.0.1 | adjudicate: raise caps to the latest stable major after reviewing the JWT/signing call sites; keep with recorded reason if any call site is incompatible |
| redis (client) | capped `<7.0` | 8.1.0 | park the cap — the deployed server is redis 7.2, client 6.x is fully compatible, and client majors 7/8 were API-removal releases |
| elasticsearch (client) | capped `<9.0` | 9.5.0 | park the cap — the client major follows the server major, and no Elasticsearch server is deployed in dev |
| OTel instrumentation (fastapi/httpx/logging) | paired with SDK 1.44.0 | 0.65b0 | stay — upstream publishes these on a permanent 0.xb channel with no stable release line (recorded exception, see Design Decisions) |

Acceptance criteria:

- `uv lock` regenerates every product's lockfile inside its declared
  ranges; each lock carries the latest stable version its range
  allows, and no lock resolves a prerelease.
- The agentscope bump (the platform kernel per ADR-0002) is verified
  beyond the unit suites: `make verify` plus a live check of the
  chat, HITL confirmation, and approved-mutating paths
  (`mutating-demo.sh` incl. the HITL leg).
- The cryptography cap decision lands one way or the other with the
  reason recorded here; the redis and elasticsearch caps stay with
  the reasons above.
- All product test suites stay green under frozen sync; no product
  changes a declared range except where this spec adjudicates it.

## Design Decisions

- **Latest stable only — no betas, no RCs.** Every adopted version
  on both surfaces is a final stable release. One recorded exception:
  the OpenTelemetry instrumentation packages (fastapi/httpx/logging)
  have no stable channel upstream — `0.xb` is their permanent
  official release convention while the SDK/API/exporter side is
  fully stable. The portal stays on the instrumentation versions its
  stable SDK pairing already locks; it does not chase the newest
  0.xb. TypeScript 7.x is parked for maturity reasons and happens to
  keep the portal on the long-stable 5.x line regardless.
- **Code migration, not version pinning.** antd already resolves to
  6.6.x in the lockfile — the warnings describe the current API, so
  pinning backwards would fight the lockstep refresh. Migrating the
  three `width` and fifteen `message` sites is small, bounded, and
  permanent; the R-2 guard keeps it permanent.
- **TypeScript stays on the 5.x line.** TypeScript 7 is the native
  (tsgo) port line; it is too new for a safety-critical portal build
  gate in this window. 5.9.x captures every current stable 5.x fix
  and leaves the 7.x move as a future hygiene slice with its own
  check.
- **vite and plugin-react move together.** @vitejs/plugin-react 6
  requires vite ^8, so they bump as a pair; the portal's vite config
  (version injection, api proxy, hash output) uses no plugin-react 4
  internals, so the pair move carries no config rewrite risk.
- **React 19 is adopted now because the peer surface is ready.** All
  three framework peers declare React 19 support today; deferring
  would only widen the gap. The gate is behavioral (suite + build +
  walkthrough), not declarative.
- **agentscope floats inside its range, verified like a kernel.**
  `>=2.0.4,<3.0` already admits the patch; re-locking is cheap, but
  agentscope is the runtime kernel — R-5 pairs the bump with the
  full verify gate and a live check of the chat/HITL/mutating paths
  rather than treating it as routine churn. `.post` releases are PEP
  440 final releases (re-publications of a stable version), so
  2.0.7.post1 satisfies the stable-only policy; if a re-publication
  ever worries the operator, plain 2.0.7 remains in range.
- **Redis and Elasticsearch caps are deliberate, not debt.** Client
  majors must be judged against the deployed server and their own
  breaking-change character; both stay capped with recorded reasons
  and a revisit trigger (server upgrade, or a security advisory the
  cap blocks).
- **No deprecation snapshot allow-list.** The R-2 guard is
  zero-tolerance rather than an allow-list: the portal's antd
  surface is small enough that every new deprecation deserves a
  decision, not a grandfather.

## Non-Goals

- TypeScript 7.x (native port line) — parked per Design Decisions.
- Prerelease, beta, or RC adoption anywhere; the single recorded
  exception (OTel instrumentation's permanent 0.xb channel) stays at
  its locked pairing rather than chasing newer betas.
- Node engine moves beyond the strictest adopted requirement; the
  portal stays on the node 22 line in both `engines` and the
  Dockerfile.
- Redis client 7/8, Elasticsearch client 9 — caps parked with
  reasons and revisit triggers.
- Any service behavior, contract, policy, audit, or execution change
  — refreshes are dependency-only; no product code changes except
  what React 19 or the cryptography cap review force, each listed in
  the delivery commit.
- Design-token, theme, or layout changes beyond preserving the exact
  current rendering.
- Migrating antd APIs that are not flagged as deprecated.
- Package-manager or workspace-tooling changes (npm and uv stay).
- The numbered-list continuation renderer item (backlog) — unrelated
  to dependency hygiene.

## Impact

- products touched: `products/operator-portal` (web-ui app and its
  Dockerfile node base pin check) plus all eight Python products'
  `uv.lock` files (R-5 re-lock) and the six products declaring
  `cryptography` (cap adjudication); the agentscope bump lands in
  `products/agent-platform`
- contracts touched: none
- identity / policy / audit / execution safety impact: none intended
  — no routes, actions, event types, or execution paths change; the
  agentscope kernel bump and the cryptography cap review carry the
  corresponding verification burden (R-5 live check, signing-path
  call-site review)
- living state docs to update on delivery: CHANGELOG, release notes
  + index, `docs/guides/configuration-reference.md` only if the node
  floor wording changes, spec index, delivery-roadmap

## Open Questions

- none recorded — every upgrade-check finding resolves to an adopt,
  a parked decision with a reason, or the one recorded stable-channel
  exception.

## Changelog

- 2026-08-28: created as `draft`. Drafted directly from the v0.23.2
  delivery-train observations (antd deprecation warnings in the
  vitest output) plus the same-day portal upgrade check — the same
  memo-free evidence-base departure as SPEC-031/032, since the check
  itself is the evidence base.
- 2026-08-28: revised per operator feedback to (a) apply a
  latest-stable-only adoption policy — no beta/RC/dev versions, with
  the OTel instrumentation 0.xb channel as the single recorded
  exception — and (b) extend scope to the backend: new R-5
  stable-channel lockfile refresh (agentscope 2.0.6 → 2.0.7.post1,
  fastapi/uvicorn in-range floats, cryptography cap adjudication,
  redis/elasticsearch caps parked with reasons). Directory renamed
  `SPEC-042-portal-dependency-hygiene` → `SPEC-042-dependency-hygiene`.
