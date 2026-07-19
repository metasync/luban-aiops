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

## Expected Integration Points

- `agent-platform` for tool invocation requests
- `execution-runtime` for approved bounded-action adapters
- external systems such as Kubernetes, observability, and ticketing platforms
- `shared/shared-contracts` for tool request and response schemas

## Boundary

This project does not own approval logic, session orchestration, or operator-facing UI flows.
