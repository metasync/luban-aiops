---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Configuration with Kustomize Profiles and Secret Provisioning Scripts
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-browser-credentials.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/platform-ops/gitops/sync-runtime-secret.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## Approach

The Luban platform uses a uniform, code-first configuration model across every Python service:

1. **Source of truth is environment variables** — each service reads `os.getenv` in a dedicated `core/config.py` (or `runtime_settings.py` for agent-service) module.
2. **Settings are frozen `dataclasses`** with a `from_env()` classmethod that parses and validates values, plus an `@lru_cache(maxsize=1)`-wrapped `get_settings()` accessor consumed by the rest of the service.
3. **No third-party config library** — there is no Pydantic Settings, Dynaconf, or similar; validation lives in `__post_init__` raising `ValueError`/`SettingsError`, and boolean parsing accepts `{"1", "true", "yes", "on"}`.
4. **Runtime profiles** (Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/`) merge additional env into the base deployment via `select-runtime-profile.sh`; the active profile label is decoupled from the LLM provider since SPEC-026.
5. **Secrets are provisioned at deploy time** by shell scripts under `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`), which generate random shared secrets and write Kubernetes Secrets. Secrets are never committed to Git; `runtime-secrets.example.env` files document required keys per service.
6. **Policy bundles** are a separate concern: the canonical file `shared/shared-contracts/policies/policy-default.yaml` is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`, and contract tests fail `make verify` on drift.
7. **A single authoritative reference** lives in `docs/guides/configuration-reference.md`, documenting every variable, default, cross-service dependency chain, secret contract, and provisioning script.

## Key Files

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, provider-specific option types, extensive `__post_init__` validation (SPEC-017/018/020/025/027/037/038/043/044/051/055/063/064).
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings`.
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` (browser/HTTP/secrets connectors, password policy tightening in `__post_init__`).
  - `products/execution-runtime/src/execution_runtime/core/config.py` — `ExecutionSettings` (worker-only knobs).
  - `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` + `parse_ingest_clients` / `parse_workload_clients`.
  - `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` + JSON source parsing with strict `source_id` regex.
  - `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings`.
  - `products/identity-broker/src/identity_service/core/config.py` — `IdentitySettings` + `ServiceClient` / `WorkloadClient` parsers.
- Kustomize overlays:
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service ConfigMap env.
  - `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` — documented secret keys.
  - `shared/platform-ops/gitops/runtime-profiles/default/`, `mutating-dev/`, `browser-dev/`, `secrets-dev/` — profile overlays.
  - `shared/platform-ops/gitops/select-runtime-profile.sh`.
- Secret provisioning scripts:
  - `shared/platform-ops/gitops/sync-*.sh` (delegation, audit, skills, incident, execution signing/handoff, browser credentials, email, OTel, runtime secret).
- Policy bundle:
  - `shared/shared-contracts/policies/policy-default.yaml` (canonical).
  - `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`.
  - `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`.
  - `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`.
- Reference documentation:
  - `docs/guides/configuration-reference.md` (feature activation matrix, cross-service chains, per-service tables, secret contracts, runtime profiles, policy management).

## Architecture and Conventions

### One setting module per service
Each product exposes its settings through `src/<product>/core/config.py` (or `runtime_settings.py` for agent-service). The pattern is consistent:

```python
@dataclass(frozen=True)
class XxxSettings:
    field_a: str = DEFAULT_A
    ...

    def __post_init__(self):
        # range/enum/validation checks raise ValueError

    @classmethod
    def from_env(cls) -> "XxxSettings":
        return cls(
            field_a=os.getenv("SERVICE_FIELD_A", DEFAULT_A),
            ...
        )

@lru_cache(maxsize=1)
def get_settings() -> XxxSettings:
    return XxxSettings.from_env()
```

### Variable naming conventions
- Service-scoped prefixes: `AGENTSCOPE_*` (agent-service), `PLATFORM_GATEWAY_*` (platform-gateway), `GATEWAY_*` (tool-gateway), `EXECUTION_*` (execution-runtime), `AUDIT_*` (audit-service), `SKILLS_*` (skills-hub), `INCIDENT_*` (incident-service), `KEYCLOAK_*`/`OIDC_*`/`IDENTITY_*` (identity-broker).
- Cross-service URLs use `<SERVICE>_SERVICE_URL` (e.g. `AGENT_SERVICE_URL`, `TOOL_GATEWAY_URL`, `IDENTITY_SERVICE_URL`).
- Client registries follow a common comma-separated `client_id=secret,...` format: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS` (colon-delimited with optional audience list `client_id:secret:aud1|aud2`).
- Workload identity uses a parallel `*_WORKLOAD_ISSUER_URL` / `*_WORKLOAD_AUDIENCE` / `*_WORKLOAD_CLIENTS` triplet.

### Validation strategy
- Boolean flags accept only `{"1", "true", "yes", "on"}` (case-insensitive); everything else is falsy.
- Numeric ranges are enforced in `__post_init__` (e.g. `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` must be `> 0` and `<= 120`, `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` must be in `(0, 0.9)`, `EXECUTION_GATEWAY_TIMEOUT_SECONDS` must be `> 0` and `<= 30`).
- Enum-like choices reject unknown values at startup (e.g. store backends limited to `memory`/`postgres`, `AGENTSCOPE_PROVIDER` limited to `dashscope`/`deepseek`/`openai`/`luban`).
- Some services define a dedicated exception type (`SettingsError` in skills-hub and incident-service; `ProviderConfigurationError` in agent-service providers).

### Feature gating
Most features are opt-in via boolean env vars that default to `false` (deny-by-default): `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`, `AGENT_MODEL_DISCOVERY_ENABLED`, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED`, `AGENTSCOPE_TASK_TOOLS_ENABLED`, `AGENTSCOPE_KERNEL_TRACING`.

### Secret handling
- Secrets are mounted as Kubernetes Secrets, not ConfigMaps.
- Each service has a `runtime-secrets.example.env` documenting required keys.
- Shared secrets between services (token delegation, audit ingestion, skills query, incident query, execution signing/handoff) are generated by `sync-*.sh` scripts and written to both sides' Secrets.
- Optional secrets (OTLP headers, SMTP passwords, browser credential sets) degrade gracefully when absent rather than failing startup.

### Policy bundle discipline
The policy bundle has exactly one canonical copy (`shared/shared-contracts/policies/policy-default.yaml`). Replicas are kept byte-identical by `make sync-policy`; `make verify` enforces parity and scenario expectations. A missing or invalid bundle at the configured path fails startup (`PolicyLoadError`, no silent fallback).

### Documentation-driven configuration
`docs/guides/configuration-reference.md` is the definitive cross-service environment variable map, including feature activation matrices, dependency diagrams, per-service variable tables, secret contracts, and the policy rollout procedure. It explicitly cites the source file for each service's settings module.