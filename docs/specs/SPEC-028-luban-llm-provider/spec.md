# SPEC-028: Luban-Hosted Small Model Provider and Hosting Guide

## Status

- status: `approved`
- owner: chi
- created: 2026-08-24
- release slice: post-0.10.0 train
- related ADRs: `docs/adr/0002-reaffirm-agentscope-runtime-kernel.md`,
  `docs/adr/0003-platform-owned-agent-service-contract.md`
- extends: `docs/specs/SPEC-026-multi-model-runtime-catalog/spec.md` and
  `docs/specs/SPEC-027-live-model-discovery/spec.md`

## Summary

The platform's model catalog (SPEC-024/026/027) is provider-generic by
construction — a provider is just `base_url + API key + model list` — but
only three public clouds are wired as adapters. SPEC-028 adds a fourth
`luban` provider for team-hosted OpenAI-compatible endpoints (Ollama,
vLLM, llama.cpp `llama-server`) and ships the operator documentation to
stand one up: token-authenticated serving, laptop/on-prem setup, and
reference Kubernetes manifests for hosting a small model inside the
cluster. This is the foundation for the big-small LLM collaboration
pattern (small edge model for pre-triage/redaction near the data, cloud
flagship for deep reasoning and tool-heavy agent turns).

## Motivation

- The SPEC-026/027 catalog mechanics (credential gating, `<PROVIDER>_MODELS`
  override, live `/models` discovery with the fail-soft ladder, per-turn
  selection, session pinning, audit attribution) all apply unchanged to a
  self-hosted server — only an adapter and operator-facing wiring docs are
  missing. The provider is named `luban` — team-owned infrastructure —
  while model ids keep naming the concrete served model (fixed-point
  pinning discipline), so audit attribution stays exact.
- The DashScope key's 403 on small models (walkthrough finding, 2026-08-24)
  showed the practical gap: small models for the edge/collaboration lab
  must come from somewhere the team controls. Open-weight models
  (qwen3-8b class and below) served on team hardware fill it, with data
  locality as a bonus.
- Operators need a repeatable, documented path — serving stack choice,
  token auth, platform wiring, verification — rather than tribal
  knowledge; and the team wants the option to host the model in the same
  Kubernetes cluster as the platform.

## Requirements

### R-1: `luban` runtime provider adapter

A fourth provider adapter (`luban`) joins the catalog through the existing
SPEC-024/026 machinery — no new selection, pinning, audit, or discovery
code paths.

Acceptance criteria:

- `RuntimeProvider` gains `"luban"`; env knobs follow the established
  pattern: `LUBAN_API_KEY` (credential gate), `LUBAN_BASE_URL`,
  `LUBAN_MODEL_NAME` (provider default), `LUBAN_MODELS` (series override,
  authoritative over discovery per SPEC-027).
- `LUBAN_BASE_URL` is mandatory when `LUBAN_API_KEY` is set (there is no
  sensible default endpoint for self-hosted servers); the provider is
  dropped from the catalog when either is missing, exactly like the other
  credential gates.
- The adapter builds an OpenAI-compatible AgentScope model
  (`OpenAIChatModel` + bearer credential) against the configured base URL;
  per-turn selection, session pinning, `/api/v2/models` discovery, portal
  grouping, and audit `details.model` attribution work for `luban` models
  with zero new code paths.

### R-2: Token-based authentication (fail-closed)

Local/on-prem endpoints authenticate with a bearer API key exactly like
public providers; the platform never calls an unauthenticated endpoint.

Acceptance criteria:

- The credential gate is unchanged: no `LUBAN_API_KEY` → no `luban`
  entries, no `/models` fetch. An empty-key escape hatch is explicitly
  out of scope.
- The operator guide documents how to enable token auth on each supported
  serving stack (Ollama `OLLAMA_API_KEY`, vLLM `--api-key`,
  llama.cpp `llama-server --api-key`) and how to rotate it (edit
  `runtime-secrets.env`, re-sync, rollout restart).

### R-3: Discovery posture for self-hosted servers

Live discovery (SPEC-027) works against self-hosted `/models` endpoints
with a permissive filter, and `LUBAN_MODELS` pinning stays the
recommended posture for fixed-point operation.

Acceptance criteria:

- The `luban` adapter applies the shared dated-snapshot/non-chat marker
  hygiene with no family-prefix restriction (self-hosted model names have
  no vendor taxonomy); the fallback ladder (live → memory → Postgres →
  curated) is reused unchanged, so an offline node never empties the
  catalog.
- The curated series for `luban` is empty except the force-included
  default model: with neither `LUBAN_MODELS` nor a reachable `/models`,
  the provider still serves exactly `LUBAN_MODEL_NAME`.
