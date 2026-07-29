# Changelog

All notable changes to this repository are documented in this file.

The format is intentionally lightweight during the current pre-release phase.
Entries are grouped by workspace-level implementation milestones rather than
published product versions.

## Unreleased

### Added — Release 1 (SPEC-001 .. SPEC-005)

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
- Added ADR-0001 (SDD adoption), ADR-0002 (AgentScope 2.0 kernel), and
  ADR-0003 (platform-owned agent-service contract) under `docs/adr/`.
- Added spec-driven development workflow under `docs/specs/` with plan/spec/tasks
  templates and delivered specs for SPEC-001 through SPEC-005.
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
