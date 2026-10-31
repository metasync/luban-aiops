---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Configuration System
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/execution-runtime/runtime-config.env
---

## Approach

The Luban AIOps platform uses a uniform, framework-free configuration pattern across every product service: each service owns a `core/config.py` (or equivalent) that defines a **frozen `dataclass`** of typed settings, parses them from environment variables in a classmethod `from_env()`, and exposes the instance through an `lru_cache(maxsize=1)` accessor (`get_settings()`). There is no shared configuration library — each module implements the same shape independently. The agent-service's `runtime_settings.py` is the most elaborate example, but the pattern is replicated verbatim in `platform-gateway/core/config.py`, `tool-gateway/core/config.py`, `execution-runtime/core/config.py`, and the other services.

Configuration values come exclusively from `os.getenv`; there are no `.env` files loaded at runtime, no YAML/JSON config files consumed by the application code, and no feature-flag framework. File-based inputs (policy bundles, credential-set JSONs, keyrings) are referenced by path and parsed lazily inside the feature code, not during settings construction.

## Key Files

- `products/agent-platform/src/agent_service/runtime_settings.py` — largest settings surface; ~60 fields covering LLM provider options, kernel tuning, HITL, evidence caps, execution handoff, audit/incident/skills client wiring, authoring-trace bounds, graduation limits, model discovery, and delegated identity trust.
- `products/tool-gateway/src/tool_gateway/core/config.py` — gateway connectors (Kubernetes, browser/web-checks, HTTP, secrets/password generation, Ansible MCP, ServiceNow), policy path, redaction, Elastic, delegated custody/acquisition/authorization (SPEC-070).
- `products/platform-gateway/src/platform_gateway/core/config.py` — identity broker, token audience/delegation, workload token path, audit/incident/skills proxy URLs, target-authorization flags.
- `products/execution-runtime/src/execution_runtime/core/config.py` — signing key, handoff token, tool-gateway URL, admission epoch, delegated identity trust for execution handoff.
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, per-service tables, secret contracts, and feature activation matrix.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service ConfigMap source of truth for non-secret defaults used by the dev overlay.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared variables (`OTEL_*`, `IDENTITY_SERVICE_URL`).

## Architecture and Conventions

### Per-service frozen dataclass
Every service defines one frozen dataclass (`RuntimeSettings`, `GatewaySettings`, `PlatformGatewaySettings`, `ExecutionSettings`) with all defaults as keyword arguments. The class is immutable after construction, so configuration cannot be mutated at request time.

### Environment parsing via `from_env()`
A `@classmethod` reads every field from `os.getenv`, applying type coercion (`int`, `float`, boolean normalization to `{"1","true","yes","on"}`, comma-split tuples, optional-string helpers). Boolean parsing is consistent: `_optional_bool` raises `ValueError` on unrecognized strings, while `_env_bool(name, default)` silently falls back to the default.

### Cached singleton access
Each module exports `get_settings()` decorated with `@lru_cache(maxsize=1)`, so the process loads configuration once and reuses it. This is the only way consumers import settings.

### Validation in `__post_init__`
Startup validation lives in `__post_init__`. Invalid ranges, unsupported enum choices, missing required dependencies for enabled features, and cross-field invariants raise `ValueError`, causing pod startup failure rather than silent misconfiguration. Examples include:
- `AGENTSCOPE_MAX_ITERS >= 1`, `context_trigger_ratio ∈ (0, 0.9)`, `tool_result_limit >= 1`.
- `execution_worker_timeout_seconds ∈ (0, 120]`.
- Enabling `execution_admission_enabled` requires both `execution_state_db_url` and `execution_admission_epoch`.
- Enabling any SPEC-070 delegated flag requires the full set of issuer/audience/JWKS/allowlist fields.
- Password-policy overrides may only tighten the contract floor; weakening raises.

### Feature flags are opt-in booleans
Most capabilities are disabled by default (`browser_enabled=false`, `http_enabled=false`, `secrets_enabled=false`, `ansible_mcp_enabled=false`, `servicenow_enabled=false`, `delegated_*_enabled=false`, `execution_admission_enabled=false`, `target_authorization_enabled=false`). Enabling a flag typically requires additional infrastructure configuration validated at startup.

### Secrets vs. configuration separation
Secrets are never read directly from env in the settings layer where possible; they are passed through as opaque strings or mounted file paths. The documentation (`docs/guides/configuration-reference.md`) catalogs every Kubernetes Secret name (`agent-platform-runtime-secrets`, `execution-signing-secret`, `execution-handoff-secret`, `platform-gateway-runtime-secrets`, `identity-service-runtime-secrets`, `tool-gateway-browser-credentials`, etc.) and the provisioning scripts (`sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-skills-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `sync-ansible-credentials.sh`, `sync-servicenow-credentials.sh`).

### Cross-service dependency chains
The configuration reference documents explicit cross-service contracts: e.g., `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` must match the corresponding `AUDIT_INGEST_CLIENTS` registry; skills/hub/query clients use dedicated registries (`SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`). These are enforced at the receiving service's authentication layer, not in the settings parser.

### Policy bundle as configuration-as-code
The action-authorization bundle has exactly one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay by `make sync-policy`; contract tests fail `make verify` on drift. A missing or invalid bundle fails startup (`PolicyLoadError`) — no silent fallback to the packaged default.

### Dev overlay convention
Each service under `shared/platform-ops/gitops/dev-k8s/base/<service>/` ships a `runtime-config.env` (ConfigMap source) and a `runtime-secrets.example.env` (template for generated secrets). The Kustomize base mounts these into the deployment, and overlays (e.g. `browser-dev`, `ansible-dev`, `servicenow-dev`) merge additional flags.

## Conventions and Constraints

- Every service's configuration is defined as a frozen `dataclass` with a `from_env()` classmethod and an `lru_cache`-wrapped `get_settings()` accessor. Observed in `agent_service.runtime_settings`, `tool_gateway.core.config`, `platform_gateway.core.config`, `execution_runtime.core.config`.
- All runtime knobs are exposed as environment variables; no `.env` loader, no YAML/JSON config consumed by application code.
- Boolean values are normalized case-insensitively against `{"1", "true", "yes", "on"}`; unknown boolean strings raise `ValueError` (agent-service's `_optional_bool`).
- Optional string helpers strip whitespace and treat empty strings as `None`: `_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice`.
- Feature switches default to `false` (deny-by-default); enabling a capability requires its supporting infrastructure to be configured, and startup validation rejects partially-enabled configurations.
- Cross-service secrets are provisioned by `make deploy`-invoked `sync-*-secrets.sh` scripts and documented in `docs/guides/configuration-reference.md#Secret Contracts`; they are never committed to Git.
- The policy bundle at `shared/shared-contracts/policies/policy-default.yaml` is the single source of truth; replicas are kept in sync by `make sync-policy` and verified by `make verify`.
- Unknown store backends (`SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND`, `EXECUTION_STATE_STORE_BACKEND`) fail startup or degrade predictably as documented.
- The configuration reference (`docs/guides/configuration-reference.md`) is the definitive cross-service dependency map; it explicitly states which variables activate which features, their defaults, and their source (profile ConfigMap, runtime-config, code default, or runtime-secrets).
- Missing required secrets for sensitive flows (execution signing key, handoff token, OIDC client secret, audit ingest credentials) cause the affected operation to fail closed (503 / rejected resume / handshake rejection) rather than degrading to an unauthenticated path.