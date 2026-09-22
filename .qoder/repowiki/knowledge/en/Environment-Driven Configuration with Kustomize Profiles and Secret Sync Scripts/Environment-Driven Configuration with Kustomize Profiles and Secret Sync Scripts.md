---
kind: configuration_system
name: Environment-Driven Configuration with Kustomize Profiles and Secret Sync Scripts
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/default/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
---

## What system/approach is used

The Luban platform uses a **pure environment-variable configuration model** — no YAML/JSON config files are read at runtime by services. Each product service defines a frozen `dataclass` in its `core/config.py` (or equivalent, e.g. `agent_service/runtime_settings.py`) that reads every setting from `os.environ` via helper functions (`_optional_str`, `_optional_int`, `_optional_bool`, `_env_bool`, etc.). A module-level `@lru_cache(maxsize=1)`-wrapped `get_settings()` function provides a singleton settings object per process. There is no Pydantic, no `.env` file loader, no TOML/INI parser; defaults live as dataclass field defaults and are validated in `__post_init__` or `from_env`. Configuration is layered through **Kustomize overlays**: base `runtime-config.env` files under `shared/platform-ops/gitops/dev-k8s/base/<service>/` provide the baseline, and feature profiles (e.g. `browser-dev`, `mutating-dev`, `secrets-dev`) merge additional env vars via Kustomize `envFrom` / `patchStrategicMerge`. Secrets are never committed to Git; they are provisioned into Kubernetes `Secret` objects by dedicated shell scripts under `shared/platform-ops/gitops/sync-*.sh` (e.g. `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`).

## Key files and packages

- Per-service settings modules:
  - `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, provider options, validation, `from_env`
  - `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass, connector enable flags, password policy overrides
  - `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass
  - `products/execution-runtime/src/execution_runtime/core/config.py`
  - `products/identity-broker/src/identity_service/core/config.py`
  - `products/audit-service/src/audit_service/core/config.py`
  - `products/skills-hub/src/skills_hub/core/config.py`
  - `products/incident-service/src/incident_service/core/config.py`
- Shared runtime defaults: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` (OTel endpoint, identity broker URL)
- Per-service runtime ConfigMaps: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`
- Feature profile overlays: `shared/platform-ops/gitops/runtime-profiles/{default,browser-dev,mutating-dev,secrets-dev}/`
- Policy bundle source of truth: `shared/shared-contracts/policies/policy-default.yaml`, synced to consumers by `make sync-policy`
- Authoritative cross-service reference: `docs/guides/configuration-reference.md` (feature activation matrix, per-service variable tables, secret contracts, dependency chains)
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh`

## Architecture and conventions

1. **One settings class per service.** Each service owns its configuration surface as a frozen `dataclass` with typed defaults. `from_env()` maps `os.environ` keys to fields; `__post_init__` enforces invariants (e.g. port ranges, positive TTLs, valid IANA timezones, allowed enum choices). Unknown values fail startup rather than degrading silently.
2. **Deny-by-default feature toggles.** Optional capabilities (browser connector, HTTP connector, secrets delivery, mutating tools, Elastic connector) are off by default and gated behind explicit `GATEWAY_*_ENABLED=true` variables plus allowlists (e.g. `GATEWAY_BROWSER_ALLOW_ORIGINS`, `GATEWAY_HTTP_ALLOW_ORIGINS` empty denies all).
3. **Cross-service secrets use shared registries.** Inter-service auth follows a client-id/secret contract: each consumer sets `<SERVICE>_CLIENT_ID` + `<SERVICE>_CLIENT_SECRET`; the server registers them in a registry env var (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`). Provisioning scripts generate random secrets once and write matching entries on both sides.
4. **Kustomize overlay-based environment composition.** Base overlays define the deny-by-default posture; feature profiles add knobs without editing bases. The `select-runtime-profile.sh` script switches the active LLM profile ConfigMap label. Two permanent postures (`mutating-dev`, `browser-dev`) merge their env into `platform-runtime-config` regardless of profile selection.
5. **Policy bundles are single-source-of-truth.** `policy-default.yaml` is edited centrally and replicated byte-identically to both gateways and the dev overlay via `make sync-policy`. Consumers load the configured path at startup; a missing/invalid bundle raises `PolicyLoadError` (no silent fallback). Both gateways expose a SHA-256 fingerprint of the loaded bundle for provenance verification.
6. **Secrets are mounted as files or injected as env vars.** Sensitive values (API keys, SMTP passwords, signing keys, client secrets) ride in Kubernetes `Secret` objects and are either mounted as env vars or referenced via `secretKeyRef` onto file paths (e.g. `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH`, `GATEWAY_PASSWORD_POLICY_PATH`, `GATEWAY_BROWSER_CREDENTIAL_SETS`). No inline secrets exist in ConfigMaps.
7. **Configuration documentation is authoritative.** `docs/guides/configuration-reference.md` is the canonical map of every environment variable, its service, default, source (ConfigMap vs Secret), and cross-service dependency chain. It is updated alongside code changes and serves as the operator-facing spec.

## Conventions and constraints

- **All configuration is read from environment variables at process start.** Services do not reload configuration at runtime; changing a ConfigMap requires a pod restart (rolling restart of gateway deployments).
- **Unknown or out-of-range values fail startup.** Validation in `__post_init__` raises `ValueError` for invalid booleans, ports outside 1–65535, negative TTLs, unsupported providers, invalid IANA timezones, etc. This prevents misconfigured pods from running.
- **Feature gates are opt-in.** Browser, HTTP, secrets, mutating tools, Elastic, and other connectors are disabled by default; enabling them requires explicit env vars and often additional policy grants (e.g. `tools:mutate`, `chat:confirm`).
- **Secrets must be provisioned before deployment.** Missing signing keys, handoff tokens, audit credentials, or skill query secrets cause the affected feature to fail closed (e.g. mutating resumes rejected with `signing_unavailable` or `worker_unavailable`, incident-report creation returns 503 "incident service not configured").
- **Cross-service secrets are generated centrally.** `make deploy` invokes the relevant `sync-*.sh` scripts which generate random shared secrets (or reuse exported variables) and create the corresponding K8s Secrets. Operators can opt out per-feature by exporting `SKIP_*_SECRETS=true`.
- **Policy drift is enforced by CI.** Contract tests run `make verify` which checks schema validity, scenario expectations against both engines, and copy-parity between the canonical `policy-default.yaml` and its replicas; any drift fails the build.
- **Per-service env var naming follows a service prefix convention.** Agent-service uses `AGENT*` / `AGENTSCOPE_*`, tool-gateway uses `GATEWAY_*`, platform-gateway uses `PLATFORM_GATEWAY_*`, identity-service uses `IDENTITY_*` / `KEYCLOAK_*`, etc. Shared variables (OTel, identity broker URL) live in the shared `runtime.env`.