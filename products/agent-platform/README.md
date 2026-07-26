# Agent Platform

## Purpose

`agent-platform` is the runtime and orchestration kernel for the platform.

It is responsible for:

- AgentScope-based orchestration
- session and conversation state
- event streaming
- agent coordination
- interaction with policy, knowledge, and tool services

## Ownership

Recommended owner:

- agent platform or orchestration team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- AgentScope-based runtime services
- session and conversation state handling
- streaming response and event fan-out paths
- orchestration across identity, policy, knowledge, and tool services

Current implementation artifacts:

- `pyproject.toml`
- `Dockerfile`
- `src/agent_service/app.py`
- `src/agent_service/main.py`
- `src/agent_service/api/`
- `src/agent_service/core/`
- `src/agent_service/entrypoints/`
- `src/agent_service/schemas/`
- `src/agent_service/services/`
- `src/agent_service/runtime_settings.py`
- `src/agent_service/runtime_kernel.py`
- `src/agent_service/providers/`
- `src/agent_service/agent_app.py`
- `src/agent_service/native_service.py`
- `src/agent_service/metadata.py`
- `tests/test_app.py`
- `tests/test_runtime_settings.py`
- `tests/test_runtime_kernel.py`
- `tests/test_runtime_providers.py`

Current scaffold status:

- uses `uv` packaging with `uv_build`
- includes a container build path for the current service contract
- keeps the existing outer HTTP adapter in `FastAPI` for current workspace integration
- organizes the transitional adapter by responsibility so route wiring, schemas, request context, and service-layer logic are no longer mixed in a single module
- centralizes AgentScope runtime construction in reusable kernel modules
- isolates provider-specific AgentScope construction behind a registry and adapter modules
- adds a native `AgentScope` runtime service entrypoint via `agent-service-runtime`
- adds a native `AgentScope 2.0` service-factory entrypoint via `agent-service-native`
- routes chat and streaming calls through a provider-configurable AgentScope runtime adapter when credentials are configured
- distinguishes between unconfigured runtime state and provider-call failures in runtime metadata
- enables real runtime replies when `AGENTSCOPE_API_KEY` is supplied to the service environment
- uses app-level provider adapters to choose and configure concrete AgentScope `*ChatModel` implementations, rather than replacing AgentScope's model layer

Current transitional service layout:

- `src/agent_service/app.py`
  - builds the `FastAPI` app and includes the shared router
- `src/agent_service/entrypoints/`
  - holds the concrete runtime entrypoint implementations for transitional, native `AgentApp`, and native `AgentScope 2.0` service modes
- `src/agent_service/api/routes/`
  - defines HTTP endpoints for health, runtime, sessions, and chat
- `src/agent_service/core/`
  - holds shared configuration and request-context helpers
- `src/agent_service/schemas/`
  - defines request and response models for the transitional HTTP contract
- `src/agent_service/services/`
  - contains transitional service-layer logic for runtime metadata, chat orchestration, cached runtime dependencies, and session handling
- `src/agent_service/runtime_*.py`, `providers/`, `agent_app.py`, `native_service.py`
  - remain runtime-focused modules that configure and expose AgentScope-backed execution paths

Entrypoint distinction:

- `src/agent_service/app.py`
  - assembles the transitional `FastAPI` application used by the current workspace HTTP contract
- `src/agent_service/agent_app.py`
  - compatibility wrapper that exposes the native `AgentScope` `AgentApp` runtime entrypoint
- `src/agent_service/native_service.py`
  - compatibility wrapper that exposes the native `AgentScope 2.0` service built with `create_app`
- `src/agent_service/main.py`
  - compatibility wrapper that runs the transitional `FastAPI` app

Configuration and singleton access:

- `src/agent_service/core/config.py`
  - exposes cached runtime settings through `get_settings()`
- `src/agent_service/services/runtime_dependencies.py`
  - exposes the cached `AgentKernel` singleton through `get_runtime_kernel()`
- `src/agent_service/services/session_store.py`
  - isolates the in-memory session persistence detail from higher-level session and chat orchestration

