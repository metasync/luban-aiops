---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Per-Service `get_settings()` Cache
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - docs/guides/configuration-reference.md
---

## Approach

Every service in the Luban platform loads configuration exclusively from **environment variables** at process startup. There is no `.env` file loader, no YAML/JSON config files consumed by the Python code, and no runtime reload of settings. The pattern is uniform across all nine product services:

1. A frozen `@dataclass` named `<Service>Settings` (or a small tree of nested frozen dataclasses) declares every configurable field with sensible defaults.
2. A classmethod `from_env(cls)` reads each field via `os.getenv`, parsing booleans as `value.strip().lower() in {"1", "true", "yes", "on"}`, integers, floats, comma-separated tuples, JSON blobs, or custom formats.
3. A module-level `@lru_cache(maxsize=1)` function `get_settings()` returns the singleton instance; callers import it as a dependency (often also registered as a FastAPI `Depends`).
4. Validation lives in `__post_init__` (raising `ValueError`) or in dedicated parser helpers that raise a per-service `SettingsError` / `SettingsException`.

The only exception is `agent_service/runtime_settings.py`, which defines `RuntimeSettings` directly (not under `core/config.py`) because it is large and contains provider-specific option subtypes (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) plus the embedded `DEFAULT_SYSTEM_PROMPT`. Its accessor is still `RuntimeSettings.from_env()` wrapped by `core/config.get_settings()`.

No third-party settings library is used — not pydantic-settings, not dynaconf, not python-dotenv. All parsing is hand-written against `os.environ`.

## Key Files

- `products/agent-platform/src/agent_service/core/config.py` — thin `get_settings()` cache over `RuntimeSettings`
- `products/agent-platform/src/agent_service/runtime_settings.py` — full `RuntimeSettings` definition (~570 lines)
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (largest, ~425 lines)
- `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings`
- `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` + `ServiceClient` / `WorkloadClient` parsers
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` + `IngestClient` / `WorkloadClient` parsers
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` + `QueryClient` / `WorkloadClient` parsers
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` + `SourceSpec` + `parse_sources` / `parse_git_tokens`
- `docs/guides/configuration-reference.md` — authoritative cross-service env-var matrix and secret contracts

## Architecture & Conventions

### Per-service isolation
Each product has its own `src/<service>/core/config.py` (or equivalent). Services never import another service's settings; cross-service contracts are expressed as environment variable names documented in `configuration-reference.md`.

### Boolean parsing convention
Booleans are parsed uniformly: `os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}`. The agent-service helper `_optional_bool` additionally accepts `"0"|"false"|"no"|"off"` and raises `ValueError` on any other non-empty value — stricter than the gateways.

### Optional vs required secrets
Secrets use an `_optional_str` helper that strips whitespace and returns `None` for empty values, so missing secrets stay unset rather than becoming empty strings. Required-but-missing secrets (e.g. `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN`) cause downstream operations to fail closed with explicit reasons like `signing_unavailable` / `worker_unavailable`; they do not degrade silently.

### Feature flags are opt-in and deny-by-default
Connector switches (`GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `GATEWAY_K8S_ENABLED`, `EXECUTION_ADMISSION_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`) default to `False`. Allowlists (`browser_allow_origins`, `http_allow_origins`, `email_recipient_allowlist`, `email_recipient_allowlist` on agent-side) default to empty tuples, enforcing deny-by-default until explicitly populated.

### Cross-service client registries
Services expose a common vocabulary for inter-service auth:
- `*_AUDIT_SERVICE_URL` / `*_AUDIT_CLIENT_ID` / `*_AUDIT_CLIENT_SECRET` → `AUDIT_INGEST_CLIENTS` registry in audit-service
- `*_WORKLOAD_ISSUER_URL` / `*_WORKLOAD_AUDIENCE` / `*_WORKLOAD_CLIENTS` → projected SA subject→client mapping
- `*_QUERY_CLIENTS` (skills-hub, incident-service) and `IDENTITY_SERVICE_CLIENTS` (identity-broker) follow the same `client_id=secret,...` or `subject=client_id` CSV format

### Policy bundle loading
Policy bundles are loaded from a filesystem path (`PLATFORM_GATEWAY_POLICY_PATH`, `GATEWAY_POLICY_PATH`), defaulting to `/etc/luban/policy/policy.yaml`. The canonical copy is `shared/shared-contracts/policies/policy-default.yaml`, replicated byte-identically by `make sync-policy`. A missing or invalid bundle fails startup (`PolicyLoadError`); there is no silent fallback to the packaged default. Bundles are cached keyed on path and are NOT hot-reloaded — a changed ConfigMap requires a pod restart.

### Runtime profiles
Agent-service supports Kustomize profile overlays selected via `select-runtime-profile.sh`; the active profile's ConfigMap supplies `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`, etc. Profiles are mutually exclusive — only one LLM profile is active at a time.

### Documentation as enforcement surface
`docs/guides/configuration-reference.md` is the single source of truth for the env-var matrix, secret contracts, provisioning scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-otel-secrets.sh`), and feature activation matrix. It links each service section back to its `core/config.py` source file.

## Conventions & Constraints

- Every service exposes a `get_settings()` function decorated with `@lru_cache(maxsize=1)` that calls a `<XxxSettings>.from_env()` classmethod. This is enforced by the test `test_runtime_dependencies.py::test_get_settings_reads_env_once`, which asserts the cache is cleared and reused.
- Settings classes are `@dataclass(frozen=True)`, making them immutable after construction.
- Invalid numeric ranges, unsupported enum values, malformed JSON, and contradictory combinations raise `ValueError` (or per-service `SettingsError`) during `__post_init__` / `from_env`, causing startup failure rather than runtime misbehavior.
- Boolean env vars accept exactly `{"1", "true", "yes", "on"}` as truthy (with agent-service additionally accepting `{"0", "false", "no", "off"}`).
- Secrets are provisioned as Kubernetes `Secret` objects and mounted as environment variables or files; they are never committed to Git. The `configuration-reference.md` Secret Contracts section documents every secret key and its provisioning script.
- Policy bundles must be edited only in `shared/shared-contracts/policies/policy-default.yaml`; `make verify` enforces byte-identical copies in both gateway packages and the dev-k8s overlay.
- Missing optional dependencies (audit-service URL, skills-hub URL, incident-service URL) degrade gracefully (log-only auditing, unregistered connector, 503 route); missing critical secrets (execution signing key, handoff token, LLM API key) fail closed at startup or at the first operation that needs them.