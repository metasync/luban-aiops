---
kind: configuration_system
name: Environment-Driven Configuration System with GitOps Profiles and Secret Provisioning
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/runtime_settings.py
    - docs/guides/configuration-reference.md
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/execution-runtime/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/incident-service/runtime-config.env
    - shared/platform-ops/gitops/runtime-profiles/browser-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/mutating-dev/kustomization.yaml
    - shared/platform-ops/gitops/runtime-profiles/model-router-dev/model-router.env
    - shared/platform-ops/gitops/sync-delegation-secrets.sh
    - shared/platform-ops/gitops/sync-audit-secrets.sh
    - shared/platform-ops/gitops/sync-skills-secrets.sh
    - shared/platform-ops/gitops/sync-execution-signing-secret.sh
    - shared/platform-ops/gitops/sync-execution-handoff-secret.sh
    - shared/shared-contracts/policies/policy-default.yaml
---

## Approach

The Luban platform uses a pure **environment-variable-driven configuration system** layered over Kubernetes ConfigMaps/Secrets, with no framework-based config loader. Each Python service owns its own settings module that reads `os.getenv` values, validates them in `__post_init__`, and exposes a frozen dataclass (e.g. `RuntimeSettings`) consumed by the application. There is no `.env` file parsing at runtime; environment variables are injected by Kubernetes from ConfigMaps and Secrets.

