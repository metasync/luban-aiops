# Runtime Profiles

This directory contains provider-specific runtime profile overlays for `agent-service`.

Each profile contributes:

- a committed non-secret `ConfigMap` named `agent-platform-runtime-profile`
- an ignored local fallback secret file path `runtime-secrets.env`
- an example secret file template `runtime-secrets.example.env`

Luban CI or another deployment pipeline can inject the same `agent-platform-runtime-secrets` contract directly without relying on the local `runtime-secrets.env` files.

The active `dev-k8s` overlay includes exactly one runtime profile overlay at a time.

Current profiles:

- `deepseek`
- `dashscope`
- `openai`

## Additional selectable models (SPEC-024)

The committed overlays are unchanged by model switching: the active
profile's provider feeds the default catalog entry through the existing
`AGENTSCOPE_*` knobs. To enable extra models, add another provider's
`<PROVIDER>_API_KEY` (plus optional `<PROVIDER>_MODEL_NAME` /
`<PROVIDER>_BASE_URL`) to the local, git-ignored `runtime-secrets.env` —
each `runtime-secrets.example.env` documents the knobs. Providers without
a resolvable key stay dropped, and the profile's provider remains the
deploy-time default entry.

## Mutating tools dev posture

`mutating-dev` is **not** an LLM provider profile: it is the committed
mutating-tools posture for dev environments (SPEC-022 R-3). It carries the
pod-delete RBAC for the bounded mutating tool `k8s.delete_pod`, and its
`mutating.env` provides `GATEWAY_MUTATING_TOOLS_ENABLED=true`, which the
`dev-k8s` overlay merges into the `platform-runtime-config` ConfigMap.
The base keeps the flag `false`, so any overlay without the profile stays
byte-identical to the deny-by-default posture. It is wired into `dev-k8s`
permanently (`select-runtime-profile.sh` preserves it when switching LLM
profiles) and is never selected as the sole runtime profile.
