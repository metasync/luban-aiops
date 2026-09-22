---
kind: configuration_system
name: Environment-Driven Runtime Configuration with Per-Service Settings Dataclasses
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/execution-runtime/runtime-config.env
---

## What system/approach is used

The Luban platform uses a **pure environment-variable configuration system** layered on top of Python `dataclass` settings objects. Each product service defines its own frozen dataclass (`RuntimeSettings`, `GatewaySettings`, `PlatformGatewaySettings`, etc.) that reads all knobs from `os.getenv()` in a single `from_env()` classmethod, validates values in `__post_init__`, and exposes the instance through an `@lru_cache(maxsize=1)` `get_settings()` accessor. There are no YAML/JSON config files loaded at runtime by services; configuration is supplied entirely via Kubernetes ConfigMaps (runtime-config.env) and Secrets (runtime-secrets), which mount as environment variables into each pod.

A single authoritative cross-service reference lives in `docs/guides/configuration-reference.md`, which documents every variable, default, source, and cross-service dependency chain for all nine products.

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — central `RuntimeSettings` dataclass with provider-specific option sub-dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and ~50 runtime knobs.
- `products/agent-platform/src/agent_service/core/config.py` — cached `get_settings()` wrapper around `RuntimeSettings.from_env()`.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` covering identity, policy, K8s/browser/HTTP/secrets connectors, audit, skills, incidents.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` for upstream agent/incident/skills URLs, identity, delegation, policy path.
- `products/execution-runtime/src/execution_runtime/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/audit-service/src/audit_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py`, `products/incident-service/src/incident_service/core/config.py` — per-service equivalents following the same pattern.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service ConfigMap content supplying defaults.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared variables (OTLP endpoint, identity URL).
- `docs/guides/configuration-reference.md` — definitive variable-to-feature matrix, cross-service chains, secret contracts, and per-service tables.

## Architecture and conventions

1. **Per-service settings dataclass**: Every service owns one frozen `@dataclass` holding all runtime knobs, with sensible defaults declared as field defaults. This makes the schema self-documenting and immutable at runtime.
2. **`from_env()` constructor**: All parsing happens in one place per service. Boolean flags use a consistent truthy set `{"1", "true", "yes", "on"}` parsed via `.strip().lower()`. Optional strings/int/float helpers return `None` when unset so callers can distinguish missing vs empty.
3. **Validation in `__post_init__`**: Range checks, allowed-choice enforcement, and cross-field invariants raise `ValueError` at startup, failing fast before any code runs with bad config (e.g. invalid timezone, out-of-range kernel tuning, unsupported provider, weakening password-policy overrides).
4. **Cached singleton access**: `@lru_cache(maxsize=1)` `get_settings()` ensures settings are parsed once per process lifetime.
5. **Provider polymorphism**: The agent-service `RuntimeSettings` selects a typed `provider_options` object (`DashScopeOptions` / `DeepSeekOptions` / `OpenAIOptions`) based on `AGENTSCOPE_PROVIDER`, validated against `SUPPORTED_RUNTIME_PROVIDERS = ("dashscope", "deepseek", "openai", "luban")`.
6. **Feature gating by absence**: Many features are opt-in by being unset (e.g. `GATEWAY_BROWSER_ENABLED=false`, `GATEWAY_HTTP_ENABLED=false`, `GATEWAY_SECRETS_ENABLED=false`, `GATEWAY_MUTATING_TOOLS_ENABLED=false`). Unset URLs leave connectors unregistered or routes fail-closed (503); unset secrets degrade to log-only auditing rather than blocking requests.
7. **Kustomize profile overlays**: Agent LLM backends are selected via Kustomize profiles under `shared/platform-ops/gitops/` that swap `AGENTSCOPE_*` env vars; `select-runtime-profile.sh` switches the active profile without changing code.
8. **Policy bundle as configuration**: Policy enforcement is configured by a single canonical YAML file (`shared/shared-contracts/policies/policy-default.yaml`) synced to both gateways and dev-k8s via `make sync-policy`; consumers load it from `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH` and validate schema at startup.
9. **Secrets as mounted env vars**: Secrets live in Kubernetes `Secret` objects and are injected as env vars (e.g. `*_CLIENT_SECRET`, `*_AUDIT_CLIENT_SECRET`, `OTEL_EXPORTER_OTLP_HEADERS`, `EXECUTION_HANDOFF_TOKEN`). They are never committed to Git; provisioning scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`) generate or inject them.
10. **Cross-service contract variables**: The configuration reference documents explicit contracts where two services must agree on values: e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`, `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`, `AGENT_EXECUTION_SIGNING_KEY` ↔ execution-runtime's `EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN` ↔ `EXECUTION_HANDOFF_TOKEN`.

## Conventions and constraints

- **All configuration is environment-driven**: No service loads `.env` files, YAML configs, or JSON at runtime; everything comes from `os.getenv()`.
- **Defaults are deny-by-default**: Browser, HTTP, secrets, mutating tools, Elastic connector, and many other capabilities are disabled unless explicitly enabled via env vars.
- **Startup validation is strict**: Invalid values (unsupported provider, non-positive timeouts, invalid IANA timezone, port outside 1–65535, weakening password-policy overrides) cause `ValueError` at import/startup time.
- **Optional dependencies degrade gracefully**: Missing `*_AUDIT_SERVICE_URL` falls back to log-only auditing; missing `GATEWAY_SKILLS_SERVICE_URL` leaves skills tools unregistered; missing `AGENT_EXECUTION_WORKER_URL` rejects mutating resumes with `worker_unavailable` rather than falling back to in-process execution.
- **Secrets are never inline**: Credential-set paths point to mounted files (`GATEWAY_BROWSER_CREDENTIAL_SETS`, `GATEWAY_HTTP_CREDENTIAL_SETS`); SMTP passwords, OTLP headers, client secrets, and signing keys come from Kubernetes Secrets.
- **Policy changes require rebuild/restart**: The policy bundle is cached keyed on its path; there is no hot reload — changed ConfigMaps take effect only after pod restart.
- **Single source of truth for policy**: `shared/shared-contracts/policies/policy-default.yaml` is edited, then `make sync-policy` replicates it byte-identically to consumer locations; `make verify` enforces parity.
- **Profile-based LLM selection**: Only one LLM profile is active at a time; switching uses `select-runtime-profile.sh` to swap the ConfigMap overlay.