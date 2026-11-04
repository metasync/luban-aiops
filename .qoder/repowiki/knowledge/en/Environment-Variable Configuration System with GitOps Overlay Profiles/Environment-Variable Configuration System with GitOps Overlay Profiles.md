---
kind: configuration_system
name: Environment-Variable Configuration System with GitOps Overlay Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/platform-ops/gitops/verify-runtime-profile.sh
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
---

## Approach

The Luban platform has no external configuration framework (no Pydantic `BaseSettings`, no `python-dotenv` loader, no `dynaconf`). Every service reads its own settings exclusively from process environment variables via `os.getenv`. The repository's configuration surface is therefore a flat set of uppercase env vars, layered by Kubernetes ConfigMaps and Secrets mounted into each pod.

## Key files and packages

**Per-service settings loaders**
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` frozen dataclass; the largest loader, covering LLM providers, kernel tuning, HITL, signed execution, durable admission, skills/incident clients, authoring-trace bounds, model routing.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` frozen dataclass; identity, delegation, policy path, audit/incident/skills proxy URLs.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` frozen dataclass; browser, HTTP, secrets, Ansible MCP, ServiceNow, delegated acquisition/authorization runtime.
- `products/execution-runtime/src/execution_runtime/core/config.py` — execution worker admission, signing key, handoff token.
- `products/audit-service/src/audit_service/core/config.py` — store backend, retention, ingest client registry.
- `products/skills-hub/src/skills_hub/core/config.py` — federated sources, composition cap, query clients.
- `products/incident-service/src/incident_service/core/config.py` — store backend, webhook token, agent triage URL.
- `products/identity-broker/src/identity_service/core/config.py` — Keycloak/OIDC, workload issuer, client registry.

**GitOps overlay profiles**
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — base ConfigMap content for every service.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared across all pods (`OTEL_ENABLED`, `IDENTITY_SERVICE_URL`).
- `shared/platform-ops/gitops/runtime-profiles/<profile>/` — feature overlays (`browser-dev`, `mutating-dev`, `ansible-dev`, `servicenow-dev`, `model-router-dev`, `delegated-dev`, `secrets-dev`) that merge additional env vars on top of the base via Kustomize.
- `shared/platform-ops/gitops/select-runtime-profile.sh`, `verify-runtime-profile.sh` — operator scripts to select and validate the active profile.

**Secret provisioning**
- `shared/platform-ops/gitops/sync-*.sh` — `sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`, etc. Each creates or updates the corresponding K8s `Secret` and documents the contract in `docs/guides/configuration-reference.md`.

**Documentation**
- `docs/guides/configuration-reference.md` — definitive cross-service environment variable dependency map: feature activation matrix, per-service tables (variable, purpose, default, source), secret contracts, cross-service chains (token delegation, audit ingestion, skills retrieval, incident intake, mutating action approval).

## Architecture and conventions

1. **One settings class per service.** Each product exposes a single frozen `dataclass` under `src/<service>/core/config.py` (or `runtime_settings.py` for agent-platform) with a `from_env()` classmethod that maps env vars to typed fields. A module-level `@lru_cache(maxsize=1)` `get_settings()` function provides a singleton accessor.

2. **Typed parsing helpers.** Both `RuntimeSettings` and `GatewaySettings` define private helpers (`_optional_str/int/float/bool`, `_optional_choice`, `_env_bool`, `_env_optional_tuple`) that normalize values before construction. Boolean truthiness accepts `1|true|yes|on`; unknown boolean strings raise `ValueError`.

3. **Validation in `__post_init__`.** Cross-field invariants are enforced at construction time, not lazily. Examples: `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED` requires `AGENTSCOPE_CONTEXT_TRIGGER_RATIO > 0.2`; enabling `AGENT_EXECUTION_ADMISSION_ENABLED` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`; password-policy env overrides may only tighten the canonical contract; delegated-acquisition/authorization routes require Postgres custody + keyring + trusted callback.

4. **Feature flags are opt-in and default-off.** New capabilities (browser connector, HTTP connector, secrets delivery, Ansible MCP, ServiceNow, model routing, context compression, delegated acquisition/authorization) are gated behind explicit env vars whose defaults are `false` or empty. An unset URL disables the connector rather than failing open.

5. **Kubernetes-native layering.** Non-secret config lives in `runtime-config.env` files mounted as ConfigMaps; secrets live in per-service `*-runtime-secrets` Secrets provisioned by `sync-*.sh` scripts. Profile overlays under `runtime-profiles/<name>/kustomization.yaml` add or override base env vars for features like browser automation, mutating tools, Ansible, ServiceNow, model routing, and delegated identity.

6. **Cross-service contracts are documented, not type-enforced.** Mutual dependencies (e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS`, `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS`) are described in `configuration-reference.md` and enforced at runtime by the receiving service's client registry; there is no schema validator that compares the two sides.

7. **Policy bundle is a separate concern from env config.** The authorization bundle lives at `shared/shared-contracts/policies/policy-default.yaml`, synced byte-identically to both gateways' packaged defaults and the dev-k8s overlay by `make sync-policy`; contract tests fail `make verify` on drift. It is loaded from a file path (`GATEWAY_POLICY_PATH` / `PLATFORM_GATEWAY_POLICY_PATH`), not from env.

8. **No hot reload.** Policy bundles and most env changes take effect only on pod restart; the documentation explicitly states "there is deliberately no hot reload" and instructs rolling-restart of gateway deployments.

## Conventions and constraints

- Every setting is an uppercase environment variable read through `os.getenv` with an explicit default; no `.env` files, no YAML/JSON config files, no framework-based loading.
- Settings classes are `frozen=True` dataclasses; once constructed they are immutable.
- Unknown enum values (e.g. unsupported `AGENTSCOPE_PROVIDER`, invalid `SESSION_STORE_BACKEND`, invalid `GATEWAY_ANSIBLE_MCP_TRANSPORT`) raise `ValueError` at startup rather than silently falling back.
- Optional booleans accept exactly `1|true|yes|on`; any other non-empty string raises `ValueError`.
- Feature-flagged connectors register themselves only when their enable flag is true AND all required infrastructure knobs are present; otherwise they stay inert or fail-closed.
- Secrets are never committed to Git and must be provisioned via the `sync-*.sh` scripts under `shared/platform-ops/gitops/`; the reference document lists each Secret name, key, purpose, and provisioning command.
- Per-service env var tables in `docs/guides/configuration-reference.md` are the authoritative source of truth for operators; the code comments and `__post_init__` validation enforce the invariants those tables describe.
- Profile selection is operator-driven via `select-runtime-profile.sh` and validated by `verify-runtime-profile.sh`; base overlays leave sensitive features disabled and opt-in overlays (e.g. `browser-dev`, `mutating-dev`) add the necessary flags.