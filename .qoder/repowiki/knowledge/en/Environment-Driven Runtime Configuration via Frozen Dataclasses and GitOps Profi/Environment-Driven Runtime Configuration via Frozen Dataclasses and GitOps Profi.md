---
kind: configuration_system
name: Environment-Driven Runtime Configuration via Frozen Dataclasses and GitOps Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/secrets-dev/secrets.env
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system. Each Python service defines its own frozen `dataclass` settings object in `src/<service>/core/config.py` (or `runtime_settings.py` for the agent-platform), with a module-level `@lru_cache(maxsize=1)` `get_settings()` accessor that calls a `from_env()` classmethod to parse `os.environ`. There are no YAML/JSON config files consumed at runtime; all behavior is toggled through environment variables, mounted secrets, and Kubernetes ConfigMaps/Secrets defined under `shared/platform-ops/gitops/`.

Configuration values are validated eagerly in `__post_init__`, so invalid settings fail process startup rather than propagating misconfiguration into requests.

## Key files and packages

- **Agent Platform**: `products/agent-platform/src/agent_service/runtime_settings.py` — the largest settings object, covering LLM provider selection (`AGENTSCOPE_PROVIDER`), kernel tuning (`AGENTSCOPE_MAX_ITERS`, `AGENTSCOPE_CONTEXT_TRIGGER_RATIO`, `AGENTSCOPE_TOOL_RESULT_LIMIT`, `AGENTSCOPE_TIMEZONE`), HITL timeouts, evidence caps, model discovery, isolated execution worker handoff, audit/incident/skills client credentials, authoring-trace bounds, and skill graduation limits. Accessor: `products/agent-platform/src/agent_service/core/config.py:get_settings()`.
- **Platform Gateway**: `products/platform-gateway/src/platform_gateway/core/config.py:PlatformGatewaySettings` — service URLs, identity/JWKS settings, token audience, policy path, auth posture, audit/incident/skills proxy URLs.
- **Tool Gateway**: `products/tool-gateway/src/tool_gateway/core/config.py:GatewaySettings` — identity/JWKS, policy, redaction, K8s/elastic integrations, browser connector, HTTP connector, secrets connector (password policy enforcement, delivery backend TTLs, Redis/email), email allowlists. Includes cross-field validation that password-policy overrides may only tighten the contract.
- **Shared helpers**: `products/agent-platform/src/agent_service/core/env.py:get_env_value/get_env_int` provide fallback-name resolution across multiple env var names.
- **GitOps profiles**: `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml` sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`; `dev-k8s/base/*/runtime-config.env` files carry per-service defaults (Redis, Postgres session store, tool-gateway URL, OTel tracing); `runtime-profiles/default/runtime-secrets.example.env` documents provider API keys and optional multi-model catalog keys.
- **Secret provisioning scripts** under `shared/platform-ops/gitops/` (e.g. `sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-otel-secrets.sh`) inject secret-bearing env vars into each service's Secret/ConfigMap at deploy time.

## Architecture and conventions

1. **Per-service frozen dataclass + cached accessor.** Every service exposes exactly one `get_settings()` function decorated with `functools.lru_cache(maxsize=1)`. Callers import it once and reuse the same immutable settings object throughout the process lifetime.
2. **All knobs are environment variables.** The `from_env()` method reads exclusively from `os.getenv(...)`, with sensible defaults baked into the dataclass field defaults. No file parsing or external config stores are consulted at startup.
3. **Eager validation in `__post_init__`.** Invalid ranges, unsupported choices, or inconsistent combinations raise `ValueError` during settings construction, causing the process to exit before serving traffic. Examples include bounded `max_iters`, open interval `(0, 0.9)` for `context_trigger_ratio`, positive timeouts, valid IANA timezone strings, and password-policy override tightening rules.
4. **Feature flags default to deny-by-default.** Optional capabilities (browser connector, HTTP connector, secrets connector, elastic, mutating tools, kernel tracing, task tools) are `False` by default and must be explicitly enabled via env vars. This makes new features opt-in without changing existing behavior.
5. **Profile label decoupled from provider.** `AGENTSCOPE_PROFILE` is a free-form deploy label (SPEC-026 R-5) set via the profile ConfigMap; it is not validated against a whitelist and is independent of `AGENTSCOPE_PROVIDER`, which is constrained to `dashscope|deepseek|openai|luban`.
6. **Provider-specific options parsed conditionally.** `_provider_options_from_env` branches on `provider` to build `DashScopeOptions`, `DeepSeekOptions`, or `OpenAIOptions` (the `luban` provider reuses the OpenAI shape). Provider-specific env vars like `DASHSCOPE_THINKING_ENABLE`, `DEEPSEEK_REASONING_EFFORT`, `OPENAI_PARALLEL_TOOL_CALLS` are only read when that provider is active.
7. **Secrets are never inline.** Credential-bearing values (`*_API_KEY`, `*_CLIENT_SECRET`, `*_PASSWORD`, `*_BASE_URL` for team-hosted servers) are documented as coming from `runtime-secrets.example.env` / synced Secrets, never committed to source. Non-sensitive tuning lives in `runtime-config.env` ConfigMaps.
8. **Cross-service shared env.** `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` provides cluster-wide variables (OTLP endpoint, `IDENTITY_SERVICE_URL`) injected into every pod, while per-service `runtime-config.env` files add service-specific defaults.
9. **Fallback chains for env var names.** `core/env.py:get_env_value(*names, default)` lets callers try multiple env var names in priority order, enabling legacy-to-new name migration without breaking deployments.

## Conventions and constraints

- **Every setting has a corresponding env var name.** The mapping is one-to-one and documented inline in `from_env()`; there is no indirection layer between env vars and fields.
- **Boolean parsing is uniform.** Truthy values are parsed as any of `{"1", "true", "yes", "on"}` (case-insensitive); falsy is everything else. A dedicated `_optional_bool` helper raises `ValueError` for non-empty strings that are not recognized booleans.
- **Optional typed parsers exist for str/int/float/bool/choice.** `_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice` centralize parsing and return `None` for unset/blank values, keeping `from_env()` declarative.
- **Tunable knobs reference their governing spec.** Comments cite SPEC numbers (e.g. SPEC-017 R-1, SPEC-020 R-2, SPEC-026 R-5, SPEC-037 R-2/R-5, SPEC-038 R-4, SPEC-043 R-3, SPEC-044 R-2, SPEC-049, SPEC-051 R-2, SPEC-055 R-1/R-4, SPEC-058, SPEC-062 R-2/R-7) to tie each field to its requirement document.
- **Missing required dependencies fail closed.** If a downstream service URL or credential is unset (e.g. `AGENT_EXECUTION_WORKER_URL`, `AGENT_AUDIT_CLIENT_SECRET`, `AGENT_INCIDENT_CLIENT_SECRET`), the dependent feature returns a specific error code (e.g. `execution_rejected`, `worker_unavailable`, `dependency not configured`) rather than silently degrading.
- **Policy overrides can only tighten.** For the secrets connector, password-policy env overrides (`GATEWAY_PASSWORD_MIN_LENGTH`, `GATEWAY_PASSWORD_REQUIRED_CLASSES`) are validated against the mounted policy contract and rejected if they weaken it — enforced in `GatewaySettings.__post_init__`.
- **Profiles are additive overlays.** The dev-k8s base provides defaults; runtime profiles under `runtime-profiles/` overlay additional ConfigMaps/Secrets (e.g. `secrets-dev/secrets.env` flips `GATEWAY_SECRETS_ENABLED=true`); deployment selects the profile via `select-runtime-profile.sh`.