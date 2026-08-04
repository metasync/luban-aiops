# Changelog

All notable changes to this repository are documented in this file.

The format is intentionally lightweight during the current pre-release phase.
Entries are grouped by workspace-level implementation milestones rather than
published product versions.

## Unreleased

### Changed — SPEC-010 code-review follow-ups

- platform-gateway `/health/ready` now verifies the policy bundle loads
  (reports a `policy_rules` count when ok; `status: degraded` with
  `policy_error` on `PolicyLoadError` instead of silently reporting ok).
- tool-gateway protected-action vocabulary corrected to the actual routes
  (`tools:list` / `tools:invoke`); regression tests added for the readiness
  degradation path.

### Changed — Shared `base-uv` container base image and non-root enforcement

- New shared Python base image `luban-aiops/base-uv:al2023`
  (`shared/base-images/base-uv/Dockerfile`): Amazon Linux 2023 minimal with
  a pinned uv (`UV_VERSION` ARG, default 0.12.1 — never `latest`), no system
  Python (uv resolves the interpreter from each product's `.python-version`
  during `uv sync`; `UV_PYTHON`/`PYTHON_VERSION` ARG default 3.12 is the
  deterministic fallback), and a non-root `app` user (uid 1000). Built by
  the new `make base-images` target, wired as a prerequisite of `make build`
  (overridable: `make base-images BASE_UV_UV_VERSION=...`).
- All four Python product Dockerfiles (`agent-platform`, `identity-broker`,
  `platform-gateway`, `tool-gateway`) now build `FROM luban-aiops/base-uv:al2023`;
  the env contract, `WORKDIR`, and `USER` move into the base, replacing the
  divergent bookworm-slim and ad-hoc amazonlinux bootstrap.
- operator-portal switches to `nginxinc/nginx-unprivileged:1.27-alpine` and
  listens on 8080 (nginx.conf, deployment containerPort, web-ui Service
  port/targetPort, dev-k8s README port-forward).
- All five app deployments gain a non-root `securityContext`
  (`runAsNonRoot`, `runAsUser` 1000 — 101 for web-ui,
  `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`).
- Docs: `python-container-strategy.md` records the Option B migration as
  executed; backend layout convention updated.

### Changed — Explicit target platform for image builds

- New `IMAGE_PLATFORM` build parameter (default `linux/amd64`, the deployment
  target) in the root `Makefile` and `mk/image.mk`: applied to
  `make base-images` and forwarded to every product build, so base and product
  images always share one platform. Override per build, e.g.
  `make build IMAGE_PLATFORM=linux/arm64` for native local/kind builds on
  arm64 hosts.

### Changed — Build configuration extracted to `mk/defaults.mk`

