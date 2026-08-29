---
kind: configuration_system
name: Environment-Driven Configuration with Kustomize Profiles and Secret Contracts
category: configuration_system
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/core/config.py
    - products/tool-gateway/src/tool_gateway/core/config.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/shared-contracts/policies/policy-default.yaml
    - docs/guides/configuration-reference.md
---

# Configuration System

## What system/approach is used

The platform uses a **pure environment-variable configuration model** layered on top of Kubernetes ConfigMaps and Secrets, orchestrated via Kustomize overlays. Each Python service defines its own typed settings dataclass that reads exclusively from `os.environ` through a `from_env()` classmethod, then exposes the instance via an `@lru_cache(maxsize=1)`-decorated `get_settings()` accessor. There are no YAML/JSON config files consumed at runtime by application code — configuration lives entirely in env vars, mounted as ConfigMap keys or Secret entries.

Runtime profiles (LLM backends) are implemented as Kustomize overlays under `shared/platform-ops/gitops/runtime-profiles/{openai,dashscope,deepseek}/configmap.yaml`, each producing a single `agent-platform-runtime-profile` ConfigMap that sets `AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, and `AGENTSCOPE_BASE_URL`. A helper script `select-runtime-profile.sh` switches which profile overlay is active.

Policy bundles are the only non-env configuration artifact: a canonical YAML at `shared/shared-contracts/policies/policy-default.yaml` is validated against a JSON schema (`make validate-policy`) and synced byte-for-byte to consumer locations under each product's `policies/` directory and into `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`, then mounted at the paths referenced by `PLATFORM_GATEWAY_POLICY_PATH` / `GATEWAY_POLICY_PATH`.

## Key files and packages

- Per-service settings loaders:
  - `products/platform-gateway/src/platform_gateway/core/config.py` → `PlatformGatewaySettings`
  - `products/tool-gateway/src/tool_gateway/core/config.py` → `GatewaySettings`
  - `products/identity-broker/src/identity_service/core/config.py` → `IdentitySettings` (+ `ServiceClient`, `WorkloadClient`)
  - `products/agent-platform/src/agent_service/runtime_settings.py` → `RuntimeSettings` (+ provider-specific option dataclasses)
  - `products/agent-platform/src/agent_service/core/config.py` → cached `get_settings()` wrapper
- Shared runtime env injected into every pod:
  - `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`
- Per-service runtime-config fragments (ConfigMap sources):
  - `shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`
  - `shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env`
  - `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`
- Secrets examples and contracts:
  - `shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.example.env`
  - `shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-secrets.example.env`
  - `shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-secrets.env` (dev-only committed secret)
- Runtime profile overlays:
  - `shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml`
  - `shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml`
  - `shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml`
- Policy bundle:
  - `shared/shared-contracts/policies/policy-default.yaml`
  - Consumer copies: `products/*/src/*/policies/policy-default.yaml`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`
- Authoritative cross-service dependency map:
  - `docs/guides/configuration-reference.md`

## Architecture and conventions

### Typed settings dataclasses
Every service defines a frozen `@dataclass` whose fields hold defaults and whose `from_env()` classmethod maps environment variables to those fields. Boolean flags are parsed uniformly: `.strip().lower() in {"1", "true", "yes", "on"}`. Optional string helpers (`_optional_str`, `_optional_int`, `_optional_float`, `_optional_bool`, `_optional_choice`) in `runtime_settings.py` raise `ValueError` when a variable is set but invalid (e.g., unsupported `AGENTSCOPE_PROVIDER` or wrong boolean value).

### Cached singleton access
Each module exposes `get_settings()` decorated with `functools.lru_cache(maxsize=1)`, so the process loads env once and reuses the settings object for the lifetime of the worker. This is how services consume configuration throughout their codebase.

### Layered env source
Configuration is layered in this order (later overrides earlier):
1. Hardcoded defaults inside the dataclass field definitions.
2. Values from per-service `runtime-config.env` files (mounted as ConfigMap keys).
3. Values from shared `runtime.env` (injected into every pod).
4. Values from `runtime-secrets.env` (mounted as Kubernetes Secrets; never committed except dev example).
5. For agent-service LLM providers, a selected runtime profile ConfigMap (`agent-platform-runtime-profile`) supplies `AGENTSCOPE_*` variables.

### Cross-service contract variables
Several environment variables form explicit contracts between services and must be kept in sync:
- `IDENTITY_SERVICE_URL` is shared across all pods via `shared/runtime.env`.
- Token delegation requires `PLATFORM_GATEWAY_SERVICE_CLIENT_ID` + `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` to match the corresponding entry in `IDENTITY_SERVICE_CLIENTS` on the identity broker.
- JWT verification requires matching `IDENTITY_TOKEN_ISSUER` and `*_TOKEN_AUDIENCE` values between issuer and consumers.
- The policy YAML must be byte-identical at all consumer locations.

### Secrets handling
Secrets are never embedded in source. Examples live in `*-secrets.example.env` files with placeholder text like `replace-with-platform-gateway-service-client-secret`. Real secrets are provisioned via scripts (`sync-delegation-secrets.sh`, `sync-runtime-secret.sh`) that create Kubernetes `Secret` objects. In dev, `identity-broker/runtime-secrets.env` contains a committed example secret; production deployments should use CI-injected values.

### Feature toggles
Features are activated by setting specific env var combinations documented in the feature activation matrix in `configuration-reference.md`: e.g., `GATEWAY_K8S_ENABLED=true` enables the Kubernetes connector, `OTEL_ENABLED=true` plus `OTEL_EXPORTER_OTLP_ENDPOINT` enables OTel push, `SESSION_STORE_BACKEND=redis` activates Redis-backed sessions.

## Conventions and constraints

- **All runtime configuration comes from environment variables.** No runtime YAML/JSON parsing in application code.
- **Settings are immutable after load.** Dataclasses are `frozen=True`; there is no mutation path.
- **Boolean env vars accept only** `1`, `true`, `yes`, `on` (case-insensitive); any other truthy-looking value is treated as false.
- **Provider selection is enforced:** `AGENTSCOPE_PROVIDER` must be one of `dashscope`, `deepseek`, `openai`; `AGENTSCOPE_PROFILE` must match the provider if both are set.
- **Optional strings return `None` when unset or empty**, not empty strings, via `_optional_str`.
- **Policy files are synchronized, not edited per-service.** The canonical copy is `shared/shared-contracts/policies/policy-default.yaml`; consumers must stay byte-identical.
- **Cross-service secrets must match exactly.** The token delegation chain requires `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` to equal the secret portion of the `platform-gateway` entry in `IDENTITY_SERVICE_CLIENTS`.
- **Profiles are mutually exclusive.** Only one `agent-platform-runtime-profile` ConfigMap may be active at a time, switched via `select-runtime-profile.sh`.
- **Defaults are conservative.** Auth is required by default (`REQUIRE_AUTH=true`), redaction is enabled by default, Elastic/K8s connectors are disabled unless explicitly enabled.