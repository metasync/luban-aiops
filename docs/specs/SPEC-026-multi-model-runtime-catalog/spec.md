# SPEC-026: Multi-Model Runtime Catalog

## Status

- status: `approved`
- owner: chi
- created: 2026-08-24
- release slice: post-0.9.1 train
- related ADRs: `docs/adr/0002-reaffirm-agentscope-runtime-kernel.md`,
  `docs/adr/0003-platform-owned-agent-service-contract.md`
- extends: `docs/specs/SPEC-024-runtime-llm-model-switching/spec.md`

## Summary

SPEC-024 delivered a credential-gated model catalog where each provider
contributes exactly one entry (id = provider name). SPEC-026 extends the
catalog so each configured provider exposes its full curated model series
(deepseek-chat / deepseek-reasoner / …, qwen-plus / qwen-max / …), each
model selectable per session. Entry identity moves from the provider name
to the model name, and the gitops runtime-profile layout is consolidated
from per-provider directories into a single generic profile, since the
profile no longer identifies "which providers exist".

## Motivation

- Operators hold one API key per provider but want to choose between that
  provider's model lineup (e.g. `qwen-plus` vs `qwen3-max`, chat vs
  reasoner variants). Under SPEC-024 the only way to change a provider's
  model was `<PROVIDER>_MODEL_NAME` + secret re-sync + restart.
- The `runtime-profiles/{deepseek,dashscope,openai}` kustomize overlays
  were named after providers when a profile meant "the one provider we
  run". Since SPEC-024, all providers are configured through the active
  profile's secret — the per-provider directories are now useless and the
  profile concept should carry a generic name.

## Requirements

### R-1: Per-provider model series, credential-gated

Each supported provider adapter ships a curated model series. Whenever a
provider's API key resolves (per-provider key with the SPEC-024
`AGENTSCOPE_*` fallback for the active provider), every model of its
series becomes a selectable catalog entry. A provider without credentials
contributes nothing (fail-closed, unchanged from SPEC-024 R-1).

Acceptance criteria:

- Curated series live in the provider adapters; the active provider's
  resolved default model (`AGENTSCOPE_MODEL_NAME` or the adapter default)
  is always part of its series even if the curated list would omit it.
- The catalog emits one entry per model; the credential gate, startup
  construction, and discovery-safety (no credentials, no base URLs in
  the public shape) are unchanged from SPEC-024.

### R-2: Model-name entry identity

Catalog entries are identified by the model name itself. The chat request
`model` field, session pinning, and audit attribution all carry model
names from here on.

Acceptance criteria:

- Entry `id` equals the model name (`deepseek-chat`, `qwen-plus`); the
  `provider` field still identifies the backing provider (enum unchanged).
- The `default` flag marks the active provider's resolved model; the
  envelope-level `default` is its id.
- Selecting a model that is not in the catalog fails closed with 4xx
  (unchanged from SPEC-024).
- Duplicate model names across providers fail startup with a clear error
  (misconfiguration guard; curated sets are collision-free).

### R-3: Legacy id compatibility

Sessions pinned before SPEC-026 carry provider-name ids (`deepseek`).
They keep working without data migration.

Acceptance criteria:

- A chat request or pinned model using a bare provider name resolves to
  that provider's default catalog entry (alias map).
- Unresolvable legacy ids fall back to the catalog default on session
  resume; unknown model names still fail closed on explicit requests.

### R-4: Series override

`<PROVIDER>_MODELS=a,b,c` restricts or replaces the curated series for
that provider, giving operators control over which of their key's models
are offered.

Acceptance criteria:

- The override is a comma-separated list parsed at startup; empty entries
  are ignored; an override for a provider without credentials is inert.
- The active provider's default model stays force-included (R-1) so the
  deploy-time default is always selectable.

### R-5: Generic profile + gitops consolidation

The runtime profile stops being provider-named: `AGENTSCOPE_PROFILE`
becomes an arbitrary deploy label decoupled from `AGENTSCOPE_PROVIDER`,
and the gitops layout consolidates to a single `default` profile.

Acceptance criteria:

- `RuntimeSettings` accepts any non-empty profile label; the
  `profile == provider` equality check is removed.
- `runtime-profiles/` contains `default/` (configmap + secrets example
  documenting all provider keys and `<PROVIDER>_MODELS` knobs) and
  `mutating-dev/`; the `deepseek/`, `dashscope/`, `openai/` directories
  are deleted.
- `select-runtime-profile.sh`, `sync-runtime-secret.sh`,
  `verify-runtime-profile.sh`, `sync-otel-secrets.sh`, the Makefile
  profile list, and the dev-k8s kustomization all reference the new
  layout; `make verify` renders the overlays cleanly.

## Non-Goals

- Per-user or per-session credentials; keys remain deployment-wide.
- Dynamic model discovery from provider APIs (curated + override only).
- Token-consumption observability (still a follow-up candidate, inherited
  from SPEC-024 non-goals).
- Multi-profile deployments (still exactly one active profile).

## Impact

- products touched: `products/agent-platform` (provider adapters,
  runtime settings, model catalog, kernel resolution),
  `products/operator-portal` (selector grouping by provider)
- contracts touched: `model-catalog.schema.json` (id semantics only;
  shape unchanged), configuration-reference
- gitops touched: `shared/platform-ops/gitops/runtime-profiles/`
  consolidation and all referencing scripts
- living state docs to update on delivery: root `CHANGELOG.md`,
  agent-platform / operator-portal READMEs, configuration-reference

## Open Questions

All resolved in plan review (2026-08-24):

- Q-1 (series source): curated defaults per provider adapter plus
  `<PROVIDER>_MODELS` override → R-1, R-4.
- Q-2 (entry identity): model name as id; legacy provider-name ids alias
  to the provider default → R-2, R-3.
- Q-3 (profile naming): single generic `default` profile;
  `AGENTSCOPE_PROFILE` decoupled from the provider → R-5.

## Changelog

- 2026-08-24: created and approved; extends SPEC-024 which delivered the
  single-entry-per-provider catalog, per-session affinity, and audit
  attribution reused unchanged here.
