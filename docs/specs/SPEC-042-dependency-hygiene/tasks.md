# SPEC-042 Tasks

## R-1: Migration off deprecated antd v6 APIs

- [ ] Migrate the two `App.tsx` navigation drawers from `width` to
      `size` (230px, 260px)
- [ ] Migrate the `DocumentsView.tsx` document drawer from `width`
      to `size` (560px)
- [ ] Migrate all fifteen `Alert message` sites to `title` across
      the nine view files
- [ ] Grep audit: no `width=` Drawer or `message=` Alert remains
      under `src/`
- [ ] Suite green with zero antd deprecation warnings in the output

## R-2: Deprecation regression guard

- [ ] Add the vitest setup guard failing on any `[antd: …] …
      deprecated` console warning
- [ ] Prove the guard: re-introduce a deprecated prop, confirm the
      suite fails, revert
- [ ] Confirm non-deprecation console output still passes through

## R-3: Managed portal component refresh

- [ ] Apply the adopt table (antd latest stable 6.x, testing-library
      patches, TypeScript latest stable 5.9.x, vite latest stable 8.x
      + plugin-react latest stable 6.x, vitest latest stable 4.x,
      jsdom latest stable 30.x, @types/node latest stable ^22.x);
      regenerate the lockfile; confirm no prerelease resolves
- [ ] Bump `engines.node` to `>=22.22.2`; confirm the Dockerfile
      node stage satisfies the floor
- [ ] Fix any type/config fallout from the bumps (behavior-preserving
      only)
- [ ] `tsc --noEmit`, vitest suite, and image build green on the
      refreshed set

## R-4: React 19 migration

- [ ] Move react/react-dom/@types to the latest stable 19.x line;
      zero peer warnings
- [ ] Behavior-preserving edits for anything React 19 tightens,
      listed in the delivery commit
- [ ] Suite + tsc + production build green
- [ ] Live walkthrough: sign-in, streamed chat turn, session panel,
      Approvals, Documents drawer — no regressions

## R-5: Backend stable-channel lockfile refresh

- [ ] `uv lock` in all eight Python products; each lock carries the
      latest stable version its range allows (agentscope 2.0.6 →
      2.0.7.post1, fastapi → 0.141.1, uvicorn → 0.52.4); no
      prerelease resolves
- [ ] Cryptography cap adjudication: review the signing call sites
      in the six declaring products; raise to the latest stable
      major or keep `<45.0` with the reason recorded in the spec
      changelog
- [ ] Confirm redis (`<7.0`) and elasticsearch (`<9.0`) caps stay
      with the recorded reasons; no range changes beyond the
      adjudication
- [ ] Agent-platform suite green, then `make verify` green, then
      live check of chat + HITL confirmation + approved-mutating
      paths (`mutating-demo.sh` incl. HITL leg) covering the
      agentscope kernel bump

## Delivery Gate

- [ ] Version lockstep to 0.24.0 (VERSION, eight pyprojects,
      metadata files, lockfiles) green under `make validate-version`
- [ ] Living-state docs: CHANGELOG, release note + index, spec
      index, delivery-roadmap
- [ ] `make build` + `make verify` green; deploy to dev-k8s
- [ ] Live browser walkthrough + screenshots under
      `.qoder/spec042-*.png`
- [ ] feat commit → scan gate → annotated tag v0.24.0 → push;
      repowiki refresh as a separate docs commit
