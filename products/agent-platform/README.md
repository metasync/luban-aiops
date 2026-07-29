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
- `src/agent_service/api/v2/` (platform-owned contract adapter)
- `src/agent_service/core/`
- `src/agent_service/entrypoints/` (native AgentScope entrypoints)
- `src/agent_service/schemas/`
- `src/agent_service/services/`
- `src/agent_service/runtime_settings.py`
- `src/agent_service/runtime_kernel.py`
- `src/agent_service/providers/`
- `src/agent_service/agent_app.py`
- `src/agent_service/native_service.py`
- `src/agent_service/metadata.py`
- `tests/`

Current scaffold status:

- uses `uv` packaging with `uv_build`
- includes a container build path for the current service contract
- exposes a single platform-owned HTTP+SSE contract at `/api/v2/` (see `ADR-0003`)
- the AgentScope kernel sits behind an adapter; no framework types leak through the contract boundary
- identity is conveyed via headers (`X-User-ID`, `x-request-id`), never in request bodies
- centralizes AgentScope runtime construction in reusable kernel modules
- isolates provider-specific AgentScope construction behind a registry and adapter modules
- adds a native `AgentScope` runtime service entrypoint via `agent-service-runtime`
- adds a native `AgentScope 2.0` service-factory entrypoint via `agent-service-native`
- routes chat and streaming calls through a provider-configurable AgentScope runtime adapter when credentials are configured
- distinguishes between unconfigured runtime state and provider-call failures in runtime metadata
- enables real runtime replies when `AGENTSCOPE_API_KEY` is supplied to the service environment

Service layout:

- `src/agent_service/app.py`
  - builds the `FastAPI` app and mounts the `/api/v2/` contract router
- `src/agent_service/api/v2/routes.py`
  - the adapter layer: validates requests, delegates to the kernel, shapes responses into contract-conformant models
- `src/agent_service/entrypoints/`
  - holds the native `AgentApp` and native `AgentScope 2.0` entrypoint implementations (for AgentScope-native consumers)
- `src/agent_service/core/`
  - holds shared configuration and request-context helpers
- `src/agent_service/schemas/`
  - `v2.py`: pydantic models bound to the platform-owned contract; `api.py`: internal session models
- `src/agent_service/services/`
  - session store, session service, runtime dependencies
- `src/agent_service/runtime_*.py`, `providers/`, `agent_app.py`, `native_service.py`
  - runtime-focused modules that configure and expose AgentScope-backed execution paths

Entrypoint distinction:

- `src/agent_service/main.py`
  - default entrypoint: runs the platform-owned contract service (`/api/v2/`)
- `src/agent_service/agent_app.py`
  - native `AgentScope` `AgentApp` runtime entrypoint (for AgentScope Studio / runtime consumers)
- `src/agent_service/native_service.py`
  - native `AgentScope 2.0` service built with `create_app` (for AgentScope-native tooling)

Configuration and singleton access:

- `src/agent_service/core/config.py`
  - exposes cached runtime settings through `get_settings()`
- `src/agent_service/services/runtime_dependencies.py`
  - exposes the cached `AgentKernel` singleton through `get_runtime_kernel()`
- `src/agent_service/services/session_store.py`
  - isolates the in-memory session persistence detail from higher-level session and chat orchestration

Local run options:

- `uv run --directory products/agent-platform agent-service`
  - runs the platform-owned contract service on port `8000`
  - accepts `AGENT_SERVICE_HOST` and `AGENT_SERVICE_PORT`
- `uv run --directory products/agent-platform agent-service-runtime`
  - runs the `AgentApp`-based entrypoint (for AgentScope-native consumers)
- `uv run --directory products/agent-platform agent-service-native`
  - runs the native `AgentScope 2.0` service built with `create_app`
  - accepts `AGENT_NATIVE_HOST`, `AGENT_NATIVE_PORT`, `AGENT_NATIVE_TITLE`, and `AGENT_NATIVE_VERSION`
  - expects a reachable `Redis` instance using `AGENTSCOPE_REDIS_HOST`, `AGENTSCOPE_REDIS_PORT`, and related env vars if you override defaults
- `docker build -t luban-aiops/agent-service:dev-local products/agent-platform`
  - builds the container image used by the development Kubernetes overlays
  - defaults to the `agent-service` entrypoint (platform-owned contract)

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
- `SESSION_TTL_SECONDS`
  - idle lifetime for in-memory sessions; defaults to `3600`
- `SESSION_MAX_ENTRIES`
  - maximum concurrent in-memory sessions before oldest-first eviction; defaults to `1000`
- `OTEL_ENABLED`
  - master switch for the OTLP push pipeline (traces + metrics); defaults to `false`; when disabled, the `/metrics` surface is unaffected
- `OTEL_EXPORTER_OTLP_ENDPOINT`
  - OTLP collector URL used when `OTEL_ENABLED=true`
- `OTEL_SERVICE_NAME`
  - logical service name reported to the collector; defaults to the agent-platform's metadata name

Session store limitations:

- sessions are kept in process memory only: state is lost on restart, and the service cannot run with multiple replicas until a shared store lands
- sessions are scoped to the creating user (via `X-User-ID` header); unknown or foreign `session_id` values return `404`
- the native runtime path delegates session state to the AgentScope runtime services instead

Current runtime status surface:

- `/api/v2/runtime`
  - returns provider, resolved model, runtime state, and the last provider error if one exists
- `/api/v2/health`
  - returns runtime mode, runtime state, provider, and whether the runtime is configured
- `/metrics`
  - always-on Prometheus exposition endpoint (auth-exempt), reporting standard HTTP RED metrics plus `agent_sessions_created_total` and `agent_chat_requests_total`; opt-in OTLP push via `opentelemetry-instrumentation-fastapi` + `opentelemetry-exporter-otlp` when `OTEL_ENABLED=true` (fail-open); see `SPEC-005` and `shared/shared-contracts/observability-conventions.md`
- `x-request-id` remains the log/portal correlation key; when OTel tracing is active it equals the W3C `trace_id`

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
