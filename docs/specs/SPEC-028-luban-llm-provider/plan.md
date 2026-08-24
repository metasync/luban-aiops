# SPEC-028: Plan

## Approach

Add the `luban` provider as a fourth adapter in the SPEC-024/026/027
machinery — the catalog, selection, pinning, discovery, and audit layers
are provider-generic already, so the code delta is one adapter, one
settings extension, and one credential-resolution rule (mandatory base
URL). The larger half of the spec is operator-facing: the hosting guide,
secrets/config docs, and reference Ollama manifests.

## Design

### R-1: adapter + settings

- `runtime_settings.py`: `RuntimeProvider` gains `"luban"`;
  `SUPPORTED_RUNTIME_PROVIDERS = (..., "luban")`. The options surface
  reuses `OpenAIOptions` (Q-3): `default_provider_options()` and
  `provider_options_type()` already fall through to `OpenAIOptions` for
  non-dashscope/deepseek providers, so cross-provider turns get
  OpenAI-shaped options with `thinking_enable=False` for free (R-4);
  `_provider_options_from_env` gains a `"luban"` branch (same shape,
  `LUBAN_THINKING_ENABLE` opt-in only) for the active-provider path.
- `providers/luban.py` (new): `LubanProvider(AgentScopeProvider)` with
  `provider_name = "luban"`, `default_base_url = None`, `model_series =
  ()`, permissive `discover_filter` (shared dated-snapshot/non-chat
  markers only, no family prefixes). `validate()` requires both api_key
  and base_url (the active-provider path); `build_model()` mirrors the
  OpenAI adapter (`OpenAIChatModel` + `OpenAICredential(api_key,
  base_url)`) — bearer token auth, identical to the public providers
  (R-2).
- `providers/registry.py`: register `"luban"`.
- `services/model_catalog.py::resolve_credentials`: the base URL today
  falls back to `adapter.default_base_url`; for adapters whose default is
  `None` (only `luban`), a missing `<PROVIDER>_BASE_URL` drops the
  provider (with a one-time warning log) instead of resolving a keyless-
  base-URL credential — R-1's mandatory-endpoint rule without touching
  the three existing providers.
- `services/model_discovery.py`: unchanged — the fetch needs a base URL,
  which `luban` now guarantees when gated in; the ladder, filters, and
  metrics are reused as-is (R-3).

### R-3: discovery posture

- Curated series is empty except the force-included default, so with no
  `LUBAN_MODELS` and no reachable `/models` the provider serves exactly
  `LUBAN_MODEL_NAME` (fail-soft bottom of the ladder).
- `LUBAN_MODELS` remains authoritative and skips discovery — the guide
  recommends pinning fixed-point ids (e.g. `qwen3-8b`) so audit
  attribution names the exact served model.

### R-5: operator guide (`docs/guides/luban-llm-guide.md`)

Sections: (1) when to self-host (big-small collaboration split, data
locality, cost) and the sub-~14B tool-calling caveat; (2) choosing a
serving stack — Ollama (CPU-friendly GGUF, simplest ops) vs vLLM (GPU
throughput) vs llama.cpp `llama-server` (single binary); (3) laptop/
desktop setup per stack with token auth (`OLLAMA_API_KEY`,
`vllm serve --api-key`, `llama-server --api-key`) and model pulls
(qwen3-8b class); (4) platform wiring — `LUBAN_API_KEY` /
`LUBAN_BASE_URL` / `LUBAN_MODEL_NAME` / `LUBAN_MODELS` in
`runtime-secrets.env`, `sync-runtime-secret.sh default`, rollout
restart; (5) Kubernetes hosting via the R-6 reference manifests
(in-cluster Service URL as `LUBAN_BASE_URL`); (6) verification checklist
(`/models` probe, `/api/v2/models`, portal selector grouping, audited
turn with `details.model`); (7) troubleshooting (401 bad token,
unreachable endpoint → discovery ladder behavior, model name drift).

Living docs: guides README row; `configuration-reference.md` knob rows
(`LUBAN_API_KEY`/`LUBAN_BASE_URL`/`LUBAN_MODEL_NAME`/`LUBAN_MODELS` +
options knobs); `runtime-secrets.example.env` commented `LUBAN_*` block
with the fixed-point pinning guidance; agent-platform README provider
bullet.

### R-6: reference manifests (`shared/platform-ops/gitops/llm-hosting/`)

Free-standing, docs-only application (Q-4) — NOT referenced by the
dev-k8s kustomization or make gates:

- `README.md`: apply order, sizing notes (CPU-only qwen3-8b-class
  quant: RAM requests ~8Gi, model-weight PVC), GPU-node variant pointer.
- `ollama/`: namespace-free Deployment (official ollama image,
  `OLLAMA_API_KEY` from Secret, weights PVC, readiness probe on
  `/api/version`), Service (cluster port 11434), Secret template,
  PVC for `/root/.ollama`.
- vLLM covered as a notes section in the guide (no manifests this slice).

### R-4: small-model-safe defaults

`LubanProvider.build_model` passes `thinking_enable=False` (and no
reasoning effort) unless the options explicitly enable it; standard
sampling parameters flow from the options. Covered by a unit test that
asserts the constructed parameters.

## Verification

- Unit tests: `luban` catalog gating (key only → dropped with warning;
  key + base URL → entries), mandatory-base-URL rule leaves
  deepseek/dashscope/openai resolution byte-identical, adapter
  `discover_filter` permissiveness (qwen3-8b passes, dated snapshot
  drops), options defaults (thinking off), duplicate-id startup guard
  with a colliding `LUBAN_MODELS` name, discovery ladder against a
  stubbed luban endpoint.
- `make verify` green; overlays render.
- Live (dev-k8s): apply the reference Ollama manifests with a small
  qwen model, wire `LUBAN_*` through `runtime-secrets.env` + sync +
  rollout, then confirm: `/api/v2/models` groups luban models, portal
  selector shows them, a streamed turn on the luban model succeeds with
  audit `details.model` attribution, and discovery metrics report
  `result="live"` for luban.

## Risks

- Dev-cluster CPU throughput is modest — a qwen3-8b-class quant may be
  slow for interactive turns; the guide documents sizing expectations
  and recommends smaller models (1.5B–4B class) for the live demo if
  needed.
- Ollama's OpenAI-compatibility surface is good but not exhaustive
  (e.g. some parameter passthrough quirks); the guide pins tested model
  + server versions.
- Model name drift between Ollama tags and the pinned ids — fixed by
  the `LUBAN_MODELS` pinning posture (R-3).
