---
kind: configuration_system
name: Configuration System — Environment Variables, Pydantic Settings, and Kustomize Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
---

# Configuration System

## Approach

The Luban platform uses a **plain-environment-variable + frozen dataclass** configuration model across every Python service. There is no centralized config framework (no `pydantic-settings`, no `dynaconf`, no `python-dotenv` loader). Each service owns its own settings module that reads `os.environ` directly, validates values in `__post_init__`, and exposes a frozen `Settings` dataclass plus a cached `get_settings()` accessor.

Kubernetes deployment is driven by **Kustomize overlays**. Base `runtime-config.env` files under `shared/platform-ops/gitops/dev-k8s/base/<service>/` declare defaults; feature-specific postures are layered through `shared/platform-ops/gitops/runtime-profiles/<profile>/` overlays (e.g. `mutating-dev`, `browser-dev`, `ansible-dev`, `servicenow-dev`, `secrets-dev`, `model-router-dev`). The `select-runtime-profile.sh` script generates the top-level `dev-k8s/kustomization.yaml`, always wiring the five dev postures alongside the chosen LLM provider profile.

Secrets are provisioned as Kubernetes `Secret` objects via dedicated shell scripts under `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-sessions-db.sh`, `sync-custody-db.sh`, etc.). Secrets are never committed to Git and are mounted into pods either as environment variables or as file mounts (credential-set JSON, policy YAML, workload token paths).

## Key Files and Packages

- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable map, secret contracts, activation matrices, and per-service tables with source/defaults.
- `products/*/src/*_service/core/config.py` — per-service settings modules (`platform_gateway/core/config.py`, `tool-gateway/core/config.py`, `audit-service/core/config.py`, `identity_service/core/config.py`, `incident_service/core/config.py`, `skills_hub/core/config.py`, `execution_runtime/core/config.py`).
- `products/agent-platform/src/agent_service/runtime_settings.py` — agent-service's largest settings module: frozen `RuntimeSettings` dataclass with typed provider options, model router candidates, validation, and `from_env()`.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — base default env for each service.
- `shared/platform-ops/gitops/runtime-profiles/<profile>/` — feature overlays that merge additional env vars and pod patches.
- `shared/platform-ops/gitops/select-runtime-profile.sh` — selects the switchable LLM provider profile and rejects non-switchable dev posture names.
- `shared/platform-ops/gitops/sync-*.sh` — secret provisioning scripts referenced from the configuration reference.

## Architecture and Conventions

1. **Per-service settings modules.** Every service defines a frozen dataclass with a `from_env()` classmethod that maps environment variables to typed fields. Values are validated in `__post_init__` (ranges, required pairs like admission epoch + DSN, IANA timezone parsing, provider/options type matching). Invalid configuration fails process startup rather than degrading silently.

2. **Boolean parsing helper.** Agent-service centralizes boolean/env helpers (`_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice`) accepting `1/true/yes/on` and `0/false/no/off`; other services inline equivalent logic.

3. **Caching layer.** Gateway-style services expose an `@lru_cache(maxsize=1)` `get_settings()` accessor so settings are parsed once at import time and reused throughout the process.

4. **Feature flags as environment variables.** Optional capabilities (browser tools, HTTP tools, mutating tools, skills ingestion, ServiceNow, Ansible MCP, delegated custody, model routing, context compression) are all controlled by explicit `*_ENABLED` / `*_TOOLS_ENABLED` env vars. Defaults are deny-by-default; enabling requires multiple coordinated knobs (e.g. browser tools need `GATEWAY_BROWSER_ENABLED=true`, `GATEWAY_BROWSER_ALLOW_ORIGINS`, reachable CDP endpoint, and `AGENT_HITL_CONFIRM_TIMEOUT > 0`).

5. **Kustomize overlay composition.** Base configs live under `dev-k8s/base/`. Feature profiles under `runtime-profiles/` add env vars and Deployment patches. `select-runtime-profile.sh` composes them into a single `kustomization.yaml`, always including the five dev postures regardless of the selected LLM provider profile.

6. **Separation of runtime-config vs runtime-secrets.** Non-sensitive env vars go into ConfigMaps (`runtime-config.env`); secrets go into Kubernetes Secrets (`runtime-secrets.example.env` templates, populated by `sync-*.sh` scripts). The configuration reference documents which variables belong in each.

7. **Cross-service client registries.** Many inter-service connections use a shared-secret registry pattern: callers register `<client_id>=<secret>` entries on the server side (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) and present matching `*_CLIENT_ID` / `*_CLIENT_SECRET` env vars. Provisioning scripts generate one random shared secret and write it to both sides.

8. **Policy bundle as code.** The canonical policy bundle lives at `shared/shared-contracts/policies/policy-default.yaml` and is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`. Drift is enforced by contract tests; hot reload is deliberately absent — changes require a pod restart.

9. **OpenTelemetry push is shared.** All services read `OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, and `OTEL_EXPORTER_OTLP_HEADERS` from the shared `runtime.env` plus per-service runtime-secrets.

## Conventions and Constraints

- **Environment variables are the sole configuration surface.** No `.env` files, no TOML/YAML config files consumed by the application at runtime (policy bundles are the only exception, loaded from a configured path).
- **Unknown backend names fail startup.** For example, `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND`, and `EXECUTION_STATE_STORE_BACKEND` reject unknown values at startup.
- **Opt-in features default off.** Mutating tools, browser tools, HTTP tools, skills ingestion, ServiceNow, Ansible MCP, delegated custody, model routing, context compression, email delivery, and signed execution all default to disabled; enabling requires multiple coordinated configuration steps documented in `configuration-reference.md`.
- **Missing critical secrets fail closed.** Absent `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN`, incident/skills query credentials, or audit ingest credentials cause the relevant operation to fail closed (503, `signing_unavailable`, `worker_unavailable`) rather than degrade to unauthenticated execution.
- **Cross-service secret contracts must match.** The configuration reference documents exact pairing rules (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`; `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`). Mismatches are caught at the receiving service's auth layer.
- **Policy bundle drift is enforced.** Editing a replica instead of the canonical `policy-default.yaml` causes `make verify` to fail; the rollout sequence mandates editing the canonical file, bumping its `version`, updating scenarios, running `make sync-policy`, then committing all replicas together.
- **Dev posture profiles are not switchable LLM profiles.** `select-runtime-profile.sh` explicitly rejects `mutating-dev`, `browser-dev`, `secrets-dev`, `ansible-dev`, `servicenow-dev`, and `model-router-dev` as switchable profiles — they are always wired in alongside the chosen LLM provider profile.
- **Bounded validation at construction.** Range checks (e.g. `AGENTSCOPE_MAX_ITERS >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, worker timeout ≤ 120s, `SKILLS_COMPOSITION_MAX_SUB_SKILLS >= 1`) raise `ValueError` during `RuntimeSettings.__post_init__`, preventing misconfigured processes from starting.