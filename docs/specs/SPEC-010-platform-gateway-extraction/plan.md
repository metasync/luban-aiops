# SPEC-010 Plan: Platform Gateway Extraction

## Approach

A mechanical, behavior-preserving extraction delivered in five stages so
each stage stays verifiable. The code moves; the behavior does not. All
four naming questions were resolved in favor of the clean rename shipped
together (spec.md Changelog 2026-07-30), so the plan treats renames as
first-class work items, not follow-ups.

Two naming conventions fixed up front:

- **Python packages**: the new edge product uses `platform_gateway`;
  `tool-gateway`'s package renames `api_gateway` → `tool_gateway`
  (imports, `[project.scripts]`, Dockerfile `CMD`, per-product Makefile
  `IMAGE_NAME`).
- **Env prefixes**: edge settings use `PLATFORM_GATEWAY_*`; `GATEWAY_*`
  remains only for tool-gateway's tool-scoped settings (`GATEWAY_K8S_*`,
  `GATEWAY_POLICY_PATH`, `GATEWAY_REDACTION_*`). Shared settings
  (`IDENTITY_SERVICE_URL`, `OTEL_*`) keep their names on both sides.

Deliberately kept simple: the policy bundle stays one shared file loaded
by both services; metric names keep their current `gateway_*` /
`delegation_*` spellings (metrics are a scrape contract; renaming is out
of scope); no shared-sdk packaging.

## Design Per Requirement

### R-1: New `platform-gateway` product carrying the portal edge

- affected files: new `products/platform-gateway/` — `pyproject.toml`
  (name `platform-gateway`, script `platform-gateway =
  platform_gateway.main:run`), `Makefile` (IMAGE_NAME
  `platform-gateway` from the shared `mk/` fragments), `Dockerfile`
  (same uv base image, `CMD ["uv", "run", "platform-gateway"]`),
  `.python-version`, `README.md`, `src/platform_gateway/`
- modules moved intact from `tool-gateway`:
  - `core/`: `config.py` (edge subset, `PLATFORM_GATEWAY_*`),
    `dependencies.py`, `metrics.py` (policy/verification/delegation
    counters), `observability.py`, `request_context.py`, `runtime.py`,
    `telemetry.py`
  - `services/`: `token_verifier.py`, `policy_engine.py`,
    `agent_client.py`, `delegation_client.py`
  - `api/routes/`: `chat.py`, `sessions.py`, `auth.py`, `identity.py`,
    `runtime.py`, `health.py`; `app.py`, `main.py`, `metadata.py`
    (service name `platform-gateway`), `schemas/api.py` (chat/session
    models), packaged `policies/policy-default.yaml` copy
- config mapping (old → new): `GATEWAY_REQUIRE_AUTH`,
  `GATEWAY_DEV_USER`, `GATEWAY_POLICY_PATH`, `GATEWAY_TOKEN_AUDIENCE`
  (default changes to `platform-gateway`), `GATEWAY_DELEGATION_AUDIENCE`
  (stays `tool-gateway`), `GATEWAY_SERVICE_CLIENT_ID` (default
  `platform-gateway`), `GATEWAY_SERVICE_CLIENT_SECRET`,
  `GATEWAY_WORKLOAD_TOKEN_PATH`, `GATEWAY_DEV_SIGNING_KEY_PATH` →
  `PLATFORM_GATEWAY_*`; `CHAT_RESPONSE_TIMEOUT_SECONDS` unchanged
- tests: the edge half of today's gateway suite moves with the code
  (app/route tests, policy enforcement on chat/session, token
  verification, delegation suite, contracts for chat/session schemas,
  observability), with env names updated

### R-2: `tool-gateway` reduced to the tool/connector home

- affected files: `products/tool-gateway/` — package rename
  `src/api_gateway` → `src/tool_gateway`, all `api_gateway` imports and
  `[project.scripts]` → `tool_gateway = tool_gateway.main:run`,
  Dockerfile `CMD`, `Makefile` IMAGE_NAME → `tool-gateway`, metadata
  name `tool-gateway`
- removed: `api/routes/chat.py`, `sessions.py`, `auth.py`,
  `identity.py`; `services/agent_client.py`, `delegation_client.py`;
  the chat/session schemas in `schemas/api.py`; the edge config keys and
  their tests; `api/router.py` shrinks to tools + health/runtime/metrics
