---
kind: configuration_system
name: Environment-Driven Configuration with Kubernetes ConfigMaps and .env Files
category: configuration_system
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/core/config.py
    - products/agent-platform/src/agent_service/runtime_settings.py
    - products/agent-platform/src/agent_service/core/env.py
    - products/identity-broker/src/identity_service/core/config.py
    - products/tool-gateway/src/api_gateway/core/config.py
    - shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env
    - shared/platform-ops/gitops/dev-k8s/base/shared/observability.env
    - shared/platform-ops/gitops/runtime-profiles/openai/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/dashscope/configmap.yaml
    - shared/platform-ops/gitops/runtime-profiles/deepseek/configmap.yaml
    - shared/platform-ops/gitops/dev-k8s/base/tool-gateway/policy.yaml
    - shared/shared-contracts/policies/policy-default.yaml
---

The Luban AIOps platform uses a consistent, environment-variable-driven configuration system across all Python services, layered on top of Kubernetes deployment assets. Each service defines its own typed settings dataclass with a `from_env()` classmethod that reads from `os.getenv`, wrapped in an `lru_cache(maxsize=1)` singleton accessor (`get_settings()`). This pattern is implemented uniformly in `agent-platform/src/agent_service/core/config.py` (via `RuntimeSettings`), `identity-broker/src/identity_service/core/config.py` (`IdentitySettings`), and `tool-gateway/src/api_gateway/core/config.py` (`GatewaySettings`). The agent-platform also includes shared helpers in `core/env.py` for fallback env lookup (`get_env_value`, `get_env_int`) and robust boolean parsing in `runtime_settings.py` (`_optional_bool`, `_optional_choice`).

Configuration sources are layered as follows:
- **Kubernetes ConfigMaps** under `shared/platform-ops/gitops/runtime-profiles/<provider>/configmap.yaml` inject provider-specific runtime profile variables (`AGENTSCOPE_PROFILE`, `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_BASE_URL`) into the agent-platform pod.
- **Per-service `.env` files** under `shared/platform-ops/gitops/dev-k8s/base/<service>/runtime-config.env` supply service-specific defaults (e.g., Redis hosts, Keycloak endpoints, gateway URLs, policy paths).
- **Shared observability config** via `shared/platform-ops/gitops/dev-k8s/base/shared/observability.env` controls OTel push pipeline opt-in behavior.
- **Policy bundles** are loaded at runtime from YAML files referenced by `GATEWAY_POLICY_PATH` (defaulting to `/etc/luban/policy/policy.yaml`), with a canonical copy maintained in `shared/shared-contracts/policies/policy-default.yaml` and a dev overlay in `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/policy.yaml`.

Each service's `pyproject.toml` declares its dependencies but does not embed configuration; instead, environment variables follow a clear naming convention: `AGENTSCOPE_*` for agent-platform runtime, `KEYCLOAK_*` / `OIDC_*` / `IDENTITY_*` for identity-broker, and `AGENT_SERVICE_URL` / `IDENTITY_SERVICE_URL` / `GATEWAY_*` for tool-gateway. Boolean values accept `1`, `true`, `yes`, `on` (case-insensitive) per the shared parsing helpers. Provider selection is constrained to `dashscope`, `deepseek`, or `openai` via literal types and validated at load time, raising `ValueError` on mismatch between `AGENTSCOPE_PROFILE` and `AGENTSCOPE_PROVIDER`. Secrets (API keys, JWT private key paths) are passed through env vars without file-based loading, keeping the configuration surface uniform across environments.