Configuration is organized into two layers:
1. **Runtime defaults** — non-secret knobs live in per-service `runtime-config.env` files under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`, mounted as ConfigMaps.
2. **Secrets** — sensitive values live in per-service `runtime-secrets.example.env` / generated K8s `Secret` objects (e.g. `agent-platform-runtime-secrets`, `execution-signing-secret`, `execution-handoff-secret`, `platform-gateway-runtime-secrets`).

A third layer of **GitOps overlays** under `shared/platform-ops/gitops/runtime-profiles/<profile>/` (e.g. `browser-dev`, `ansible-dev`, `mutating-dev`, `model-router-dev`, `delegated-dev`, `secrets-dev`) merges additional environment variables on top of the base via kustomization, enabling feature toggles without changing source code.

## Key Files

- `products/agent-platform/src/agent_service/runtime_settings.py` — canonical settings loader for agent-service; defines `RuntimeSettings`, `_optional_str/int/float/bool/choice`, `from_env()`, and all validation in `__post_init__`.
- `docs/guides/configuration-reference.md` — authoritative cross-service env-var dependency map, feature activation matrix, secret contracts, and per-service tables linking each variable to its source (`runtime-config` vs `runtime-secrets`).
- `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` — one per service, defining default values.
- `shared/platform-ops/gitops/runtime-profiles/<profile>/` — feature-profile overlays (kustomization.yaml + env files) merged on deploy.
- `shared/platform-ops/gitops/sync-*.sh` scripts — secret provisioning entry points (`sync-delegation-secrets.sh`, `sync-audit-secrets.sh`, `sync-skills-secrets.sh`, `sync-execution-signing-secret.sh`, `sync-execution-handoff-secret.sh`, `sync-incident-secrets.sh`, `sync-otel-secrets.sh`, `sync-email-secrets.sh`, `sync-browser-credentials.sh`, `sync-servicenow-credentials.sh`, `sync-runtime-secret.sh`).
- Per-service config modules: `products/execution-runtime/src/execution_runtime/core/config.py`, `products/platform-gateway/src/platform_gateway/core/config.py`, `products/tool-gateway/src/tool_gateway/core/config.py`, `products/identity-broker/src/identity_service/core/config.py`, `products/audit-service/src/audit_service/core/config.py`, `products/skills-hub/src/skills_hub/core/config.py`, `products/incident-service/src/incident_service/core/config.py`.
- `shared/shared-contracts/policies/policy-default.yaml` — single canonical policy bundle, replicated byte-identically to both gateways' packaged defaults.

## Architecture and Conventions

### Settings loading pattern
Each service's settings class follows the same shape: helper functions `_optional_str/_optional_int/_optional_float/_optional_bool/_optional_choice` parse raw env vars, `from_env()` constructs the frozen dataclass, and `__post_init__` enforces cross-field invariants (ranges, required pairs, type compatibility). The agent-service's `RuntimeSettings` is the most complete example, covering LLM provider options, kernel tuning, model routing, HITL bridging, execution signing, isolated worker handoff, durable admission, browser flow TTL, audit/incident/skills client wiring, authoring-trace bounds, and skill graduation limits.

### Validation philosophy
Validation is **fail-fast at startup**: invalid ranges raise `ValueError` with explicit messages referencing the env var name; missing required pairs (e.g. `AGENT_EXECUTION_ADMISSION_ENABLED=true` requires both `AGENT_EXECUTION_STATE_DB_URL` and `AGENT_EXECUTION_ADMISSION_EPOCH`; `AGENTSCOPE_MODEL_ROUTER_ENABLED` with candidates requires `AGENTSCOPE_MODEL_ROUTER_MODEL`) fail startup rather than degrading silently. Many features are opt-in with sensible defaults so an unset deployment behaves identically to the previous release (e.g. `compress_context_enabled=False`, `model_router_enabled=False`, `execution_admission_enabled=False`).

### Feature flags
Feature flags are exposed through the authenticated `GET /api/v1/runtime/flags` gateway route (proxying agent's `/api/v2/runtime/flags`), gated by the `runtime:flags` policy action. The flag inventory reports only toggleable knobs (`model_routing`, `model_discovery`, `context_compression`, `outbound_delegated_identity`, `kernel_tracing`, `task_tools`, `reply_token_budget`, `hitl_bridging`, `signed_execution`) — not invariants like permission enforcement or evidence capture.

### Policy configuration
Policy bundles have exactly one canonical copy at `shared/shared-contracts/policies/policy-default.yaml`. It is replicated byte-identically to both gateways' packaged defaults and the dev-k8s overlay by `make sync-policy`; contract tests fail `make verify` on any drift. A missing or invalid bundle at the configured path fails startup (`PolicyLoadError`, no silent fallback to the packaged default).

### Secret provisioning
Secrets are provisioned exclusively through shell scripts invoked by `make deploy`, never committed to Git. Cross-service secrets follow a shared-secret contract: e.g. `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` must match the corresponding entry in `IDENTITY_SERVICE_CLIENTS`; `*_AUDIT_CLIENT_SECRET` values must match entries in `AUDIT_INGEST_CLIENTS`; skills/incident query credentials must match their respective `*_QUERY_CLIENTS` registries. Scripts generate random secrets when none are exported, and support `SKIP_*_SECRETS=true` opt-out.

### Profile-based feature activation
Kustomization overlays under `runtime-profiles/<profile>/` enable optional capabilities (browser sidecar, ansible MCP mock, mutating tools, model router, delegated identity, secrets delivery, servicenow mock) by merging additional env vars. This is how dev-k8s opts into features like `GATEWAY_BROWSER_ENABLED=true`, `GATEWAY_HTTP_ENABLED=true`, `GATEWAY_ANSIBLE_MCP_ENABLED=true`, and `GATEWAY_SERVICENOW_ENABLED=true` without changing base configs.

### Documentation as contract
`docs/guides/configuration-reference.md` is the definitive cross-service dependency map. Every env var table lists Purpose, Default, and Source (`runtime-config` vs `runtime-secrets` vs `code default`), and every cross-service chain diagram documents the matching secret contract and provisioning script.

## Conventions and Constraints

- All runtime configuration is read from environment variables via `os.getenv`; there is no `.env` file parser, YAML config loader, or framework config object used at runtime.
- Non-secret defaults live in `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`; secrets live in generated K8s `Secret` objects referenced by `secretKeyRef` in deployments.
- Optional features default to disabled (`false`); enabling a feature requires setting its dedicated `*_ENABLED` env var plus any required companion variables.
- Missing required dependencies fail closed (503 or startup error) rather than degrading silently — e.g. unset `AGENT_EXECUTION_WORKER_URL` rejects mutating resumes with `worker_unavailable`; unset `AGENT_EXECUTION_SIGNING_KEY` rejects with `signing_unavailable`; unset incident/skills URLs fail creation with 503.
- Fire-and-forget audit emission degrades to log-only when unreachable; user-facing requests are never blocked by audit-service availability.
- The policy bundle has one canonical source (`shared/shared-contracts/policies/policy-default.yaml`); edits must go through `make sync-policy` and `make verify` enforces copy parity across both gateways.
- Cross-service secrets use shared-secret contracts documented in the configuration reference; provisioning scripts create both sides of the contract atomically.
- Feature profiles are additive kustomization overlays; the base remains production-safe with all optional connectors disabled.
- The `configuration-reference.md` is maintained as the authoritative source of truth and links each env var back to its code location and gitops fragment.