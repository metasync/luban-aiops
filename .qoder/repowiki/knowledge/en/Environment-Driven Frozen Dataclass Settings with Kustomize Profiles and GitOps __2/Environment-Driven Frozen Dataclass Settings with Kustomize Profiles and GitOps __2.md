---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Kustomize Profiles and GitOps Secret Sync
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/audit-service/src/audit_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
---

# Configuration System

## Approach

The platform uses a uniform, environment-variable-driven configuration system across all Python services. Each service defines its own frozen `dataclass` settings object in `src/<service>/core/config.py`, exposes a classmethod `from_env()` that reads values from `os.environ`, and provides a module-level cached accessor (e.g. `get_settings()`) consumed by the rest of the application. There is no YAML/JSON config file parsed at runtime — configuration is purely **environment variables**, mounted into pods via Kubernetes ConfigMaps (`runtime-config.env`) and Secrets (`*-runtime-secrets`).

## Key Files and Packages

- Per-service settings classes: `products/*/src/*/core/config.py` (agent-platform uses a slightly different layout under `runtime_settings.py`, loaded through `core/config.py`).
- Shared env helpers: `products/agent-platform/src/agent_service/core/env.py` (`get_env_value`, `get_env_int`).
- Global documentation of every variable: `docs/guides/configuration-reference.md`.
- Deployment overlays: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` and `runtime-secrets.example.env` per service, plus `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` for cross-cutting vars like `OTEL_*` and `IDENTITY_SERVICE_URL`.
- Profile overlays: `shared/platform-ops/gitops/runtime-profiles/` (default, browser-dev, mutating-dev) and scripts `select-runtime-profile.sh`, `verify-runtime-profile.sh`.
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh` (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-skills-secrets.sh`, `sync-browser-credentials.sh`, `sync-runtime-secret.sh`, `sync-sessions-db.sh`).
- Policy bundle source: `shared/shared-contracts/policies/policy-default.yaml`, replicated to both gateways and dev overlay via `make sync-policy`.

## Architecture and Conventions

### One frozen dataclass per service
Every service follows the same shape: a frozen `@dataclass` holding all runtime knobs, a `from_env()` classmethod that parses `os.environ`, optional `__post_init__` validation, and a module-level cached getter. Examples include `AuditSettings`, `ExecutionSettings`, `IdentitySettings`, `IncidentSettings`, `platform_gateway.core.config.Settings`, and `agent_service.runtime_settings.RuntimeSettings`. The agent-platform additionally splits provider-specific option types (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) into sibling frozen dataclasses and validates that `provider_options` matches the active `provider` in `__post_init__`.

### Strict startup-time validation
Invalid values fail fast during import/startup rather than silently degrading. Validation covers ranges (`max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, timeouts `> 0`), allowed choices (`AGENTSCOPE_PROVIDER` must be one of `dashscope|deepseek|openai|luban`, `DEEPSEEK_REASONING_EFFORT` in `{high,max}`, `OPENAI_REASONING_EFFORT` in `{none,minimal,low,medium,high,xhigh}`), IANA timezone names, and type mismatches between `provider` and `provider_options`.

### Optional vs required knobs
Optional settings are read via `_optional_str/_optional_bool/_optional_int/_optional_float` helpers that treat empty strings as unset; required secrets (API keys, signing keys, client secrets) are simply not set unless provisioned, and downstream code treats their absence as a failure mode (e.g. missing `AGENT_EXECUTION_SIGNING_KEY` fails mutating resumes closed with `signing_unavailable`; missing `AGENT_EXECUTION_WORKER_URL` fails with `worker_unavailable`; unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing). This gives each feature a clear on/off surface.

### Layered deployment via Kustomize profiles
Configuration is layered: base `runtime-config.env` per service, optional profile overlays under `runtime-profiles/` (default, browser-dev, mutating-dev), and secret files mounted separately. `select-runtime-profile.sh` switches the active profile; `verify-runtime-profile.sh` asserts profile validity. The LLM backend is selected via `AGENTSCOPE_PROVIDER` inside the active profile's ConfigMap, decoupled from the profile label since SPEC-026.

### Cross-service secret contracts
Secrets are never committed to Git. They are generated or rotated by `sync-*.sh` scripts and mounted as Kubernetes Secrets. Cross-service chains enforce matching pairs:
- Token delegation: `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry.
- Audit ingestion: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry in audit-service.
- Skills query: `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`.
- Incident query: `*INCIDENT_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`.
- Execution signing: `AGENT_EXECUTION_SIGNING_KEY` ↔ `EXECUTION_SIGNING_KEY`.
- Execution handoff: `AGENT_EXECUTION_HANDOFF_TOKEN` ↔ `EXECUTION_HANDOFF_TOKEN`.

### Policy-as-code
The action-authorization policy bundle has exactly one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to both gateways' packaged defaults and the dev overlay via `make sync-policy`. A missing or invalid bundle at the configured path fails startup (`PolicyLoadError`, no silent fallback); consumers expose a SHA-256 fingerprint of the loaded bundle for provenance verification.

### OpenTelemetry as shared runtime config
All pods inherit `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `IDENTITY_SERVICE_URL` from `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`. The OTLP auth header (`OTEL_EXPORTER_OTLP_HEADERS`) lives in each service's runtime-secrets Secret and is provisioned by `sync-otel-secrets.sh`.

## Conventions and Constraints

- **Environment-only**: No runtime-parsed YAML/JSON config files are used for application settings; everything comes from `os.environ`.
- **Frozen dataclasses**: All settings objects are immutable once constructed, preventing accidental mutation at runtime.
- **Fail-closed by default**: Features are disabled when their required variables are absent (e.g. mutating tools, browser connector, skills/hub/incident connectors, isolated execution worker). Enabling them requires explicit opt-in variables.
- **Graceful degradation where safe**: Unreachable audit-service degrades to log-only emission without blocking requests; model discovery failures fall through a ladder (live → memory → Postgres → curated) without blocking chat.
- **Typed parsing with strict errors**: Boolean parsing accepts only `1|true|yes|on` / `0|false|no|off`; choice fields reject unknown values; numeric fields validate bounds in `__post_init__`.
- **Secrets live in K8s Secrets, never in Git**: Provisioned exclusively by `sync-*.sh` scripts; examples live in `*-secrets.example.env` as templates.
- **Profiles are additive overlays**: Base env + profile overlay + secrets form the final pod environment; non-LLM postures (`mutating-dev`, `browser-dev`) merge permanently alongside the active LLM profile.
- **Single source of truth for policy**: Editing replicas directly is prohibited; changes go through the canonical file and `make sync-policy`.
- **Cross-service dependency map is documented**: `docs/guides/configuration-reference.md` enumerates every variable, its default, source (ConfigMap vs Secret), and the activation chain it participates in.