---
kind: configuration_system
name: Environment-Driven Configuration with Per-Service Dataclass Settings and GitOps Overlay
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## What system/approach is used

The platform uses a **pure environment-variable configuration model** layered over Kubernetes ConfigMaps/Secrets, with no file-based config parsers (no `.env` files at runtime, no YAML/TOML for runtime settings). Each service defines its own frozen `dataclass` that reads from `os.environ` via typed helpers (`_optional_str`, `_optional_int`, `_optional_bool`, `_optional_choice`) in a `from_env()` classmethod. A module-level `@lru_cache(maxsize=1)` accessor (`get_settings()`) provides process-wide singleton access to the parsed settings.

Configuration values are supplied by:
- **Per-service `runtime-config.env` files** under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — these are mounted as Kubernetes ConfigMaps and form the base configuration for each pod.
- **A shared `runtime.env`** under `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — injected into every pod (OTel endpoint, identity broker URL).
- **Per-service `runtime-secrets.example.env`** files — templates for Kubernetes Secrets containing sensitive values (API keys, client secrets, JWT private keys).
- **Kustomize profile overlays** under `shared/platform-ops/gitops/runtime-profiles/` — e.g. `mutating-dev` and `browser-dev` merge additional env vars on top of the base without changing it; only one LLM profile is active at a time.
- **GitOps sync scripts** under `shared/platform-ops/gitops/` — `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `select-runtime-profile.sh` — generate random secrets, write K8s Secret objects, and wire cross-service credential contracts.

## Key files and packages

- `products/agent-platform/src/agent_service/core/config.py` — cached `get_settings()` returning `RuntimeSettings`.
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass with full env parsing, validation (`__post_init__` enforces bounds, IANA timezone, provider type), and defaults.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass with `from_env()` and `get_settings()`.
- `products/platform-gateway/src/platform_gateway/core/config.py` — per-service settings dataclass.
- `products/execution-runtime/src/execution_runtime/core/config.py` — execution-runtime settings.
- `products/identity-broker/src/identity_service/core/config.py` — identity broker settings.
- `products/audit-service/src/audit_service/core/config.py` — audit service settings.
- `products/skills-hub/src/skills_hub/core/config.py` — skills hub settings.
- `products/incident-service/src/incident_service/core/config.py` — incident service settings.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared env for all pods.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — per-service base configs.
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-secrets.example.env` — secret templates.
- `shared/platform-ops/gitops/gitops/*.sh` — secret provisioning and profile selection scripts.
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable map, dependency chains, and secret contract documentation.
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle (configuration-as-code for authorization rules), synced byte-identically to both gateways and the dev overlay.

## Architecture and conventions

1. **One dataclass per service**: Every service exposes a single frozen dataclass whose fields map 1:1 to environment variables. There is no nested config hierarchy or hierarchical merging beyond what Kubernetes ConfigMap/Secret mounting provides.
2. **Typed, validated loading**: Parsing happens in `from_env()` with explicit type coercion (`int`, `float`, boolean truthiness set `{'1','true','yes','on'}`) and validation in `__post_init__` rejects out-of-range values at startup (e.g. `AGENTSCOPE_MAX_ITERS >= 1`, `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS >= 1`, valid IANA timezone, positive timeouts).
3. **Deny-by-default feature flags**: Optional features (browser tools, mutating tools, Elastic connector, workload identity, model discovery) are disabled unless explicitly enabled via env var. An unset URL leaves a connector unregistered rather than falling back to a default.
4. **Cross-service secret contracts**: Mutual authentication between services uses matching `<SERVICE>_CLIENT_ID` + `<SERVICE>_CLIENT_SECRET` pairs registered in a central registry on the receiving side (e.g. `IDENTITY_SERVICE_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`). The `configuration-reference.md` documents every chain with diagrams showing which variables must match across deployments.
5. **Separation of concerns between config and secrets**: Non-sensitive runtime knobs live in `runtime-config.env` (ConfigMap); secrets live in `runtime-secrets.example.env` (Secret). Scripts generate random values and write them to K8s Secrets.
6. **Policy-as-code**: Authorization rules are not code defaults but a YAML bundle (`policy-default.yaml`) loaded from a configured path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`). It has a `version` field bumped on every change, is synced byte-identically to consumers, and both gateways expose a SHA-256 fingerprint of the loaded bundle on readiness endpoints.
7. **Profile overlays**: Base configs stay deny-by-default; capabilities like mutating tools and browser tools are activated by applying a Kustomize profile overlay (`mutating-dev`, `browser-dev`) that merges additional env vars. Only one LLM profile is active at a time, selected via `select-runtime-profile.sh`.
8. **Fail-closed vs fail-open degradation**: Some dependencies degrade gracefully (audit ingestion falls back to log-only when unreachable/unconfigured; model discovery failures are logged and swallowed), while critical ones fail closed (missing signing key → rejecting mutating resumes with `signing_unavailable`; missing worker URL/token → `worker_unavailable`).

## Conventions and constraints

- **Every configurable value has an environment variable name** documented in `docs/guides/configuration-reference.md` with its purpose, default, and source (runtime-config, runtime-secrets, or code default). New features must add entries here.
- **Boolean env vars use a consistent truthy set**: `{"1", "true", "yes", "on"}` (case-insensitive, stripped). False is any other value.
- **Optional string env vars are trimmed and treated as None if empty** via `_optional_str`.
- **Unknown backend names fail startup** (e.g. unknown `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND`).
- **Secrets are never committed to Git**: All secrets are provisioned via `sync-*` scripts that generate random values or read from local files, then write K8s Secrets. `runtime-secrets.example.env` files are templates only.
- **Policy bundle edits follow a strict workflow**: edit canonical `policy-default.yaml`, bump version, validate with `make validate-policy`, sync with `make sync-policy`, verify with `make verify` (scenario expectations guard against unintended grants), review with `make policy-diff`, commit together, deploy. Hot reload is intentionally not supported — changed bundles take effect on pod restart.
- **Cross-service credentials must be symmetric**: The `configuration-reference.md` specifies exact formats (e.g. `client_id:client_secret:audience1|audience2` for delegation clients, `client_id=secret,...` for registries) and which script provisions each pair.
- **Feature activation requires multiple coordinated knobs**: Enabling mutating tools requires `GATEWAY_MUTATING_TOOLS_ENABLED=true`, matching `tools:mutate` policy grant, RBAC applied, and `AGENT_HITL_CONFIRM_TIMEOUT>0`. Enabling browser tools requires `GATEWAY_BROWSER_ENABLED=true`, origin allowlist, reachable CDP endpoint, and HITL timeout. This multi-knob gating is enforced by comments in the base `runtime-config.env` files.