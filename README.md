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

- Repository changelog: [CHANGELOG.md](CHANGELOG.md)
- Spec-driven development workflow and spec index: [README.md](docs/specs/README.md)
- Architecture decision records: [README.md](docs/adr/README.md)
- Platform study index: [README.md](docs/agentic-aiops-platform/README.md)
- Release notes index: [README.md](docs/agentic-aiops-platform/release-notes/README.md)
- Workspace docs index: [README.md](docs/workspace/README.md)
- Python container strategy: [python-container-strategy.md](docs/workspace/python-container-strategy.md)
- GitHub governance baseline: [github-repository-governance.md](docs/workspace/github-repository-governance.md)
- Agent platform runtime options: [agent-platform-runtime-options.md](docs/agentic-aiops-platform/agent-platform-runtime-options.md)

## Design Rules

- keep platform boundaries product-oriented, not only technology-oriented
- keep identity, policy, and execution concerns separated
- keep shared modules small and dependency-light
- prefer API and event contracts over direct internal coupling
- expand capabilities release by release with clear validation points

## Python Toolchain

- Python services standardize on `uv` for environment and package management
- the workspace pins the preferred interpreter version with `.python-version`
- Python product directories also carry `.python-version` so product-local container builds can honor the same interpreter target
- the current backend images use the official `uv` Python base for simplicity, but the codebase is now aligned for future CI or runtime images that install `uv` on top of an environment-specific base and let `uv` manage both the interpreter and packages

## Current State

Release 0 (platform foundation) and Release 1 (SPEC-001 through SPEC-006) are delivered: `agent-platform`, `identity-broker`, `tool-gateway`, and `operator-portal` are implemented, tested, and deployable to the `dev-k8s` overlay. SPEC-007 (read-only tool execution) and SPEC-008 (service-to-service identity) remain open.

See [CHANGELOG.md](CHANGELOG.md) for delivered work and the [spec index](docs/specs/README.md) for the status of each spec.

## Routines

Day-to-day routines are driven by the root [Makefile](Makefile): `make verify` (the pre-commit/pre-push gate — all product test suites plus GitOps overlay rendering), `make test`, `make build`, `make lint`, and `make deploy`. Run `make help` for the full list, or `make -C products/<name> help` for per-product targets.
