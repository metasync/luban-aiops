# Spec-Driven Development Workflow

## Objective

Define how this workspace manages specifications so that implementation work is always driven by a reviewable, decision-complete spec, and so that documentation cannot silently drift from the code.

This workflow formalizes the discipline already practiced during the platform study and `Release 0`, and makes it repeatable for every future change wave.

## Documentation Tiers

All workspace documentation belongs to exactly one of three tiers, each with a different lifecycle:

### Tier 1: Architecture Record

- long-lived, rarely edited
- examples: `docs/agentic-aiops-platform/part-1-decision-matrix.md`, `part-2-reference-architecture.md`, `identity-and-authorization-design.md`, `docs/workspace/workspace-model.md`
- new architectural decisions are captured as ADRs in `docs/adr/` instead of growing these documents
- edits are limited to corrections and explicit supersession notes

### Tier 2: Feature Specs

- short-lived, written before implementation, frozen after delivery
- live under `docs/specs/SPEC-NNN-<slug>/`
- each spec owns its requirements, technical plan, and task list
- once delivered, a spec is a historical record; follow-up changes require a new spec

### Tier 3: Living State Docs

- must always reflect the current state of the workspace
- examples: root `README.md`, `CHANGELOG.md`, product `README.md` files, GitOps overlay `README.md` files
- kept intentionally minimal so there is less surface that can go stale
- every delivered spec includes a task to update affected living state docs

## When A Spec Is Required

Write a spec before implementation when a change:

- adds or modifies a product capability or service endpoint
- changes a shared contract in `shared/shared-contracts`
- crosses product boundaries or affects the trust model
- changes identity, policy, approval, audit, or execution behavior
- spans more than one focused pull request

A spec is not required for:

- typo and formatting fixes
- dependency bumps without behavior change
- single-file bug fixes with an existing test demonstrating the regression
- documentation-only corrections inside one tier

When in doubt, write the spec. A small spec is cheap; an untracked cross-boundary change is not.

## Spec Structure

Each spec is a directory:

```text
docs/specs/
  SPEC-NNN-<slug>/
    spec.md     # what and why: requirements with acceptance criteria
    plan.md     # how: technical approach, decisions, sequencing
    tasks.md    # execution: tracked task checklist
```

Templates live in `docs/specs/templates/`.

- `spec.md` is written and agreed first
- `plan.md` is written after the spec is approved and before implementation starts
- `tasks.md` is derived from the plan and updated as work proceeds

## Spec Lifecycle

Every `spec.md` carries a status header. Allowed statuses:

- `draft` — under discussion, not yet agreed
- `approved` — agreed scope, implementation may start
- `in-progress` — implementation underway, tasks tracked in `tasks.md`
- `delivered` — all acceptance criteria met and validated; spec is frozen
- `superseded` — replaced by a later spec, which must be linked

Rules:

- requirements in an `approved` spec change only by agreement, recorded in the spec changelog section
- a `delivered` spec is never rewritten; corrections go into the spec changelog section or a new spec
- every implementation pull request links the spec ID it serves

## Numbering And Naming

- specs are numbered sequentially: `SPEC-001`, `SPEC-002`, ...
- slugs are short and kebab-case, for example `SPEC-001-release-1-platform-hardening`
- requirement IDs inside a spec use `R-1`, `R-2`, ... and are stable once the spec is approved
- tasks reference requirement IDs so delivery is traceable from requirement to code

## Relationship To Existing Workflow

- branch naming and commit prefixes follow `CONTRIBUTING.md`; spec work typically uses branches like `feat/spec-001-gateway-auth`
- the design review checklist in `CONTRIBUTING.md` is applied when reviewing `spec.md`, not only the code
- release slices in `delivery-roadmap.md` group specs; a release closes when its specs are `delivered`
- `CHANGELOG.md` entries reference spec IDs for traceability

## Enforcement

Current enforcement is by review discipline:

- pull requests that qualify under `When A Spec Is Required` must link a spec
- reviewers check acceptance criteria before marking a spec `delivered`

Mechanical enforcement:

