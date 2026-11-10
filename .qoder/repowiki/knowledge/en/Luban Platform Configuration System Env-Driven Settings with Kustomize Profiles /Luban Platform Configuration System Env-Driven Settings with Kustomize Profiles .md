---
kind: configuration_system
name: 'Luban Platform Configuration System: Env-Driven Settings with Kustomize Profiles and Secret Sync Scripts'
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
---

# Luban Platform Configuration System

## Approach

The platform has no external configuration framework (no Pydantic-settings, Dynaconf, or env-loader library). Each service owns its own frozen `dataclass` settings object that reads exclusively from environment variables via `os.getenv`, validates them in `__post_init__`, and exposes a `from_env()` constructor plus an `lru_cache`-memoized `get_settings()` accessor. The only shared concern is the Kubernetes deployment surface: Kustomize overlays under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` supply non-secret values, while per-service runtime secrets live in dedicated K8s `Secret` objects provisioned by shell scripts.

## Key Files

**Per-service settings modules:**
- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, ~760 lines of env parsing + validation for LLM providers, kernel tuning, HITL, execution worker, durable admission, skills/incident clients, authoring traces, orchestration budgets.
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass (~850 lines), browser/HTTP/Ansible MCP/ServiceNow connectors, secret delivery, delegated identity/acquisition/authorization workflows (SPEC-070).
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass (135 lines), token delegation, policy path, audit/incident/skills proxy URLs.
- `products/execution-runtime/src/execution_runtime/core/config.py` — execution-worker admission and handoff config.
- `products/audit-service/src/audit_service/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/incident-service/src/incident_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py` — analogous per-service settings.

**Deployment surface:**
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — one env file per service, mounted as a ConfigMap.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared keys (`OTEL_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `IDENTITY_SERVICE_URL`) applied to every pod.
- `shared/platform-ops/gitops/runtime-profiles/` — feature profiles (`browser-dev`, `ansible-dev`, `servicenow-dev`, `mutating-dev`, `delegated-dev`, `model-router-dev`, `secrets-dev`) that overlay additional env on top of the base.
- `shared/platform-ops/gitops/sync-*.sh` — secret provisioning scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-email-secrets.sh`, `sync-browser-credentials.sh`, `sync-servicenow-credentials.sh`, `sync-custody-db.sh`).

**Documentation contract:**
- `docs/guides/configuration-reference.md` — authoritative cross-service environment variable dependency map, feature activation matrix, secret contracts, and per-service tables linking each variable to its source file and default.

## Architecture and Conventions

### One dataclass per service
Each service defines exactly one frozen dataclass holding all runtime knobs. There is no nested config hierarchy; everything is flat env vars. The class defaults encode the code-level defaults, and `from_env()` maps env vars to fields. A module-level `@lru_cache(maxsize=1)` `get_settings()` function provides process-wide singleton access.

### Validation in `__post_init__`
Invalid values fail startup with `ValueError`, never degrade silently. Cross-field constraints are enforced here: e.g., `RuntimeSettings.__post_init__` rejects enabling model routing without a classifier model id, requires both ledger DSN and epoch when durable admission is enabled, validates IANA timezone names, enforces agentscope's `context_buffer_ratio < trigger_ratio` invariant, and constrains worker timeout to ≤120s.

### Boolean parsing convention
Booleans accept `1`, `true`, `yes`, `on` (case-insensitive) as truthy; empty strings are falsy. The agent-service helper `_optional_bool` raises `ValueError` for any other value. The tool-gateway uses a local `_env_bool(name, default)` helper with the same set.

### Feature flags are opt-in and off-by-default
Every new capability is gated behind a boolean env var that defaults to `false`: `GATEWAY_BROWSER_ENABLED`, `GATEWAY_HTTP_ENABLED`, `GATEWAY_ANSIBLE_MCP_ENABLED`, `GATEWAY_SERVICENOW_ENABLED`, `GATEWAY_SECRETS_ENABLED`, `AGENT_EXECUTION_ADMISSION_ENABLED`, `AGENTSCOPE_MODEL_ROUTER_ENABLED`, `AGENTSCOPE_COMPRESS_CONTEXT_ENABLED`, `AGENT_TARGET_AUTHORIZATION_ENABLED`, `PLATFORM_GATEWAY_TARGET_AUTHORIZATION_ENABLED`, etc. Enabling a flag often requires additional infrastructure (Postgres DSN, keyring mount, JWKS URL, actor allowlist); missing prerequisites cause startup failure rather than partial enablement.

### Secrets vs. non-secrets separation
Non-secret configuration lives in `runtime-config.env` ConfigMaps. Secrets (API keys, client secrets, signing keys, OTLP headers, SMTP passwords) live in per-service K8s `Secret` objects created by `sync-*.sh` scripts. The documentation explicitly marks which variables come from **runtime-secrets** versus runtime-config. Some sensitive values are injected via optional `secretKeyRef` so an absent secret fails closed (e.g., `AGENT_EXECUTION_SIGNING_KEY`, `AGENT_EXECUTION_HANDOFF_TOKEN`).

### Cross-service credential contracts
Inter-service auth uses a consistent pattern: each caller gets a `<SERVICE>_CLIENT_ID` / `<SERVICE>_CLIENT_SECRET` pair, and the callee maintains a registry like `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`. Provisioning scripts generate matching pairs and write them into both sides' secrets. The `configuration-reference.md` documents each chain with ASCII diagrams showing required matches.

### Policy bundle as code
The action-authorization bundle has exactly one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to both gateways' packaged defaults and the dev-k8s GitOps overlay via `make sync-policy`; `make verify` fails on drift. Bundles are cached by path and require a pod restart to reload — there is no hot reload.

### Kustomize profile composition
Feature toggling is done through Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/`. For example, `browser-dev` merges `tool-gateway-browser-sidecar.yaml` and `browser.env` on top of the base, enabling `GATEWAY_BROWSER_ENABLED=true` and wiring the CDP sidecar. `mutating-dev`, `ansible-dev`, `servicenow-dev`, `delegated-dev`, `model-router-dev`, and `secrets-dev` follow the same pattern. The base overlay leaves capabilities disabled.

