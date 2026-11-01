---
kind: configuration_system
name: Environment-Driven Settings with Kustomize Profiles and Secret Provisioning
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
    - products/identity-broker/src/identity_service/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/default/kustomization.yaml
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## Approach

Luban has no centralized configuration framework. Each Python service owns its settings via a frozen `dataclass` with an `from_env()` classmethod that reads `os.environ`, validates in `__post_init__`, and exposes the instance through an `lru_cache(maxsize=1)`-memoized `get_settings()` accessor (used by platform-gateway, tool-gateway, execution-runtime; agent-service uses `RuntimeSettings.from_env()` directly). There is no Pydantic `BaseSettings`, no `.env` file loader, no YAML/JSON config parser for runtime values — environment variables are the sole runtime configuration mechanism.

Kubernetes deployment manifests under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` are mounted as ConfigMaps and/or `envFrom` into each pod. Secrets live in per-service Kubernetes `Secret` objects (`*-runtime-secrets`, plus dedicated secrets like `execution-signing-secret`, `execution-handoff-secret`, `tool-gateway-browser-credentials`). A single shared ConfigMap at `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` supplies cross-pod values (`OTEL_*`, `IDENTITY_SERVICE_URL`).

Profiles layer on top of the base via Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/` (`default`, `browser-dev`, `ansible-dev`, `servicenow-dev`, `mutating-dev`, `secrets-dev`, `delegated-dev`). The `select-runtime-profile.sh` script chooses one profile overlay to merge with the base before `make deploy`. Feature toggles (e.g. `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED`, `AGENTSCOPE_MODEL_ROUTER_ENABLED`) are all boolean env vars defaulting to `false`; enabling them wires additional connectors or middleware.

## Key Files

- Per-service settings modules: `products/agent-platform/src/agent_service/runtime_settings.py`, `products/platform-gateway/src/platform_gateway/core/config.py`, `products/tool-gateway/src/tool_gateway/core/config.py`, `products/execution-runtime/src/execution_runtime/core/config.py`, `products/audit-service/src/audit_service/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/incident-service/src/incident_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py`
- Shared runtime defaults: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`
- Base deployments + per-service `runtime-config.env`: `shared/platform-ops/gitops/dev-k8s/base/*/runtime-config.env`
- Profile overlays: `shared/platform-ops/gitops/runtime-profiles/*/kustomization.yaml` and their env files
- Cross-service dependency map and operator-facing reference: `docs/guides/configuration-reference.md`
- Secret provisioning scripts: `shared/platform-ops/gitops/sync-*.sh` (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-otel-secrets.sh`, `sync-email-secrets.sh`, `sync-browser-credentials.sh`, `sync-ansible-credentials.sh`, `sync-servicenow-credentials.sh`, `sync-runtime-secret.sh`)
- Policy bundle source of truth: `shared/shared-contracts/policies/policy-default.yaml` (replicated to gateways by `make sync-policy`)

## Architecture and Conventions

