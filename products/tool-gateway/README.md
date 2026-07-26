# Tool Gateway

## Purpose

`tool-gateway` is the standardized tool and connector access layer for the platform.

It is responsible for:

- connector normalization
- `MCP` and tool integration
- Kubernetes and observability connectors
- collaboration and ticketing connectors
- stable tool contracts and execution metadata

## Ownership

Recommended owner:

- integrations or platform connectors team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- connector abstraction and normalization
- `MCP`-compatible tool exposure
- read-only and future bounded-action connector pathways
- connector execution metadata and health reporting

Current implementation artifacts:

- `pyproject.toml`
- `Dockerfile`
- `src/api_gateway/app.py`
- `src/api_gateway/api/routes/`
- `src/api_gateway/core/`
- `src/api_gateway/services/`

Current scaffold status:

- proxies the current portal contract to backend services
- defaults to `auto` backend resolution for `agent-service`
- prefers the transitional runtime surface when available and falls back to the native AgentScope service surface when needed
- routes session and chat bridging through backend adapters instead of scattering mode checks across each endpoint
- organizes the FastAPI package by app bootstrap, route modules, shared request/config helpers, and backend orchestration services

## Expected Integration Points

- `agent-platform` for tool invocation requests
- `execution-runtime` for approved bounded-action adapters
- external systems such as Kubernetes, observability, and ticketing platforms
- `shared/shared-contracts` for tool request and response schemas

## Boundary

This project does not own approval logic, session orchestration, or operator-facing UI flows.
