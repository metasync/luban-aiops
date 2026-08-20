# SPEC-019 Plan: Portal Transparency — Permission Matrix, Workspace Resources, and Navigation

## Approach

All backend work lands in `platform-gateway`; it already owns the portal-facing edge, the policy engine, the delegation client, and the audit/incidents proxy conventions this spec reuses. tool-gateway and skills-hub are consumed read-only and unchanged. The portal stays vanilla HTML/CSS/JS and gains three views (Permissions, Tools, Skills) plus the sectioned sidebar.

## R-2: Live permission matrix endpoint

- Extend `services/policy_engine.py`:
  - parse the bundle `version` field alongside the rules; expose `bundle_metadata(settings)` returning `{"version": int, "source": "configured"|"packaged-default"}` (a configured path that fails to load raises `PolicyLoadError` — no fallback, matching existing semantics);
  - add `ACTION_POLICY_READ` ("policy:read"), `ACTION_TOOLS_LIST` ("tools:list"), `ACTION_SKILLS_READ` ("skills:read") constants to `PROTECTED_ACTIONS`.
- New `services/policy_matrix.py::build_policy_matrix(settings, identity)`:
  - roles = sorted union of `roles_any` across loaded rules; actions = sorted union of rule actions ∪ `PROTECTED_ACTIONS`;
  - each cell evaluated via the existing `evaluate()` (one role at a time) so priority/explicit-deny/disabled semantics are inherited, never re-implemented;
  - scoping: `platform-admin` in caller roles → all rows, `scope: "full"`; otherwise only the caller's granted roles, `scope: "own"`;
  - payload includes metadata `version` + `source`.
- New contract `shared/shared-contracts/schemas/policy-matrix.schema.json` (draft 2020-12, `additionalProperties: false`, `$id` per existing convention) and mirror model `PolicyMatrixResponse` in `schemas/api.py`; contract pairs registered in `tests/test_contracts.py`.
- New `api/routes/policy.py`: `GET /api/v1/policy/matrix` → resolve identity → `enforce_policy(..., "policy:read")` → build matrix (`PolicyLoadError` → 503) → `log_event` → return.

## R-4: Workspace resource proxies

- `core/config.py` gains `tool_gateway_url`, `skills_hub_url`, `skills_client_id`, `skills_client_secret` (`PLATFORM_GATEWAY_*` env vocabulary, empty defaults like audit/incident settings).
- New `services/tool_gateway_client.py`: `list_tools(settings, request_id, delegated_token)` → `GET {tool_gateway_url}/api/v2/tools` with `Authorization: Bearer <delegated>`; incident-client error mapping (503 unconfigured, 502 transport/5xx, 4xx passthrough).
- New `services/skills_hub_client.py`: `list_skills(settings, request_id, params)` → `GET {skills_hub_url}/api/v1/skills` with Basic `(skills_client_id, skills_client_secret)`; same error mapping.
- New routes `api/routes/tools.py` (`GET /api/v1/tools`, `tools:list`) and `api/routes/skills.py` (`GET /api/v1/skills`, `skills:read`, offset/limit/source/tag passthrough):
  - tools route obtains a delegated token via the existing `obtain_delegated_token` (audience already `tool-gateway`) and 503s when the chain is unavailable — triage-route precedent;
  - routers registered in `api/router.py`; route inventory test gains the three new routes (the `/api/v2/`-absent guard stays intact).

## R-1 / R-3 / R-4 (portal)

- Sidebar restructured in `index.html`: Chat standalone; Control section (Incidents, Audit trail, Permissions); Workspace section (Tools, Skills, Settings & Debug). Section headers are muted labels; a section hides when every entry in it is hidden. Version chip moves into `.sidebar-logo`; `.version-card` removed.
- `app.js`: three new VIEWS with lazy load on activation (signed-out visitors get the sign-in prompt placeholder instead of a request); `syncResolvedUser()` toggles the new entries on authentication state and recomputes section visibility; matrix renders as role × action table with allow/deny badges (`status-badge success`/`denied`) plus scope/version/source meta; tools render name/title/description, skills render id/title/source/tags.
- `styles.css`: `.nav-section`/`.nav-section-label`/`.version-chip` additions, `.version-card` removal; matrix table reuses `.audit-table`. Cache-busting query strings bumped on both assets.

## R-5: Policy, docs, dev-k8s

- `policy-default.yaml` gains `allow-all-policy-read` and `allow-all-skills-read` (all five roles, priority 100); `make sync-policy` refreshes the two packaged copies and the overlay ConfigMap source.
- dev-k8s: platform-gateway `runtime-config.env` gains `PLATFORM_GATEWAY_TOOL_GATEWAY_URL`/`PLATFORM_GATEWAY_SKILLS_HUB_URL`/`PLATFORM_GATEWAY_SKILLS_CLIENT_ID`; `sync-skills-secrets.sh` registers `platform-gateway` in `SKILLS_QUERY_CLIENTS`, upserts `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` into the gateway secret, and restarts platform-gateway; secrets example files updated.
- Docs: `authorization-matrix.md` (new actions + live-matrix pointer), `configuration-reference.md` (platform-gateway env + skills chain note), `products/operator-portal/README.md`.

## Test strategy

- `tests/test_policy_matrix.py`: admin full scope vs own-rows scoping, deny-by-default for ungranted role (403 at the route), disabled-rule and explicit-deny semantics via temp bundle files, configured vs packaged source reporting, `PolicyMatrixResponse` validating against the JSON schema.
- `tests/test_workspace_proxies.py`: fake-httpx pattern from `test_incidents_proxy.py` — tools: delegated bearer forwarded, 503 when delegation unavailable/unconfigured, 502 on transport error, 4xx passthrough; skills: Basic credential forwarded, params passthrough, 503 unconfigured, 502/passthrough mapping.
- Route inventory + contract tests updated; `make verify` as the gate.

## Sequencing

1. Contracts + policy bundle rules → 2. gateway engine/service/routes/clients → 3. gateway tests → 4. portal (html/css/js) → 5. dev-k8s wiring + sync scripts → 6. docs + delivery gate.

## Decisions

- Matrix rows are evaluated one role at a time so the rendered cell equals what `enforce_policy` would decide for that role — no parallel evaluation logic.
- Permissions/Tools/Skills nav entries require an authenticated session (all five roles are granted the actions); signed-out visitors see the sign-in prompt in-view, matching R-3.
- Tools proxy fails closed (503) without delegation rather than serving an unauthenticated catalog — the downstream requires operator authority and the gateway must not widen it.
