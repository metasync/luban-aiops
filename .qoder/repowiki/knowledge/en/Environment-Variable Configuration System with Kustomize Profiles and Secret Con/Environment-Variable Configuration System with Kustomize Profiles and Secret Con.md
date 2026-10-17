---
kind: configuration_system
name: Environment-Variable Configuration System with Kustomize Profiles and Secret Contracts
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
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/browser.env
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/mutating.env
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## Approach

Luban has no centralized configuration framework. Each Python service owns its own configuration loader: a frozen `dataclass` with a `from_env()` classmethod that reads `os.environ`, plus an `@lru_cache(maxsize=1)`-wrapped `get_settings()` accessor. There is no `.env` file parsing at runtime — values come exclusively from Kubernetes environment variables (ConfigMap + Secret), mounted files, or projected service-account tokens.

Configuration is layered through Kustomize:
- Base overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` provide per-service defaults.
- Shared knobs live in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (e.g. `OTEL_ENABLED`, `IDENTITY_SERVICE_URL`).
- Feature profiles (`default`, `mutating-dev`, `browser-dev`) under `shared/platform-ops/gitops/runtime-profiles/` merge additional env into the base via separate Kustomization overlays.
- LLM provider selection uses a profile overlay whose ConfigMap sets `AGENTSCOPE_PROVIDER` / `AGENTSCOPE_PROFILE`; only one profile is active at a time, selected via `shared/platform-ops/gitops/select-runtime-profile.sh`.

Secrets are never committed. They are provisioned as Kubernetes `Secret` objects by scripts under `shared/platform-ops/gitops/sync-*.sh` (e.g. `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`). Each script creates or updates the relevant `<service>-runtime-secrets` Secret and documents the cross-service secret contract in `docs/guides/configuration-reference.md`.

## Key Files

- Per-service loaders:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, `from_env()`, typed provider options (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), extensive `__post_init__` validation.
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`.
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (browser, HTTP, secrets connectors).
  - `products/execution-runtime/src/execution_runtime/core/config.py`
  - `products/identity-broker/src/identity_service/core/config.py`
  - `products/audit-service/src/audit_service/core/config.py`
  - `products/incident-service/src/incident_service/core/config.py`
  - `products/skills-hub/src/skills_hub/core/config.py`
- Canonical operator documentation: `docs/guides/configuration-reference.md` (feature activation matrix, cross-service dependency chains, per-service variable tables, secret contracts, runtime profiles, policy rollout workflow).
- Kustomize bases: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env`.
- Profile overlays: `shared/platform-ops/gitops/runtime-profiles/{default,mutating-dev,browser-dev}/`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh`.
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml`, replicated to both gateways' packaged defaults and dev-k8s via `make sync-policy`.

## Architecture and Conventions

1. **Per-service frozen dataclass loaders.** Every service defines a single frozen dataclass holding all runtime settings, with a `from_env()` constructor mapping environment variables to fields. A module-level `get_settings()` caches the instance via `functools.lru_cache(maxsize=1)`. Settings are immutable after construction.

2. **Typed helper parsers.** Common parsers (`_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice` in agent-service; `_env_bool`, `_env_optional_int`, `_env_optional_tuple` in tool-gateway) normalize env input. Boolean parsing accepts `1|true|yes|on` (case-insensitive); unknown choices raise `ValueError`.

3. **Validation in `__post_init__`.** Range checks, cross-field consistency, and domain constraints fail startup with explicit `ValueError` messages rather than degrading silently. Examples: `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` must be in `(0, 0.9)`; `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`; `GATEWAY_SECRET_DELIVERY_BACKEND` must be `memory` or `redis`; password-policy overrides may only tighten the contract floor.

4. **Deny-by-default feature toggles.** Browser tools (`GATEWAY_BROWSER_ENABLED=false`), HTTP tools (`GATEWAY_HTTP_ENABLED=false`), mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED=false`), secrets delivery (`GATEWAY_SECRETS_ENABLED=false`), model discovery (`AGENT_MODEL_DISCOVERY_ENABLED=true` but degraded on failure), and durable execution admission (`AGENT_EXECUTION_ADMISSION_ENABLED=false`) are all opt-in. Unset URLs for downstream services typically disable the corresponding connector or route (503) rather than falling through.

