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

## Spec-Driven Development

This workspace follows the spec-driven workflow defined in `docs/specs/README.md`:

- qualifying changes (new capabilities, contract changes, cross-boundary or trust-model changes) require a spec under `docs/specs/` before implementation
- architecturally significant decisions are recorded as ADRs under `docs/adr/`
- implementation pull requests link the spec ID they serve
- delivered specs are frozen; follow-up changes get a new spec

## Versioning

The platform follows semantic versioning (MAJOR.MINOR.PATCH). The root
`VERSION` file is the single source of truth:

- MAJOR — breaking cross-service contract or API changes
- MINOR — release trains (each delivered release slice bumps the minor)
- PATCH — fixes between releases

Products version in **lockstep** with the platform: every
`products/*/pyproject.toml`, every `metadata.py` `SERVICE_VERSION`, and the
portal's `PLATFORM_VERSION` must equal `VERSION`. Product versions express
"which platform release this build belongs to", not independent change
histories — products ship together under one coordinated image tag and share
one changelog. A product may opt out of lockstep only when it becomes
independently consumable.

`make validate-version` (part of `make verify`) enforces the lockstep, and
the coordinated image tag is prefixed with the semver
(`<semver>-<prefix>-<gitsha>[-dirty-<timestamp>]`).

Release workflow: entries accumulate under `Unreleased` in `CHANGELOG.md`;
closing a release bumps `VERSION` everywhere (run `make validate-version`
to catch misses), moves the entries into a versioned section, and tags the
release.

## Change Principles

- keep identity, policy, orchestration, and execution concerns separated
- prefer explicit APIs and contracts over hidden cross-project coupling
- keep risky operational behavior behind approval and audit boundaries
- update documentation when product boundaries or release sequencing changes

## Pull Requests

Before opening a pull request:

1. align the change to a workspace product or shared module
2. link the spec the change implements, or state why no spec is required per `docs/specs/README.md`
3. describe the release or roadmap slice the change supports
4. call out any impact on identity, policy, approvals, audit, or execution safety
5. update related documentation and examples
6. run the relevant local validation for the files you changed

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
