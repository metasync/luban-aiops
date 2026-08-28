# SPEC-042 Implementation Plan

## Approach

Portal-only refresh in two coupled passes: migrate the three
deprecated antd call sites and lock the posture with a vitest guard
(R-1/R-2), then apply the recorded adopt set — including the React 19
migration — and run one consolidated regression pass (suite + tsc +
image build + live walkthrough) over the refreshed tree (R-3/R-4).
No new services, routes, policy actions, or audit event types. Version
lockstep to 0.24.0.

## Workstreams

### W-1: antd deprecation migration (portal)

- `App.tsx`: the two navigation `Drawer`s move `width={230}` /
  `width={260}` to `size={230}` / `size={260}` (antd 6's `size`
  accepts numbers — verified against `Drawer.d.ts`).
- `views/workspace/DocumentsView.tsx`: the document drawer moves
  `width={560}` to `size={560}`.
- `Alert` `message` → `title` across the fifteen sites in nine
  files: `App.tsx`, `chat/ChatView.tsx`,
  `views/workspace/DocumentsView.tsx`, `views/audit/AuditView.tsx`,
  `views/control/SkillsView.tsx`, `views/control/ApprovalsView.tsx`,
  `views/control/ToolsView.tsx`, `views/control/PermissionsView.tsx`,
  `views/incidents/IncidentsView.tsx`. `description` stays — it is
  not deprecated.
- Grep audit afterwards: no `width=` on a Drawer and no `message=`
  on an Alert remain under `src/`.

### W-2: Deprecation regression guard (portal tests)

- vitest setup (the existing setup file or a new one wired through
  `vitest.config.ts`): intercept `console.error`/`console.warn`
  during the run; if any message matches
  `[antd: …] … deprecated`, record it and fail the suite at teardown
  with the offending text. Non-deprecation console output passes
  through untouched.
- Verification: run the suite — zero deprecation warnings — then
  temporarily re-introduce a deprecated prop to prove the guard
  fails the run, and revert.

### W-3: Dependency refresh (portal)

- `package.json` + `npm install` per the spec's adopt table:
  antd → latest 6.x, @testing-library/react + dom → latest patches,
  typescript → 5.9.x, vite → latest 8.x paired with
  @vitejs/plugin-react → latest 6.x, vitest → latest 4.x, jsdom →
  latest 30.x, @types/node → latest ^22.x. Regenerate
  `package-lock.json` in the same step.
- `engines.node` bumps to `>=22.22.2` (jsdom 30's floor); confirm
  the Dockerfile's `node:22-alpine` build stage resolves at or above
  that floor and `tsc --noEmit && vite build` passes in the image
  build.
- Fix any type or config fallout from the bumps (e.g. vitest 4
  config shape, plugin-react 6 options) — fixes stay
  behavior-preserving.

### W-4: React 19 migration (portal)

- `react`, `react-dom` → 19.x; `@types/react`, `@types/react-dom` →
  19.x; reinstall and confirm zero peer warnings.
- Address anything React 19 tightens (types, removed legacy APIs)
  with behavior-preserving edits; list each in the delivery commit.
- Regression pass: full vitest suite, `tsc --noEmit`, production
  build.

## Verification

- Portal vitest suite green with the R-2 guard active and zero
  antd deprecation warnings in the output; `tsc --noEmit` and the
  image build green; `make verify` green at 0.24.0.
- Live check: deploy, then a browser walkthrough covering sign-in,
  a streamed chat turn, the session panel, Approvals (pending +
  history tabs), and the Documents drawer (digest tabs, expanded
  narrative, export) with no rendering or interaction regressions;
  screenshots filed under `.qoder/spec042-*.png`.

## Release

0.24.0 (minor) through the full train: version lockstep, living-state
docs, live check, feat commit, scan gate, annotated tag, push,
repowiki refresh as a separate docs commit.
