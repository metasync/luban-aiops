# Agentic AIOps Platform Study

This folder contains the working documentation for the proposed enterprise-grade agentic AIOps platform.

Related workspace structure documents live in `docs/workspace/`.

## Recommended Reading Order

Read the documents in this sequence:

1. `part-1-decision-matrix.md`
2. `part-2-reference-architecture.md`
3. `identity-and-authorization-design.md`
4. `authorization-matrix.md`
5. `policy-specification.md`
6. `agent-platform-runtime-options.md`
7. `delivery-roadmap.md`
8. `release-notes/README.md`
9. `../workspace/workspace-model.md`
10. `../workspace/product-boundaries.md`
11. `../workspace/repository-reorganization-plan.md`

## Document Set

- `part-1-decision-matrix.md`
  - Framework comparison and selection rationale
  - Includes the revised scoring model with `API gateway / service exposure readiness`
  - Establishes why `AgentScope 2.0` was selected

- `part-2-reference-architecture.md`
  - Reference architecture for the selected framework
  - Completed and based on `AgentScope 2.0`
  - Defines the platform control plane, execution plane, security boundaries, and service layout

- `identity-and-authorization-design.md`
  - Dedicated design for `SSO`, `Keycloak`, `AD` federation, authorization, approval identity, and audit attribution
  - Defines the enterprise identity and end-to-end attribution model

- `authorization-matrix.md`
  - Concrete role, environment, action, and approval matrix for platform enforcement
  - Translates identity design into explicit access boundaries

- `policy-specification.md`
  - Machine-oriented policy rule model, evaluation flow, and sample policy objects
  - Turns the authorization design into enforceable policy structure

- `agent-platform-runtime-options.md`
  - Decision note comparing a custom `FastAPI` shell with a more native AgentScope runtime service
  - Recommends how `products/agent-platform` should evolve from `Release 0` toward the target architecture

- `delivery-roadmap.md`
  - Stacked delivery roadmap with self-contained releases, value themes, and operator validation checkpoints
  - Shows how capabilities should be introduced one by one

- `release-notes/README.md`
  - Index for milestone-oriented release notes captured during implementation
  - Links the current implementation wave back to the design and checklist documents

- `../workspace/workspace-model.md`
  - Defines the repository as a modular workspace with product-oriented projects and shared modules

- `../workspace/product-boundaries.md`
  - Defines ownership, integration points, and trust boundaries across workspace products

- `../workspace/repository-reorganization-plan.md`
  - Explains how the current study repository should evolve into the modular workspace

## Current Status

- Part 1: finalized and documented
- Part 2: completed and documented
- Identity and authorization design: completed and documented
- Authorization matrix: completed and documented
- Policy specification: completed and documented
- Agent platform runtime options: completed and documented
- Delivery roadmap: completed and documented
- Release notes index: completed and documented
- Workspace model: completed and documented
- Product boundaries: completed and documented
- Repository reorganization plan: completed and documented
- Spec-driven development (SDD): adopted as formal workflow (`docs/specs/`)
- Delivered specs: tracked in the spec index (`docs/specs/README.md`), which is the authoritative status list

## Goal

The goal of this document set is to provide a durable design record for:

- framework selection
- target architecture
- MVP scope and delivery sequencing
- identity and authorization design
- concrete authorization rules and approval boundaries
- machine-enforceable policy structure and evaluation flow
- executable implementation sequencing
- release-by-release delivery and validation planning
- modular workspace structure and project boundaries

## Document Relationships

- `Part 1` selects the framework foundation
- `Part 2` defines the target architecture built on that decision
- `Identity and authorization design` defines enterprise access and attribution requirements that support both the architecture and the MVP
- `Authorization matrix` translates identity and approval design into explicit operational permissions
- `Policy specification` describes how those permissions should be enforced by the platform
- `Agent platform runtime options` clarifies the implementation path for the runtime kernel service
- `Delivery roadmap` shows how releases stack into a practical adoption path
- `Release notes` summarize concrete implementation waves and validation outcomes
- `Workspace model` defines how the platform should be represented as a modular repository workspace
- `Product boundaries` define ownership and interfaces for each workspace project
- `Repository reorganization plan` shows how to evolve from the current study repository into the target workspace
- `docs/specs/` holds the SDD workflow and the authoritative delivered-spec index that replaced the earlier MVP plan, backlog, and Release 0 checklist
