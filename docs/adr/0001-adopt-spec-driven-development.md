# ADR-0001: Adopt Spec-Driven Development With Tiered Documentation

## Status

`accepted`

- date: 2026-07-28
- deciders: workspace maintainers
- related specs: `SPEC-001`

## Context

The workspace already practices heavy docs-first delivery: a platform study set, an implementation backlog, a release checklist, and milestone release notes. This discipline worked for `Release 0`, but two failure modes appeared:

- documentation drift: living state statements (for example the root `README.md` current-state section and the `tool-gateway` product description) fell behind the implemented code, and drift had to be fixed reactively more than once
- non-executable contracts: JSON Schemas exist in `shared/shared-contracts` but no service consumes or validates against them, so the contracts do not constrain the code

With `Release 1` hardening work starting, the workspace needs a documentation model where specs drive implementation and cannot silently rot.

## Decision

Adopt spec-driven development using plain Markdown in-repo, organized in three documentation tiers with distinct lifecycles:

1. architecture record — long-lived design documents plus ADRs in `docs/adr/` for new decisions
2. feature specs — per-change `spec.md` / `plan.md` / `tasks.md` under `docs/specs/`, written before implementation and frozen after delivery
3. living state docs — minimal always-current documents (`README.md`, `CHANGELOG.md`, product READMEs) updated as a delivery-gate task of every spec

No external SDD tooling is adopted at this stage; the workflow is defined in `docs/specs/README.md` and enforced through review discipline, with CI enforcement planned in `SPEC-001`.

## Alternatives Considered

- adopt an SDD toolchain (spec-kit style) immediately — rejected: the manual Markdown flow matches the existing doc culture; tooling can be revisited if the manual flow proves burdensome
- continue informal docs-first practice — rejected: it already produced doc drift and unenforced contracts
- specs outside the repository (wiki, tracker) — rejected: violates the workspace principle of keeping the design record versioned with the code

## Consequences

- every qualifying change gets a reviewable, decision-complete spec before implementation
- delivered specs become immutable historical records, ending retroactive rewriting of plans
- living state docs shrink to reduce drift surface; updating them becomes a mandatory delivery-gate task
- additional writing overhead per change wave, accepted as the cost of traceability
- follow-up: `SPEC-001` introduces CI and contract tests so enforcement does not rely on review discipline alone
