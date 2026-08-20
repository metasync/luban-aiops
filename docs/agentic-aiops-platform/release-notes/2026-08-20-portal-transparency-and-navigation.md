# Release Notes: 2026-08-20 — Portal Transparency and Navigation (SPEC-019)

## Summary

SPEC-019 turns the operator portal from a chat shell with auxiliary panels
into a transparent workspace. The sidebar is reorganized into labeled
sections (Chat standalone; **Control** for Incidents, Audit trail, and the
new Permissions view; **Workspace** for Tools, Skills, and Settings &
Debug), section headers hide themselves automatically when none of their
views are available to the signed-in role, and the version card collapses
into a chip beside the logo.

The centerpiece is a *live* permission matrix: platform-gateway gains
`GET /api/v1/policy/matrix`, which evaluates the exact policy bundle the
gateway enforces and returns a role × action allow/deny matrix with bundle
version and source. Operators no longer need to read YAML to learn what
they — or anyone else — can do; the portal Permissions view renders the
matrix with server-side scoping (`platform-admin` sees the full matrix,
every other role sees only its own row).

The workspace gains two read-only inventory views proxied through
platform-gateway: **Tools** lists the tool-gateway catalog (name,
description, category, risk level) via delegated operator tokens, and
**Skills** lists the skills-hub inventory via the platform-gateway's own
query credential. Two new policy actions — `policy:read` and `skills:read`
— join the deny-by-default bundle, granted to all five operational roles.

Two guardrails hold throughout: server-side enforcement remains the only
gate (portal visibility is convenience, never security), and the proxies
fail closed — unconfigured upstreams answer 503, transport failures 502,
upstream 4xx pass through verbatim.

`make verify` is green: all product suites pass (platform-gateway now at
137 tests including the new policy-matrix and workspace-proxy suites), all
four Kustomize overlays render cleanly, `validate-policy` confirms the
ten-rule deny-by-default bundle, and `validate-version` confirms lockstep.

## Change Set 1: Sectioned navigation and version consolidation (R-1)

### Highlights

- Sidebar navigation is grouped into sections: **Control** (Incidents,
  Audit trail, Permissions) and **Workspace** (Tools, Skills, Settings &
  Debug); Chat stays unsectioned above them
- Section headers hide automatically when every button in the section is
  hidden (role-based availability and signed-in gating keep the sidebar
  uncluttered for restricted roles)
- Permissions/Tools/Skills views require a signed-in user: signing out
  hides the nav entries and returns any of those views to Chat
- The sidebar version card is removed; the platform version renders as a
  chip inside the logo row (`Luban AIOps <version>`), one source, one place

### Why It Matters

- the portal now scales to more views without a flat list of buttons — new
  workspace surfaces slot into a section rather than reordering muscle
  memory
- consolidating version display removes a redundant card and keeps the
  version visible on every view without occupying vertical space

## Change Set 2: Live permission matrix (R-2, R-3)

### Highlights

- `GET /api/v1/policy/matrix` (platform-gateway): gated by the new
  `policy:read` action, evaluated against the *loaded enforced bundle* —
  never a copy or a cached document
- Response contract (`policy-matrix.schema.json` in shared-contracts):
  per-role action verdicts plus `bundle.version` and `bundle.source`
  (`configured` vs `packaged-default`) so provenance is visible
- Server-side scoping: `platform-admin` receives `scope: "full"` (every
  role); all other roles receive `scope: "own"` (their row only) — the
  endpoint cannot be coaxed into leaking other roles' permissions
- Degraded-bundle semantics: `PolicyLoadError` maps to 503 both in the
  enforcement step and in matrix construction — a broken bundle fails
  closed and visible, never as an unhandled 500
- Portal Permissions view: bundle provenance line (version, source, scope)
  and a roles × actions table with allow/deny badges; XSS-safe rendering
  (textContent only)

### Why It Matters

- authorization truth moves from static docs to the exact artifact the
  gateway enforces — docs and behavior cannot silently diverge
- operators can self-serve "why was I denied?" without reading policy YAML

