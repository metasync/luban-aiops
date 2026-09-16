---
kind: configuration_system
name: Environment-Driven Configuration with Kustomize Profiles and GitOps Secret Sync
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## What system/approach is used

The platform uses a **pure environment-variable configuration model** layered over Kubernetes ConfigMaps and Secrets, orchestrated through Kustomize overlays. There is no YAML/JSON config file format consumed at runtime by the services — every setting is read from `os.environ` via typed dataclasses that validate values at startup. Configuration is provisioned declaratively in `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` files (ConfigMap sources) and per-service `*-runtime-secrets` Kubernetes Secrets, then merged into each pod's environment at deploy time.

A single shared `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` supplies cross-cutting variables (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`) to every pod. Service-specific feature toggles are applied via Kustomize profile overlays under `shared/platform-ops/gitops/dev-k8s/base/runtime-profiles/` (e.g. `mutating-dev`, `browser-dev`, LLM provider profiles), which merge additional env vars on top of the base without changing it.

## Key files and packages

- Per-service settings modules: `products/*/src/*_service/core/config.py` (platform-gateway, tool-gateway, audit-service, identity-broker, incident-service, skills-hub, execution-runtime) define frozen dataclass settings parsed from `os.getenv` with defaults; agent-platform centralizes its larger surface in `products/agent-platform/src/agent_service/runtime_settings.py`.
- Settings accessors: each service exposes a module-level `get_settings()` function decorated with `@lru_cache(maxsize=1)` so the process loads config once at import.
- Dev-k8s env manifests: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `base/shared/runtime.env` are the source-of-truth for non-secret runtime knobs.
- Secret provisioning scripts: `shared/platform-ops/gitops/gitops/sync-*-secrets.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `sync-runtime-secret.sh`) generate random secrets and write them into the appropriate K8s Secrets.
- Policy bundle: `shared/shared-contracts/policies/policy-default.yaml` is the canonical policy document; `make sync-policy` copies it byte-identically to both gateway consumers and the dev-k8s overlay.
- Authoritative reference: `docs/guides/configuration-reference.md` documents every variable, default, source, and cross-service dependency chain.

## Architecture and conventions

### Typed settings with startup validation
Each service defines a frozen dataclass whose fields have sensible defaults. A classmethod `from_env()` reads every field from `os.getenv`, casting to the correct type. The agent-platform `RuntimeSettings.__post_init__` enforces value ranges (e.g. `AGENTSCOPE_MAX_ITERS >= 1`, `AGENTSCOPE_CONTEXT_TRIGGER_RATIO ∈ (0, 0.9)`, IANA timezone names, positive timeouts) and raises `ValueError` at startup if invalid — misconfiguration fails fast rather than producing subtle runtime errors.

### Feature flags as boolean env vars
Feature activation follows a uniform pattern: an env var like `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_BROWSER_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`, or `AGENT_MODEL_DISCOVERY_ENABLED` gates behavior. Defaults are deny-by-default (`false`) for dangerous features (mutating tools, browser automation, mutating resume handoff). Optional capabilities degrade gracefully when unset (audit emission falls back to log-only, missing skill/incident URLs return 503).

### Secrets are never committed
All secrets live in Kubernetes Secrets provisioned by `sync-*-secrets.sh`. The scripts either generate random values or accept exported overrides (e.g. `DELEGATION_CLIENT_SECRET`, `AUDIT_INGEST_SECRET`, `SKILLS_GIT_TOKEN`). Each secret has a well-known name (`agent-platform-runtime-secrets`, `execution-signing-secret`, `execution-handoff-secret`, `platform-gateway-runtime-secrets`, `identity-service-runtime-secrets`, `tool-gateway-runtime-secrets`, `tool-gateway-browser-credentials`, `audit-service-runtime-secrets`, `skills-hub-runtime-secrets`, `incident-service-runtime-secrets`) and a documented key-to-purpose mapping in the configuration reference.

### Cross-service contracts enforced by matching env pairs
Configuration is not siloed — many features require coordinated env vars across services:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_ID` / `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the corresponding entry in `IDENTITY_SERVICE_CLIENTS`.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` must match the `client_id=secret,...` registry in `AUDIT_INGEST_CLIENTS`.
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` must match the `tool-gateway` entry in `SKILLS_QUERY_CLIENTS`.
- Incident query: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` / `GATEWAY_INCIDENTS_CLIENT_SECRET` / `AGENT_INCIDENT_CLIENT_SECRET` must match entries in `INCIDENT_QUERY_CLIENTS`.
- Execution signing: `AGENT_EXECUTION_SIGNING_KEY` (agent-service) and `EXECUTION_SIGNING_KEY` (execution-runtime) share the same `execution-signing-secret`.
- Execution handoff: `AGENT_EXECUTION_HANDOFF_TOKEN` and `EXECUTION_HANDOFF_TOKEN` share the `execution-handoff-secret`.

These contracts are enforced at runtime (mismatched clients get rejected) and documented as "must match" chains in the configuration reference.

### Policy bundle lifecycle
The action-authorization bundle has exactly one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay by `make sync-policy`. Changes require editing the canonical file, bumping its `version` field, updating scenario expectations in `policy-scenarios.yaml`, running `make verify` (schema + scenario + parity checks), then deploying. A missing or invalid bundle at the configured path fails startup (`PolicyLoadError`) — there is no silent fallback to a packaged default.

### Runtime profiles
LLM provider selection and capability toggles are applied via Kustomize profile overlays under `shared/platform-ops/gitops/dev-k8s/base/runtime-profiles/`. Only one LLM profile is active at a time (selected via `select-runtime-profile.sh`); two non-LLM postures (`mutating-dev`, `browser-dev`) permanently merge their env into `platform-runtime-config`. Base configs stay deny-by-default; profiles opt features in.

## Conventions and constraints

- **Every setting is an environment variable.** No `.env` files, `.yaml` configs, or TOML files are read by application code at runtime.
- **Defaults are defined in code.** Dataclass field defaults encode the safe baseline; `runtime-config.env` only overrides what differs from defaults.
- **Dangerous features are off by default.** Mutating tools, browser automation, and mutating resume handoff all default to `false`; enabling requires explicit env vars plus policy grants plus RBAC.
- **Missing dependencies fail closed or degrade safely.** Unset service URLs return 503 (fail-closed proxy routes); unset audit URLs fall back to log-only emission; unreachable Postgres session stores fall open to memory for agent state but fail startup for unknown backend names.
- **Secrets are provisioned, not authored.** Operators run `sync-*-secrets.sh` scripts; secrets are never checked into Git.
- **Policy bundles are immutable at runtime.** Bundles are cached keyed on their path; changes take effect only on pod restart. Both gateways expose a SHA-256 fingerprint of the loaded bundle for provenance verification.
- **Cross-service credentials use a client_id=secret registry pattern.** Consumers register a client id and secret; servers maintain a `client_id=secret,...` registry and reject unknown clients.
- **Validation happens at import/startup.** Invalid values raise `ValueError` before the service becomes ready, preventing misconfigured deployments from serving traffic.