1. **One dataclass per service.** Each service defines a single frozen dataclass (`PlatformGatewaySettings`, `GatewaySettings`, `RuntimeSettings`, etc.) whose fields mirror every env var it consumes. Defaults are declared as field defaults, not in `from_env`.
2. **Validation in `__post_init__`.** Range checks, allowed-value enums, cross-field invariants (e.g. enabling admission requires both DSN and epoch; enabling delegated acquisition requires Postgres custody + keyring + config path + trusted callback), and provider-specific constraints raise `ValueError` at startup rather than degrading.
3. **Opt-in feature flags.** New capabilities are added as new env vars defaulting to `false` (or empty tuple/list) so existing deployments are byte-identical. Enabling a flag without required infrastructure fails closed at startup.
4. **Cross-service contracts are env-var pairs.** Every inter-service secret is documented as a "must match" pair in `configuration-reference.md`: e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`, `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`, `INCIDENT_WEBHOOK_TOKEN`, signing keys between agent-service and execution-runtime. The provisioning scripts generate random values once and write them into every consumer's secret.
5. **Policy bundle is code-only.** `shared/shared-contracts/policies/policy-default.yaml` is the canonical copy; `make sync-policy` replicates it to both gateways' packaged defaults and the dev-k8s GitOps overlay. Contract tests fail `make verify` on any drift. Bundles are loaded from a file path (`GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`, default `/etc/luban/policy/policy.yaml`) and cached keyed on path — there is deliberately no hot reload; changes require a pod restart.
6. **Secrets never enter Git.** All sensitive material is provisioned via `sync-*.sh` scripts invoked by `make deploy`. Scripts support opt-out via `SKIP_*_SECRETS=true` and reuse ladders (generate → reuse exported variable if present).
7. **Credential sets are mounted JSON files, not env vars.** Browser, HTTP, Ansible MCP, and ServiceNow credential sets are read from paths referenced by `GATEWAY_BROWSER_CREDENTIAL_SETS`, `GATEWAY_HTTP_CREDENTIAL_SETS`, `GATEWAY_ANSIBLE_MCP_CREDENTIAL_SETS`, `GATEWAY_SERVICENOW_CREDENTIAL_SETS`. Paths fall back across surfaces (http→browser, ansible/http→browser) so one mounted secret can serve multiple connectors.
8. **Profile-based composition.** Base manifests define the static shape; runtime profiles add/override env vars and small resources (mock servers, sidecars, network policies). `select-runtime-profile.sh` selects one profile; `verify-runtime-profile.sh` validates the selection.
9. **Shared OTel baseline.** `OTEL_ENABLED=true` and `OTEL_EXPORTER_OTLP_ENDPOINT` come from the shared ConfigMap; auth headers are injected per-service via `sync-otel-secrets.sh` into each service's runtime-secrets Secret.

## Conventions and Constraints

- Runtime configuration is read exclusively from environment variables via `os.getenv`; no `.env` files, no YAML/JSON runtime config loaders, no Pydantic `BaseSettings`.
- Boolean env vars accept `1`, `true`, `yes`, `on` (case-insensitive); invalid strings raise `ValueError` (see `_optional_bool` in agent-service settings and `_env_bool` helpers).
- Unknown backend names fail startup (e.g. `SESSION_STORE_BACKEND`, `AGENT_STATE_STORE_BACKEND`, `SECRET_DELIVERY_BACKEND`, `ANSIBLE_MCP_TRANSPORT`).
- Enabling a feature flag without its required dependencies fails closed at startup — there is no silent fallback for critical paths (e.g. `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`; `GATEWAY_DELEGATED_ACQUISITION_ENABLED` requires Postgres custody + keyring + config path + trusted callback; `GATEWAY_DELEGATED_AUTHORIZATION_ENABLED` additionally requires the authorization-workload trust set).
- Missing cross-service secrets do not degrade to unauthenticated access: absent `AGENT_EXECUTION_SIGNING_KEY` leaves mutating resumes failed-closed (`signing_unavailable`); absent `AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`.
- Audit ingestion is fire-and-forget: unset `*_AUDIT_SERVICE_URL` falls back to log-only auditing; user-facing requests are never blocked by audit-service reachability.
- Policy bundle load failure raises `PolicyLoadError` with no silent fallback to a packaged default; readiness reports degraded policy state.
- The policy bundle is edited only in `shared/shared-contracts/policies/policy-default.yaml` and must be replicated via `make sync-policy`; contract tests enforce copy parity between engines.
- Secrets are provisioned as Kubernetes `Secret` objects by `sync-*.sh` scripts and mounted into pods; they are never committed to Git.
- Credential-set files are mounted at paths referenced by env vars — inline credentials are never accepted as env values.
- Profile overlays compose over the base via Kustomize; `select-runtime-profile.sh` selects one profile and `verify-runtime-profile.sh` validates the result.