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
