# Agentic AIOps Workspace

This repository is the workspace for the proposed enterprise-grade agentic AIOps platform.

The workspace is organized as a modular platform made up of multiple product-oriented projects with clear boundaries, explicit integration points, and shared platform contracts.

## Workspace Goals

- keep the platform modular and maintainable
- support independent evolution of major platform capabilities
- preserve clear ownership boundaries
- make integration points explicit
- allow self-contained release slices across the platform

## Top-Level Structure

- `products/`
  - product-oriented projects that deliver core platform capabilities
- `shared/`
  - shared contracts, SDKs, and platform operations assets
- `docs/`
  - architecture, design, delivery, and workspace documents

## Product Projects

- `products/operator-portal`
  - web portal for operators, approvers, and auditors
- `products/agent-platform`
  - agent runtime, orchestration, session handling, and streaming
- `products/policy-center`
  - policy evaluation, approval orchestration, and authorization controls
- `products/identity-broker`
  - `SSO`, identity federation, group normalization, and identity propagation
- `products/skills-hub`
  - Git-based Markdown skill ingestion, validation, indexing, and retrieval support
- `products/tool-gateway`
  - normalized tool and connector access, including `MCP` and external system integration
- `products/execution-runtime`
  - isolated execution workers for bounded operational actions

## Shared Modules

- `shared/shared-contracts`
  - API, event, policy, approval, and domain contracts
- `shared/shared-sdk`
  - shared client libraries, auth helpers, and tracing helpers
- `shared/platform-ops`
  - Kubernetes, gateway, deployment, and environment assets

## Key Documents

- Platform study index: [README.md](docs/agentic-aiops-platform/README.md)
- Workspace docs index: [README.md](docs/workspace/README.md)
- GitHub governance baseline: [github-repository-governance.md](docs/workspace/github-repository-governance.md)
- Release 0 checklist: [release-0-implementation-checklist.md](docs/agentic-aiops-platform/release-0-implementation-checklist.md)
- Agent platform runtime options: [agent-platform-runtime-options.md](docs/agentic-aiops-platform/agent-platform-runtime-options.md)

## Design Rules

- keep platform boundaries product-oriented, not only technology-oriented
- keep identity, policy, and execution concerns separated
- keep shared modules small and dependency-light
- prefer API and event contracts over direct internal coupling
- expand capabilities release by release with clear validation points

## Current State

This workspace currently contains the platform design and planning documents plus the initial modular directory layout.

Implementation can now proceed by release and by product area without losing overall platform coherence.