- The guide recommends `LUBAN_MODELS` pinning (fixed-point ids) so audit
  attribution names the exact served model, mirroring the DashScope
  pinning decision.

### R-4: Small-model-safe runtime defaults

The adapter's default generation parameters suit small models, which are
the realistic `luban` lineup.

Acceptance criteria:

- Thinking/reasoning toggles default off for the `luban` provider
  (self-hosted small models generally lack a thinking mode; sending the
  flag must not 4xx the turn); standard sampling parameters
  (temperature/top_p/max_tokens) stay configurable.
- The guide documents the known limitation that sub-~14B models are weak
  at tool calling, and recommends small models for pre-triage/
  summarization/redaction turns and cloud flagships for tool-heavy agent
  turns (the big-small collaboration split).

### R-5: Operator hosting guide

A new operator guide `docs/guides/luban-llm-guide.md` is the single
operator-facing document for standing up a luban-hosted model.

Acceptance criteria:

- Covers: serving-stack selection (Ollama vs vLLM vs llama.cpp
  `llama-server` — trade-offs for CPU-only vs GPU, model formats
  GGUF/AWQ/safetensors); laptop/desktop setup; token-auth enablement per
  stack; network reachability from agent-service (cluster → LAN node);
  platform wiring (`LUBAN_*` knobs in `runtime-secrets.env` + sync +
  rollout); verification checklist (models endpoint, portal selector,
  audited turn); model-pinning guidance (R-3).
- Registered in `docs/guides/README.md`; `configuration-reference.md`
  gains the `LUBAN_*` knob rows; `runtime-secrets.example.env` gains a
  commented `LUBAN_*` block.

### R-6: Kubernetes hosting option

Reference manifests let the team host a small model server inside the
platform's own Kubernetes cluster, documented as opt-in.

Acceptance criteria:

- Reference manifests ship under `shared/platform-ops/gitops/llm-hosting/`
  (Deployment + Service + Secret for the API key, with storage/PVC notes
  for model weights) for the Ollama stack (primary reference; vLLM
  covered as notes for GPU nodes); sizing notes cover CPU-only deployment
  of a qwen3-8b-class model.
- The manifests are NOT part of the default `dev-k8s` overlay or
  `make deploy` — hosting a model server is an explicit operator choice;
  the guide documents applying them and pointing `LUBAN_BASE_URL` at the
  in-cluster Service.

## Non-Goals

- Multiple `luban` endpoints in one deployment (one `LUBAN_*` set per
  deploy; a future spec can generalize to `LUBAN2_*` or list syntax).
- Model lifecycle management (download/caching/quantization pipelines,
  autoscaling, GPU device plugins) — the manifests are a reference
  starting point, not an MLOps platform.
- Auto-allowing `luban` models for mutating/tool-heavy turns — policy and
  HITL gating are model-agnostic and unchanged.
- Making a `luban` model the `AGENTSCOPE_PROVIDER` deploy-time default is
  allowed by construction but not documented as a recommended posture in
  this slice (cloud flagship stays the default).

## Impact

- products touched: `products/agent-platform` (settings provider list,
  new `providers/luban.py` adapter, options defaults, tests); docs:
  new `docs/guides/luban-llm-guide.md`, guides README,
  configuration-reference, runtime-secrets example, agent-platform README,
  CHANGELOG
- contracts touched: none (catalog envelope and stream schema unchanged)
- identity / policy / audit / execution safety impact: none — `luban`
  models ride existing policy/HITL/audit surfaces; credentials stay in
  the runtime secret
- living state docs to update on delivery: root/product READMEs,
  configuration-reference, guides README, delivery-roadmap, spec index

## Open Questions

All resolved in spec review (2026-08-24):

- Q-1 (provider id): `luban` with `LUBAN_*` env prefix — team-owned
  infrastructure naming chosen by the owner; model ids keep naming the
  concrete served model so audit attribution stays exact -> R-1, R-3.
- Q-2 (reference stack for K8s manifests): Ollama as the primary
  reference (CPU-friendly GGUF quants, simplest ops, native
  `OLLAMA_API_KEY` auth), vLLM covered as notes for GPU nodes -> R-6.
- Q-3 (options surface): reuse the OpenAI-style options shape; the
  adapter defaults thinking off -> R-4.
- Q-4 (manifest placement): free-standing `llm-hosting/` directory with
  docs-only application; not wired into the make gates -> R-6.

## Changelog

- 2026-08-24: created as `draft`; extends the SPEC-026/027 catalog and
  discovery mechanics, motivated by the big-small LLM collaboration
  direction and the DashScope small-model 403 walkthrough finding.
- 2026-08-24: approved — provider id resolved to `luban` (`LUBAN_*`
  knobs); Ollama chosen as the primary K8s reference stack; OpenAI-shaped
  options reused; manifests stay free-standing.
