# SPEC-042 Tasks: Portal Dependency Hygiene

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Migration off deprecated antd v6 APIs

- [ ] Drawer `width` → `size` on the two navigation drawers (`products/operator-portal/.../App.tsx`, 230px and 260px)
- [ ] Drawer `width` → `size` on the document drawer (`products/operator-portal/.../views/workspace/DocumentsView.tsx`, 560px)
- [ ] Alert `message` → `title` across the fifteen sites in nine files (App, ChatView, DocumentsView, AuditView, SkillsView, ApprovalsView, ToolsView, PermissionsView, IncidentsView)
- [ ] Grep audit: no Drawer `width=` and no Alert `message=` remain under `src/`; vitest output shows zero antd deprecation warnings

## R-2: Deprecation regression guard

- [ ] vitest setup intercepts console output and fails the run on any `[antd: …] … deprecated` warning, reporting the offending text (`products/operator-portal/web-ui/app`)
- [ ] Prove the guard: temporarily re-introduce a deprecated prop, confirm the suite fails, revert

## R-3: Managed component refresh

- [ ] Bump adopt set: antd latest 6.x, @testing-library/react + dom patches, typescript 5.9.x, vite 8.x + @vitejs/plugin-react 6.x, vitest 4.x, jsdom 30.x, @types/node latest ^22.x; regenerate `package-lock.json` (`products/operator-portal/web-ui/app`)
- [ ] `engines.node` → `>=22.22.2`; confirm the Dockerfile node stage satisfies it
- [ ] Resolve type/config fallout from the bumps behavior-preservingly (vitest 4 config, plugin-react 6)
- [ ] `tsc --noEmit`, vitest suite, and `npm run build` green on the refreshed set

## R-4: React 19 migration

- [ ] react + react-dom → 19.x, @types/react + @types/react-dom → 19.x; zero peer warnings on install (`products/operator-portal/web-ui/app`)
- [ ] Behavior-preserving edits for anything React 19 tightens; each listed in the delivery commit
- [ ] Regression pass: full vitest suite, `tsc --noEmit`, production build

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified
- [ ] live browser walkthrough green (sign-in, streamed chat turn, session panel, Approvals, Documents drawer incl. expanded narrative and export); screenshots under `.qoder/spec042-*.png`
- [ ] living state docs updated (see spec `Impact` section)
- [ ] `CHANGELOG.md` entry added referencing the spec ID
- [ ] spec index in `docs/specs/README.md` updated
- [ ] spec status set to `delivered`
