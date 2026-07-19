# Contributing

## Purpose

This repository is organized as a workspace for an enterprise-grade agentic AIOps platform.

Contributions should preserve:

- product-oriented boundaries
- explicit trust and control boundaries
- traceable, reviewable changes
- release-by-release delivery discipline

## Workspace Structure

Work in the directory that owns the capability you are changing:

- `products/` for user-facing and service-facing product capabilities
- `shared/` for low-level shared contracts, SDKs, and platform operations assets
- `docs/` for platform design, delivery plans, and workspace guidance

Do not move logic into `shared/` unless it is genuinely reusable and dependency-light.

## Change Principles

- keep identity, policy, orchestration, and execution concerns separated
- prefer explicit APIs and contracts over hidden cross-project coupling
- keep risky operational behavior behind approval and audit boundaries
- update documentation when product boundaries or release sequencing changes

## Pull Requests

Before opening a pull request:

1. align the change to a workspace product or shared module
2. describe the release or roadmap slice the change supports
3. call out any impact on identity, policy, approvals, audit, or execution safety
4. update related documentation and examples
5. run the relevant local validation for the files you changed

## Recommended Branch Naming

Use descriptive branch names, for example:

- `docs/release-0-foundation`
- `feat/operator-portal-shell`
- `feat/policy-center-evaluator`
- `chore/repo-governance`

## Commit Guidance

Prefer small, reviewable commits with clear scope. Example prefixes:

- `docs:`
- `feat:`
- `fix:`
- `chore:`
- `refactor:`

## Design Review Checklist

Use this checklist when a change crosses product boundaries:

- does the change stay within the owning product boundary?
- are new contracts explicit and documented?
- does the change preserve the three-zone trust model?
- is user identity preserved for approvals, execution, and audit?
- is the change aligned to a named release slice?
