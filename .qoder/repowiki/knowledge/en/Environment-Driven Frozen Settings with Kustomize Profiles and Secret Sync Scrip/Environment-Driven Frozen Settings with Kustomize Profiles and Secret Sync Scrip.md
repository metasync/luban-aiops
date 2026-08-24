---
kind: configuration_system
name: Environment-Driven Frozen Settings with Kustomize Profiles and Secret Sync Scripts
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/tool-gateway-pod-delete.yaml
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## Approach

Every product service in the monorepo implements a **pure environment-variable configuration system** built on Python `dataclasses` that are frozen at load time. There is no YAML/JSON config file loaded at runtime by the services themselves; instead, each service defines a single frozen `@dataclass` (e.g. `PlatformGatewaySettings`, `AuditSettings`, `SkillsSettings`, `IncidentSettings`, `IdentitySettings`, `GatewaySettings`, `RuntimeSettings`) with a classmethod `from_env()` that reads values from `os.getenv(...)` using explicit defaults, plus a module-level `@lru_cache(maxsize=1) get_settings()` accessor consumed throughout the service.

Configuration is supplied to pods via Kubernetes ConfigMaps and Secrets mounted as environment variables. The platform uses **Kustomize overlays** (`shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` per service, plus `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml` for LLM backends) and **shell provisioning scripts** under `shared/platform-ops/gitops/sync-*.sh` to generate and inject secrets into `*-runtime-secrets` Kubernetes Secrets.

## Key Files

- Per-service settings modules: `products/*/src/*_service/core/config.py` (and `agent-platform/src/agent_service/runtime_settings.py`)
- Central cross-service variable map and secret contracts: `docs/guides/configuration-reference.md`
- Kustomize base env files: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`
- Runtime profiles (LLM provider selection): `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml`
- Profile selector and overlay wiring: `shared/platform-ops/gitops/select-runtime-profile.sh`, `dev-k8s/kustomization.yaml`
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-incident-secrets.sh`, `sync-skills-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`
- Policy bundle (configuration-as-data, not env): `shared/shared-contracts/policies/policy-default.yaml`, mirrored into `products/*/policies/policy-default.yaml` and `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`

## Architecture and Conventions

### Frozen dataclass + cached accessor pattern
Each service follows an identical shape:
```
@dataclass(frozen=True)
class XxxSettings:
    field_a: str = "default"
    ...
    @classmethod
    def from_env(cls) -> "XxxSettings":
        return cls(
            field_a=os.getenv("SERVICE_FIELD_A", "default"),
            ...
        )

@lru_cache(maxsize=1)
def get_settings() -> XxxSettings:
    return XxxSettings.from_env()
```
The `frozen=True` makes settings immutable after startup, and `lru_cache(maxsize=1)` ensures a single process-wide singleton loaded once at import time.

### Boolean parsing convention
Boolean flags are parsed uniformly as `.strip().lower() in {"1", "true", "yes", "on"}` (used for `*_REQUIRE_AUTH`, `*_ENABLED`, etc.). The agent-platform's `runtime_settings.py` centralizes this via `_optional_bool` helpers that raise `ValueError` on malformed booleans.

### Complex multi-value fields use compact string encoders
- Comma-separated key=value pairs: `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_WORKLOAD_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`, `IDENTITY_WORKLOAD_CLIENTS` — parsed by small helper functions (`parse_ingest_clients`, `parse_query_clients`, `_parse_service_clients`, etc.)
- JSON-encoded lists/maps: `SKILLS_SOURCES` (list of source specs), `SKILLS_GIT_TOKENS` (source_id→token map) — parsed with strict validation that raises a service-local `SettingsError` on malformed input
- Provider-specific options are nested dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) selected by `AGENTSCOPE_PROVIDER` and validated in `__post_init__`

