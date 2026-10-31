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
---

## Approach

The Luban platform uses a uniform, code-first configuration system across all Python services: each service owns a `core/config.py` (or equivalent) that defines a **frozen `dataclass`** with typed defaults and an `@classmethod from_env()` loader reading exclusively from `os.environ`. There is no `.env` file parser, no YAML/JSON config files consumed at runtime by the application code, and no feature-flag framework. Configuration values are supplied to pods via Kubernetes ConfigMaps (`runtime-config.env`) and Secrets (`runtime-secrets`, plus specialized secrets like `execution-signing-secret`, `execution-handoff-secret`, and per-connector credential-set JSON mounts). A module-level `@lru_cache(maxsize=1)`-decorated `get_settings()` function provides process-wide singleton access.

This pattern is implemented in every service:
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` (the largest, ~600 lines), covering LLM provider options, kernel tuning, HITL, evidence caps, execution handoff, audit/incident/skills clients, authoring-trace bounds, and skill graduation limits.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings`, covering identity, policy, K8s tools, browser/HTTP/Ansible/ServiceNow connectors, secret delivery, email, and audit clients.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`, covering agent/identity URLs, token exchange, workload tokens, policy path, audit/incident/skills clients, and portal proxy endpoints.
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings`, covering signing key, handoff token, tool-gateway URL, state store backend, admission epoch, and audit client.
- `products/audit-service/src/audit_service/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/incident-service/src/incident_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py` follow the same shape.

The canonical cross-service variable map lives in `docs/guides/configuration-reference.md`; it is treated as the authoritative operator-facing contract and links each section back to its source file.

## Architecture and Conventions

### Frozen dataclasses + `from_env()`
Every settings class is `@dataclass(frozen=True)`, so mutation after construction is impossible. Defaults live on the class fields; parsing happens only in `from_env()`, which reads `os.getenv(...)` with explicit defaults. This makes the default behavior part of the type definition rather than hidden in a loader.

### Validation in `__post_init__`
Type coercion happens in `from_env()`; semantic validation happens in `__post_init__`, raising `ValueError` with human-readable messages. Examples include:
- `RuntimeSettings.__post_init__`: validates `max_iters >= 1`, `context_trigger_ratio` in `(0, 0.9)`, `AGENTSCOPE_TIMEZONE` against `zoneinfo.ZoneInfo`, `execution_worker_timeout_seconds <= 120`, required pairs for durable admission (`execution_admission_enabled` requires both `execution_state_db_url` and `execution_admission_epoch`).
- `GatewaySettings.__post_init__`: validates `secret_delivery_backend` ∈ `{memory, redis}`, positive TTLs/capacities, port ranges, Ansible transport ∈ `{streamable_http, stdio}`, and password-policy overrides may only *tighten* the canonical floor (imported lazily to avoid a module-level dependency).
- `ExecutionSettings.__post_init__`: validates gateway timeout ∈ `(0, 30]`, `state_store_backend` ∈ `{memory, postgres}`, flight retention ≥ 1.

### Boolean parsing helpers
Services define small helpers for truthy parsing: `agent_service.runtime_settings._optional_bool` accepts `"1", "true", "yes", "on"` (and their falsy counterparts); `tool_gateway.core.config._env_bool` uses the same set with a default string argument. Unknown boolean strings raise `ValueError` in the agent service's helper.

### Optional vs required semantics
Optional values return `None` when unset/blank (via `_optional_str` / `_optional_int` / `_optional_float` / `_env_optional_int` / `_env_optional_tuple`), letting downstream code distinguish "not configured" from a zero/false value. Required values either have non-empty defaults or fail startup in `__post_init__`.