- New `mk/defaults.mk` is the single source of truth for overridable build
  settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`,
  `REGISTRY`, `AUTO_LOAD_KIND`/`KIND_CLUSTER_NAME`, `BASE_UV_*`), included by
  the root `Makefile` and by `mk/image.mk`, so root-driven and standalone
  product builds resolve identical defaults. All values use `?=`, so
  command-line overrides still win; `mk/` fragments keep processing logic
  only. `IMAGE_TAG` and `IMAGE_CONTEXT` intentionally stay in `mk/image.mk`
  (computed fallback / per-product hook).

### Changed — SPEC-010: Platform Gateway Extraction (ADR-0005)

- Split the former combined gateway into two products with the boundaries
  ADR-0005 assigns: new `products/platform-gateway` owns the portal-facing
  edge (token verification for portal sessions, action policy, chat/session
  proxying, broker delegation client, `/api/v1` portal routes); the existing
  product renames its package `api_gateway` → `tool_gateway` and keeps only
  the tool/connector home (`ToolRegistry`, connectors, `tools:list` /
  `tools:invoke`, redaction choke point, tool audit). HTTP contract shapes,
  deny-by-default policy, and audit fields are unchanged.
- env contract (Q-1): edge settings rename `GATEWAY_*` → `PLATFORM_GATEWAY_*`;
  `GATEWAY_*` stays tool-scoped only (k8s, policy path, redaction, token
  audience, auth knobs, host/port).
- k8s (Q-2): `api-gateway` deployment/service/image rename to
  `platform-gateway`; new `tool-gateway` deployment/service/SA/RBAC with
  image `luban-aiops/tool-gateway`; policy ConfigMap `gateway-policy` →
  `platform-policy` mounted on both services from one shared bundle;
  `deploy-overlay.sh` and root `Makefile` updated (`.images.env` gains
  `PLATFORM_GATEWAY_IMAGE` + `TOOL_GATEWAY_IMAGE`). Portal `nginx.conf`
  proxies to `platform-gateway:8000`.
- identity (Q-3/Q-4): portal platform JWTs change audience `tool-gateway` →
  `platform-gateway` (broker `IDENTITY_TOKEN_AUDIENCE` default, overlay,
  schema note, edge verifier); delegated tokens keep `aud = tool-gateway`.
  The edge registers as a new `platform-gateway` broker client
  (`act.sub = platform-gateway`); the old `tool-gateway` client entry is
  removed.
- guards: both gateways gain route-inventory tests pinning their surfaces
  (edge: `/api/v1/*` portal routes only; tool: health/metrics +
  `/api/v2/tools*` only). Metric names unchanged (`gateway_*` /
  `delegation_*` remain the scrape contract).
- docs: platform-gateway/tool-gateway READMEs, dev-k8s README (incl. the
  one-time `kubectl delete deployment/api-gateway service/api-gateway`
  cleanup), workspace model, product boundaries, layout convention, and
  governance label scheme updated; spec status `delivered`.

### Added — SPEC-009: Pre-Production Hardening (Tool Output Redaction and Workload-Identity Service Tokens)

- Closes the two deadline-bound Release 1 deferrals before the first non-dev
  deployment: SPEC-007 Q-3 (tool-output redaction) and the SPEC-008 R-3
  workload-identity upgrade path.
- tool-gateway: code-owned redaction engine applied at the single
  `invoke_tool` choke point before both the response and the audit log —
  value patterns (JWTs, `Bearer`/`Basic` values, PEM private keys, AWS-style
  key IDs) plus a bounded explicit key list; clean output passes through
  byte-identical. Fail-closed: results whose redacted fraction exceeds
  `GATEWAY_REDACTION_OVERFLOW_FRACTION` (default 0.2) are withheld with a
  `REDACTION_OVERFLOW` error. New `gateway_tool_redacted_spans_total{tool}`
  metric and `redacted_spans` audit field; `GATEWAY_REDACTION_ENABLED`
  (default `true`) is the dev-debugging opt-out.
- identity-broker: the exchange endpoint now also accepts Kubernetes
  projected service-account tokens as the service credential
  (`Authorization: Bearer`), validated against the cluster OIDC issuer JWKS
  (`IDENTITY_WORKLOAD_ISSUER_URL`, empty = feature off) with an audience
  check (`IDENTITY_WORKLOAD_AUDIENCE`) and a workload-subject registry
  (`IDENTITY_WORKLOAD_CLIENTS`); delegated-token claims are identical to the
  static path. Invalid/expired/wrong-audience/unregistered tokens yield 401.
- tool-gateway delegation: `GATEWAY_WORKLOAD_TOKEN_PATH` prefers the
  projected token file (re-read per exchange; kubelet rotates it in place)
  over the static secret; a missing file falls back to the static secret
  with a once-per-process warning. Unsetting the path is the rollback
  switch; the dev path is unchanged.
- docs: dev-k8s README documents the redaction opt-out and the workload-token
  contract (projected volume snippet, issuer/audience env names); the
  gateway `runtime-secrets.example.env` marks the static secret as the dev
  fallback.

### Added — Release 1 (SPEC-008: Service-to-Service Identity)

- Implemented ADR-0004 broker-mediated token delegation, closing SPEC-007 R-4/R-6
  and open questions Q-1/Q-2 and completing Release 1.
- identity-broker: platform JWTs are now audience-bound (`aud`, default
  `["tool-gateway"]`); added `POST /api/v1/auth/exchange` which authenticates a
  registered service credential, verifies the subject token, and mints a
  short-lived delegated token (`sub`/`username`/`roles` copied never elevated,
  `act` naming the caller, `aud` = requested audience, TTL
  `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` default 300s). New service-client
  registry `IDENTITY_SERVICE_CLIENTS` and `token_exchange_total` metric.
- tool-gateway: verifies token `aud` (`GATEWAY_TOKEN_AUDIENCE`); exchanges the
  verified user token for a delegated token via a per-user TTL cache
  (`delegation_exchange_total`, `delegation_cache_total` metrics) and forwards
  it downstream as `Authorization: Bearer`; exchange failure is non-fatal
  (chat proceeds tool-less). Tool routes derive identity solely from the
  verified token (`identity_context` removed from the invoke contract);
  `GET /api/v2/tools` is authenticated and gated by a new `tools:list` policy
  action; audit logs record both `sub` and `act`.
- agent-platform: relays the delegated token as a bearer token on tool
  discovery and invocation, bound per-user into the toolkit closures (no
  cross-user sharing); removed `identity_context` from the invoke payload;
  no-token path degrades to an empty Toolkit / structured error.
- contracts: `identity-token.schema.json` documents `aud` (required) and `act`
  (optional) with a delegated-token note; `policy-default.yaml` adds
  `tools:list`. Contract tests bind both gateway and identity-broker models to
  the updated schema.
- dev-k8s overlay: sets `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`,
  `IDENTITY_TOKEN_AUDIENCE`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`; the gateway
  and broker service secrets are provisioned as optional K8s Secrets
  (`api-gateway-runtime-secrets`, `identity-service-runtime-secrets`) and are
  not committed.

### Changed — Single Image Build Path

- Folded `build-images.sh` into `make build`: the root target now builds all
  four product images (delegating to each product's Makefile) with a
  coordinated `IMAGE_TAG`, writes `.images.env` for `make deploy`, and keeps
  the `AUTO_LOAD_KIND` / `KIND_CLUSTER_NAME` kind-load support.
- Removed `shared/platform-ops/gitops/dev-k8s/build-images.sh` and the separate
  `build-images` Make target; `make build` is now the single build path.
- Per-product `build` always tags the local image and adds a registry tag when
  `REGISTRY` is set; `push` re-tags then pushes, so build and push stay
  consistent.
- Updated the dev-k8s README to use `make build` / `make deploy` and corrected
  stale `dev-k8s-transitional` paths to `dev-k8s`.

### Changed — Build & Verification Tooling

- Added a forge-agnostic root `Makefile` (with per-product Makefiles and shared
  `mk/` fragments) consolidating project routines: `verify` (the
  pre-commit/pre-push gate), `test`, `sync`, `lint`, `build`, `push`,
  `overlays`, `deploy`, and `clean`.
- Removed the GitHub Actions workflows (`.github/workflows/ci.yml`,
  `overlays.yml`). The verification gate now lives in `make verify`,
  decoupling the project from GitHub-specific CI; the same checks run
  locally and under any CI provider.
- Updated the SDD enforcement guidance (`docs/specs/README.md`) to name
  `make verify` as the mechanical gate in place of the CI workflows.

### Added — Release 1 (SPEC-007: Tool Execution Framework)

- Added tool execution framework to tool-gateway: `ToolRegistry`, `BaseTool`
  abstraction, and structured `ToolResult` evidence envelope.
- Added Kubernetes read-only connector with four tools: `k8s.list_pods`,
  `k8s.get_pod`, `k8s.get_events`, `k8s.get_pod_logs` (kubernetes-client/python).
- Added `GET /api/v2/tools` (discovery) and `POST /api/v2/tools/invoke`
  (execution) endpoints with policy enforcement and audit logging.
- Added `tools:invoke` policy action granted to platform-admin, operator, and
  developer roles; read-only-observer is excluded.
- Added agent-platform Toolkit integration: when `TOOL_GATEWAY_URL` is
  configured, the AgentScope kernel discovers and registers gateway tools so
  the LLM can autonomously invoke them.
- Added shared contract schemas: `tool-invocation.schema.json` and
  `tool-result.schema.json`.
- Added RBAC (ServiceAccount + Role + RoleBinding) to dev-k8s overlay granting
  tool-gateway read-only access to pods, events, and pods/log.

### Changed — Release 1 Close

- Changed `GATEWAY_REQUIRE_AUTH` default from `false` to `true` in code and
  the dev overlay, completing the outstanding SPEC-001 release-close step.
  Unauthenticated requests to business routes now return `401` by default.
- Added `POST /api/v1/auth/refresh` to identity-broker: exchanges a Keycloak
  refresh_token for a fresh platform JWT, re-fetching userinfo so role changes
  are picked up on refresh.
- Added gateway proxy route `POST /api/v1/auth/refresh` forwarding to
  identity-broker.
- Added silent token refresh in operator-portal: schedules a background refresh
  60 seconds before JWT expiry; on failure, clears the session and prompts
  re-authentication.
- Collapsed the dual GitOps overlay (`dev-k8s-transitional` + `dev-k8s-native`)
  into a single `shared/platform-ops/gitops/dev-k8s` overlay. The
  transitional/native distinction no longer exists at the code level after
  SPEC-002 retired the transitional surface; a single overlay removes
  configuration drift and maintenance overhead.

### Added — Release 1 (SPEC-001 .. SPEC-006)

- Added `SPEC-001` release-1 platform hardening (delivered): gateway authentication
  enforcement behind `GATEWAY_REQUIRE_AUTH`, role propagation in structured logs,
  transitional session integrity (ownership scoping, 404 on unknown session IDs,
  TTL/size-bounded store, per-session agent isolation), typed contract
  enforcement bound to shared-contracts schemas, cached backend resolution with
  bounded outbound timeouts, and the GitHub Actions CI baseline.
- Added `SPEC-002` agent-service contract (delivered): platform-owned
  agent-service contract (ADR-0003) with v2 envelope (`content` replacing
  `response`, simplified stream events, header-based identity), `/api/v2/`
  adapter in agent-platform over the AgentScope kernel, tool-gateway migrated to
  a single agent-service client, retired the transitional `/api/v1/` surface,
  and bidirectional contract tests.
- Added `SPEC-003` identity-trust hardening (delivered): identity-broker now
  issues RSA-signed platform JWTs (`POST /api/v1/auth/token`) and publishes a
  JWKS endpoint (`GET /.well-known/jwks.json`, RFC 7517); the gateway verifies
  tokens locally via PyJWKClient, validates the `iss` claim, and derives
  `X-User-ID` exclusively from verified claims; removed `DEFAULT_USER_ID`
  fallback in favour of explicit `GATEWAY_DEV_USER` with synthetic identity
  logging.
- Added `SPEC-004` deny-by-default policy enforcement (delivered): defined the
  policy contract in shared-contracts (`policy-rule.schema.json`,
  `policy-decision.schema.json`, `policies/policy-default.yaml`) as a strict
  `action_authz` subset of the Tier-1 policy specification; the gateway
  evaluates every business request (`chat`, `session:create`, `session:read`)
  against a versioned role→action bundle, denying by default with a structured
  403 and audit-logging every decision.
- Added `SPEC-005` observability baseline (delivered): metrics naming
  conventions, OTel switch semantics, and `x-request-id` ↔ `trace_id` bridging
  rule in `shared/shared-contracts/observability-conventions.md`; all three
  Python services expose an always-on `/metrics` Prometheus surface plus an
  opt-in OTLP push pipeline gated by `OTEL_ENABLED`; standard HTTP RED metrics,
  domain counters (`agent_sessions_created_total`, `identity_tokens_issued_total`,
  `gateway_policy_decisions_total`, `gateway_token_verification_total`), and
  Prometheus scrape annotations on every deployment manifest.
- Added `SPEC-006` session durability (delivered): Redis-backed session store
  with strategy-pattern interface (`InMemorySessionStore` for dev/CI,
  `RedisSessionStore` for deployed environments); backend selection via
  `SESSION_STORE_BACKEND` env; graceful fallback to in-memory when Redis is
  unreachable; session store backend and readiness reported in `/health`;
  `session_store_backend`, `session_store_errors_total`, and
  `session_store_fallbacks_total` Prometheus metrics.
- Added ADR-0001 (SDD adoption), ADR-0002 (AgentScope 2.0 kernel), and
  ADR-0003 (platform-owned agent-service contract) under `docs/adr/`.
- Added spec-driven development workflow under `docs/specs/` with plan/spec/tasks
  templates and delivered specs for SPEC-001 through SPEC-006.
- Added `docs/agentic-aiops-platform/part-1b-framework-revalidation.md`.

### Added — Release 0

- Added typed provider-specific runtime options for `products/agent-platform`,
  including provider-owned defaults for `dashscope`, `deepseek`, and `openai`.
- Added provider adapters and a provider registry that resolve runtime settings
  into concrete AgentScope chat model implementations.
- Added gateway backend adapters so `products/tool-gateway` can resolve
  `transitional` versus `native` agent-service backends through a shared
  interface.
- Added deterministic local image build and deploy scripts for the GitOps-based
  Kubernetes development overlays under `shared/platform-ops/gitops/`,
  including both `dev-k8s-transitional` and `dev-k8s-native`.
- Added shared runtime profile overlays and selector helpers so provider
  selection stays explicit, reviewable, and Git-diffable in the deployment
  layer.
- Added Dockerfiles for the Release 0 development overlay services and an
  `nginx` proxy baseline for `products/operator-portal`.
- Added a minimal `OIDC` authorization-code callback path across
  `products/operator-portal`, `products/identity-broker`, and
  `products/tool-gateway`.
- Added configurable `OIDC_SCOPES` support so the shared identity flow can work
  against realms that do not expose the default `profile` and `email` scopes.
- Added focused tests for runtime settings, runtime metadata, provider registry
  behavior, and gateway backend resolution.
- Added release notes under `docs/agentic-aiops-platform/release-notes/`.
- Added a Git-tracked Keycloak browser-client reconciliation script for
  `dev-k8s-transitional` so the portal client redirect URIs, PKCE/public-client
  settings, and `preferred_username` / `email` mappers stay durable across
  overlay deploys.

### Changed

- Changed runtime metadata to expose resolved provider, model, base URL, and
  provider option details instead of only raw environment overrides.
- Changed `api-gateway` development overlay configuration to prefer `auto`
  backend resolution rather than pinning `AGENT_BACKEND_MODE` to
  `transitional`.
- Changed the platform-ops layout to use the durable
  `shared/platform-ops/gitops/` root for active operational assets while
  keeping `Release 0` wording in milestone-planning documents.
- Changed the development overlay rollout workflow to use explicit,
  overlay-specific image tags and per-overlay `.images.env` state instead of
  reusing a single static placeholder tag.
- Changed the operator portal browser baseline to default API requests to the
  current origin and route them through the local `nginx` proxy.
- Changed backend package layout across `agent-platform`, `tool-gateway`, and
  `identity-broker` to follow a clearer FastAPI-by-responsibility structure.
- Changed the gateway and portal request path so authenticated bearer identity
  now overrides manually entered user IDs for session and chat operations.
- Changed the GitOps overlay roots to set the deployment namespace explicitly so
  shared runtime-profile config maps are created in the same namespace as the
  services that consume them.
- Changed the committed `dev-k8s-transitional` OIDC baseline to match the live
  shared sandbox `Keycloak` validation path used for `Release 0` closure.

### Fixed

- Fixed a runtime settings mismatch where direct `RuntimeSettings(...)`
  construction could pair a provider with the wrong provider-options type.
- Fixed development cluster rollout ambiguity caused by stale same-tag image reuse.
- Fixed native AgentScope streaming compatibility so incremental reply updates
  preserve all accumulated content blocks instead of dropping earlier blocks.
- Fixed the native overlay image-build wrapper so it is directly executable as
  documented and writes to the correct overlay-specific image-state file.
- Fixed local runtime artifact hygiene by ignoring generated `**/.workspaces/`
  directories.
- Fixed the remaining `Release 0` auth gap by adding identity-broker token
  exchange, portal callback handling, optional identity-service secret
  injection, and structured request/session logs across the core services.
- Fixed fresh-namespace startup for `api-gateway` and `identity-service` by
  ignoring Kubernetes service-link `*_PORT=tcp://...` values when parsing their
  listen ports.
- Fixed the live `Release 0` overlay wiring so `agent-platform-runtime-profile`
  is created in the target namespace instead of `default`.
- Fixed the portal SSO identity contract in the shared sandbox realm by making
  the browser client emit durable `preferred_username` and `email` claims, so
  authenticated identity no longer falls back to the UUID subject value.
- Fixed the remaining `Release 0` documentation drift so the checklist,
  release notes, and closure status now consistently describe `Release 0` as
  completed with only post-closure follow-up items remaining.
