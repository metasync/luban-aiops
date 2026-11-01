---
kind: configuration_system
name: Configuration System — Environment-Driven Settings with Per-Service Dataclasses and GitOps Overlays
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
---

## Approach

Luban has no centralized configuration framework. Each Python service owns its own settings module under `products/<service>/src/<service_name>/core/config.py` (or, for agent-service, `runtime_settings.py`). Configuration is loaded exclusively from **environment variables** at process startup via `os.getenv`, parsed into frozen `dataclass` instances, and cached through an `@lru_cache(maxsize=1)` `get_settings()` accessor.

There are two complementary layers:

1. **Code-level defaults + env overrides** — every setting has a typed default in the dataclass; `from_env()` reads the corresponding environment variable and validates it in `__post_init__`. Unknown values or out-of-range values raise `ValueError` at startup rather than degrading silently.
2. **GitOps overlays** — Kubernetes manifests under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` supply per-environment values; secrets go into separate `runtime-secrets.example.env` files and are provisioned by `sync-*-secrets.sh` scripts invoked from `make deploy`.

The canonical cross-service dependency map lives in `docs/guides/configuration-reference.md`, which documents every variable, its source (`runtime-config`, `runtime-secrets`, or code default), default value, and cross-service contracts (e.g. token delegation, audit ingestion, skills query).

## Key Files

- `docs/guides/configuration-reference.md` — authoritative cross-service environment-variable matrix and secret contracts
- `products/agent-platform/src/agent_service/runtime_settings.py` — agent-service settings (`RuntimeSettings.from_env()`, `__post_init__` validation)
- `products/tool-gateway/src/tool_gateway/core/config.py` — tool-gateway settings (`GatewaySettings`, delegated acquisition/authorization/validation helpers)
- `products/platform-gateway/src/platform_gateway/core/config.py` — platform-gateway settings (`PlatformGatewaySettings`)
- `products/execution-runtime/src/execution_runtime/core/config.py` — execution-runtime settings
- `products/audit-service/src/audit_service/core/config.py` — audit-service settings
- `products/identity-broker/src/identity_service/core/config.py` — identity-broker settings
- `products/incident-service/src/incident_service/core/config.py` — incident-service settings
- `products/skills-hub/src/skills_hub/core/config.py` — skills-hub settings
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service config fragments mounted as ConfigMaps
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared variables (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`)

## Architecture and Conventions

### One settings class per service
Each service defines exactly one frozen dataclass holding all runtime knobs. There is no inheritance between services' settings classes; cross-service contracts are expressed in `configuration-reference.md` and enforced at the wire level (client_id/secret matching), not in shared code.

### Parsing helpers
Services use small private helpers to parse env vars consistently:
- `_optional_str / _optional_int / _optional_float / _optional_bool` (agent-service) accept empty strings as `None` and validate booleans against `{"1", "true", "yes", "on"}`
- `_env_bool(name, default)` and `_env_optional_tuple` (tool-gateway) follow the same truthy convention
- `_optional_choice` enforces a fixed set of allowed values

### Validation strategy
Validation lives in `__post_init__` (or a dedicated `from_env` constructor). Rules include:
- Range checks on numeric fields (e.g. `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` must be > 0 and ≤ 120)
- Enum/choice validation (e.g. `GATEWAY_ANSIBLE_MCP_TRANSPORT` must be `streamable_http` or `stdio`)
- Cross-field consistency (e.g. enabling `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`)
- URL/URI parsing and sanitization for delegated identity trust endpoints
- Policy tightening: password-policy env overrides may only tighten the contract floor; weakening raises `ValueError`

### Feature flags
Most optional capabilities are opt-in boolean flags that default to `false` (deny-by-default):
- `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `GATEWAY_DELEGATED_ACQUISITION_ENABLED`, `GATEWAY_DELEGATED_AUTHORIZATION_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED`, etc.
- Enabling a flag often triggers additional `__post_init__` validation requiring other infrastructure to be present (e.g. Postgres DSN, keyring path, trusted callback).

### Secrets handling
Secrets are never embedded in `runtime-config.env`. They are provisioned as Kubernetes `Secret` objects via `sync-*-secrets.sh` scripts:
- `sync-delegation-secrets.sh` — token delegation client secrets
- `sync-audit-secrets.sh` — audit ingest credentials
- `sync-skills-secrets.sh` — skills query credentials
- `sync-execution-signing-secret.sh` / `sync-execution-handoff-secret.sh` — execution signing/handoff keys
- `sync-otel-secrets.sh` — OTLP exporter headers
- `sync-browser-credentials.sh`, `sync-ansible-credentials.sh`, `sync-servicenow-credentials.sh` — connector credential sets

Cross-service secrets follow a client/server registry pattern: each server maintains an `*_CLIENTS` registry (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`) keyed by `client_id=client_secret,...`; callers receive their own `<SERVICE>_CLIENT_SECRET` and `<SERVICE>_CLIENT_ID`.

### Policy bundle
Policy is not an environment variable but a file-based configuration artifact:
- Canonical copy: `shared/shared-contracts/policies/policy-default.yaml`
- Replicated byte-identically to gateways via `make sync-policy`
- Loaded from paths configured by `PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`)
- Missing or invalid bundle fails startup (`PolicyLoadError`); no silent fallback
- Hot reload is deliberately absent — changes require pod restart

### Deployment wiring
Kubernetes deployments mount `runtime-config.env` as a ConfigMap and reference secrets via `secretKeyRef`. The dev overlay uses `kustomization.yaml` to compose base manifests with profile-specific patches. Shared variables live in `shared/runtime.env` and are consumed by all pods.

## Conventions and Constraints

- **Environment-only loading**: All runtime configuration is read from `os.environ` at startup; there is no `.env` file loader, YAML config parser, or runtime reloader.
- **Typed defaults in frozen dataclasses**: Every setting has a default value declared in the dataclass field; `from_env()` is the single source of truth for mapping env vars to fields.
- **Fail-closed on invalid config**: Invalid enum values, out-of-range numbers, missing required fields for enabled features, and unknown backends raise `ValueError` during initialization — they do not degrade silently.
- **Opt-in feature gates**: Optional connectors and capabilities default to `false`; enabling them typically requires additional infrastructure configuration validated at startup.
- **Secrets outside source control**: Secret values are provisioned via `sync-*-secrets.sh` scripts into Kubernetes `Secret` objects; example templates exist under `runtime-secrets.example.env` but actual values are never committed.
- **Cross-service contracts documented centrally**: `docs/guides/configuration-reference.md` is the authoritative source for inter-service variable dependencies, secret contracts, and provisioning procedures; it references the per-service `config.py` source files.
- **Policy bundle immutability**: The policy bundle is edited only in `shared/shared-contracts/policies/policy-default.yaml` and synced via `make sync-policy`; direct edits to gateway replicas are rejected by `make verify` parity checks.
- **No hot reload**: Policy bundles and configuration changes take effect only on pod restart; this is explicitly stated in the configuration reference.