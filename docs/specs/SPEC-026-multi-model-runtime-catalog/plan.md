# SPEC-026: Plan

## Approach

Extend the SPEC-024 catalog along its existing seams: provider adapters
gain a curated `model_series`, the catalog emits one entry per model
(id = model name), the kernel resolves model names through the same
`MODEL_CATALOG` chokepoint with a legacy provider-name alias map, and the
gitops profiles consolidate to one generic `default` profile.

## Decisions

- D-1: Curated series live on the provider adapters
  (`AgentScopeProvider.model_series`); `<PROVIDER>_MODELS` env replaces
  the curated list when set. The active provider's resolved default model
  is force-included so the deploy-time default is always selectable.
- D-2: Entry identity is the model name. Model names in the curated sets
  are globally unique across providers; a duplicate-id startup guard
  fails fast on misconfiguration.
- D-3: Legacy ids (bare provider names, pinned by pre-SPEC-026 sessions
  and requests) alias to that provider's default entry. Unresolvable
  legacy ids fall back to the catalog default on session resume; unknown
  model names on explicit requests still fail closed with 4xx.
- D-4: `AGENTSCOPE_PROFILE` becomes a free-form deploy label; the
  `profile == provider` equality check is dropped (profile must remain a
  non-empty string when set).
- D-5: GitOps consolidates `runtime-profiles/{deepseek,dashscope,openai}`
  into `runtime-profiles/default` (configmap keeps
  `AGENTSCOPE_PROVIDER=deepseek` for dev-k8s); `mutating-dev` untouched.
  Local untracked `runtime-secrets.env` migrates directory with its
  content preserved.

## Sequencing

1. agent-platform: adapter series, settings (profile decoupling,
   `<PROVIDER>_MODELS`), catalog rework, kernel alias resolution,
   unit tests.
2. shared-contracts: `model-catalog.schema.json` id description update.
3. operator-portal: `ModelSelect` provider grouping + test updates.
4. gitops: `default` profile, script/Makefile/kustomization reference
   updates, housekeeping deletions, secret-file migration.
5. Living docs: CHANGELOG, product READMEs, configuration-reference.
6. Verification: `make verify`, commit, build, deploy, live catalog +
   per-model chat turns + audit attribution, L3 gate, push.

## Risks

- Pinned sessions storing provider-name ids: mitigated by D-3 alias map,
  verified by kernel tests.
- Curated series drift vs provider lineups: `<PROVIDER>_MODELS` override
  is the operator escape hatch.
