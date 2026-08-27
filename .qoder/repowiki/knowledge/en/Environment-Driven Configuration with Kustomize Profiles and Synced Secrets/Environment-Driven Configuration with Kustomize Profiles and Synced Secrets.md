---
kind: configuration_system
name: Environment-Driven Configuration with Kustomize Profiles and Synced Secrets
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/audit-service/src/audit_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
---

## What system/approach is used

The platform uses a **pure environment-variable configuration model** — every service reads its runtime settings exclusively from `os.getenv` at process startup, wrapped in frozen dataclasses with defaults. There are no YAML/JSON config files loaded by the Python services themselves; configuration is injected via Kubernetes ConfigMaps (non-secret knobs) and Secrets (secrets), mounted as environment variables into each pod. Cross-service secrets and client registries are provisioned centrally by shell scripts under `shared/platform-ops/gitops/sync-*.sh`, which generate random values and write them into per-service K8s Secret objects.

Configuration is layered through **Kustomize overlays**: a base set of `runtime-config.env` files per service plus a shared `runtime.env` (for OTLP endpoint and identity broker URL) form the default deployment, and runtime profiles (e.g. `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml`) overlay LLM provider settings on top. The active profile is selected at deploy time via `select-runtime-profile.sh`.

Policy bundles are the only non-env configuration consumed by code: a single canonical YAML (`shared/shared-contracts/policies/policy-default.yaml`) is validated against a JSON schema and synced byte-for-byte to both gateway consumers (`products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`) and the Kustomize overlay (`shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`). Consumers load it from a path configured via `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`).

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` (platform-gateway, tool-gateway, audit-service, execution-runtime, identity-broker, incident-service, skills-hub) and `products/agent-platform/src/agent_service/runtime_settings.py` for the agent kernel.
- Shared runtime env: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTLP endpoint, identity broker URL).
- Per-service runtime configs: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`.
- Runtime profiles: `shared/platform-ops/gitops/runtime-profiles/*/configmap.yaml` (LLM provider selection).
- Policy bundle: `shared/shared-contracts/policies/policy-default.yaml` (canonical source).
- Provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-skills-secrets.sh`, `sync-runtime-secret.sh`, `sync-sessions-db.sh`, `verify-runtime-profile.sh`.
- Authoritative reference: `docs/guides/configuration-reference.md` documents every variable, cross-service dependency chain, secret contract, and provisioning command.

## Architecture and conventions

1. **Frozen dataclass + `from_env()` + `@lru_cache(maxsize=1)` getter.** Every service defines a frozen dataclass with sensible defaults and a classmethod that reads `os.getenv(name, default)`. A module-level `get_settings()` caches the instance for the process lifetime. This pattern is identical across all services.
2. **Boolean parsing convention.** Booleans are parsed by stripping whitespace, lowercasing, and matching against `{"1", "true", "yes", "on"}`. Invalid strings raise `ValueError` (agent-platform's `_optional_bool` enforces this strictly).
3. **Optional helpers.** Agent-platform centralizes `_optional_str/_optional_int/_optional_float/_optional_bool/_optional_choice` helpers that return `None` when unset and validate choices against an allowlist.
4. **Startup validation.** `__post_init__` validates ranges (e.g. `AGENTSCOPE_MAX_ITERS >= 1`, `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS >= 1`, IANA timezone names). Invalid configuration fails process startup rather than degrading silently.
5. **Fail-closed vs fail-open features.** Optional integrations degrade predictably:
   - Unset `*_AUDIT_SERVICE_URL` → log-only auditing (fire-and-forget never blocks requests).
   - Unset `GATEWAY_SKILLS_SERVICE_URL` / `PLATFORM_GATEWAY_SKILLS_HUB_URL` / `PLATFORM_GATEWAY_TOOL_GATEWAY_URL` → respective routes return 503.
   - Missing `AGENT_EXECUTION_SIGNING_KEY` or `AGENT_EXECUTION_HANDOFF_TOKEN` → mutating resumes fail closed with `signing_unavailable` / `worker_unavailable` (no in-process fallback).
6. **Cross-service secret contracts.** Each inter-service call has a documented two-sided secret pair (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`; `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`). Provisioning scripts generate one random secret and write it into both sides' K8s Secrets.
7. **Workload identity support.** Services accept optional `*_WORKLOAD_ISSUER_URL` / `*_WORKLOAD_AUDIENCE` / `*_WORKLOAD_CLIENTS` / `<SERVICE>_WORKLOAD_TOKEN_PATH` for projected service-account tokens (disabled by default in dev).
8. **OpenTelemetry push pipeline.** Enabled globally via `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` in the shared ConfigMap; per-signal auth headers (`OTEL_EXPORTER_OTLP_HEADERS`) are injected per-service via `sync-otel-secrets.sh`.
9. **Runtime profiles for LLM providers.** The agent-service supports multiple providers (`dashscope`, `deepseek`, `openai`, `luban`) selected via `AGENTSCOPE_PROVIDER` and model catalog entries via `<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL_NAME` / `<PROVIDER>_BASE_URL` / `<PROVIDER>_MODELS`. Live model discovery (`AGENT_MODEL_DISCOVERY_ENABLED`) periodically refreshes provider catalogs with a fail-soft ladder (live → memory → Postgres → curated).

## Conventions and constraints

- **No config files in Git for runtime values.** All runtime configuration comes from K8s ConfigMaps/Secrets; nothing is committed except example `.env` templates (`*-runtime-secrets.example.env`) and the policy bundle.
- **Secrets are provisioned, not edited manually.** `make deploy` calls the relevant `sync-*.sh` script, which generates random secrets (or reuses exported ones like `DELEGATION_CLIENT_SECRET`, `INCIDENT_WEBHOOK_TOKEN`, `SKILLS_GIT_TOKEN`) and writes K8s Secrets idempotently. `SKIP_*_SECRETS=true` opts out per subsystem.
- **Policy bundle is the single source of truth.** Changes must go through `validate-policy` then `sync-policy`; consumer copies must stay byte-identical.
- **Feature toggles are environment variables.** Enabling/disabling capabilities (e.g. `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_ELASTIC_ENABLED`, `AGENT_MODEL_DISCOVERY_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`) is done purely via env vars; there is no runtime reload — changes require redeploy.
- **Defaults are safe.** Every setting has a conservative default in code (e.g. `require_auth=True`, `redaction_enabled=True`, `model_discovery_enabled=True`, `AGENT_HITL_CONFIRM_TIMEOUT=600`). Dev overrides live in `runtime-config.env` files, not in code.
- **Cross-service URLs follow `<SERVICE>_URL` naming.** Upstream endpoints are named after the target service (`AGENT_SERVICE_URL`, `TOOL_GATEWAY_URL`, `IDENTITY_SERVICE_URL`, `PLATFORM_GATEWAY_INCIDENT_SERVICE_URL`, etc.), making dependency graphs predictable.