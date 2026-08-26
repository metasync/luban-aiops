---
kind: configuration_system
name: Environment-Driven Frozen Settings with Per-Service Config Modules and GitOps Secret Provisioning
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
    - products/platform-gateway/src/platform_gateway/policies/policy-default.yaml
    - products/tool-gateway/src/tool_gateway/policies/policy-default.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
---

# Configuration System

## Approach

Every service in the platform follows a uniform, environment-variable-driven configuration model built on Python `dataclasses` that are **frozen** (`@dataclass(frozen=True)`) and loaded exclusively from `os.environ`. There is no YAML/JSON config file loading at runtime for application settings — configuration lives entirely in environment variables (injected via Kustomize `runtime-config.env` files and Kubernetes Secrets). Policy rules are the only exception: they are loaded from YAML bundles mounted into each gateway pod.

Each product exposes its own `core/config.py` defining a single frozen `*Settings` dataclass plus a module-level `get_settings()` accessor cached via `functools.lru_cache(maxsize=1)`. A classmethod `from_env()` reads every setting from an `os.getenv(...)` call with a documented default. Complex values (comma-separated client registries, JSON lists of sources/tokens) are parsed by small helper functions (`parse_ingest_clients`, `parse_workload_clients`, `parse_sources`, `parse_git_tokens`, `parse_connectors`) that raise a per-service `SettingsError` on malformed input so misconfiguration fails fast at startup rather than later.

The agent-platform diverges slightly: its runtime knobs live in `agent_service/runtime_settings.py` as `RuntimeSettings` with typed provider option sub-dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and a `__post_init__` that validates ranges, IANA timezone names, and provider/options type compatibility. It also provides `_optional_str/int/float/bool/choice` helpers that raise `ValueError` on invalid booleans or choices.

A parallel `core/runtime.py` in each service defines a tiny `*RunSettings` dataclass (host/port) used only by the HTTP server bootstrap; it shares the same `from_env` + `lru_cache` pattern but is separate from business configuration.

## Key Files

- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings`
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings`
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings`
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings`
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` (+ provider options)
- `products/*/src/*/core/runtime.py` — per-service host/port run settings
- `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml` — action authorization policy bundle
- `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml` — identical copy consumed by tool-gateway
- `shared/shared-contracts/policies/policy-default.yaml` — canonical source (mirrored to consumers)
- `docs/guides/configuration-reference.md` — authoritative cross-service env var map, secret contracts, and provisioning scripts
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service non-secret defaults injected into pods
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` — per-service secret key inventory
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared OTLP / identity broker URL
- `shared/platform-ops/gitops/*.sh` — `sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-otel-secrets.sh`, `select-runtime-profile.sh`

## Architecture and Conventions

1. **One frozen settings class per service.** Each service has exactly one `*Settings` dataclass in `core/config.py` with a `from_env()` classmethod and a `@lru_cache(maxsize=1)` `get_settings()` accessor. Consumers import `get_settings()` and never touch `os.getenv` directly.
2. **All defaults are explicit.** Every field carries a sensible default in the dataclass definition; `from_env()` only overrides when an env var is set. This makes deployments fully configurable without requiring all variables to be present.
3. **Boolean parsing is normalized.** Booleans accept `"1", "true", "yes", "on"` (case-insensitive, stripped) and everything else is falsy. The agent-platform's `_optional_bool` additionally rejects unknown strings by raising `ValueError`.
4. **Complex lists/maps use comma-delimited or JSON env vars.** Client registries use `client_id=secret,...` format; skills sources and git tokens use JSON arrays/objects. Parser helpers validate shape and reject unknown types or duplicates at parse time.
5. **Validation happens at construction.** `__post_init__` (agent-platform) and parser helpers enforce constraints (range bounds, IANA timezone, provider/options type match, duplicate `source_id`, relative path checks). Invalid configuration raises `ValueError` / `SettingsError` during process start-up.
6. **Policy is externalized to YAML.** Authorization rules live in `policies/policy-default.yaml` (and the canonical `shared/shared-contracts/policies/policy-default.yaml`). They are not read from env; instead services load them from a path configured via `*_POLICY_PATH` env vars. The default bundle enforces deny-by-default with tiered approval (`tier_1` self-approval vs `tier_2` distinct approver).
7. **Secrets are provisioned via scripts, never committed.** All secrets (API keys, client secrets, webhook tokens, OTLP headers, execution signing keys) are created by `sync-*secrets.sh` scripts that generate random values or read from CI-provided inputs and write Kubernetes Secrets. `runtime-secrets.example.env` documents the keys but contains no real values.
8. **Cross-service credential contracts are symmetric.** Emitter services configure `<SERVICE>_AUDIT_CLIENT_ID` + `<SERVICE>_AUDIT_CLIENT_SECRET`; the audit-service registers them in `AUDIT_INGEST_CLIENTS`. Token delegation requires matching `PLATFORM_GATEWAY_SERVICE_CLIENT_*` ↔ `IDENTITY_SERVICE_CLIENTS` entries. Skills, incidents, and delegation chains follow the same emitter↔registry pattern.
9. **Feature flags are env-driven toggles.** Features like mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED`), Elastic connector (`GATEWAY_ELASTIC_ENABLED`), HITL bridging (`AGENT_HITL_CONFIRM_TIMEOUT > 0`), live model discovery (`AGENT_MODEL_DISCOVERY_ENABLED`), and audit emission (`*_AUDIT_SERVICE_URL` set) are controlled purely by env vars; unset means disabled/log-only.
10. **Kustomize overlays drive deployment profiles.** Runtime profiles under `shared/platform-ops/gitops/runtime-profiles/` swap ConfigMaps that set `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, etc. `select-runtime-profile.sh` switches the active profile.

## Conventions and Constraints

- **No `.env` files checked in.** All configuration is injected at runtime via Kustomize ConfigMaps and Kubernetes Secrets; there are no checked-in `.env` files.
- **Configuration is immutable per process.** Frozen dataclasses + `lru_cache` mean settings cannot be mutated after first access; restart is required to change configuration.
- **Unknown store backends fail startup.** `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` reject unknown values at parse time.
- **Missing secrets degrade gracefully where safe.** Unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; unset `GATEWAY_SKILLS_SERVICE_URL` leaves the skills connector unregistered; unset `PLATFORM_GATEWAY_INCIDENT_SERVICE_URL` makes portal routes return 503. However, `AGENT_EXECUTION_SIGNING_KEY` absent causes mutating resumes to fail closed with `signing_unavailable` — missing signing never degrades to unsigned execution.
- **Policy must stay byte-identical across consumers.** The canonical source is `shared/shared-contracts/policies/policy-default.yaml`; consumers mirror it via `make sync-policy` and validation runs against a JSON schema before deploy.
- **Per-service env var prefixes are mandatory.** Variables are scoped with their service prefix (`PLATFORM_GATEWAY_*`, `GATEWAY_*`, `AUDIT_*`, `SKILLS_*`, `INCIDENT_*`, `AGENTSCOPE_*`, `AGENT_*`) to avoid collisions between services.
- **Port resolution tolerates Kubernetes `tcp://IP:PORT` strings.** The `_resolve_port` helper in each `runtime.py` falls back to the default if the port env var is not a plain integer.
- **Workload identity is opt-in.** Projected SA token paths (`PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH`, `GATEWAY_WORKLOAD_TOKEN_PATH`) and workload issuer/client mappings are empty/disabled by default and must be explicitly provisioned.