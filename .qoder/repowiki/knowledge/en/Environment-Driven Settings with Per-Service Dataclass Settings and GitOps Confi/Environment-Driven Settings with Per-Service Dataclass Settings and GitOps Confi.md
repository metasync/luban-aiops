---
kind: configuration_system
name: Environment-Driven Settings with Per-Service Dataclass Settings and GitOps ConfigMaps
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

## What system/approach is used

The platform uses a uniform, environment-variable-driven configuration system across all nine Python services. Each service defines its own frozen `dataclass` settings model in `src/<service>/core/config.py` (or `runtime_settings.py` for agent-service) with a classmethod `from_env()` that reads values from `os.environ`, applies typed parsing and validation, and exposes a module-level `@lru_cache(maxsize=1)` `get_settings()` accessor. There is no YAML/JSON config file consumed at runtime by the services themselves; configuration is injected via Kubernetes ConfigMaps and Secrets mounted as environment variables.

Configuration sources are layered:
1. **Shared runtime env** — `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` provides cross-cutting values like `OTEL_EXPORTER_OTLP_ENDPOINT` and `IDENTITY_SERVICE_URL` to every pod.
2. **Per-service runtime-config.env** — each service under `products/*/src/...` has a matching `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` declaring its knobs, defaults, and source (`runtime-config` vs `runtime-secrets`).
3. **Per-service runtime-secrets** — sensitive values live in K8s `Secret` objects provisioned by scripts under `shared/platform-ops/gitops/sync-*.sh` (e.g. `sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-browser-credentials.sh`, `sync-otel-secrets.sh`). These are never committed to Git.
4. **Runtime profiles** — agent-service supports pluggable LLM backends via Kustomize profile overlays selected through `select-runtime-profile.sh`; the active profile's ConfigMap supplies provider/model/base-url knobs while secrets ride a separate `agent-platform-runtime-secrets` Secret.
5. **Policy bundle** — a single canonical YAML at `shared/shared-contracts/policies/policy-default.yaml` is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`; consumers load it from a path configured by `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`. A missing or invalid bundle fails startup (`PolicyLoadError`) — there is no silent fallback.

## Key files and packages

- `products/agent-platform/src/agent_service/core/config.py` — thin `get_settings()` wrapper returning `RuntimeSettings.from_env()`.
- `products/agent-platform/src/agent_service/runtime_settings.py` — the central `RuntimeSettings` dataclass with extensive `__post_init__` validation, per-provider option types (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`), and `from_env()` mapping ~60 environment variables.
- `products/{platform-gateway,tool-gateway,identity-broker,audit-service,execution-runtime,incident-service,skills-hub}/src/{service}/core/config.py` — per-service frozen dataclass settings + `from_env()` + cached `get_settings()`.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — declarative per-service variable catalog.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTel and identity broker endpoint.
- `docs/guides/configuration-reference.md` — authoritative cross-service dependency map, feature activation matrix, secret contracts, and per-service variable tables.
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle source of truth.
- `shared/platform-ops/gitops/sync-*.sh` — secret provisioning scripts that generate random shared secrets and write K8s Secrets.

## Architecture and conventions

- **One settings class per service.** Every service follows the same shape: frozen dataclass with sensible defaults, `from_env()` reading `os.getenv(name, default)`, and an `@lru_cache(maxsize=1)` `get_settings()` so the process loads config once at import/startup.
- **Typed parsing and validation in `from_env` / `__post_init__`.** Booleans are parsed via a truthy set `{"1", "true", "yes", "on"}`; integers/floats are cast with defaults; enums are validated against supported sets; ranges are enforced in `__post_init__` (e.g. `AGENTSCOPE_MAX_ITERS >= 1`, `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS >= 1`, `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS > 0`). Invalid values fail startup rather than propagating misconfiguration.
- **Feature flags are opt-in by default.** Mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED=false`), browser connector (`GATEWAY_BROWSER_ENABLED=false`), Elastic connector (`GATEWAY_ELASTIC_ENABLED=false`), workload identity, and most integrations are disabled unless explicitly enabled — deny-by-default posture.
- **Cross-service secrets are paired client_id/client_secret registries.** The audit-service, skills-hub, incident-service, and identity-service each maintain a registry (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) where each caller's secret must match the registered value. Provisioning scripts generate one random shared secret and write it into every consumer's `*-runtime-secrets` plus the server's registry.
- **Config is immutable at runtime.** Policy bundles are cached keyed on their path; changing a ConfigMap takes effect only after pod restart (rolling restart). No hot-reload mechanism exists.
- **Degrade-to-log-only for non-critical dependencies.** Unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes closed (`signing_unavailable`); unset `AGENT_EXECUTION_WORKER_URL` rejects with `worker_unavailable`. Non-essential features degrade gracefully; critical ones (policy bundle load, required secrets) fail fast.
- **Kubernetes-native deployment surface.** All configuration lives in `runtime-config.env` files consumed by Kustomize/K8s manifests; secrets are mounted as K8s Secrets. There are no `.env` files checked into version control.

## Conventions and constraints

- **Every environment variable is documented in `docs/guides/configuration-reference.md`** with its purpose, default, and source (`runtime-config` vs `runtime-secrets`). This document is the authoritative cross-service dependency map.
- **Secrets are never committed to Git.** They are generated by `sync-*.sh` scripts and stored in K8s Secrets. Example keys include `AGENTSCOPE_API_KEY`, `AGENT_AUDIT_CLIENT_SECRET`, `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET`, `OIDC_CLIENT_SECRET`, `AUDIT_INGEST_CLIENTS`, etc.
- **Cross-service chains require matching pairs.** Token delegation requires `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` to match the `IDENTITY_SERVICE_CLIENTS` entry; audit ingestion requires each emitter's `*_AUDIT_CLIENT_SECRET` to match `AUDIT_INGEST_CLIENTS`; skills/incidents query credentials must match their respective registries.
- **Policy bundle drift is enforced.** `make verify` runs contract tests that fail if the canonical `policy-default.yaml` diverges from the replicas in `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`, and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.
- **Startup-time validation is strict.** Unsupported `AGENTSCOPE_PROVIDER`, out-of-range numeric knobs, invalid IANA timezone strings, and unknown store backends raise `ValueError` during `from_env()` / `__post_init__`, preventing the service from starting misconfigured.
- **Feature activation is explicit.** A capability is active only when all required variables are set to non-empty values (documented in the Feature Activation Matrix table). For example, browser web-checks require `GATEWAY_BROWSER_ENABLED=true`, reachable `GATEWAY_BROWSER_CDP_ENDPOINT`, and optionally `GATEWAY_MUTATING_TOOLS_ENABLED=true` plus HITL bridging for write-class flows.
- **Profiles decouple provider selection from deployment labels.** The agent-service profile label is free-form; provider selection is a ConfigMap knob (`AGENTSCOPE_PROVIDER`). Only one LLM profile is active at a time, switched via `select-runtime-profile.sh`.