- retained unchanged in behavior: `tools/` (base, registry,
  k8s_connector, redaction), `api/routes/tools.py`, `services/
  gateway_service.py` reduced to the tool-invocation orchestration
  (invoke choke point, redaction, audit, readiness), `token_verifier`
  stays (delegated-token verification, `aud = tool-gateway`),
  `policy_engine` stays (actions `tools:list` / `tools:invoke`),
  `GATEWAY_K8S_*` / `GATEWAY_POLICY_PATH` / `GATEWAY_REDACTION_*`
- route-inventory proof: an app-level test asserts the tool-gateway app
  exposes only `/api/v2/tools*`, `/api/v1/runtime`, health, and metrics
  (no `/api/v1/chat`, no `/api/v1/sessions`)
- config guard: `GATEWAY_TOKEN_AUDIENCE` default stays `tool-gateway`

### R-3: Identity plumbing across the new boundary

- affected files: `products/identity-broker/src/identity_service/core/
  config.py` (`IDENTITY_TOKEN_AUDIENCE` default `tool-gateway` →
  `platform-gateway`), broker tests; edge `token_verifier` default
  audience; `shared/shared-contracts/schemas/identity-token.schema.json`
  (aud description updated to name both audiences: platform tokens bind
  `platform-gateway`, delegated tokens bind `tool-gateway`)
- flow after the split:
  1. portal presents a platform JWT (`aud = platform-gateway`) to the
     edge; the edge verifies issuer + audience
  2. the edge exchanges at the broker as client `platform-gateway`
     (static secret or projected workload token per SPEC-009), requesting
     audience `tool-gateway`; broker maps the client registry entry
     `platform-gateway:<secret>:tool-gateway`
  3. delegated token: `sub` = user, `roles` copied, `act.sub` =
     `platform-gateway`, `aud = tool-gateway` — the tool side's claim
     shape is unchanged
  4. `agent-platform` relays it on `/api/v2/tools*`; tool-gateway
     verifies exactly as today
- dev synthetic identity: the edge mints the dev subject token with
  `aud = [platform-gateway]`; the broker's dev trust path is unchanged
- policy: one shared `policy-default.yaml` (all five actions) stays
  packaged in both services and mounted via one ConfigMap; each service
  enforces only the actions its routes carry — deny-by-default covers
  the rest. No grants added or removed

### R-4: Overlay, build, and deployment alignment

- affected files: root `Makefile` (`PYTHON_PRODUCTS` and
  `IMAGE_PRODUCTS` gain `platform-gateway`; `.images.env` entries become
  `PLATFORM_GATEWAY_IMAGE` and `TOOL_GATEWAY_IMAGE`, replacing
  `API_GATEWAY_IMAGE`; kind-load list updated),
  `shared/platform-ops/gitops/deploy-overlay.sh` (deployment/image names
  `platform-gateway` and `tool-gateway`),
  `shared/platform-ops/gitops/dev-k8s/`:
  - `base/platform-gateway/`: `platform-gateway-deployment.yaml`,
    `platform-gateway-service.yaml` (port 8000), `runtime-config.env`
    (`AGENT_SERVICE_URL`, `IDENTITY_SERVICE_URL`,
    `PLATFORM_GATEWAY_REQUIRE_AUTH=true`,
    `PLATFORM_GATEWAY_POLICY_PATH=/etc/luban/policy/policy.yaml`,
    `PLATFORM_GATEWAY_TOKEN_AUDIENCE=platform-gateway`,
    `PLATFORM_GATEWAY_DELEGATION_AUDIENCE=tool-gateway`,
    `PLATFORM_GATEWAY_SERVICE_CLIENT_ID=platform-gateway`),
    `runtime-secrets.example.env` (`PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET`,
    workload-token note carried from the SPEC-009 text)
  - `base/tool-gateway/`: deployment/service renamed to `tool-gateway`
    (image `luban-aiops/tool-gateway:dev-local`), `runtime-config.env`
    keeps `GATEWAY_K8S_*`, `GATEWAY_POLICY_PATH`,
    `GATEWAY_TOKEN_AUDIENCE=tool-gateway`; the delegation credential
    entries are removed; `rbac.yaml` renames SA/Role/RoleBinding
    `api-gateway*` → `tool-gateway*`
  - policy ConfigMap `gateway-policy` → `platform-policy`, sourced from
    `base/shared/policy.yaml`, mounted read-only at `/etc/luban/policy`
    on both deployments; `kustomization.yaml` updated
  - `base/agent-platform/runtime-config.env`: `TOOL_GATEWAY_URL` →
    `http://tool-gateway:8000`
  - `base/identity-broker/runtime-config.env`: `IDENTITY_TOKEN_AUDIENCE`
    → `platform-gateway`; the secrets example documents the
    `platform-gateway` client registry entry replacing `tool-gateway`
