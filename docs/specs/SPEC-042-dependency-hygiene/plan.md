# SPEC-042 Implementation Plan

## Approach

Two coupled portal passes plus one backend pass. Portal: migrate the
three deprecated antd call sites and lock the posture with a vitest
guard (R-1/R-2), then apply the recorded adopt set — including the
React 19 migration — and run one consolidated portal regression pass
(suite + tsc + image build + live walkthrough) over the refreshed
tree (R-3/R-4). Backend: re-lock every product inside its declared
ranges to the latest stable versions, adjudicate the cryptography
caps, and verify the agentscope kernel patch with the full gate plus
a live HITL/mutating check (R-5). All adoptions are latest stable —
no alpha, beta, RC, or dev versions. No new services, routes, policy
actions, or audit event types. Version lockstep to 0.24.0.

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

### W-3: Portal dependency refresh

- `package.json` + `npm install` per the spec's adopt table:
  antd → latest stable 6.x, @testing-library/react + dom → latest
  stable patches, typescript → latest stable 5.9.x, vite → latest
  stable 8.x paired with @vitejs/plugin-react → latest stable 6.x,
  vitest → latest stable 4.x, jsdom → latest stable 30.x, @types/node
  → latest stable ^22.x. Regenerate `package-lock.json` in the same
  step; confirm no resolved version is a prerelease.
- `engines.node` bumps to `>=22.22.2` (jsdom 30's floor); confirm
  the Dockerfile's `node:22-alpine` build stage resolves at or above
  that floor and `tsc --noEmit && vite build` passes in the image
  build.
- Fix any type or config fallout from the bumps (e.g. vitest 4
  config shape, plugin-react 6 options) — fixes stay
  behavior-preserving.

### W-4: React 19 migration (portal)

- `react`, `react-dom` → latest stable 19.x; `@types/react`,
  `@types/react-dom` → 19.x; reinstall and confirm zero peer
  warnings.
- Address anything React 19 tightens (types, removed legacy APIs)
  with behavior-preserving edits; list each in the delivery commit.
- Regression pass: full vitest suite, `tsc --noEmit`, production
  build.

### W-5: Backend stable-channel re-lock

- Run `uv lock` in every Python product; each lockfile floats to the
  latest stable inside its declared ranges (headline: agentscope
  2.0.6 → 2.0.7.post1 in agent-platform, fastapi → 0.141.1, uvicorn
  → 0.52.4; the rest are already latest stable). Verify no lockfile
  resolves a prerelease.
- **Cryptography cap adjudication**: review the JWT/signing call
  sites in the six products declaring `cryptography>=43.0,<45.0`
  (identity-broker token work, audit-service, incident-service,
  platform-gateway, skills-hub, tool-gateway). If the call sites are
  compatible with the latest stable major, raise the caps together
  and re-lock; otherwise keep `<45.0` and record the reason in the
  spec changelog.
- Redis (`<7.0`) and elasticsearch (`<9.0`) caps stay as-is with the
  reasons recorded in the spec — no code work.
- agentscope is the runtime kernel: after the re-lock, run the full
  agent-platform suite, then `make verify`, then a live check of the
  chat, HITL confirmation, and approved-mutating paths
  (`mutating-demo.sh` with the HITL leg) before anything ships.

## Verification

- Portal vitest suite green with the R-2 guard active and zero
  antd deprecation warnings in the output; `tsc --noEmit` and the
  image build green.
- All eight Python product suites green under frozen sync after the
  re-lock; `make verify` green at 0.24.0.
- Live check: deploy, then a browser walkthrough covering sign-in,
  a streamed chat turn, the session panel, Approvals (pending +
  history tabs), and the Documents drawer (digest tabs, expanded
  narrative, export) with no rendering or interaction regressions;
  plus `mutating-demo.sh` (incl. HITL leg) green to cover the
  agentscope kernel bump; screenshots filed under
  `.qoder/spec042-*.png`.

## Release

0.24.0 (minor) through the full train: version lockstep, living-state
docs, live check, feat commit, scan gate, annotated tag, push,
repowiki refresh as a separate docs commit.