### Documentation-driven configuration
`docs/guides/configuration-reference.md` is the single source of truth for operators. Every table links each variable back to its source file (`products/<service>/src/<service>/core/config.py` or `runtime_settings.py`) and its deployment fragment (`shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`). The document also records cross-service chains, secret contracts, and the exact `sync-*` script used to provision each secret.

## Conventions and Constraints

- **Environment-only loading**: All runtime configuration comes from `os.getenv`; no `.yaml`, `.toml`, `.ini`, or `.env` files are parsed by application code at runtime. File paths (policy bundles, credential sets, keyrings) are configured but the files themselves are not loaded by the settings layer.
- **Frozen dataclasses with `from_env()`**: Every service follows this shape; adding a new setting means adding a field with a sensible default and mapping it in `from_env()`.
- **Startup-time validation**: Invalid or incomplete configuration aborts process startup via `ValueError`; there is no runtime fallback for critical knobs (execution signing key, worker handoff token, durable admission epoch, delegated custody runtime).
- **Opt-in features**: New capabilities default to `false` and require explicit env activation plus any prerequisite infrastructure.
- **Deny-by-default security posture**: Browser/HTTP origin allowlists default to empty (deny-all); mutating tools default off; delegated identity/acquisition/authorization workflows default off and validate full trust configuration before enabling.
- **Secrets are never committed**: All secrets are provisioned via `sync-*.sh` scripts into K8s `Secret` objects; the repository contains only `runtime-secrets.example.env` templates.
- **Cross-service credentials must match**: Client IDs and secrets registered on the callee side must match what callers send; provisioning scripts enforce this pairing.
- **Policy bundle integrity**: Editing the canonical `policy-default.yaml` requires bumping its `version` field, updating `policy-scenarios.yaml`, running `make sync-policy` and `make verify`, and committing the bundle plus synced replicas together.
- **No hot reload for policy bundles**: Changed ConfigMaps take effect only on pod restart; the documentation instructs rolling restarts after bundle changes.
- **Configuration reference is authoritative**: The `configuration-reference.md` tables are the contract between developers and operators; new variables should be added there alongside the code change.