- `make verify` is the verification gate: it runs every product test suite and renders every GitOps overlay (`kustomize build`). It is forge-agnostic — the same command runs locally before commit/push and under any CI, so the project does not couple to a specific provider's workflow format. (`SPEC-001` first delivered this gate as GitHub Actions workflows; they were replaced by the portable root `Makefile`.)
- contract tests bind gateway models to `shared/shared-contracts` schemas

## Spec Index

| ID | Title | Status |
| --- | --- | --- |
| `SPEC-001` | Release 1 platform hardening | `delivered` |
| `SPEC-002` | Platform-owned agent-service contract | `delivered` |
| `SPEC-003` | Identity trust hardening | `delivered` |
| `SPEC-004` | Deny-by-default policy enforcement | `delivered` |
| `SPEC-005` | Observability baseline — metrics, tracing, and request correlation | `delivered` |
| `SPEC-006` | Session durability — Redis-backed session store | `delivered` |
| `SPEC-007` | Read-only tool execution framework | `delivered` |
| `SPEC-008` | Service-to-service identity — broker-mediated token delegation | `delivered` |
| `SPEC-009` | Pre-production hardening — tool output redaction and workload-identity service tokens | `delivered` |
| `SPEC-010` | Platform gateway extraction — splitting `tool-gateway` into `platform-gateway` and `tool-gateway` | `delivered` |
| `SPEC-011` | Observability connector and evidence panels — Elastic connector, tool trace events, portal evidence panel | `delivered` |
| `SPEC-012` | Operator guide and deployment documentation — getting started, configuration, troubleshooting, tools, architecture | `delivered` |
| `SPEC-013` | Durable audit trail — audit event contract, audit service store, permission-scoped query API | `delivered` |
| `SPEC-014` | Skills and grounded guidance — skills-hub ingestion/retrieval, skills.search tool, cited answers | `delivered` |
| `SPEC-015` | Incident triage and collaboration — incident-service intake/triage, connector framework, portal Incidents experience | `delivered` |
| `SPEC-016` | Session store separation — Postgres session backend for agent-platform, kernel Redis untouched | `delivered` |
| `SPEC-017` | Agent kernel utilization and conversation durability — kernel configs, structured triage output, AgentState persistence to Postgres | `delivered` |
| `SPEC-018` | Kernel middleware alignment — middleware-based tracing/permission hooks, built-in task tools (sequenced after SPEC-017) | `delivered` |
| `SPEC-019` | Portal transparency — permission matrix, workspace resource views, sectioned navigation | `delivered` |
| `SPEC-020` | HITL confirmation bridging — kernel ASK to portal approve/deny, `chat:confirm` action, `confirmation_decided` audit | `delivered` |
| `SPEC-021` | Bounded mutating actions — first approval-gated write tool (`k8s.delete_pod`), `tools:mutate` action, Approval and HITL Governance Guide | `delivered` |
| `SPEC-022` | Multi-session foundations — session lifecycle API with transcripts and parked-confirmation flags, voice-readiness contract, `mutating-dev` deployment profile (portal UI deferred to the rebuild spec) | `delivered` |
| `SPEC-023` | Portal framework rebuild — multi-session workspace UI on Ant Design X behind a platform-owned SSE contract adapter (consumes SPEC-022 Appendix A) | `delivered` |
| `SPEC-024` | Runtime LLM model switching — credential-gated model catalog, per-session selection with affinity, audited choice, portal composer selector | `delivered` |
| `SPEC-025` | Evidence persistence in session transcripts — durable tool-evidence frames with traceability and metrics, replayed evidence cards on reopened sessions | `delivered` |
| `SPEC-026` | Multi-model runtime catalog — curated model series per provider with model-name entry ids, series override, generic profile consolidation (extends SPEC-024) | `delivered` |
| `SPEC-027` | Live model discovery — provider `/models` endpoints feed the catalog with a fail-soft fallback ladder (live -> memory -> Postgres -> curated) and periodic refresh (extends SPEC-026) | `delivered` |
| `SPEC-028` | Luban-hosted small model provider — `luban` adapter for team-hosted OpenAI-compatible servers (Ollama/vLLM/llama.cpp) with token auth, operator hosting guide, and reference K8s manifests (extends SPEC-026/027) | `delivered` |
