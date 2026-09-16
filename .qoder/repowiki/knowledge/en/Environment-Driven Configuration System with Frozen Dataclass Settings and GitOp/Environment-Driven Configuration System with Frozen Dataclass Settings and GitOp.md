---
kind: configuration_system
name: Environment-Driven Configuration System with Frozen Dataclass Settings and GitOps Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
---

# Configuration System

## What system/approach is used

The Luban AIOps Platform uses a **pure environment-variable configuration system** built on Python `dataclasses` with frozen instances, loaded at process startup via a single `from_env()` classmethod per service. There are no YAML/JSON config files consumed by the services at runtime; all settings come from `os.environ`. The authoritative cross-service variable map is documented in `docs/guides/configuration-reference.md`, which enumerates every variable, default, source (runtime-config ConfigMap vs. runtime-secrets Secret), and cross-service dependency chain.

Configuration loading follows a uniform pattern across every product:
- A frozen `@dataclass` named `<Service>Settings` declares all knobs with typed defaults.
- A module-level `get_settings()` function wraps `Settings.from_env()` in `functools.lru_cache(maxsize=1)` so the parsed settings object is singleton-scoped per process.
- Boolean flags are parsed through a shared truthy set `{"1", "true", "yes", "on"}`.
- Optional secrets are read via a `_secret(name)` helper that strips whitespace and returns `None` for empty values, allowing features to degrade gracefully when their secret is absent.
- Startup validation lives in `__post_init__` or dedicated parsers and raises `ValueError` / `SettingsError` to fail fast on invalid configuration.