- `products/operator-portal/nginx.conf`: `proxy_pass` →
  `http://platform-gateway:8000`
- `.github/CODEOWNERS`: add `/products/platform-gateway/
  @metasync/platform-security`
- smoke contract (manual after deploy, scripted checks in the README):
  SSO login → portal shell → session create → streamed chat → tool
  invocation through the relayed delegated token

### R-5: Living-state docs advanced

- affected files: root `README.md` (product list, current state),
  `products/platform-gateway/README.md` (new — edge surface, env knobs,
  observability), `products/tool-gateway/README.md` (rewritten for the
  connector mandate), `products/identity-broker/README.md` (audience and
  client registry wording), `docs/workspace/workspace-model.md` and
  `product-boundaries.md` (add `platform-gateway` product entry; the
  boundary table already matches the post-split tool-gateway mandate),
  `docs/workspace/backend-service-layout-convention.md` and
  `product-structure-review.md` references, `docs/agentic-aiops-platform/
  identity-and-authorization-design.md` (service list),
  `docs/workspace/github-repository-governance.md` (labels/ownership),
  `CHANGELOG.md`, spec index
- dev-k8s README: service list, wiring text, secrets section, and
  verify commands updated for the two services; the SPEC-009
  redaction/workload sections move their gateway wording to
  platform-gateway where the concern now lives

## Sequencing And Dependencies

1. Stage 1 — scaffold `products/platform-gateway` and move the edge
   (R-1) — depends on nothing
2. Stage 2 — reduce and rename `tool-gateway` (R-2) — depends on Stage 1
   (the edge code must exist at its new home before deletion)
3. Stage 3 — identity plumbing: broker audience/client rename, edge
   verifier default, schema note, contract tests (R-3) — depends on
   Stages 1–2 for the test targets
4. Stage 4 — overlays, Makefile, nginx, deploy script, CODEOWNERS (R-4)
   + full `make verify` — depends on Stages 1–3
5. Stage 5 — living-state docs + delivery docs (R-5) — depends on Stage 4
6. Delivery — CHANGELOG, spec index/status, commit — depends on Stage 5

Stages 1 and 2 land together in working-tree terms (one intermediate
state where both products compile and their suites pass) because the
package rename on the tool side and the move on the edge side share no
code but share the verify gate.

## Test Strategy

- platform-gateway suite (moved + renamed tests): app/route parity for
  chat/sessions/auth/identity/runtime, policy deny-by-default on portal
  actions, token verification with `aud = platform-gateway`, delegation
  cache/fallback/workload preference, contracts for chat/session schemas
- tool-gateway suite (retained tests): tool invoke/discovery authorization,
  redaction (SPEC-009 suite moves nowhere — it stays), policy on tool
  actions, contracts, observability; new route-inventory test proving the
  portal surface is gone
- identity-broker suite: audience default change (platform tokens mint
  `aud = platform-gateway`), client registry entry rename (`act.sub =
  platform-gateway`), exchange subject-token audience validation update
- overlay validation: `kustomize build` renders all overlays (part of
  `make verify`); the end-to-end dev smoke path is documented, not
  automated

## Rollout And Migration

- deployment changes: the dev overlay gains the platform-gateway and
  tool-gateway deployments and drops `api-gateway`; a redeploy is a
  fresh `make build && make deploy` (the old deployment is removed by
  the kustomize apply delta — documented as a one-time
  `kubectl delete deployment/api-gateway service/api-gateway` cleanup in
  the README since kustomize does not prune removed resources)
- backward compatibility: HTTP contract shapes are unchanged for portal
  and agent-platform callers; broker-issued tokens change audience, so
  the broker and the edge must deploy together (single overlay apply)
- rollback: revert the overlay + images commit; token audiences revert
  with the broker config in the same fragment
