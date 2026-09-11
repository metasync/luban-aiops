---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with GitOps Runtime Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
---

## What system/approach is used

Every service in the Luban AIOps platform loads configuration exclusively from **environment variables** via frozen Python `dataclass` settings objects. There are no `.env` files read at runtime, no YAML/JSON config files consumed by the application code, and no centralized config server. Configuration is layered through Kubernetes ConfigMaps (runtime-config.env per service) and Secrets (per-service `*-runtime-secrets`, plus shared secrets like `execution-signing-secret`, `execution-handoff-secret`, `audit-service-runtime-secrets`, etc.), which are mounted as environment variables into each pod.

The canonical cross-service variable map is documented in `docs/guides/configuration-reference.md`, which enumerates every variable, its purpose, default, source (runtime-config vs runtime-secrets), and cross-service dependency chains (token delegation, audit ingestion, skills retrieval, incident intake, browser web-checks, signed execution, isolated worker handoff).

## Key files and packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — largest settings object; defines `RuntimeSettings` with ~60 knobs for LLM provider options, kernel tuning, HITL timeouts, evidence caps, model discovery, signed execution, isolated worker handoff, audit/incident/skills client credentials, authoring-trace bounds, skill graduation limits, plus validation in `__post_init__`. Accessed via `core/config.get_settings()` cached with `lru_cache(maxsize=1)`.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` (agent/identity URLs, JWKS cache, token audience/delegation, policy path, dev user, audit/incident/skills tool-gateway/proxy URLs).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (auth/policy, K8s connector, mutating tools gate, redaction, Elastic connector, audit/skills/incidents clients, full browser connector: CDP endpoint, session TTL, max sessions, origin allowlist, flow step budget, credential-sets file path, screenshot cap, upload dir).
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` (signing key, handoff token, tool-gateway URL, state store backend/db url, audit client, flight retention); startup validation enforces positive timeout and valid postgres DSN when backend is postgres.
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` + `ServiceClient` / `WorkloadClient` models; parses comma-delimited `IDENTITY_SERVICE_CLIENTS` (`client_id:secret:aud1|aud2`) and `IDENTITY_WORKLOAD_CLIENTS` (`subject=client_id:aud1|aud2`).
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings`; parses JSON `SKILLS_SOURCES` (local/git entries with strict id/url/path validation), JSON `SKILLS_GIT_TOKENS`, comma-separated `SKILLS_QUERY_CLIENTS`, workload mappings.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings`; parses `INCIDENT_QUERY_CLIENTS`, `INCIDENT_WORKLOAD_CLIENTS`, `INCIDENT_CONNECTORS` (defaults to built-in `audit`).
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings`; parses `AUDIT_INGEST_CLIENTS`, `AUDIT_WORKLOAD_CLIENTS`, validates positive `AUDIT_EXPORT_MAX_ROWS`.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service ConfigMap env files that supply non-secret defaults (URLs, feature toggles, storage backends).
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared variables (OTLP endpoint, identity broker URL).
- `shared/platform-ops/gitops/gitops/*.sh` — secret provisioning scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-browser-credentials.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`).
- `shared/shared-contracts/policies/policy-default.yaml` — single canonical policy bundle copied byte-identically to both gateways and the dev overlay via `make sync-policy`.

## Architecture and conventions

1. **One frozen dataclass per service.** Each service defines a single `@dataclass(frozen=True)` settings class under `src/<service>/core/config.py` (or `runtime_settings.py` for agent-platform). All fields have sensible defaults so services start without any configuration except what they need.
2. **`from_env()` classmethod + `lru_cache` singleton.** Every settings class exposes `from_env()` that reads `os.getenv(...)` with defaults, and a module-level `get_settings()` cached function returns the same instance for the process lifetime. This is the only way to access configuration inside services.
3. **Strict startup validation in `__post_init__`.** Invalid values raise `ValueError` immediately, failing startup fast rather than degrading silently. Examples: `AGENTSCOPE_MAX_ITERS >= 1`, `AGENTSCOPE_CONTEXT_TRIGGER_RATIO ∈ (0, 0.9)`, unknown store backends rejected, postgres backend requires `*_DB_URL`, positive timeouts enforced, IANA timezone validated via `zoneinfo.ZoneInfo`.
4. **Boolean parsing is uniform.** Truthy strings are `{"1", "true", "yes", "on"}`; all other values are false. Some services use a local helper (`_env_bool`, `_optional_bool`) while others inline the check.
5. **Secrets never live in ConfigMaps.** Secrets are provisioned as Kubernetes `Secret` objects by dedicated `sync-*` scripts and injected as env vars or mounted files (e.g., `GATEWAY_BROWSER_CREDENTIAL_SETS` points to a mounted JSON file containing credential sets — no inline secrets accepted).
6. **Cross-service client registries follow a consistent pattern.** Services expose a registry of allowed callers parsed from a comma-delimited env var:
   - `AUDIT_INGEST_CLIENTS` (`client_id=secret,...`)
   - `SKILLS_QUERY_CLIENTS` (`client_id=secret,...`)
   - `INCIDENT_QUERY_CLIENTS` (`client_id=secret,...`)
   - `IDENTITY_SERVICE_CLIENTS` (`client_id:secret:aud1|aud2,...`)
   - `*_WORKLOAD_*CLIENTS` for projected Kubernetes SA tokens (`subject=client_id,...`)
7. **Feature flags are opt-in by default.** Mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED=false`), browser connector (`GATEWAY_BROWSER_ENABLED=false`), Elastic connector (`GATEWAY_ELASTIC_ENABLED=false`), kernel tracing (`AGENTSCOPE_KERNEL_TRACING=false`), task tools (`AGENTSCOPE_TASK_TOOLS_ENABLED=false`), model discovery (`AGENT_MODEL_DISCOVERY_ENABLED=true` but can be disabled) — features are disabled unless explicitly enabled.
8. **Policy bundle is single-source-of-truth.** `shared/shared-contracts/policies/policy-default.yaml` is the canonical copy; `make sync-policy` replicates it to both gateway consumers and the dev overlay. Drift fails `make verify`. Consumers load from a configured path (`PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`) and fail startup on missing/invalid bundles.
9. **Runtime profiles decouple LLM provider selection from profile labels.** Since SPEC-026 the profile is a free-form deploy label; provider is selected via `AGENTSCOPE_PROVIDER`. Profile overlays merge additional env into `platform-runtime-config`, and two permanent postures (`mutating-dev`, `browser-dev`) always merge their env regardless of active profile.
10. **Degrade-to-log-only for optional dependencies.** Audit emission, skills retrieval, incident-report assembly, and isolated execution handoff all degrade gracefully when their URLs/secrets are unset — never blocking the primary request path.

## Conventions and constraints

- **All configuration is environment-variable driven.** No file-based config loading exists in application code; files are only used for mounted secrets (credential sets, policy bundles at configured paths, JWKS endpoints).
- **Defaults must be safe and conservative.** New knobs default to deny-by-default or disabled (e.g., mutating tools off, browser off, Elastic off, kernel tracing off) so deployments are secure out of the box.
- **Unknown store backends fail startup.** Values like `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `EXECUTION_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND` reject unknown values at parse time.
- **Missing required secrets fail closed, not open.** Absent `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes with `signing_unavailable`; absent `AGENT_EXECUTION_WORKER_URL`/`AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`; absent `INCIDENT_WEBHOOK_TOKEN` disables intake with 503; unset `*_SERVICE_URL` leaves routes fail-closed (503).
- **Cross-service secrets must match exactly.** The `configuration-reference.md` documents the exact contract for each chain (delegation secret between platform-gateway and identity-service, audit ingest secret between emitters and audit-service, skills/incident query secrets between callers and their registries). Provisioning scripts generate and propagate matching values.
- **Policy changes require a documented workflow.** Edit canonical `policy-default.yaml`, update scenario expectations if needed, run `make sync-policy`, verify with `make verify`, then deploy — there is no hot reload of policy bundles.
- **Secrets are provisioned via scripts, never committed.** Every `sync-*.sh` script generates random secrets or reads them from CI/local env and writes K8s Secrets; `SKIP_*_SECRETS=true` flags opt out of provisioning.