Local run options:

- `uv run --directory products/agent-platform agent-service`
  - runs the transitional `FastAPI` adapter on port `8000`
  - accepts `AGENT_TRANSITIONAL_HOST` and `AGENT_TRANSITIONAL_PORT`
- `uv run --directory products/agent-platform agent-service-runtime`
  - runs the `AgentApp`-based entrypoint
  - emits incremental native AgentScope reply events for text/thinking blocks
  - reuses the same unconfigured/provider-error fallback behavior as the transitional runtime path
- `uv run --directory products/agent-platform agent-service-native`
  - runs the native `AgentScope 2.0` service built with `create_app`
  - accepts `AGENT_NATIVE_HOST`, `AGENT_NATIVE_PORT`, `AGENT_NATIVE_TITLE`, and `AGENT_NATIVE_VERSION`
  - expects a reachable `Redis` instance using `AGENTSCOPE_REDIS_HOST`, `AGENTSCOPE_REDIS_PORT`, and related env vars if you override defaults
  - the default development Kubernetes transitional overlay provisions this dependency at `shared/platform-ops/gitops/dev-k8s-transitional`
- `docker build -t luban-aiops/agent-service:dev-local products/agent-platform`
  - builds the container image used by the development Kubernetes overlays
  - defaults to the transitional `agent-service` entrypoint so the current gateway contract remains runnable

Current runtime environment knobs:

- `AGENTSCOPE_PROVIDER`
  - selects the provider-specific AgentScope chat model
  - current supported values: `dashscope`, `deepseek`, `openai`
- `AGENTSCOPE_PROFILE`
  - optional deployment-level selector for the active runtime profile
  - when set, it must match `AGENTSCOPE_PROVIDER`
- `AGENTSCOPE_API_KEY`
  - required to move provider-backed chat/runtime paths out of unconfigured placeholder behavior
- `AGENTSCOPE_MODEL_NAME`
  - optional provider-specific model override; when omitted, the selected provider supplies its default model
- `AGENTSCOPE_BASE_URL`
  - optional override for provider endpoints
- `AGENTSCOPE_ORGANIZATION`
  - optional organization identifier for `openai`
- `AGENTSCOPE_MAX_TOKENS`, `AGENTSCOPE_TEMPERATURE`, `AGENTSCOPE_TOP_P`
  - common provider-agnostic inference controls
- `AGENTSCOPE_AGENT_NAME`
  - defaults to `LubanOpsRuntime`
- `AGENTSCOPE_SYSTEM_PROMPT`
  - defaults to the current runtime grounding prompt
- `DASHSCOPE_THINKING_ENABLE`, `DASHSCOPE_THINKING_BUDGET`, `DASHSCOPE_TOP_K`, `DASHSCOPE_PARALLEL_TOOL_CALLS`
  - DashScope-specific runtime options
- `DEEPSEEK_THINKING_ENABLE`, `DEEPSEEK_REASONING_EFFORT`
  - DeepSeek-specific runtime options
- `OPENAI_THINKING_ENABLE`, `OPENAI_REASONING_EFFORT`, `OPENAI_PARALLEL_TOOL_CALLS`
  - OpenAI-compatible runtime options

Current runtime status surface:

- `/api/v1/runtime`
  - returns provider, resolved model, resolved base URL, provider options, runtime state, and the last provider error if one exists
- `/health/ready`
  - returns runtime mode, runtime state, provider, and whether the runtime is configured

Testing note:

- keep adding focused tests as the runtime surface grows
- the current package includes a lightweight `pytest`-based starting point for runtime configuration and placeholder behavior

## Expected Integration Points

- `identity-broker` for normalized identity context
- `policy-center` for action and approval decisions
- `skills-hub` for knowledge retrieval inputs
- `tool-gateway` for grounded tool access
- `shared/shared-contracts` and `shared/shared-sdk` for shared interfaces

## Boundary

This project may propose actions and request policy decisions, but it does not directly authorize or execute privileged operations.