There is no framework like Pydantic `BaseSettings`; the codebase deliberately avoids external config libraries in favor of explicit, auditable parsing logic.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass with provider-specific option types (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and extensive `__post_init__` validation for kernel tuning, HITL timeouts, evidence caps, model discovery, execution signing, browser flow TTL, and authoring-trace bounds.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` covering agent/identity URLs, JWT audience/issuer, delegation client, policy path, audit/incident/skills proxy URLs and credentials.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` including K8s connector, mutating-tools gate, Elastic connector, redaction, skills/incidents clients, and the full browser connector surface (CDP endpoint, session pool, origin allowlist, credential-set file path).
- `products/execution-runtime/src/execution_runtime/core/config.py` — Minimal `ExecutionSettings` owning only signing key, handoff token, tool-gateway URL, store backend, and flight retention; missing secrets intentionally do not fail startup (health checks still serve).
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` plus `ServiceClient` and `WorkloadClient` models; parses `IDENTITY_SERVICE_CLIENTS` (`client_id:secret:aud1|aud2`) and `IDENTITY_WORKLOAD_CLIENTS` (`subject=client_id:aud1|aud2`).
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` with `IngestClient`/`WorkloadClient` registries parsed from `AUDIT_INGEST_CLIENTS` (`client_id=secret,...`).
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with JSON-parsed `SKILLS_SOURCES` (local/git federation entries) and `SKILLS_GIT_TOKENS`, plus a distinct `SKILLS_QUERY_CLIENTS` registry.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with `INCIDENT_QUERY_CLIENTS`, `INCIDENT_CONNECTORS` (comma list, defaults to `audit`), and webhook token.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — Per-service ConfigMap env files providing non-secret defaults for dev deployments.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — Shared variables (`OTEL_*`, `IDENTITY_SERVICE_URL`) mounted into every pod.
- `docs/guides/configuration-reference.md` — Canonical reference documenting every variable, cross-service chains, secret contracts, runtime profiles, and policy rollout workflow.

## Architecture and conventions

### One setting object per service, cached once
Every service exposes `core/config.py` (or `runtime_settings.py` for agent-platform) with a frozen dataclass and a `@lru_cache(maxsize=1)` `get_settings()` accessor. Consumers import `get_settings()` and never re-parse environment variables.

### Feature toggles are environment flags
Capabilities are enabled by setting a boolean flag to one of `{"1", "true", "yes", "on"}`:
- `GATEWAY_K8S_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_ELASTIC_ENABLED`, `GATEWAY_REDACTION_ENABLED`, `GATEWAY_BROWSER_ENABLED`
- `PLATFORM_GATEWAY_REQUIRE_AUTH`, `AGENT_MODEL_DISCOVERY_ENABLED`, `AGENTSCOPE_KERNEL_TRACING`, `AGENTSCOPE_TASK_TOOLS_ENABLED`
- `EXECUTION_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND`

Unset flags use safe defaults (most connectors disabled, auth required, memory stores). Unknown values for enum-like fields (e.g. store backends, providers) raise startup errors.

### Secrets are provisioned as Kubernetes Secrets, never committed
Secrets live in per-service `*-runtime-secrets` Secrets (`platform-gateway-runtime-secrets`, `tool-gateway-runtime-secrets`, `identity-service-runtime-secrets`, `audit-service-runtime-secrets`, `skills-hub-runtime-secrets`, `incident-service-runtime-secrets`, `execution-signing-secret`, `execution-handoff-secret`, `tool-gateway-browser-credentials`). They are created by scripts under `shared/platform-ops/gitops/sync-*.sh` invoked by `make deploy`. Each script generates random shared secrets (or reuses exported ones) and writes both the emitter-side secret and the consumer-side registry entry.

### Cross-service client registries follow a consistent contract
Services expose themselves to callers via comma-separated client registries:
- `AUDIT_INGEST_CLIENTS` = `client_id=secret,...`
- `SKILLS_QUERY_CLIENTS` = `client_id=secret,...`
- `INCIDENT_QUERY_CLIENTS` = `client_id=secret,...`
- `IDENTITY_SERVICE_CLIENTS` = `client_id:secret:aud1|aud2,...`
Callers configure matching `<SERVICE>_CLIENT_ID` + `<SERVICE>_CLIENT_SECRET` pairs. Mismatches cause authentication failures at the receiver.

### Workload identity support
Several services accept projected ServiceAccount tokens via `*_WORKLOAD_ISSUER_URL` + `*_WORKLOAD_AUDIENCE` + `*_WORKLOAD_CLIENTS` (`subject=client_id,...`), enabling cluster-native auth without static secrets.

### Policy bundle is a separate concern from runtime config
Policy enforcement uses a canonical YAML bundle at `shared/shared-contracts/policies/policy-default.yaml`, synced byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`. It is loaded from a file path (`PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`) and is **not** hot-reloaded; changes take effect on pod restart. A missing or invalid bundle fails startup with `PolicyLoadError`.

### Runtime profiles
Agent-service LLM backends are selected via `AGENTSCOPE_PROVIDER` + profile-specific `AGENTSCOPE_*` keys, with multi-model catalog entries exposed through `<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL_NAME` / `<PROVIDER>_BASE_URL` / `<PROVIDER>_MODELS` environment variables. Profiles are switched via `select-runtime-profile.sh` and merged into `platform-runtime-config` alongside permanent postures `mutating-dev` and `browser-dev`.

## Conventions and constraints

- **All configuration is environment-only.** No `.env` files, YAML configs, or TOML files are read by services at runtime. The `*.env` files under `gitops/dev-k8s/base/*/runtime-config.env` are ConfigMap sources, not application config files.
- **Settings are immutable after construction.** All `Settings` dataclasses are `frozen=True`; mutation is impossible.
- **Startup validation is strict.** Invalid enum values, out-of-range numbers, unknown store backends, unsupported providers, and malformed JSON (e.g. `SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`) raise exceptions that prevent the process from starting.
- **Optional dependencies degrade gracefully.** Unset `*_AUDIT_SERVICE_URL`, unset `GATEWAY_SKILLS_SERVICE_URL`, unset `GATEWAY_INCIDENTS_SERVICE_URL`, and unset `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` disable the corresponding feature rather than failing the whole service.
- **Critical security paths fail closed.** Missing `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN`, `EXECUTION_SIGNING_KEY`, `EXECUTION_HANDOFF_TOKEN`, `OIDC_CLIENT_SECRET`, or `INCIDENT_WEBHOOK_TOKEN` reject requests or return 503 — there is no silent fallback to unauthenticated execution.
- **Cross-service secrets must match.** Every emitted secret has a counterpart registered in a consumer's client registry; provisioning scripts enforce this invariant.
- **Policy bundles are single-source-of-truth.** The canonical `policy-default.yaml` is the only editable copy; replicas are generated by `make sync-policy`, and `make verify` enforces byte parity.
- **No hot reload of policy or configuration.** Changes to ConfigMaps or mounted secrets require a pod restart to take effect.