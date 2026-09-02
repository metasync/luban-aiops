# Runtime Profiles

This directory contains the runtime profile overlays for `agent-service`.

The LLM profile contributes:

- a committed non-secret `ConfigMap` named `agent-platform-runtime-profile`
- an ignored local fallback secret file path `runtime-secrets.env`
- an example secret file template `runtime-secrets.example.env`

Luban CI or another deployment pipeline can inject the same `agent-platform-runtime-secrets` contract directly without relying on the local `runtime-secrets.env` files.

The active `dev-k8s` overlay includes exactly one LLM runtime profile overlay at a time.

Current LLM profile:

- `default` — generic deploy label (`AGENTSCOPE_PROFILE=default`), decoupled from the active provider (`AGENTSCOPE_PROVIDER` in the ConfigMap). Provider selection is a ConfigMap knob, not a directory choice, so there is one profile for any provider mix.

## Multi-model catalog (SPEC-026)

Every supported provider (`deepseek`, `dashscope`, `openai`) with an API key
in the local, git-ignored `runtime-secrets.env` joins the catalog with its
curated model series — one selectable entry per model (entry id = model
name). `<PROVIDER>_MODELS=a,b,c` optionally overrides/restricts the series.
Providers without a resolvable key stay dropped (fail-closed), and the
active provider's `AGENTSCOPE_MODEL_NAME` remains the deploy-time default.
The `runtime-secrets.example.env` documents every knob.

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

## Browser web-check dev posture

`browser-dev` is **not** an LLM provider profile: it is the committed
browser web-check posture for dev environments (SPEC-049 R-7). It carries
the `chromium-headless-shell` sidecar patch for the tool-gateway
Deployment, the sample `browser-check-target` web app (static login +
status pages), and `browser.env` — `GATEWAY_BROWSER_ENABLED=true`, the
pod-local CDP endpoint, and the dev origin allowlist — which the `dev-k8s`
overlay merges into the `platform-runtime-config` ConfigMap. The base keeps
`GATEWAY_BROWSER_ENABLED=false` with no allowlist, so any overlay without
the profile stays byte-identical to the deny-by-default posture. Like
`mutating-dev`, it is wired into `dev-k8s` permanently
(`select-runtime-profile.sh` preserves it when switching LLM profiles) and
is never selected as the sole runtime profile. Named credential sets for
web logins are synced out of band via `sync-browser-credentials.sh` into
the `tool-gateway-browser-credentials` secret.
