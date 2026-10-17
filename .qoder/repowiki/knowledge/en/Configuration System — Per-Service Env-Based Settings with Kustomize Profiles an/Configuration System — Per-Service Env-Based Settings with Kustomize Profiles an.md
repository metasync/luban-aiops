---
kind: configuration_system
name: Configuration System — Per-Service Env-Based Settings with Kustomize Profiles and GitOps Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/execution-runtime/src/execution_runtime/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/audit-service/src/audit_service/core/config.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/incident-service/src/incident_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/runtime-profiles/README.md
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-incident-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/platform-ops/gitops/sync-browser-credentials.sh
    - shared/platform-ops/gitops/sync-email-secrets.sh
    - shared/platform-ops/gitops/sync-otel-secrets.sh
    - docs/guides/configuration-reference.md
---

# Configuration System

## Approach

The Luban platform uses a **12-factor-style environment-variable configuration** model. Each Python service owns its settings as a frozen `dataclass` with a `from_env()` classmethod that reads values from `os.environ`, validates them in `__post_init__`, and exposes the result through an `lru_cache` singleton (`get_settings()`). There is no centralized config library, YAML/JSON config loader, or feature-flag framework; configuration is purely env-driven.

Kubernetes deployment is driven by **Kustomize overlays** under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` (ConfigMap) plus per-service `runtime-secrets.example.env` templates. Secrets are never committed to Git — they are generated at deploy time by scripts under `shared/platform-ops/gitops/sync-*.sh` and mounted as Kubernetes `Secret` objects.

A single shared ConfigMap (`shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`) provides cross-pod defaults (OTel endpoint, identity broker URL), while LLM provider selection is layered via **runtime profiles** under `shared/platform-ops/gitops/runtime-profiles/` (`default`, `mutating-dev`, `browser-dev`, `ansible-dev`, `secrets-dev`). Profile switching is done through `select-runtime-profile.sh`; only one profile is active at a time.

## Key Files and Packages

- `products/agent-platform/src/agent_service/runtime_settings.py` — `RuntimeSettings` dataclass, agent-service's complete env surface (LLM providers, session/state stores, HITL, execution worker, evidence caps, authoring-trace bounds, skills/incident clients).
- `products/tool-gateway/src/tool_gateway/core/config.py` — `GatewaySettings` dataclass, browser/HTTP/secrets/Ansible-MCP connectors, policy path, audit/skills/incidents clients.
- `products/platform-gateway/src/platform_gateway/core/config.py` — `PlatformGatewaySettings` dataclass, token delegation, policy path, portal proxy URLs.
- `products/execution-runtime/src/execution_runtime/core/config.py` — execution-worker admission, signing key, handoff token.
- `products/identity-broker/src/identity_service/core/config.py` — Keycloak/OIDC client, workload-token issuer, service-client registry.
- `products/audit-service/src/audit_service/core/config.py` — store backend, retention, eviction, ingest client registry.
- `products/skills-hub/src/skills_hub/core/config.py` — federated sources, git tokens, composition cap, query client registry.
- `products/incident-service/src/incident_service/core/config.py` — webhook token, query client registry, triage connector.
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — per-service ConfigMap env files.
- `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — shared env for every pod.
- `shared/platform-ops/gitops/runtime-profiles/` — Kustomize profile overlays.
- `shared/platform-ops/gitops/sync-*.sh` — secret provisioning scripts (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-incident-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-browser-credentials.sh`, `sync-email-secrets.sh`, `sync-otel-secrets.sh`, `sync-runtime-secret.sh`).
- `docs/guides/configuration-reference.md` — authoritative cross-service variable map, dependency chains, and secret contracts.

## Architecture and Conventions

1. **Per-service settings module.** Every service defines a single `core/config.py` (or equivalent) exposing a frozen `@dataclass` + `from_env()` + cached `get_settings()`. The dataclass defaults encode the code-level default; `from_env()` overrides with `os.getenv(name, default)`.

2. **Boolean parsing is uniform.** Truthy strings are `{"1", "true", "yes", "on"}` (lowercased, stripped); falsy is everything else. Optional booleans use `_optional_bool` returning `None` when unset so callers can distinguish "not set" from `false`.

3. **Validation in `__post_init__`.** Range checks, allowed-value enums, and cross-field invariants raise `ValueError` at startup rather than failing later. Examples: `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` must be in `(0, 0.9)`; `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS` must be `> 0` and `<= 120`; `GATEWAY_SECRET_DELIVERY_BACKEND` must be `memory` or `redis`; password-policy env overrides may only tighten the contract.

4. **Feature flags are opt-in and deny-by-default.** Browser tools (`GATEWAY_BROWSER_ENABLED=false`), HTTP tools (`GATEWAY_HTTP_ENABLED=false`), secrets delivery (`GATEWAY_SECRETS_ENABLED=false`), mutating tools (`GATEWAY_MUTATING_TOOLS_ENABLED=false`), elastic connector, Ansible MCP ingestion, model discovery, kernel tracing, task tools, compression — all off by default. Enabling a capability requires setting both the flag and any required companion variables.

5. **Cross-service credentials follow a client-id/client-secret pattern.** A caller sets `<SERVICE>_CLIENT_ID` / `<SERVICE>_CLIENT_SECRET` pointing at a server-side registry (`IDENTITY_SERVICE_CLIENTS`, `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`) formatted as `client_id=secret,...`. The `sync-*-secrets.sh` scripts generate matching pairs and write them into each side's runtime-secrets Secret.

6. **Secrets live in Kubernetes Secrets, not ConfigMaps.** Sensitive keys (`*_API_KEY`, `*_SECRET`, `*_PASSWORD`, `*_TOKEN`, `OTEL_EXPORTER_OTLP_HEADERS`, HMAC signing keys, handoff tokens) are provisioned exclusively via `sync-*.sh` scripts and mounted as Secrets. Non-sensitive knobs go in `runtime-config.env` ConfigMaps.

7. **Policy bundle has exactly one canonical copy.** `shared/shared-contracts/policies/policy-default.yaml` is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay via `make sync-policy`. Contract tests enforce parity; editing a replica is prohibited.

8. **Profiles layer on top of base config.** `runtime-profiles/default` supplies the active LLM provider ConfigMap; `mutating-dev` and `browser-dev` merge additional env flags without being switchable. `select-runtime-profile.sh` selects the profile; `verify-runtime-profile.sh` validates it.

9. **Documentation is the source of truth for operators.** `docs/guides/configuration-reference.md` enumerates every variable, default, owning service, and cross-service chain. It is referenced directly by the per-service sections and kept in sync with the code.

## Conventions and Constraints

- **Environment variables are the sole runtime configuration mechanism.** No `.env` files are read at runtime; values come from the container environment (Kubernetes ConfigMap/envFrom + Secret envFrom).
- **Unknown boolean values fail fast.** `_optional_bool` raises `ValueError` for unrecognized strings; unknown enum choices (e.g. `SESSION_STORE_BACKEND`, `AGENTSCOPE_PROVIDER`, `GATEWAY_SECRET_DELIVERY_BACKEND`) also raise at parse/validation time.
- **Missing required secrets fail closed, never degrade silently.** Missing `AGENT_EXECUTION_SIGNING_KEY` rejects mutating resumes with `signing_unavailable`; missing `AGENT_EXECUTION_HANDOFF_TOKEN` rejects with `worker_unavailable`; missing `AGENT_INCIDENT_CLIENT_SECRET` fails incident-report creation with 503; unset `*_AUDIT_SERVICE_URL` degrades to log-only auditing (the documented exception).
- **Policy bundle load failure fails startup.** A missing or invalid bundle at `PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH` raises `PolicyLoadError`; there is no silent fallback to the packaged default.
- **Cross-service secret contracts are enforced by provisioning scripts.** `make deploy` calls the relevant `sync-*-secrets.sh` scripts which generate random shared secrets (or reuse exported ones like `DELEGATION_CLIENT_SECRET`, `AUDIT_INGEST_SECRET`, `SKILLS_GIT_TOKEN`, `INCIDENT_WEBHOOK_TOKEN`) and create the corresponding K8s Secrets.
- **Profile selection is explicit.** Only one LLM profile is active; switching requires running `shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>`.
- **Policy changes require a prescribed workflow.** Edit the canonical file → bump `version` → update scenarios → `make sync-policy` → `make verify` → `make policy-diff` → commit synced replicas → redeploy. Bundles are cached keyed on path and do not hot-reload; a changed ConfigMap takes effect on pod restart.
- **Secrets are never committed.** All `*-runtime-secrets` manifests reference dynamically created Secrets; `runtime-secrets.example.env` files are templates only.