# Luban-Hosted Small Model Guide

How to stand up a team-hosted (local or on-prem) small LLM and wire it
into the platform as the `luban` provider (SPEC-028). Covers serving-stack
selection, token-authenticated setup on a laptop/desktop or server,
platform wiring, optional Kubernetes hosting, verification, and
troubleshooting.

## 1. When to self-host

The platform runs a multi-model catalog: cloud flagships (DashScope,
DeepSeek, OpenAI) plus — with this guide — a team-hosted server. Common
reasons to self-host:

- **Data locality**: prompts and tool evidence never leave infrastructure
  the team controls.
- **Cost**: small models on existing hardware for high-volume, low-stakes
  turns.
- **The big-small collaboration split**: a small edge model for
  pre-triage, summarization, and redaction turns near the data; a cloud
  flagship for deep reasoning and tool-heavy agent turns.

**Known limitation — tool calling.** Sub-~14B models are weak at tool
calling. Use a self-hosted small model for advisory/chat turns and keep
tool-heavy triage turns on a cloud flagship. Policy and HITL gating are
model-agnostic; nothing stops you selecting a luban model for any turn,
but expect degraded tool reliability on small models.

## 2. Choosing a serving stack

Any server exposing the OpenAI-compatible `/v1/models` +
`/v1/chat/completions` surface works. Three common choices:

| Stack | Best for | Model format | Token auth |
|---|---|---|---|
| **Ollama** | CPU-only or mixed hardware, simplest ops | GGUF quants | `OLLAMA_API_KEY` env var |
| **vLLM** | GPU nodes, high throughput | safetensors / AWQ | `vllm serve --api-key` |
| **llama.cpp `llama-server`** | Single binary, minimal footprint | GGUF | `llama-server --api-key` |

This guide uses Ollama as the primary reference (CPU-friendly GGUF
quants, simplest ops, native bearer-token auth). vLLM notes for GPU
nodes appear inline where they differ.

Model-size guidance: for interactive turns on modest CPU hardware, prefer
the 1.5B–4B class; a qwen3-8b-class quant works but is slow without GPU.

## 3. Server setup with token auth

### 3.1 Ollama

```sh
# Install (macOS/Linux), then enable bearer-token auth and start serving.
export OLLAMA_API_KEY="$(openssl rand -hex 32)"   # generate once, store safely
export OLLAMA_HOST=0.0.0.0:11434                  # reachable from the platform
ollama serve &

# Pull a small model (qwen3-8b class; substitute a smaller tag on CPU-only).
ollama pull qwen3:8b
```

> Ollama enforces `OLLAMA_API_KEY` on every API request once the
> variable is set on the server process — unauthenticated callers get
> 401. The platform never calls an unauthenticated endpoint.

### 3.2 vLLM (GPU nodes)

```sh
vllm serve Qwen/Qwen3-8B \
  --api-key "$(openssl rand -hex 32)" \
  --host 0.0.0.0 --port 8000
```

### 3.3 llama.cpp

```sh
llama-server -m qwen3-8b-q4_k_m.gguf \
  --api-key "$(openssl rand -hex 32)" \
  --host 0.0.0.0 --port 8080
```

### 3.4 Reachability

`agent-service` must reach the server over HTTP:

- **Laptop/LAN node**: confirm the platform pod/namespace can route to
  the node's IP and port (firewall rules permitting). Use a stable DNS
  name or IP — the value lands in `LUBAN_BASE_URL`.
- **In-cluster hosting**: use the Kubernetes Service DNS (see §5); this
  is the most reliable topology and the one the reference manifests
  target.

Probe before wiring the platform:

```sh
curl -sS -H "Authorization: Bearer $OLLAMA_API_KEY" \
  http://<host>:11434/v1/models
```

Expected: a JSON envelope with `data[].id` listing the pulled models.

## 4. Platform wiring

Add the `LUBAN_*` knobs to the agent-platform runtime secret:

```sh
# shared/platform-ops/gitops/runtime-profiles/default/runtime-secrets.env
LUBAN_API_KEY=<same token the server enforces>
LUBAN_BASE_URL=http://ollama.llm-hosting.svc:11434/v1   # in-cluster example
LUBAN_MODEL_NAME=qwen3:8b                               # provider default model
LUBAN_MODELS=qwen3:8b,qwen3:1.7b                        # recommended pinning
```

Semantics:

