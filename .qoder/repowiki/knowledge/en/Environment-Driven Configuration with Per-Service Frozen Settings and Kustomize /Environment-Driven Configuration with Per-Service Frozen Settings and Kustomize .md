---
kind: configuration_system
name: Environment-Driven Configuration with Per-Service Frozen Settings and Kustomize Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/env.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a **pure environment-variable configuration model** with no runtime file parsing for application settings. Each Python service defines its own frozen `@dataclass` settings object in `src/<service>/core/config.py` (or `runtime_settings.py` for the agent-service), exposing a `from_env()` classmethod that reads values from `os.getenv(...)` against well-known uppercase variable names, and an `@lru_cache(maxsize=1)`-decorated `get_settings()` accessor consumed by the rest of the service. There are no `.env` files loaded at process start; secrets are injected via Kubernetes Secrets mounted as env vars or volume-mounted files (e.g. `workload_token_path`, `dev_signing_key_path`).

Configuration is layered through **Kustomize overlays**: every service under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` holds a flat key=value list of non-secret knobs, while per-service `runtime-secrets.example.env` documents secret keys. A shared `base/shared/runtime.env` provides cross-cutting variables (e.g. `IDENTITY_SERVICE_URL`, `OTEL_*`). Profile overlays under `shared/platform-ops/gitops/runtime-profiles/` switch LLM provider defaults for the agent-service without touching code.

## Key files and packages

- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (agent-service URL, identity JWKS, delegation audience, audit/incident/skills client credentials).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (K8s connector, Elastic, redaction, skills/incidents connectors, policy path).
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` plus `parse_ingest_clients` / `parse_workload_clients` helpers; supports `memory`/`postgres` backends.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` with `parse_query_clients` / `parse_workload_clients` / `parse_connectors`; raises `SettingsError` on malformed input.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` with strict JSON validation (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`) and regex-checked `source_id`s; raises `SettingsError`.
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` with typed provider options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), `__post_init__` validation enforcing agentscope bounds (e.g. `max_iters >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, valid IANA timezone), and `_optional_bool/_optional_choice` helpers.
- `products/agent-platform/src/agent_service/core/env.py` — shared `get_env_value` / `get_env_int` fallback helper.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service non-secret config fragments mounted into pods.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTLP and identity broker endpoints.
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, feature activation matrix, secret contracts, and per-service variable tables.

## Architecture and conventions

1. **Frozen dataclass + `from_env` pattern.** Every service's settings class is `@dataclass(frozen=True)`, so once constructed it cannot be mutated at runtime. Defaults live as class-level attributes; `from_env()` overrides them only when the corresponding env var is set. This makes the configuration schema self-documenting and testable.

2. **Per-service setting namespace.** Variables are scoped to their service: `PLATFORM_GATEWAY_*` for the gateway, `GATEWAY_*` for tool-gateway, `AUDIT_*` for audit-service, `SKILLS_*` for skills-hub, `INCIDENT_*` for incident-service, `AGENTSCOPE_*` / `AGENT_*` for agent-service. Cross-service URLs use plain hostnames (e.g. `http://audit-service:8000`) configured in the overlay `.env` files.

3. **Boolean parsing convention.** Booleans are parsed via `os.getenv(...).strip().lower() in {"1", "true", "yes", "on"}` (gateway services) or a dedicated `_optional_bool` helper that also accepts `{"0", "false", "no", "off"}` and raises `ValueError` otherwise (agent-service). Unknown boolean strings fail fast.

4. **Complex multi-value parsing.** Lists and maps are encoded as delimited strings and parsed at load time:
   - Comma-separated `client_id=secret,...` pairs for ingest/query registries (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `*_WORKLOAD_CLIENTS`).
   - JSON-encoded lists/maps for richer structures (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`), validated with explicit error messages raising `SettingsError`.
   - Comma-separated connector name lists (`INCIDENT_CONNECTORS`), defaulting to `("audit",)` when empty.

5. **Fail-fast startup validation.** Invalid configuration raises exceptions during `from_env()` / `__post_init__` rather than failing later: unsupported providers, out-of-range kernel tuning values, invalid IANA timezones, duplicate `source_id`s, unknown source types, missing required fields for `local`/`git` sources.

6. **Secrets vs. config separation.** Non-secret knobs go in `runtime-config.env` ConfigMaps; secrets (API keys, client secrets, webhook tokens, OTLP headers) go in per-service `*-runtime-secrets` Kubernetes Secrets provisioned by scripts under `shared/platform-ops/gitops/` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`). The configuration reference explicitly marks which variables must come from secrets.

7. **Feature gating via optional URLs.** Many capabilities are opt-in by leaving a URL unset: if `PLATFORM_GATEWAY_INCIDENT_SERVICE_URL`, `PLATFORM_GATEWAY_SKILLS_HUB_URL`, `PLATFORM_GATEWAY_TOOL_GATEWAY_URL`, `GATEWAY_SKILLS_SERVICE_URL`, or `GATEWAY_INCIDENTS_SERVICE_URL` is empty, the corresponding routes/connectors stay disabled (503 or unregistered tools). Audit emission falls back to log-only when `*_AUDIT_SERVICE_URL` is unset.

8. **Policy bundle as external YAML.** Policy enforcement is not embedded in code; both gateways read a YAML bundle from `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`), synchronized from the canonical `shared/shared-contracts/policies/policy-default.yaml` via `make sync-policy`.

## Conventions and constraints

- **Every service exposes `get_settings()` cached at module level**, so the process loads configuration exactly once at import time.
- **Store backends are selected by a `<SERVICE>_STORE_BACKEND` env var** (`memory` | `postgres`); unknown values cause startup failure (enforced by the `store_backend.strip().lower()` assignment followed by downstream selection logic documented in the configuration reference).
- **Cross-service credential contracts are enforced at runtime:** e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` must match the corresponding client id in `AUDIT_INGEST_CLIENTS`; `GATEWAY_SKILLS_CLIENT_SECRET` must match the `tool-gateway` entry in `SKILLS_QUERY_CLIENTS`. These contracts are documented in `docs/guides/configuration-reference.md` and provisioned together by the `sync-*` scripts.
- **Mutating tools require a four-link chain** (documented in the configuration reference): `GATEWAY_MUTATING_TOOLS_ENABLED=true`, `tools:mutate` policy grant, `AGENT_HITL_CONFIRM_TIMEOUT>0`, and pod-delete RBAC — enabling only one link is deliberately insufficient.
- **Agent-service provider selection is constrained to `SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai", "luban")`; unsupported values raise `ValueError` at startup.**
- **Profile-based LLM configuration:** the agent-service profile label is decoupled from the provider (SPEC-026 R-5); switching profiles is done via `select-runtime-profile.sh`, which swaps the ConfigMap containing `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_API_KEY`, etc.
- **Unknown store backends fail startup** (asserted by the configuration reference stating unknown values fail startup for `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, and each service's `*_STORE_BACKEND`).
- **Git source `source_id` must match `^[a-z0-9][a-z0-9-]*$`**; duplicates are rejected; `local` sources require `path`, `git` sources require `url`; git `path` must be a relative subdirectory (no leading `/`, no `..` components).