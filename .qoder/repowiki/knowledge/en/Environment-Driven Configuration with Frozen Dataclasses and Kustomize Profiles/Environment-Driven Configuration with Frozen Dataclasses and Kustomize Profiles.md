---
kind: configuration_system
name: Environment-Driven Configuration with Frozen Dataclasses and Kustomize Profiles
category: configuration_system
scope:
    - '**'
source_files:
    - products/tool-gateway/src/api_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/openai/runtime-secrets.example.env
    - shared/shared-contracts/policies/policy-default.yaml
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/policy.yaml
---

The repository implements a uniform, environment-variable-driven configuration system across all Python services (agent-platform, tool-gateway, identity-broker). Each service defines its settings as frozen dataclasses with a `from_env()` classmethod that reads values from `os.environ`, and exposes an `@lru_cache(maxsize=1)` accessor (`get_settings()`) so the configuration is loaded once per process lifetime.

**Core pattern per service**
- `src/<service>/core/config.py` or `runtime_settings.py` declares a frozen dataclass (e.g. `GatewaySettings`, `IdentitySettings`, `RuntimeSettings`) with sensible defaults and a `from_env()` constructor that maps `ENV_VAR_NAME` to fields via `os.getenv(..., default)`.
- A module-level `get_settings()` function wraps the constructor with `functools.lru_cache(maxsize=1)`, guaranteeing single-load semantics.
- Boolean flags are parsed through a consistent helper that accepts `{"1","true","yes","on"}` as truthy and `{"0","false","no","off"}` as falsy; unsupported boolean strings raise `ValueError`.
- Choice-type fields validate against a fixed set of supported values and raise `ValueError` when invalid.

**Service-specific configuration scopes**
- **Agent Platform** (`RuntimeSettings`): provider selection (`AGENTSCOPE_PROVIDER`), model name/base URL/API key/organization, per-provider options (`DASHSCOPE_*`, `DEEPSEEK_*`, `OPENAI_*`), session store backend and Redis connection, workspace directory/TTL, and the upstream `TOOL_GATEWAY_URL`. Provider/options types are validated in `__post_init__` so `AGENTSCOPE_PROFILE` must match `AGENTSCOPE_PROVIDER` when both are set.
- **Tool Gateway** (`GatewaySettings`): downstream URLs for agent-service and identity-service, JWKS cache TTL, token issuer/audience, workload-token path, dev signing key/user, policy file path, chat timeout, auth toggle, Kubernetes connector enablement/namespace, and redaction toggles.
- **Identity Broker** (`IdentitySettings`): Keycloak base URL/realm, OIDC client credentials/scopes/redirect URIs, JWT private key path and TTLs, issuer/audience, plus two composite env formats: `IDENTITY_SERVICE_CLIENTS` (comma-separated `client_id:secret:aud1|aud2`) and `IDENTITY_WORKLOAD_CLIENTS` (comma-separated `subject=client_id:aud1|aud2`).

**Kubernetes / GitOps delivery**
- Runtime configuration is delivered via per-deployment `runtime-config.env` files mounted into each pod (e.g. `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env`).
- Secrets are separated into `runtime-secrets.example.env` files (never committed) and synced into cluster Secrets (`identity-service-runtime-secrets`, `api-gateway-runtime-secrets`).
- LLM provider profiles are switched at deploy time through Kustomize ConfigMaps under `shared/platform-ops/gitops/runtime-profiles/<provider>/configmap.yaml`, which set `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`; corresponding `runtime-secrets.example.env` holds provider API keys.
- Policy enforcement rules are loaded from a YAML bundle referenced by `GATEWAY_POLICY_PATH` (default `policy-default.yaml` in `shared/shared-contracts/policies/` and copied into `tool-gateway/policy.yaml`). The policy engine enforces deny-by-default, explicit-deny-overrides-allow, and priority-based rule resolution.

**Conventions observed**
- All configuration lives in environment variables — no `.env` files are read at runtime; example `.env` templates exist only under `runtime-secrets.example.env` for developers.
- Settings objects are immutable (`frozen=True`) to prevent mutation after startup.
- New configuration fields follow the naming convention `SERVICE_*_VAR` (e.g. `GATEWAY_*`, `IDENTITY_*`, `AGENTSCOPE_*`) and are exposed through `from_env()` with a documented default.
- Complex multi-value settings use delimited string formats parsed inside `from_env()` (comma + colon/pipe for clients/workload mappings).
- Validation is strict: unsupported enum values and malformed booleans raise exceptions at load time rather than failing later.