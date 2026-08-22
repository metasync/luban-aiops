---
kind: configuration_system
name: Environment-Driven Frozen Settings with Kustomize Overlay Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - shared/shared-contracts/policies/policy-default.yaml
    - products/platform-gateway/src/platform_gateway/policies/policy-default.yaml
    - products/tool-gateway/src/tool_gateway/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/agent-service-deployment.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/runtime-secrets.example.env
---

## Overview

The platform uses a uniform, environment-variable-driven configuration system across all Python services. Each service defines frozen dataclass settings that are loaded exclusively from `os.getenv` at process startup and cached globally via `functools.lru_cache(maxsize=1)`. There is no runtime reload of configuration — changes require a process restart.

## Per-service settings modules

Every product service exposes its own `src/<service>/core/config.py` (or equivalent) containing:
- A `@dataclass(frozen=True)` settings class with typed defaults (e.g. `PlatformGatewaySettings`, `AuditSettings`, `GatewaySettings`, `IncidentSettings`, `SkillsSettings`, `IdentitySettings`).
- A `from_env()` classmethod that reads values from `os.getenv` with service-scoped env var names (e.g. `PLATFORM_GATEWAY_*`, `AUDIT_*`, `GATEWAY_*`, `INCIDENT_*`, `SKILLS_*`, `IDENTITY_*`, `AGENTSCOPE_*`).
- A module-level `get_settings()` function decorated with `@lru_cache(maxsize=1)` that returns the singleton settings instance.

The agent-platform service is slightly different: its settings live in `src/agent_service/runtime_settings.py` as `RuntimeSettings`, which also parses provider-specific options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and validates kernel tuning knobs (`max_iters`, `context_trigger_ratio`, `tool_result_limit`, `timezone`, `reply_token_budget`, etc.) in `__post_init__`, raising `ValueError` on invalid values so misconfiguration fails fast at startup.

## Boolean and list parsing conventions

- Booleans are parsed case-insensitively from strings: `"1", "true", "yes", "on"` → `True`; `"0", "false", "no", "off"` → `False` (used for `*_REQUIRE_AUTH`, `*_ENABLED`, `*_TRACING`, `*_MUTATING_TOOLS_ENABLED`).
- Comma-separated lists are parsed into tuples of small structs (e.g. `AUDIT_INGEST_CLIENTS`, `AUDIT_WORKLOAD_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_WORKLOAD_CLIENTS`). The format is `client_id=secret,...` or `subject=client_id,...`.
- Complex nested config is passed as JSON strings and parsed at load time (e.g. `SKILLS_SOURCES` as a JSON list of `{source_id, type, url, ref, path}` entries; `SKILLS_GIT_TOKENS` as a JSON map).
- Optional string helpers (`_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice`) normalize empty strings to `None` and validate choices against a known set.

## Validation strategy

Validation happens eagerly during `from_env()` / `__post_init__`:
- Type coercion errors raise `ValueError` (e.g. invalid boolean, out-of-range numeric, unsupported `AGENTSCOPE_PROVIDER`, invalid IANA timezone).
- Semantic constraints are enforced (e.g. `AGENTSCOPE_PROFILE` must match `AGENTSCOPE_PROVIDER`; `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` must be in `(0, 0.9)`; `AGENTSCOPE_TIMEZONE` must not be empty).
- Some services define a dedicated `SettingsError` exception (audit, incident, skills-hub) for malformed structured env vars like client registries or source specs.

## Secrets vs non-secret configuration

Secrets are kept separate from plain configuration:
- Non-secret runtime config lives in Kubernetes ConfigMaps mounted via `envFrom.configMapRef` (e.g. `platform-runtime-config`, `agent-platform-runtime-profile`).
- Secrets live in Kubernetes Secrets mounted via `envFrom.secretRef` (e.g. `agent-platform-runtime-secrets`, `runtime-secrets.example.env` templates).
- The agent-platform deployment mounts both plus an optional secret reference, enabling profile-based overrides without duplicating deployments.

## Runtime profiles (Kustomize overlays)

Runtime profiles under `shared/platform-ops/gitops/runtime-profiles/<provider>/` (dashscope, deepseek, openai, mutating-dev) provide per-provider ConfigMaps that set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`, and corresponding secrets. The `select-runtime-profile.sh` and `verify-runtime-profile.sh` scripts switch between profiles. This lets the same container image run against different LLM backends without code changes.

## Policy configuration

Authorization policy bundles are YAML files (`policies/policy-default.yaml`) co-located with each gateway service (platform-gateway, tool-gateway) and shared under `shared/shared-contracts/policies/policy-default.yaml`. They are loaded via a `policy_path` setting (e.g. `PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`) and enforce deny-by-default semantics with explicit allow rules keyed by role/action pairs. The default bundle is identical across services, ensuring consistent authorization behavior.

## Deployment wiring

Kubernetes manifests mount configuration through three layers:
1. Base `runtime-config.env` ConfigMap with service-agnostic defaults (Redis, Postgres URLs, workspace paths, OTel tracing toggles).
2. Profile-specific ConfigMap (`agent-platform-runtime-profile`) selecting the LLM provider/model.
3. Secret references for API keys and tokens.

The agent-platform deployment explicitly sets `enableServiceLinks: false` to avoid Kubernetes injecting legacy `*_PORT` env vars that collide with the service's own port settings; DNS names are used instead.