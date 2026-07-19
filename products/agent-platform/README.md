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
- `src/agent_service/main.py`
- `src/agent_service/runtime_settings.py`
- `src/agent_service/runtime_kernel.py`
- `src/agent_service/agent_app.py`
- `src/agent_service/native_service.py`
- `tests/test_runtime_settings.py`
- `tests/test_runtime_kernel.py`

Current scaffold status:

- uses `uv` packaging with `uv_build`
- keeps the existing outer HTTP adapter in `FastAPI` for current workspace integration
- centralizes AgentScope runtime construction in reusable kernel modules
- adds a native `AgentScope` runtime service entrypoint via `agent-service-runtime`
- adds a native `AgentScope 2.0` service-factory entrypoint via `agent-service-native`
- routes chat and streaming calls through an initial AgentScope runtime adapter when credentials are configured
- falls back to deterministic placeholder responses when AgentScope model credentials are not yet configured

Local run options:

- `uv run --directory products/agent-platform agent-service`
  - runs the transitional `FastAPI` adapter on port `8000`
- `uv run --directory products/agent-platform agent-service-runtime`
  - runs the `AgentApp`-based entrypoint
- `uv run --directory products/agent-platform agent-service-native`
  - runs the native `AgentScope 2.0` service built with `create_app`
  - expects a reachable local `Redis` instance using `AGENTSCOPE_REDIS_HOST`, `AGENTSCOPE_REDIS_PORT`, and related env vars if you override defaults

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
