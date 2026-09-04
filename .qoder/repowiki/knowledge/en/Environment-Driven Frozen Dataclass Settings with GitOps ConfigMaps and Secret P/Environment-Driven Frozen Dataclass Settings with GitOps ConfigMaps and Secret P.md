---
kind: configuration_system
name: Environment-Driven Frozen Dataclass Settings with GitOps ConfigMaps and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - docs/guides/configuration-reference.md
    - shared/shared-contracts/policies/policy-default.yaml
---

## What system/approach is used

Every service in the Luban AIOps platform loads configuration exclusively from **environment variables** at process start, into a **frozen `dataclass`** that exposes a module-level `get_settings()` cached via `functools.lru_cache(maxsize=1)`. There is no YAML/JSON config file parsing inside services; files are only used as deployment manifests. Configuration is layered through Kustomize overlays: shared defaults live in `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`, per-service overrides in `<service>/runtime-config.env`, and secrets in `<service>-runtime-secrets.example.env` (or generated Secrets). The canonical cross-service variable map is maintained in `docs/guides/configuration-reference.md`, which doubles as the source of truth for operators.

## Key files and packages

- Per-service settings modules: `products/*/src/<service>/core/config.py` (platform-gateway, tool-gateway, audit-service, skills-hub, incident-service, execution-runtime) plus `products/agent-platform/src/agent_service/runtime_settings.py`.
- Shared runtime defaults: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`.
- Per-service runtime env fragments: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`.
- Secret examples: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-secrets.example.env`.
- Deployment manifests mounting these as ConfigMap/Secret env vars under `shared/platform-ops/gitops/dev-k8s/base/<service>/*-deployment.yaml`.
- Cross-service provisioning scripts under `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `sync-runtime-secret.sh`).
- Policy bundle: canonical `shared/shared-contracts/policies/policy-default.yaml`, synced to both gateways' packaged defaults and `base/shared/policy.yaml` via `make sync-policy`.
- Documentation: `docs/guides/configuration-reference.md` (authoritative variable matrix), `docs/guides/tool-configuration.md`, `docs/guides/approval-and-hitl.md`.

## Architecture and conventions

### Frozen dataclass + `from_env` + cached accessor
Each service defines one frozen dataclass (e.g. `PlatformGatewaySettings`, `GatewaySettings`, `AuditSettings`, `SkillsSettings`, `IncidentSettings`, `ExecutionSettings`, `RuntimeSettings`) whose fields have sensible defaults. A classmethod `from_env()` reads every field from `os.getenv(...)`, applying type coercion and parsing helpers. A module-level `@lru_cache(maxsize=1)` function `get_settings()` returns a singleton instance consumed throughout the service. This pattern is uniform across all eight Python services.

### Boolean parsing convention
Boolean knobs accept the same truthy set everywhere: `{"1", "true", "yes", "on"}` (lowercased, stripped). A helper `_env_bool(name, default)` in tool-gateway centralizes this; agent-service uses an inline `_optional_bool` helper. Non-boolean strings are rejected by explicit membership checks.

### Complex values parsed from delimited/env strings
- Comma-separated key=value pairs: `AUDIT_INGEST_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `*_WORKLOAD_CLIENTS`, `*_AUDIT_*_CLIENT_SECRET` — parsed by small `parse_*_clients(raw)` helpers that split on `,` then `partition("=")`.
- JSON blobs: `SKILLS_SOURCES` (list of `{source_id, type, url, ref, path}`), `SKILLS_GIT_TOKENS` (map `source_id→token`), validated with strict schema checks that raise `SettingsError` on malformed input.
- Path-based secrets: `workload_token_path`, `dev_signing_key_path`, `policy_path`, `browser_credential_sets_path` point to mounted files rather than inline values.

### Validation strategy
Validation happens in two places:
1. **Field-level coercion** during `from_env()` (int/float parsing, boolean normalization).
2. **Post-init validation** in `__post_init__` or constructor helpers (e.g. `ExecutionSettings.__post_init__` enforces `state_store_backend ∈ {memory, postgres}`, requires `state_db_url` when postgres, positive timeouts; `RuntimeSettings.__post_init__` validates agentscope kernel tuning bounds, IANA timezone, provider/options type match; `parse_sources` rejects unknown types, duplicate `source_id`, path traversal).
Invalid configuration fails startup — there is no silent fallback for core knobs.

### Feature flags via environment
Capabilities are toggled by dedicated env vars with deny-by-default semantics:
- `GATEWAY_MUTATING_TOOLS_ENABLED=false` (write/admin tools absent from discovery)
- `GATEWAY_BROWSER_ENABLED=false` (web.* tools disabled, origin allowlist empty = deny-all)
- `GATEWAY_ELASTIC_ENABLED=false`
- `PLATFORM_GATEWAY_REQUIRE_AUTH=true`
- `AGENT_MODEL_DISCOVERY_ENABLED=true` (default on; can be disabled)
- `AGENT_HITL_CONFIRM_TIMEOUT=600` (0 disables HITL bridging entirely)

### Cross-service secret contracts
Configuration references form inter-service contracts enforced at runtime:
- **Token delegation**: `PLATFORM_GATEWAY_SERVICE_CLIENT_ID`/`SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` entry.
- **Audit ingestion**: each emitter's `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` registry.
- **Skills query**: `GATEWAY_SKILLS_CLIENT_SECRET` / `PLATFORM_GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`.
- **Incidents query**: `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` / `GATEWAY_INCIDENTS_CLIENT_SECRET` / `AGENT_INCIDENT_CLIENT_SECRET` ↔ `INCIDENT_QUERY_CLIENTS`.
- **Signed execution**: `AGENT_EXECUTION_SIGNING_KEY` ↔ `EXECUTION_SIGNING_KEY` (HMAC envelope verification).
- **Worker handoff**: `AGENT_EXECUTION_HANDOFF_TOKEN` ↔ `EXECUTION_HANDOFF_TOKEN` (constant-time comparison).
These are provisioned by `sync-*.sh` scripts that generate random secrets and write them into Kubernetes Secrets; they are never committed to Git.

### Policy bundle management
The action-authorization policy has exactly one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to both gateway consumers and the dev overlay via `make sync-policy`; contract tests fail `make verify` on any drift. Consumers load it from a configured path (`GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH`); a missing or invalid bundle raises `PolicyLoadError` at startup with no silent fallback.

### Runtime profiles
LLM provider configuration is delivered via Kustomize profile overlays under `shared/platform-ops/gitops/runtime-profiles/`. Profiles are deploy labels decoupled from providers; provider selection is a ConfigMap knob (`AGENTSCOPE_PROVIDER`). Two non-switchable postures (`mutating-dev`, `browser-dev`) permanently merge their env into `platform-runtime-config`.

## Conventions and constraints

- **All runtime configuration comes from environment variables**; no service parses application YAML/JSON at startup.
- **Settings objects are immutable** (`frozen=True` dataclasses) — once loaded, they cannot be mutated at runtime.
- **Defaults are code-first**: every setting has a safe default in the dataclass; unset env vars fall back to those defaults.
- **Deny-by-default feature gating**: optional features (mutating tools, browser tools, Elastic, auth) are off unless explicitly enabled.
- **Secrets are never inline**: sensitive values arrive via Kubernetes Secrets mounted as env vars or file paths; example `.env` files are templates only.
- **Cross-service credentials are paired registries**: every caller must register its client id+secret in the callee's registry (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`).
- **Provisioning is scripted**: `make deploy` orchestrates `sync-*.sh` scripts that generate and apply secrets; operators opt out per-feature via `SKIP_*_SECRETS=true`.
- **Policy changes require a documented workflow**: edit canonical file → validate → sync → verify → review diff → commit → deploy → confirm SHA-256 fingerprint matches.
- **Unknown store backends fail startup**: e.g. `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `AUDIT_STORE_BACKEND`, `SKILLS_STORE_BACKEND`, `INCIDENT_STORE_BACKEND` reject unknown values; `postgres` backends require a corresponding `*_DB_URL`.