## Change Set 3: Workspace inventory proxies (R-4)

### Highlights

- `GET /api/v1/tools` (platform-gateway → tool-gateway): obtains a
  delegated operator token (SPEC-008 chain), gated by `tools:list`;
  returns the tool catalog with name, description, category, and risk
  level
- `GET /api/v1/skills` (platform-gateway → skills-hub): uses the
  platform-gateway's own Basic query credential, gated by the new
  `skills:read` action; passes through `source` / `tag` filters and
  `offset` / `limit` (validated 1–100 before any upstream call)
- Uniform error mapping on both proxies: 503 when the upstream URL or the
  delegation chain is unconfigured, 502 on transport failure or upstream
  5xx, upstream 4xx forwarded with the upstream's own message
- Portal Tools and Skills views with refresh buttons, source/tag filter
  inputs on Skills, and a status line summarizing the fetched inventory;
  the Tools table uses fixed column geometry so the short category/risk
  columns are not starved by the free-form description column

### Why It Matters

- operators can audit "what can the agent touch?" (tools) and "what
  guidance is loaded?" (skills) from the same surface they chat in —
  transparency into both capability and grounding
- the skills proxy reuses the SPEC-014 query-credential vocabulary
  (platform-gateway joins tool-gateway as a registered `SKILLS_QUERY_CLIENTS`
  client) — no new token flows

## Change Set 4: Policy, docs, and dev-k8s wiring (R-5)

### Highlights

- Policy bundle grows from eight to ten rules: `allow-all-policy-read`
  and `allow-all-skills-read` grant the new actions to all five
  operational roles; the bundle syncs to all four consumer copies
- `architecture-overview.md` gains the new protected actions and rule
  rows plus the dual-gateway `tools:list` note; `authorization-matrix.md`
  gains a Live Matrix Transparency subsection pointing at the new
  endpoint and view
- `configuration-reference.md` documents the four new
  `PLATFORM_GATEWAY_*` settings (tool-gateway URL, skills-hub URL, skills
  client id/secret) and the updated skills-query registry contract
- dev-k8s: platform-gateway `runtime-config.env` carries the three new
  non-secret settings; `sync-skills-secrets.sh` now registers
  platform-gateway as a second skills query client, upserts
  `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET`, syncs both secrets, and rolls
  skills-hub and platform-gateway

### Why It Matters

- the deny-by-default invariant survives the expansion: every new action
  is explicit in the bundle and validated by `validate-policy`
- one script reproduces the whole skills-query wiring for a fresh cluster

## Validation

- `make verify` green: platform-gateway 137 tests (new
  `test_policy_matrix.py` and `test_workspace_proxies.py` suites plus the
  extended policy-engine boundary), all other product suites pass, four
  overlays render, ten-rule bundle validates, version lockstep holds
- Deployed to the dev cluster: all pods rolled out on the coordinated
  tag; `SKILLS_QUERY_CLIENTS` registry holds both clients; smoke tests
  confirm `/api/v1/policy/matrix`, `/api/v1/tools`, and `/api/v1/skills`
  are live and auth-gated (401 without credentials)
- One route fix folded in during delivery: the matrix route now catches
  `PolicyLoadError` raised by `enforce_policy`'s own bundle load, so a
  degraded bundle answers 503 instead of an unhandled 500 (recorded in
  the spec changelog)

## Known Limitations

- The matrix reflects policy only; effective access can still be narrowed
  by upstream service auth (e.g. skills-hub credential registry) — the
  matrix is the platform-gateway layer's truth
- Skills inventory is fetched with a fixed page size (limit 100); paging
  beyond one page is not surfaced in the portal yet
- The Tools view renders the catalog as data only — per-tool parameter
  schemas stay in the tool-gateway API

## Related Documents

- `../../specs/SPEC-019-portal-transparency-navigation/spec.md`
- `../../specs/SPEC-019-portal-transparency-navigation/plan.md`
- `../../specs/README.md` (spec index, SPEC-019 delivered)
- `../../../CHANGELOG.md`