### Feature flags are environment variables
Capabilities are toggled via dedicated env vars (e.g. `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `AGENT_MODEL_DISCOVERY_ENABLED`, `EXECUTION_ADMISSION_ENABLED`). The convention is **deny-by-default**: connector flags default to `False`, allowlists default to empty tuples, and enabling them requires explicit operator configuration.

### Secrets handling
Secrets are never inline env values accepted by the config layer; they are read from `os.getenv()` but documented as coming from Kubernetes Secret mounts. Credential sets for browser/HTTP/Ansible/ServiceNow connectors are mounted as JSON files referenced by a path env var (`GATEWAY_BROWSER_CREDENTIAL_SETS`, etc.), with fallback chains (e.g. `GATEWAY_HTTP_CREDENTIAL_SETS` → `GATEWAY_BROWSER_CREDENTIAL_SETS`; `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS` → `GATEWAY_HTTP_CREDENTIAL_SETS` → `GATEWAY_BROWSER_CREDENTIAL_SETS`). Cross-service shared secrets (token delegation, audit ingestion, skills query, incident query) are provisioned by scripts under `shared/platform-ops/gitops/` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-ansible-credentials.sh`, `sync-servicenow-credentials.sh`, `sync-otel-secrets.sh`).

### Policy bundle as config-as-code
The action-authorization policy is the one non-env configuration artifact: canonical source `shared/shared-contracts/policies/policy-default.yaml`, synced byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`. Consumers load it from a filesystem path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`, default `/etc/luban/policy/policy.yaml`). A missing or invalid bundle fails startup (`PolicyLoadError`, no silent fallback). Version discipline is enforced by `make verify` checking schema, scenario expectations, and copy parity.

### Runtime profiles (agent-service only)
The agent-service supports pluggable LLM backends through Kustomize profile overlays selected by `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`. Profiles are decoupled from providers since SPEC-026: the profile label is generic (`default`) and provider selection is a ConfigMap knob (`AGENTSCOPE_PROVIDER`). Five non-LLM postures (`mutating-dev`, `browser-dev`, `secrets-dev`, `ansible-dev`, `servicenow-dev`) merge additional env into `platform-runtime-config` and are not switchable.

### Documentation as enforcement surface
`docs/guides/configuration-reference.md` is the definitive cross-service environment variable dependency map. It documents the Feature Activation Matrix, per-service variable tables (with Source column distinguishing `runtime-config`, `runtime-secrets`, and `code default`), cross-service dependency chain diagrams, secret contracts, and the policy rollout workflow. Each per-service table cites its source file, making the doc a spec that can be audited against the code.

## Conventions and Constraints

- Every service exposes a frozen `dataclass` settings object with a `from_env()` classmethod and a cached `get_settings()` accessor — observed consistently across `agent_service`, `tool_gateway`, `platform_gateway`, `execution_runtime`, `audit_service`, `identity_service`, `incident_service`, and `skills_hub`.
- All configuration is read from `os.environ`; there is no `.env` file loading, no YAML/JSON runtime config consumption, and no feature-flag library.
- Connector features are off-by-default behind explicit `*_ENABLED` env vars; enablement requires both the flag and any required companion variables (URLs, credentials, allowlists).
- Semantic validation is performed in `__post_init__` and raises `ValueError` with descriptive messages — misconfiguration fails fast at startup rather than degrading silently.
- Cross-service shared secrets use a client_id/client_secret registry pattern where the consumer registers its id+secret and the server maintains a `*_CLIENTS` registry (e.g. `IDENTITY_SERVICE_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`), with provisioning handled by `sync-*` scripts.
- Password policy overrides (`GATEWAY_PASSWORD_MIN_LENGTH`, `GATEWAY_PASSWORD_REQUIRED_CLASSES`, `GATEWAY_PASSWORD_EXCLUDE_AMBIGUOUS`) may only tighten the canonical contract in `tools/password_policy.py`; weakening overrides raise `ValueError` in `GatewaySettings.__post_init__`.
- Durable execution admission (`EXECUTION_ADMISSION_ENABLED`) requires matching `EXECUTION_STATE_DB_URL` and `EXECUTION_ADMISSION_EPOCH` on both agent-service and execution-runtime; enabling without both fails startup.
- The policy bundle at `shared/shared-contracts/policies/policy-default.yaml` is the single source of truth; replicas in `products/*/policies/` and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` must stay byte-identical, enforced by `make verify`.
- Secrets are provisioned as Kubernetes `Secret` objects via `sync-*` scripts under `shared/platform-ops/gitops/`; they are never committed to Git and never passed inline in env vars consumed by the config layer.