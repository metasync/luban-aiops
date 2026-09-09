---
kind: configuration_system
name: Environment-Driven Configuration with Kustomize Profiles and GitOps Secrets
category: configuration_system
scope:
    - '**'
source_files:
    - docs/guides/configuration-reference.md
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - products/platform-gateway/src/platform_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/select-runtime-profile.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

# Configuration System

## What system/approach is used

The platform uses a **pure environment-variable configuration model** layered over Kubernetes ConfigMaps, Secrets, and Kustomize overlays. There are no YAML-based application config files consumed at runtime; every service reads `os.getenv(...)` from its process environment. The `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` files define the per-service defaults, which Kustomize merges into a single `platform-runtime-config` ConfigMap mounted as env vars. Secrets (API keys, client secrets, signing keys) live in per-service `*-runtime-secrets` Kubernetes Secret objects and are provisioned by dedicated shell scripts under `shared/platform-ops/gitops/sync-*.sh`. LLM provider selection is decoupled from deployment profiles via Kustomize profile overlays (`runtime-profiles/default`, `mutating-dev`, `browser-dev`) selected through `select-runtime-profile.sh`.

## Key files and packages

- Per-service settings loaders: `products/*/src/*_service/core/config.py` — frozen dataclasses parsed from `os.getenv` with `@lru_cache(maxsize=1)` singleton accessors (e.g. `PlatformGatewaySettings.from_env()`).
- Agent-platform rich settings: `products/agent-platform/src/agent_service/runtime_settings.py` — typed dataclass with `__post_init__` validation, provider-specific option parsing, and feature-flag toggles for HITL, evidence caps, execution worker, browser flow TTL, etc.
- Shared runtime env: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env` — OTLP endpoint and identity broker URL shared across all pods.
- Per-service runtime configs: `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — the canonical source of truth for each service's non-secret knobs.
- Profile selector: `shared/platform-ops/gitops/select-runtime-profile.sh` — generates the Kustomization that merges base + chosen LLM profile + always-on dev postures (`mutating-dev`, `browser-dev`).
- Secret provisioning scripts: `sync-audit-secrets.sh`, `sync-delegation-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-skills-secrets.sh`, `sync-otel-secrets.sh`, `sync-browser-credentials.sh`, `sync-runtime-secret.sh`.
- Policy bundle: `shared/shared-contracts/policies/policy-default.yaml` — the single canonical RBAC policy file replicated byte-identically to both gateways' packaged defaults and the dev overlay via `make sync-policy`.
- Authoritative reference: `docs/guides/configuration-reference.md` — cross-service dependency map, feature activation matrix, secret contracts, and per-service variable tables.

## Architecture and conventions

### Layering
1. **Code defaults** — hard-coded fallbacks in each service's settings dataclass (e.g. `AGENTSCOPE_PROVIDER = "dashscope"`, `SESSION_STORE_BACKEND = "postgres"`).
2. **Kustomize ConfigMap** — `runtime-config.env` files merged into `platform-runtime-config`; values here override code defaults.
3. **Kubernetes Secrets** — sensitive values injected as env vars from `*-runtime-secrets` (never committed to Git).
4. **Runtime profiles** — Kustomize overlays that add or merge additional env vars on top of the base (LLM provider switch, mutating tools, browser sidecar).
5. **Policy bundle** — loaded from a file path (`PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH`, default `/etc/luban/policy/policy.yaml`); missing or invalid bundle fails startup with `PolicyLoadError`, no silent fallback.

### Cross-service secret contracts
Every inter-service call authenticates via a shared secret pair: the caller has `<PREFIX>_CLIENT_ID` + `<PREFIX>_CLIENT_SECRET` in its runtime-secrets, and the callee registers them in a registry env var (e.g. `AUDIT_INGEST_CLIENTS`, `SKILLS_QUERY_CLIENTS`, `INCIDENT_QUERY_CLIENTS`, `IDENTITY_SERVICE_CLIENTS`) as `client_id=secret,...`. Provisioning scripts generate one random shared secret per chain and write it to both sides idempotently. A mismatch causes authentication failure at the callee.

### Validation and fail-closed posture
Settings are validated in `__post_init__` (agent-platform) or at parse time (gateway), raising `ValueError` on startup for out-of-range values (e.g. `AGENTSCOPE_CONTEXT_TRIGGER_RATIO` must be in `(0, 0.9)`, `AGENT_EXECUTION_WORKER_TIMEOUT_SECONDS > 0`, `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS >= 1`). Optional features degrade gracefully (unset audit URL → log-only), but security-sensitive paths fail closed (missing `AGENT_EXECUTION_SIGNING_KEY` → mutating resumes rejected with `signing_unavailable`; missing `AGENT_EXECUTION_HANDOFF_TOKEN` → `worker_unavailable`; unset `INCIDENT_WEBHOOK_TOKEN` → intake disabled with 503).

### Feature gating
Capabilities are activated by boolean flags plus required dependencies:
- Mutating tools: `GATEWAY_MUTATING_TOOLS_ENABLED=true` AND `tools:mutate` policy grant AND pod-delete RBAC AND `AGENT_HITL_CONFIRM_TIMEOUT>0`.
- Browser web-checks: `GATEWAY_BROWSER_ENABLED=true` AND reachable CDP endpoint AND origin allowlist AND (for write-class flows) `AGENT_HITL_CONFIRM_TIMEOUT>0`.
- Skills/incident/audit: set `<SERVICE>_SERVICE_URL` + matching client credentials; unset URL leaves the connector unregistered or route fail-closed (503).

### Policy management workflow
The canonical policy lives in `shared/shared-contracts/policies/policy-default.yaml`. Changes require editing this file, bumping its `version`, updating `policy-scenarios.yaml`, running `make sync-policy`, verifying with `make verify` (schema check, scenario-expectation guard against both engines, copy-parity assertions), then deploying. Both gateways expose a SHA-256 fingerprint of the loaded bundle for provenance verification.

## Conventions and constraints

- **All configuration is environment variables.** No `.yaml`/`.toml`/`.env` files are read directly by application code; only Kustomize-generated ConfigMaps and Secrets provide the process environment.
- **Secrets are never committed.** All secrets are provisioned via `sync-*.sh` scripts into Kubernetes Secrets; example templates use `*-secrets.example.env` filenames.
- **Defaults are safe-by-default.** Mutating tools, browser tools, Elastic, and workloads tokens are `false`/disabled in base; opt-in via profile overlays.
- **Cross-service secrets are paired.** Every emitter's `<PREFIX>_CLIENT_SECRET` must match the corresponding entry in the callee's registry env var; provisioning scripts enforce this pairing.
- **Startup-time validation.** Invalid numeric ranges, unsupported providers, or unknown store backends cause the process to exit with an error rather than misbehaving at runtime.
- **Single source of truth for policy.** `shared/shared-contracts/policies/policy-default.yaml` is the only editable copy; replicas are generated, not edited.
- **Profiles are additive.** Kustomize merges base + chosen LLM profile + always-on dev postures; `mutating-dev` and `browser-dev` cannot be switched off.
- **Feature documentation is authoritative.** `docs/guides/configuration-reference.md` is the definitive cross-service dependency map and must stay synchronized with code changes.