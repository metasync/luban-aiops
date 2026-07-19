# Agentic AIOps Platform Study

This folder contains the working documentation for the proposed enterprise-grade agentic AIOps platform.

Related workspace structure documents live in `docs/workspace/`.

## Recommended Reading Order

Read the documents in this sequence:

1. `part-1-decision-matrix.md`
2. `part-2-reference-architecture.md`
3. `part-3-mvp-plan.md`
4. `identity-and-authorization-design.md`
5. `authorization-matrix.md`
6. `policy-specification.md`
7. `implementation-backlog.md`
8. `release-0-implementation-checklist.md`
9. `delivery-roadmap.md`
10. `../workspace/workspace-model.md`
11. `../workspace/product-boundaries.md`
12. `../workspace/repository-reorganization-plan.md`

## Document Set

- `part-1-decision-matrix.md`
  - Framework comparison and selection rationale
  - Includes the revised scoring model with `API gateway / service exposure readiness`
  - Establishes why `AgentScope 2.0` was selected

- `part-2-reference-architecture.md`
  - Reference architecture for the selected framework
  - Completed and based on `AgentScope 2.0`
  - Defines the platform control plane, execution plane, security boundaries, and service layout

- `part-3-mvp-plan.md`
  - MVP scope, phases, and delivery plan
  - Completed and aligned with the reference architecture
  - Narrows the architecture into a safe and realistic first release

- `identity-and-authorization-design.md`
  - Dedicated design for `SSO`, `Keycloak`, `AD` federation, authorization, approval identity, and audit attribution
  - Defines the enterprise identity and end-to-end attribution model

- `authorization-matrix.md`
  - Concrete role, environment, action, and approval matrix for platform enforcement
  - Translates identity design into explicit access boundaries

- `policy-specification.md`
  - Machine-oriented policy rule model, evaluation flow, and sample policy objects
  - Turns the authorization design into enforceable policy structure

- `implementation-backlog.md`
  - Release-oriented implementation backlog with self-contained epics, integration points, and validation scenarios
  - Translates the design set into executable platform work

- `release-0-implementation-checklist.md`
  - Execution-oriented checklist for the first platform foundation release
  - Maps `Release 0` work into workspace products, shared modules, and validation gates

- `delivery-roadmap.md`
  - Stacked delivery roadmap with self-contained releases, value themes, and operator validation checkpoints
  - Shows how capabilities should be introduced one by one

- `../workspace/workspace-model.md`
  - Defines the repository as a modular workspace with product-oriented projects and shared modules

- `../workspace/product-boundaries.md`
  - Defines ownership, integration points, and trust boundaries across workspace products

- `../workspace/repository-reorganization-plan.md`
  - Explains how the current study repository should evolve into the modular workspace

## Current Status

- Part 1: finalized and documented
- Part 2: completed and documented
- Part 3: completed and documented
- Identity and authorization design: completed and documented
- Authorization matrix: completed and documented
- Policy specification: completed and documented
- Implementation backlog: completed and documented
- Release 0 implementation checklist: completed and documented
- Delivery roadmap: completed and documented
- Workspace model: completed and documented
- Product boundaries: completed and documented
- Repository reorganization plan: completed and documented

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
- `Part 3` defines the first release shape derived from the architecture
- `Identity and authorization design` defines enterprise access and attribution requirements that support both the architecture and the MVP
- `Authorization matrix` translates identity and approval design into explicit operational permissions
- `Policy specification` describes how those permissions should be enforced by the platform
- `Implementation backlog` translates the design set into buildable work grouped by self-contained releases
- `Release 0 implementation checklist` turns the first release into a product-mapped execution guide
- `Delivery roadmap` shows how those releases stack into a practical adoption path
- `Workspace model` defines how the platform should be represented as a modular repository workspace
- `Product boundaries` define ownership and interfaces for each workspace project
- `Repository reorganization plan` shows how to evolve from the current study repository into the target workspace

This keeps the platform study versioned inside the project repository for future reference and iteration.
