---
kind: configuration_system
name: Environment-Driven Settings with Frozen Dataclasses and Kustomize Overlays
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

The Luban AIOps Platform uses a **12-factor environment-variable configuration** model. Every service reads its runtime settings exclusively from `os.getenv()` at process start, wraps them in **frozen dataclasses**, and exposes them through a module-level `@lru_cache(maxsize=1) get_settings()` accessor. There is no YAML/JSON config file consumed by the Python code at runtime; configuration files under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` are only sources for Kubernetes ConfigMaps that become environment variables in each pod.

Configuration is layered via **Kustomize overlays**: a shared `runtime.env` (OTel, identity broker URL) plus per-service `runtime-config.env` files, with secrets provisioned separately as Kubernetes Secrets (`*-runtime-secrets`) and mounted as env vars. Runtime profiles (openai / dashscope / deepseek) are selected by swapping a ConfigMap overlay via `select-runtime-profile.sh`, which changes `AGENTSCOPE_PROVIDER` / `AGENTSCOPE_PROFILE` / `AGENTSCOPE_MODEL_NAME` without rebuilding images.

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` (platform-gateway, tool-gateway, audit-service, skills-hub, identity-broker) and `products/agent-platform/src/agent_service/runtime_settings.py`. Each defines a frozen `*Settings` dataclass with a `from_env()` classmethod and a cached `get_settings()` accessor.
- GitOps env manifests: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` and per-service `runtime-config.env` files under `agent-platform/`, `platform-gateway/`, `tool-gateway/`, `identity-broker/`, `audit-service/`, `skills-hub/`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-runtime-secret.sh` — generate random secrets or read from exported variables and create K8s Secrets.
- Policy bundle: canonical source `shared/shared-contracts/policies/policy-default.yaml`, synced to `products/*/policies/policy-default.yaml` and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`; path is configured via `PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH`.
- Authoritative cross-service reference: `docs/guides/configuration-reference.md` documents every variable, default, secret contract, and cross-service dependency chain.

## Architecture and conventions

1. **Single source of truth per setting**: each setting has exactly one `os.getenv(<NAME>, <DEFAULT>)` call inside one `from_env()` method. Boolean flags are normalized via `.strip().lower() in {"1","true","yes","on"}` (or an explicit `_optional_bool` helper in agent-platform).
2. **Frozen dataclasses + lru_cache**: settings objects are immutable and memoized globally so they can be imported anywhere without re-parsing env. This is the de facto singleton pattern across all services.
3. **Strict parsing with fail-fast validation**: complex settings raise exceptions at startup rather than silently misbehaving:
   - `SkillsSettings.parse_sources` rejects unknown types, duplicate `source_id`s, malformed IDs (`[a-z0-9][a-z0-9-]*`), and missing type-specific fields.
   - `RuntimeSettings.from_env` validates `AGENTSCOPE_PROVIDER` against `SUPPORTED_RUNTIME_PROVIDERS` and enforces `AGENTSCOPE_PROFILE == AGENTSCOPE_PROVIDER` in `__post_init__`.
   - `IdentitySettings._parse_service_clients` and `WorkloadClient` parsers enforce the documented comma-separated `key=value` formats.
4. **Secrets vs non-secrets split**: sensitive values (API keys, client secrets, JWT private keys) are never placed in `runtime-config.env`; they are injected via separate `*-runtime-secrets` Kubernetes Secrets. Non-sensitive endpoints, timeouts, feature toggles, and policy paths live in `runtime-config.env`.
5. **Cross-service credential contracts**: every inter-service boundary declares a matching pair of env vars that must agree at deploy time:
   - Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry `platform-gateway:<secret>:tool-gateway`.
   - Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry in audit-service.
   - Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS` in skills-hub.
   These contracts are enforced at runtime by the receiving service's auth middleware using the parsed client registries.
6. **Feature toggling via env presence**: optional features are enabled by setting their flag env var to a truthy value and providing required companion vars (e.g. `GATEWAY_ELASTIC_ENABLED=true` plus `GATEWAY_ELASTIC_URL`/auth; `GATEWAY_K8S_ENABLED=true` plus namespace; unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `GATEWAY_SKILLS_SERVICE_URL` leaves the connector unregistered).
7. **Policy-as-code**: the RBAC policy is a single YAML document validated against a JSON schema (`make validate-policy`) and distributed byte-identically to consumers; it is not edited per service.

## Conventions and constraints

- **Every service follows the same shape**: a `core/config.py` defining a frozen `*Settings` dataclass, a `from_env()` that reads env vars, and a cached `get_settings()` accessor. The agent-platform is the exception — it centralizes LLM provider options in `runtime_settings.py` but still uses the same frozen-dataclass + cached accessor pattern.
- **Boolean normalization**: boolean env vars accept `1|true|yes|on` (case-insensitive); anything else is treated as false (or raises `ValueError` when a strict helper is used).
- **Default hostnames assume in-cluster DNS**: defaults like `agent-service:8000`, `identity-service:8000`, `redis:6379` are hard-coded in settings, so deployments must keep those service names.
- **No runtime reload**: because settings are cached via `lru_cache(maxsize=1)` on import, changing env vars after process start has no effect — configuration is effectively immutable for the lifetime of the process.
- **Profiles are mutually exclusive**: only one LLM profile (openai/dashscope/deepseek) may be active at a time, selected by swapping the ConfigMap overlay; `AGENTSCOPE_PROFILE` must match `AGENTSCOPE_PROVIDER`.
- **Secrets are never committed**: the configuration reference explicitly states secrets are provisioned as K8s Secrets and never committed to Git; example `.env` files exist only as documentation (`runtime-secrets.example.env`).
- **Policy sync is mandatory**: editing `shared/shared-contracts/policies/policy-default.yaml` requires running `make sync-policy` to propagate the change to all consumer locations; consumers read the policy from the path set in `*_POLICY_PATH`.