5. **Cross-service secret contracts.** Client-to-server authentication follows a uniform `client_id` / `client_secret` registry pattern: each emitter holds a secret, and the receiver maintains a registry (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) of matching pairs. Scripts generate random secrets and write them to every side simultaneously.

6. **Policy bundle as code-as-data.** The action-authorization bundle has exactly one canonical copy (`shared/shared-contracts/policies/policy-default.yaml`), synced byte-identically to both gateway images and the dev-k8s overlay via `make sync-policy`. Drift is caught by `make verify`. Consumers load it from a configured path; a missing or invalid bundle fails startup (`PolicyLoadError`, no silent fallback). Bundles are not hot-reloaded — changes take effect on pod restart.

7. **Separation of non-secret config and secrets.** `runtime-config.env` (ConfigMap) carries tunables; `runtime-secrets.example.env` documents required keys; actual secrets are provisioned by `sync-*.sh` scripts into Kubernetes `Secret` objects. Some sensitive paths (e.g. `GATEWAY_BROWSER_CREDENTIAL_SETS`, `GATEWAY_PASSWORD_POLICY_PATH`) are mounted as files rather than injected as env vars.

8. **Profile-based LLM backend switching.** The agent-service supports providers `dashscope`, `deepseek`, `openai`, `luban` via `AGENTSCOPE_PROVIDER`; the profile label is decoupled from the provider (SPEC-026 R-5). Multi-model catalog entries are added via `<PROVIDER>_API_KEY` / `<PROVIDER>_MODEL_NAME` / `<PROVIDER>_BASE_URL` / `<PROVIDER>_MODELS` env vars, with live discovery (`AGENT_MODEL_DISCOVERY_ENABLED`) falling back curated → Postgres last-good → in-memory last-good.

## Conventions and Constraints

- All runtime configuration is read from environment variables via `os.getenv`; no `.env` file loading occurs at runtime. Source of truth is documented per service in `docs/guides/configuration-reference.md` with the owning `runtime-config.env` path.
- Boolean configuration values are parsed case-insensitively against `{1, true, yes, on}`; any other value raises `ValueError` (enforced by the `_optional_bool` helpers).
- Unknown enum-like values (e.g. unsupported `AGENTSCOPE_PROVIDER`, unknown `SESSION_STORE_BACKEND`, unknown `SECRET_DELIVERY_BACKEND`) fail startup with a `ValueError` listing supported values.
- Optional numeric/string configuration uses sentinel `None` (via `_optional_str` / `_optional_int` helpers); unset means "use contract default" rather than a zero/false default.
- Startup-time validation lives in `__post_init__` of each settings dataclass; invalid configuration aborts process startup rather than degrading silently (e.g. `AGENT_EXECUTION_ADMISSION_ENABLED` without ledger DSN + epoch, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED` without `CONTEXT_TRIGGER_RATIO > 0.2`).
- Cross-service secrets are provisioned exclusively through the `shared/platform-ops/gitops/sync-*.sh` scripts; they are never committed to Git. Each script documents which K8s `Secret` it creates and the contract between producer/consumer sides.
- The policy bundle is edited only in `shared/shared-contracts/policies/policy-default.yaml`; consumers must stay byte-identical replicas. `make sync-policy` performs the replication; `make verify` enforces parity and schema validity.
- Feature switches are deny-by-default: browser tools, HTTP tools, mutating tools, secrets delivery, and durable execution admission are all disabled unless explicitly enabled via their respective `*_ENABLED` env vars.
- Policy bundles are not hot-reloaded; a changed ConfigMap takes effect only on pod restart (rolling restart the gateway deployments).
- OpenTelemetry push is enabled globally via `OTEL_ENABLED=true` in `shared/runtime.env`; the OTLP auth header is a secret injected per-service via `sync-otel-secrets.sh`.