- `LUBAN_API_KEY` is the credential gate — no key, no `luban` entries.
- `LUBAN_BASE_URL` is **mandatory**: an API key without a base URL gates
  the provider out (self-hosted endpoints have no default endpoint).
- `LUBAN_MODEL_NAME` sets the provider default model.
- `LUBAN_MODELS` (recommended): fixed-point pinning, authoritative over
  live discovery — the catalog serves exactly this list. Pin the concrete
  served model ids so audit attribution (`details.model`) names the exact
  model. Without it, live discovery populates the lineup from `/models`
  (fail-soft: unreachable endpoint degrades to `LUBAN_MODEL_NAME` only).
- Optional: `LUBAN_THINKING_ENABLE=true` opts a thinking-capable model
  into thinking mode; the default is off (small-model-safe).

Then sync the secret and restart the service:

```sh
shared/platform-ops/gitops/sync-runtime-secret.sh default
kubectl -n dev-luban-aiops rollout restart deployment/agent-service
kubectl -n dev-luban-aiops rollout status deployment/agent-service
```

**Token rotation**: generate a new token, update it on the server and in
`runtime-secrets.env`, re-run the sync + rollout above. Both sides must
carry the new token before the rollout completes; expect 401s on luban
turns in between (other providers are unaffected).

## 5. Kubernetes hosting (opt-in)

Reference manifests for an in-cluster Ollama server ship under
[`shared/platform-ops/gitops/llm-hosting/`](../../shared/platform-ops/gitops/llm-hosting/README.md).
They are **free-standing** — not part of the `dev-k8s` overlay or
`make deploy`; applying them is an explicit operator choice.

```sh
kubectl apply -f shared/platform-ops/gitops/llm-hosting/ollama/
# Pull a model into the PVC-backed inventory:
kubectl -n llm-hosting exec deploy/ollama -- ollama pull qwen3:8b
```

Then point the platform at the in-cluster Service:

```sh
LUBAN_BASE_URL=http://ollama.llm-hosting.svc:11434/v1
```

See the `llm-hosting` README for sizing notes (RAM requests for CPU-only
qwen3-8b-class quants, model-weight PVC) and the GPU-node variant.

## 6. Verification checklist

1. **Endpoint probe**: `curl -H "Authorization: Bearer $LUBAN_API_KEY"
   $LUBAN_BASE_URL/models` returns the expected model ids.
2. **Catalog**: `GET /api/v2/models` (agent-service, via platform-gateway)
   lists the luban models with `"provider": "luban"`.
3. **Portal**: the model selector groups the luban models; select one.
4. **Audited turn**: run a chat turn on the luban model; the audit trail
   shows `details.model` equal to the concrete served model id.
5. **Discovery metrics** (when not pinned via `LUBAN_MODELS`): the model
   discovery metric reports `provider="luban"` with `result="live"`.

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 on luban turns | Token mismatch (rotation half-done, or server has `OLLAMA_API_KEY` unset while the platform sends one) | Align the token on both sides; confirm the server enforces auth with a keyless `curl` (should 401) |
| No `luban` models in `/api/v2/models` | Missing `LUBAN_API_KEY` or `LUBAN_BASE_URL` in the synced secret | Both are required; check agent-service logs for the `LUBAN_BASE_URL is required` gate warning, then re-sync + rollout |
| Endpoint unreachable, lineup shrank to the default model | Discovery ladder fail-soft: live fetch failed, fell back to memory/Postgres/curated | Fix routing/DNS for `LUBAN_BASE_URL`; the catalog recovers on the next refresh (default 30 min) or pod restart |
| Model id selected but turns 404 | Name drift between the pinned id and the server's actual model name (e.g. `qwen3-8b` vs `qwen3:8b`) | Align `LUBAN_MODELS`/`LUBAN_MODEL_NAME` with the ids returned by `/models` |
| Tool calls fail or loop on the luban model | Sub-~14B tool-calling weakness | Switch tool-heavy turns to a cloud flagship; keep the small model for chat/summarization |
| Thinking-mode flag rejected (4xx) | Server/model lacks a thinking mode | Leave `LUBAN_THINKING_ENABLE` unset (defaults off) |

## Related

- [Configuration Reference](configuration-reference.md) — `LUBAN_*` knob
  rows and the provider catalog model
- [Troubleshooting](troubleshooting.md) — platform-wide diagnostics
- [llm-hosting manifests](../../shared/platform-ops/gitops/llm-hosting/README.md) —
  Ollama reference Deployment/Service/Secret/PVC
