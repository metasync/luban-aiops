---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with Kustomize Runtime Profiles
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
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/README.md
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

Every Python service in the platform implements a **single frozen dataclass settings object** loaded exclusively from environment variables at process start, wrapped in an `@lru_cache(maxsize=1)` accessor. There are no runtime config file parsers (no YAML/JSON/TOML loaders inside services), no `.env` file loading libraries, and no dynamic reload — configuration is immutable for the lifetime of the process. The pattern is consistent across all seven services: `core/config.py` defines a frozen `*Settings` dataclass with a `from_env()` classmethod that reads `os.getenv(...)` against typed defaults, plus a module-level `get_settings()` cached function consumed by the rest of the service.

The agent-service uses a slightly richer `RuntimeSettings` class in `runtime_settings.py` that includes provider-specific option sub-dataclasses (`DashScopeOptions`, `DeepSeekOptions`, `OpenAIOptions`) and performs cross-field validation in `__post_init__` (e.g. `profile` must match `provider`; bounded ranges for kernel tuning knobs; IANA timezone validation). Boolean flags use a uniform parser accepting `{"1", "true", "yes", "on"}` as truthy.

Kubernetes deployment injects configuration via two layers:
- **ConfigMaps** for non-secret knobs (service URLs, feature toggles, policy paths) — mounted as env files or individual keys.
- **Kubernetes Secrets** for secrets (API keys, client secrets, webhook tokens, OTLP headers) — mounted per service under a `*-runtime-secrets` Secret name.

A dedicated **runtime-profile overlay system** (`shared/platform-ops/gitops/runtime-profiles/<profile>/configmap.yaml`) lets operators swap LLM backends without changing base manifests. Each profile contributes a ConfigMap named `agent-platform-runtime-profile` setting `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. A helper script selects one profile at a time into the active dev-k8s overlay.

Policy bundles are the only structured configuration files consumed at runtime: each gateway loads a YAML policy file from a path configured via `*_POLICY_PATH` (default `/etc/luban/policy/policy.yaml`). The canonical source is `shared/shared-contracts/policies/policy-default.yaml`, synchronized to consumer locations via `make sync-policy`.

## Key files and packages

- `products/*/src/*_service/core/config.py` — per-service frozen settings dataclass + `from_env()` + cached `get_settings()`
- `products/agent-platform/src/agent_service/runtime_settings.py` — agent-service's extended settings with provider options and startup validation
- `shared/platform-ops/gitops/runtime-profiles/*/configmap.yaml` — LLM backend profile ConfigMaps
- `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env` — per-service default env var fragments applied by dev-k8s overlay
- `shared/platform-ops/gitops/sync-*-secrets.sh` — scripts that generate and provision Kubernetes Secrets for inter-service credential contracts
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, secret contract matrix, and per-service reference tables
- `shared/shared-contracts/policies/policy-default.yaml` — canonical policy bundle synced to consumers
- `products/*/src/*_service/policies/policy-default.yaml` — deployed copies consumed by policy engines

## Architecture and conventions

1. **One settings class per service.** Each service owns exactly one frozen dataclass representing its entire configuration surface. Complex lists/mappings are parsed from comma-separated strings (e.g. `AUDIT_INGEST_CLIENTS` = `client_id=secret,...`) or JSON (e.g. `SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`) by dedicated `parse_*` helpers that raise `SettingsError` on malformed input so bad configuration fails fast at startup.

2. **Environment-variable-only ingestion.** All values come from `os.getenv`. There is no fallback to config files, no dotenv loader, no HTTP config server. Defaults are hard-coded in the dataclass field defaults, not in shell scripts.

3. **Cached singleton access.** Every settings module exposes `get_settings()` decorated with `@lru_cache(maxsize=1)`, guaranteeing a single parsed instance per process and zero repeated env lookups.

4. **Typed parsing with strict booleans.** Booleans are parsed via a uniform set `{"1", "true", "yes", "on"}`; unknown values fall through to Python's truthiness. Integers/floats are cast directly from env strings. Strings are stripped and optionally validated (e.g. `SESSION_STORE_BACKEND` must be known).

5. **Startup validation.** Invalid configuration raises exceptions during `from_env()` / `__post_init__` rather than failing later at request time. Examples: unsupported `AGENTSCOPE_PROVIDER`, out-of-range `AGENTSCOPE_CONTEXT_TRIGGER_RATIO`, invalid IANA timezone, duplicate `source_id` in `SKILLS_SOURCES`, missing required fields for git/local sources.

6. **Cross-service credential contracts.** Secrets are never committed to Git; they are provisioned by `sync-*-secrets.sh` scripts that generate random shared secrets and write matching entries into both sides of the contract (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry; `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`). The configuration reference documents every such contract explicitly.

7. **Feature gating via empty-string defaults.** Optional features (audit ingestion, skills hub, incidents, tool-gateway proxies) are disabled when their URL/env var is unset — the code treats empty string as "feature off" rather than raising an error. This enables minimal deployments where only chat works.

8. **Profile-based LLM configuration.** Agent-service provider selection is driven by the `agent-platform-runtime-profile` ConfigMap, which is swapped via `select-runtime-profile.sh`. Mutating tools posture is layered separately via the `mutating-dev` profile overlay.

9. **Policy-as-code with enforced synchronization.** Policy YAML is the single source of truth under `shared/shared-contracts/policies/`. Consumers must stay byte-identical; `make validate-policy` checks schema compliance and `make sync-policy` propagates changes to all three consumer locations.

## Conventions and constraints

- **All settings classes are `frozen=True` dataclasses.** Once loaded, configuration cannot be mutated at runtime.
- **Complex multi-value settings use compact string encodings:** comma-separated `key=value` pairs for client registries (`AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`), pipe-delimited audiences (`IDENTITY_SERVICE_CLIENTS` format `client_id:secret:aud1|aud2`), and JSON blobs for structured lists (`SKILLS_SOURCES`, `SKILLS_GIT_TOKENS`).
- **Secrets live in Kubernetes Secrets named `<service>-runtime-secrets`, never in Git.** Provisioning is done via `sync-*-secrets.sh` scripts invoked by `make deploy`.
- **Non-secret configuration lives in ConfigMaps or `*.env` fragments** under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`, merged into pod specs by Kustomize.
- **Boolean flags accept only the four truthy forms** `1`, `true`, `yes`, `on` (case-insensitive); everything else is falsy. This is enforced consistently across `platform-gateway`, `tool-gateway`, and agent-service optional features.
- **Unknown store backends fail startup.** `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` reject unknown values early.
- **Workload identity is opt-in and disabled by default.** `*_WORKLOAD_ISSUER_URL` and `*_WORKLOAD_CLIENTS` are empty in dev; enabling them requires explicit provisioning.
- **Mutating tools are deny-by-default.** `GATEWAY_MUTATING_TOOLS_ENABLED=false` in the base overlay; enabling requires the `mutating-dev` profile overlay plus RBAC and HITL bridging.
- **Audit delivery degrades gracefully.** If `*_AUDIT_SERVICE_URL` is unset or the audit service is unreachable, events are logged but requests are never blocked.
- **Policy bundles must remain byte-identical across all consumers.** The canonical file under `shared/shared-contracts/policies/` is the single source; any drift breaks enforcement.