# Workspace Documentation

This folder contains the documents that define how the platform should be organized as a modular workspace.

## Recommended Reading Order

1. `workspace-model.md`
2. `product-boundaries.md`
3. `product-structure-review.md`
4. `backend-service-layout-convention.md`
5. `python-container-strategy.md`
6. `repository-reorganization-plan.md`
7. `github-repository-governance.md`

## Document Set

- `workspace-model.md`
  - defines the workspace structure, design principles, dependency rules, and module layout

- `product-boundaries.md`
  - defines the responsibility boundaries, integration points, and ownership model for each product project

- `repository-reorganization-plan.md`
  - explains how the current repository and design set map into the new workspace model

- `github-repository-governance.md`
  - defines the baseline GitHub settings, labels, milestones, and review controls for the workspace repository

- `product-structure-review.md`
  - compares the current implementation structure of each workspace product and recommends where normalization should happen next

- `backend-service-layout-convention.md`
  - defines the recommended package structure for backend products that expose HTTP service boundaries

- `python-container-strategy.md`
  - defines the current Python container baseline, evaluates the environment-specific base image option, and records the recommended migration path

## Relationship To The Platform Study

These documents extend the main platform study in `docs/agentic-aiops-platform/` by answering:

- how the platform should be split into products
- how those products should relate to one another
- how the repository should evolve into a modular workspace

## Current Status

- Workspace model: completed and documented
- Product boundaries: completed and documented
- Product structure review: completed and documented
- Backend service layout convention: completed and documented
- Python container strategy: completed and documented
- Repository reorganization plan: completed and documented
- GitHub repository governance: completed and documented
