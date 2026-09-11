---
kind: configuration_system
name: Environment-Driven Settings with Frozen Dataclass Profiles and GitOps ConfigMaps
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system across all Python services. Each service defines a frozen `dataclass` (e.g. `RuntimeSettings`, `GatewaySettings`, `PlatformGatewaySettings`) in its `src/<service>/core/config.py` or `runtime_settings.py`, with a classmethod `from_env()` that reads values from `os.environ` and applies defaults. A module-level `@lru_cache(maxsize=1)` accessor (`get_settings()`) provides a process-wide singleton so settings are parsed once at import time. There is no YAML/JSON config file loader inside the services — files are only consumed as policy bundles (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`) or secret-mounted credential files (`GATEWAY_BROWSER_CREDENTIAL_SETS`).

Configuration is delivered to pods via Kubernetes ConfigMaps mounted as environment variables, with secrets injected through K8s Secrets. The canonical per-service variable map lives in `docs/guides/configuration-reference.md`, which documents every variable, default, source (runtime-config vs runtime-secrets), and cross-service dependency chain.

## Key files and packages

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, typed provider options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), validation in `__post_init__`, `from_env()` parsing of ~40 knobs.
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass with browser connector, Elastic, audit, skills, incidents, and mutating-tool flags.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` for identity, delegation, policy path, audit, incidents, skills, tool-gateway proxy.
  - `products/execution-runtime/src/execution_runtime/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/audit-service/src/audit_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py`, `products/incident-service/src/incident_service/core/config.py` — analogous patterns.
- Shared env helpers: `products/agent-platform/src/agent_service/core/env.py` (`get_env_value`, `get_env_int` fallback readers).
- Dev-k8s deployment overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env` provide the concrete defaults per service.
- Cross-cutting shared vars in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTLP endpoint, shared identity URL).
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml`, synced to both gateways' packaged copies and the dev overlay via `make sync-policy`; consumers load it from the path configured by `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`.
- Documentation contract: `docs/guides/configuration-reference.md` is the authoritative reference mapping every variable to its service, default, and provisioning script.

## Architecture and conventions

1. **One frozen dataclass per service.** All settings are immutable (`frozen=True`) and constructed exclusively via `from_env()`. This makes the shape explicit, type-checked, and impossible to mutate at runtime.
2. **Defaults live in code; overrides come from environment.** Every field has a sensible default in the dataclass definition. Environment variables override them; unset variables fall back to the code default. Unknown values often fail startup (e.g. unsupported `AGENTSCOPE_PROVIDER`, invalid IANA timezone, out-of-range bounds) rather than silently degrading.
3. **Process-wide singleton via `lru_cache`.** `get_settings()` caches one instance per process, so downstream code imports `settings` without re-parsing env.
4. **Typed provider options.** Agent-service distinguishes providers (`dashscope`, `deepseek`, `openai`, `luban`) with distinct option dataclasses; `__post_init__` validates that the active `provider_options` type matches the selected provider.
5. **Validation on construction.** `__post_init__` enforces numeric bounds (e.g. `max_iters >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, timeouts > 0), rejects unknown enum choices, and validates IANA timezone strings. Invalid configuration fails fast at import/startup.
6. **Feature flags are boolean env vars parsed uniformly.** Truthy set `{"1", "true", "yes", "on"}` is used consistently (see `_env_bool` in tool-gateway). Defaults are deny-by-default for security-sensitive features (`GATEWAY_MUTATING_TOOLS_ENABLED=false`, `GATEWAY_BROWSER_ENABLED=false`, `GATEWAY_REDACTION_ENABLED=true`).
7. **Secrets are never inline.** Sensitive values (API keys, client secrets, webhook tokens, OTLP headers) are read from K8s Secrets mounted as env vars or file paths. The `runtime-secrets.example.env` files document required keys but contain no real values.
8. **Cross-service contracts are enforced by naming conventions.** Client IDs and secrets must match registries on the receiving side (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`). Provisioning scripts (`sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-delegation-secrets.sh`, etc.) generate matching pairs.
9. **Policy bundle is single-source-of-truth.** `policy-default.yaml` is edited centrally and copied byte-identically to both gateways and the dev overlay via `make sync-policy`; `make verify` enforces parity.
10. **ConfigMap-based delivery.** Each service's `runtime-config.env` under `shared/platform-ops/gitops/dev-k8s/base/<service>/` is mounted into the pod as environment variables, keeping non-secret configuration versioned alongside the deployment manifests.

## Conventions and constraints

- **Startup-time parsing:** Settings are loaded when the settings module is imported (via `get_settings()`), typically during application bootstrap. Invalid values raise `ValueError` before the app starts.
- **Deny-by-default posture:** Security-sensitive capabilities (mutating tools, browser automation, auth enforcement) default to disabled and must be explicitly enabled via env vars.
- **Fail-closed on missing secrets:** Missing signing keys, handoff tokens, or query credentials cause the dependent feature to fail closed (e.g. mutating resumes rejected with `signing_unavailable` or `worker_unavailable`; incident-report creation returns 503 if `AGENT_INCIDENT_CLIENT_SECRET` is absent).
- **Degrade-to-log-only for observability:** Unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; fire-and-forget audit emission never blocks user requests.
- **No hot reload:** Policy bundles and settings are cached; changes take effect only on pod restart. The documentation explicitly states there is no hot reload mechanism.
- **Provisioning scripts own secrets:** All cross-service secrets are generated and distributed by shell scripts under `shared/platform-ops/gitops/` (`sync-*` scripts); operators should not edit secrets by hand.
- **Canonical documentation rule:** `docs/guides/configuration-reference.md` is the definitive cross-service variable map; any new env var must be added there with its service, default, and source.