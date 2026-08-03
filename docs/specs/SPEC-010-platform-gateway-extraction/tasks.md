# SPEC-010 Tasks: Platform Gateway Extraction

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: New `platform-gateway` product carrying the portal edge

- [x] scaffold `products/platform-gateway/`: `pyproject.toml` (script
  `platform-gateway = platform_gateway.main:run`), `Makefile`
  (IMAGE_NAME `platform-gateway`), `Dockerfile`, `.python-version`
- [x] move edge modules into `src/platform_gateway/`: core
  (config/dependencies/metrics/observability/request_context/runtime/
  telemetry), services (token_verifier, policy_engine, agent_client,
  delegation_client), routes (chat, sessions, auth, identity, runtime,
  health), app/main/metadata, chat+session schemas, packaged
  `policies/policy-default.yaml`
- [x] rename edge config keys to `PLATFORM_GATEWAY_*`
  (`REQUIRE_AUTH`, `DEV_USER`, `POLICY_PATH`, `TOKEN_AUDIENCE` default
  `platform-gateway`, `DELEGATION_AUDIENCE`, `SERVICE_CLIENT_ID` default
  `platform-gateway`, `SERVICE_CLIENT_SECRET`, `WORKLOAD_TOKEN_PATH`,
  `DEV_SIGNING_KEY_PATH`)
- [x] move the edge half of the gateway test suite (app/routes, policy,
  token verification, delegation, contracts, observability) with env
  names updated; suite green under `uv run pytest`

## R-2: `tool-gateway` reduced to the tool/connector home

- [x] rename package `src/api_gateway` → `src/tool_gateway` (imports,
  scripts entry, Dockerfile `CMD`, Makefile IMAGE_NAME `tool-gateway`,
  metadata name)
- [x] delete the edge surface: chat/sessions/auth/identity routes,
  agent_client, delegation_client, chat/session schemas, edge config
  keys, and their tests
- [x] reduce `gateway_service`/router to the tool surface (tools routes,
  runtime, health, metrics); tool verification keeps `aud = tool-gateway`
- [x] add a route-inventory test asserting no `/api/v1/chat` or
  `/api/v1/sessions` surface remains; tool suite green

## R-3: Identity plumbing across the new boundary

- [x] broker: `IDENTITY_TOKEN_AUDIENCE` default `tool-gateway` →
  `platform-gateway`; update broker tests (issued tokens, exchange
  subject validation)
- [x] broker: service-client registry entry renames to
  `platform-gateway:<secret>:tool-gateway`; delegated tokens carry
  `act.sub = platform-gateway`; exchange tests updated
- [x] contracts: `identity-token.schema.json` aud description names both
  audiences; contract tests bind both services
- [x] edge: dev subject token minted with `aud = [platform-gateway]`;
  verifier default audience `platform-gateway`

## R-4: Overlay, build, and deployment alignment

- [x] root `Makefile`: `PYTHON_PRODUCTS`/`IMAGE_PRODUCTS` gain
  `platform-gateway`; `.images.env` entries `PLATFORM_GATEWAY_IMAGE` +
  `TOOL_GATEWAY_IMAGE` replace `API_GATEWAY_IMAGE`; kind-load list
  updated
- [x] dev-k8s: new `base/platform-gateway/` (deployment, service,
  runtime-config.env, runtime-secrets.example.env); policy ConfigMap
  `gateway-policy` → `platform-policy` from `base/shared/policy.yaml`,
  mounted on both gateway deployments
- [x] dev-k8s: `base/tool-gateway/` becomes the tool service
  (deployment/service `tool-gateway`, image `luban-aiops/tool-gateway`,
  env keeps `GATEWAY_*` tool settings only, delegation secrets removed);
  `rbac.yaml` renames `api-gateway*` → `tool-gateway*`
- [x] dev-k8s: broker `IDENTITY_TOKEN_AUDIENCE=platform-gateway` in
  runtime-config.env; secrets example registers the `platform-gateway`
  client; `agent-platform` `TOOL_GATEWAY_URL=http://tool-gateway:8000`
- [x] `deploy-overlay.sh` sets images/rollouts for `platform-gateway` and
  `tool-gateway` (drops `api-gateway`); portal `nginx.conf` proxies to
  `platform-gateway:8000`
- [x] `.github/CODEOWNERS` gains `/products/platform-gateway/`
- [x] `make verify` green (all suites + all overlays render)

## R-5: Living-state docs advanced

- [x] new `products/platform-gateway/README.md`; rewritten
  `products/tool-gateway/README.md`; identity-broker README wording
- [x] workspace docs: `workspace-model.md`, `product-boundaries.md`,
  `backend-service-layout-convention.md`, `github-repository-governance.md`
  gain/adjust the `platform-gateway` product
- [x] dev-k8s README: service list, wiring, secrets, SPEC-009 sections
  updated for the two services; one-time `api-gateway` cleanup command
  documented
- [x] root `README.md` product list and current state; identity design
  doc service list

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (`make verify` green)
- [x] `CHANGELOG.md` entry added referencing SPEC-010
- [x] spec index in `docs/specs/README.md` updated
- [x] spec status set to `delivered`
