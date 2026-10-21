---
kind: configuration_system
name: Environment-Driven Configuration System Across Luban Services
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - docs/guides/configuration-reference.md
---

## Approach

Luban has no external configuration library. Every service reads its runtime configuration directly from `os.environ` (i.e. Kubernetes environment variables mounted from ConfigMaps and Secrets) and validates it at process startup. There is no hot reload: a changed ConfigMap takes effect only after the pod restarts.

The system is organized per-product under `products/<service>/src/<service_package>/core/config.py`, with one frozen dataclass per service plus an `@lru_cache(maxsize=1)`-memoized `get_settings()` accessor that callers import instead of calling `os.getenv` directly.

The agent-platform (`agent-service`) is the exception to the tiny-dataclass pattern: its settings live in `runtime_settings.py` as a large `RuntimeSettings` dataclass with typed provider-option sub-models, helper parsers (`_optional_str/int/float/bool/choice`), and extensive `__post_init__` validation. The thin `core/config.py` re-exports `get_settings()` for the rest of the package.

## Key Files

- `products/agent-platform/src/agent_service/runtime_settings.py` — largest settings model; LLM providers, kernel tuning, HITL, execution handoff, evidence caps, authoring-trace bounds, skill graduation limits.
- `products/agent-platform/src/agent_service/core/config.py` — thin `get_settings()` wrapper.
- `products/audit-service/src/audit_service/core/config.py` — `AuditSettings` + `IngestClient` / `WorkloadClient` parsers.
- `products/incident-service/src/incident_service/core/config.py` — `IncidentSettings` + connector/query/workload client parsers.
- `products/skills-hub/src/skills_hub/core/config.py` — `SkillsSettings` + JSON-based source/git-token/query/workload client parsers.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — non-secret defaults per service.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env` — secret key names per service.
- `shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml` — active LLM profile ConfigMap.
- `docs/guides/configuration-reference.md` — authoritative cross-service variable map, dependency chains, and secret contracts.

## Architecture and Conventions

1. **One module per service.** Each product ships `src/<pkg>/core/config.py` defining a frozen `*Settings` dataclass, a `from_env()` classmethod reading `os.getenv(...)` with defaults, and a cached `get_settings()` returning the singleton instance.
2. **Frozen dataclasses.** All settings classes are `@dataclass(frozen=True)`, so once constructed they cannot be mutated at runtime.
3. **Fail-fast parsing.** Complex env vars have dedicated `parse_*` helpers (`parse_query_clients`, `parse_workload_clients`, `parse_ingest_clients`, `parse_sources`, `parse_git_tokens`, `parse_connectors`, `parse_composition_max_sub_skills`, `parse_positive_int`). Malformed values raise `SettingsError` or `ValueError` during `from_env()`, which is called early in `main.py` / entrypoints so bad config kills the process before serving traffic.
4. **Typed optionals via helpers.** Agent-platform uses `_optional_str/int/float/bool(name)` helpers that return `None` when unset and raise `ValueError` on malformed booleans; choices go through `_optional_choice(name, supported_set)`.
5. **Cross-service credential registries.** Consumers register a `client_id=secret,...` list against a server's registry env var:
   - `AUDIT_INGEST_CLIENTS` (audit-service)
   - `SKILLS_QUERY_CLIENTS` (skills-hub)
   - `INCIDENT_QUERY_CLIENTS` (incident-service)
   - `IDENTITY_SERVICE_CLIENTS` (identity-broker)
   Callers set matching `*_CLIENT_ID` / `*_CLIENT_SECRET` env vars pointing at the same registry.
6. **Secrets vs non-secrets split.** Non-secret knobs go into `runtime-config.env` (ConfigMap); secrets go into per-service `*-runtime-secrets` K8s Secrets provisioned by `sync-*.sh` scripts (`sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, etc.).
7. **Kustomize overlays.** `dev-k8s/base/<service>/runtime-config.env` provides dev defaults; `runtime-profiles/<profile>/` overlays add feature flags (e.g. `browser-dev`, `mutating-dev`, `ansible-dev`, `servicenow-dev`); `select-runtime-profile.sh` swaps the active profile.
8. **No framework.** No Pydantic, no `pydantic-settings`, no `python-dotenv`. Configuration is plain `os.getenv` + dataclass construction + manual validation.
9. **Documentation as contract.** `docs/guides/configuration-reference.md` is the single source of truth for every env var across all services, including cross-service chains (token delegation, audit ingestion, skills retrieval, incident intake, mutating action approval) and secret provisioning procedures.

## Conventions and Constraints

- Settings are loaded exclusively from environment variables; there is no `.env` file loader, no YAML/TOML config reader, and no runtime override mechanism.
- Each service defines its own `SettingsError` subclass (or raises `ValueError` in agent-platform) for malformed configuration; the convention is "fail startup fast" rather than degrade silently.
- Boolean env vars accept `1/true/yes/on` as true and `0/false/no/off` as false (agent-platform helpers); other values raise `ValueError`.
- Store backends use a string knob (`STORE_BACKEND`) with `memory` as default and unknown values failing startup (seen in audit-service, skills-hub, incident-service).
- Cross-service URLs default to in-cluster Service DNS names (`http://tool-gateway:8000`, `http://audit-service:8000`, `http://incident-service:8000`, `http://skills-hub:8000`, `http://execution-runtime:8000`) in dev-k8s.
- Audit emission is fire-and-forget: if `*_AUDIT_SERVICE_URL` is unset, the service falls back to log-only auditing; if reachable, failures are swallowed so user requests are never blocked.
- Missing required secrets fail closed: e.g. absent `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes with `signing_unavailable`; absent `AGENT_EXECUTION_WORKER_URL` / `AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`; absent `AGENT_INCIDENT_CLIENT_SECRET` returns 503 "dependency not configured".
- Policy bundles are loaded from a filesystem path (`GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`, default `/etc/luban/policy/policy.yaml`); a missing or invalid bundle fails startup (`PolicyLoadError`, no silent fallback to packaged default). The canonical bundle lives at `shared/shared-contracts/policies/policy-default.yaml` and is replicated byte-identically to both gateways and the dev overlay via `make sync-policy`.
- Runtime profiles are selected via Kustomize overlays; only one LLM profile is active at a time, switched with `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`.
- The `get_settings()` accessor is memoized with `functools.lru_cache(maxsize=1)`, so the parsed settings object is reused across the process lifetime.