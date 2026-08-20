# SPEC-019 Tasks: Portal Transparency — Permission Matrix, Workspace Resources, and Navigation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Sectioned sidebar navigation and version consolidation

- [x] Restructure sidebar into Chat / Control / Workspace sections with auto-hiding section headers (`products/operator-portal/web-ui/index.html`, `styles.css`)
- [x] Move version chip into logo row; remove `.version-card` (`products/operator-portal/web-ui/index.html`, `app.js`, `styles.css`)
- [x] Update view/nav wiring and section visibility logic in `showView`/`syncResolvedUser` (`products/operator-portal/web-ui/app.js`)
- [x] Bump cache-busting query strings for `app.js`/`styles.css` (`products/operator-portal/web-ui/index.html`)

## R-2: Live permission matrix endpoint

- [x] Add `policy-matrix.schema.json` response contract (`shared/shared-contracts/schemas/`)
- [x] Implement matrix derivation from loaded policy bundle via policy engine (`products/platform-gateway/src/platform_gateway/services/`)
- [x] Add `GET /api/v1/policy/matrix` route with `policy:read` enforcement and server-side role scoping (`products/platform-gateway/src/platform_gateway/api/routes/`)
- [x] Tests: scoping (admin full vs own rows), deny-by-default, disabled-rule/explicit-deny semantics, fallback-source reporting, contract binding (`products/platform-gateway/tests/`)

## R-3: Portal Permissions view

- [x] Add Permissions view + Control-section entry visible to all signed-in users (`products/operator-portal/web-ui/index.html`, `app.js`)
- [x] Render role × action matrix table with allow/deny badges, scope/version/source metadata, error states (`products/operator-portal/web-ui/app.js`, `styles.css`)

## R-4: Workspace resource views — Tools catalog and Skills inventory

- [x] Add tool-gateway and skills-hub settings to platform-gateway frozen settings (`products/platform-gateway/src/platform_gateway/core/config.py`)
- [x] Implement `GET /api/v1/tools` proxy to tool-gateway `GET /api/v2/tools` with delegated token (`tools:list`) (`products/platform-gateway/src/platform_gateway/api/routes/`)
- [x] Implement `GET /api/v1/skills` proxy to skills-hub `GET /skills` with query credential (`skills:read`) (`products/platform-gateway/src/platform_gateway/api/routes/`)
- [x] Tests: proxy success passthrough, 4xx passthrough, 502 on outage, 503 on unset config (`products/platform-gateway/tests/`)
- [x] Add Tools and Skills views to Workspace section with list/empty/error states (`products/operator-portal/web-ui/index.html`, `app.js`, `styles.css`)

## R-5: Policy, documentation, and verification sync

- [x] Add `policy:read` and `skills:read` rules to `policy-default.yaml`; `make sync-policy` (`shared/shared-contracts/policies/`)
- [x] Document new actions and live-matrix pointer in `authorization-matrix.md` (`docs/agentic-aiops-platform/`)
- [x] Document new platform-gateway settings and dev-k8s wiring in `configuration-reference.md` (`docs/guides/`)
- [x] Extend platform-gateway deployment env / skills secret wiring in dev-k8s overlay if needed (`shared/platform-ops/gitops/dev-k8s/`)
- [x] Update `products/operator-portal/README.md` with new sections and views
- [x] `make verify` green (all suites, overlays, policy and version gates)

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified
- [x] living state docs updated (see spec `Impact` section)
- [x] `CHANGELOG.md` entry added referencing the spec ID
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