### Validation fails fast at startup
Settings classes validate constraints in `__post_init__` or during parsing: invalid timezone (IANA check), out-of-range `max_iters` / `context_trigger_ratio` / `tool_result_limit`, mismatched `AGENTSCOPE_PROFILE` vs `AGENTSCOPE_PROVIDER`, unknown store backends, duplicate `source_id` values, non-relative git paths, missing required fields per source type. This means misconfiguration is caught before the service becomes ready.

### Cross-service secret contracts
The configuration system is designed around **paired secrets**: every consumer exposes a `<SERVICE>_AUDIT_CLIENT_ID` / `<SERVICE>_AUDIT_CLIENT_SECRET` pair that must match an entry in the producer's registry (e.g. `AUDIT_INGEST_CLIENTS`). The `docs/guides/configuration-reference.md` documents these chains explicitly (Token Delegation Chain, Audit Ingestion Chain, Skills Retrieval Chain, Incident Intake Chain, Identity Verification Chain). Provisioning is done by `make deploy`, which invokes the corresponding `sync-*.sh` script to generate random shared secrets and write them into the relevant Kubernetes Secrets.

### Feature toggles via environment
Capabilities are enabled/disabled by setting specific env vars to truthy values: `GATEWAY_K8S_ENABLED`, `GATEWAY_MUTATING_TOOLS_ENABLED`, `GATEWAY_ELASTIC_ENABLED`, `PLATFORM_GATEWAY_REQUIRE_AUTH`, `OTEL_ENABLED`, `AGENTSCOPE_KERNEL_TRACING`, `AGENTSCOPE_TASK_TOOLS_ENABLED`, `AGENT_HITL_CONFIRM_TIMEOUT > 0`. Unset URLs disable optional integrations (e.g. unset `PLATFORM_GATEWAY_INCIDENT_SERVICE_URL` leaves portal routes fail-closed with 503).

### Runtime profiles for LLM backends
The agent-service supports pluggable LLM providers through Kustomize profile overlays under `shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml`. Each profile sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. Only one profile is active at a time; switching is done via `select-runtime-profile.sh`. A separate `mutating-dev` profile merges additional env (`mutating.env`) and RBAC manifests to enable bounded mutating tools.

### Policy as configuration
Authorization policy is not read from env; it is a YAML bundle sourced from `shared/shared-contracts/policies/policy-default.yaml` and copied verbatim into both gateway services and the Kustomize base. Consumers mount it at `policy_path` (env `GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`). Editing requires running `make validate-policy` against a JSON schema, then `make sync-policy` to propagate changes.

## Conventions and Constraints

- **All runtime configuration comes from environment variables**; services never read application YAML/JSON files directly.
- **Settings are immutable after construction** (`frozen=True`); there is no hot-reload mechanism.
- **Every boolean flag accepts the same canonical truthy set**: `1`, `true`, `yes`, `on` (case-insensitive).
- **Optional integrations are disabled by default** when their URL/env is unset (audit log-only, skills connector off, incidents routes 503), rather than failing open.
- **Cross-service credentials are paired secrets**, not single values: every emitter's client id/secret must be registered in the receiver's list env var; provisioning scripts enforce this pairing.
- **Store backends are chosen by `*_STORE_BACKEND`** (`memory` | `postgres`; unknown values fail startup) with a matching `*_DB_URL`.
- **Workload identity** (Kubernetes projected tokens) is configured via triplets: `*_WORKLOAD_ISSUER_URL`, `*_WORKLOAD_AUDIENCE`, `*_WORKLOAD_CLIENTS` (subject→client mapping), and is disabled by default.
- **Secrets are never committed to Git**; they are generated at deploy time by `sync-*.sh` scripts and stored in Kubernetes Secrets. Example env files (`runtime-secrets.example.env`) document keys but contain no real values.
- **Policy bundles must stay byte-identical** across all consumer locations; `make sync-policy` enforces this contract.
- **Agent runtime tuning knobs** (`AGENTSCOPE_MAX_ITERS`, `CONTEXT_TRIGGER_RATIO`, `TIMEZONE`, `REPLY_TOKEN_BUDGET`, etc.) have documented bounds enforced in `__post_init__` so invalid values cannot reach the agentscope kernel.