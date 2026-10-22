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

The gateway profile does **not** enable SPEC-063 durable execution admission.
Agent and worker admission default to disabled and require a verified Postgres
ledger, matching externally configured epoch, and separate explicit enablement.
The first SPEC-063 deployment requires the coordinated mutation-disabled
[cutover procedure](../../../../docs/guides/execution-cutover-restore.md), even
though its coordinated version is an upgrade. Profile selection is not a
migration, safety check, or authorization to restore mutation execution.

## Browser web-check dev posture

`browser-dev` is **not** an LLM provider profile: it is the committed
browser web-check posture for dev environments (SPEC-049 R-7). It carries
the `chromium-headless-shell` sidecar patch for the tool-gateway
Deployment, its NetworkPolicy, and `browser.env` —
`GATEWAY_BROWSER_ENABLED=true`, the pod-local CDP endpoint, and the dev
origin allowlist — which the `dev-k8s` overlay merges into the
`platform-runtime-config` ConfigMap. The profile ships no target of its
own: SPEC-061 retired the static `browser-check-target` web app, so the
one allowlisted origin is `acme-admin`, the sample app deployed
out-of-band by `make deploy-sample-app`. The base keeps
`GATEWAY_BROWSER_ENABLED=false` with no allowlist, so any overlay without
the profile stays byte-identical to the deny-by-default posture. Like
`mutating-dev`, it is wired into `dev-k8s` permanently
(`select-runtime-profile.sh` preserves it when switching LLM profiles) and
is never selected as the sole runtime profile. Named credential sets for
web logins are synced out of band via `sync-browser-credentials.sh` into
the `tool-gateway-browser-credentials` secret.

## Secure password generation dev posture

`secrets-dev` is **not** an LLM provider profile: it is the committed
secure-password-generation posture for dev environments (SPEC-062 R-7).
It is env-only — it ships no resource and no patch, just `secrets.env`
providing `GATEWAY_SECRETS_ENABLED=true`, which the `dev-k8s` overlay
merges into the `platform-runtime-config` ConfigMap. No extra mount is
needed: the password-policy contract already rides the base
`platform-policy` ConfigMap at `/etc/luban/policy/password-policy.yaml`
(`GATEWAY_PASSWORD_POLICY_PATH`). Email delivery stays inert here — no
SMTP host or TLS is configured by this profile, so
`secrets.deliver(channel="email")` still fails closed with
`EMAIL_NOT_CONFIGURED` until SMTP is provisioned out of band via
`sync-email-secrets.sh`. The base keeps the flag `false`, so an overlay
without the profile stays byte-identical to the deny-by-default posture.

## Ansible MCP-ingestion dev posture

`ansible-dev` is **not** an LLM provider profile: it is the committed
Ansible read-tier MCP-ingestion posture for dev environments (SPEC-069
R-6). It carries the thin mock MCP server (`ansible-mock-mcp`, a
streamable-HTTP responder generated off the real `.py` so the mounted
script and the committed source cannot drift), its Service and
NetworkPolicy, and `ansible.env` — `GATEWAY_ANSIBLE_MCP_ENABLED=true` plus
the transport, URL, timeout, and credential-set knobs — which the `dev-k8s`
overlay merges into `platform-runtime-config`. The mock speaks the same
wire as the production `ansible/aap-mcp-server`, so swapping it for real
AAP (or open-source AWX via `lycorp-jp/awx-mcp`) is a config-only change:
a new `_URL` and, where tool names differ, a new binding.
`tool-gateway-ansible-credentials.yaml` is deliberately **not** listed
under `resources:` — it is a strategic merge patch the `dev-k8s` overlay
applies to the tool-gateway Deployment, which lives in the base the
overlay assembles. Credentials are synced out of band via
`sync-ansible-credentials.sh` (one generator, two sinks: the gateway's
credential set and the mock's bearer gate) into
`tool-gateway-ansible-credentials` and `ansible-mock-credentials`;
`ANSIBLE_MCP_BEARER_TOKEN` points it at a real server and
`SKIP_ANSIBLE_CREDENTIALS=true` leaves both unwritten so the connector
fails closed (`CREDENTIAL_SET_NOT_FOUND`) and the mock 401s every call.
`GATEWAY_ANSIBLE_NATIVE_ENABLED` is deliberately left unset: the native
`ansible-inventory` shell-out is the OQ-1 fallback for when no MCP server
is wired, and this profile wires one. Like `mutating-dev` and
`browser-dev`, it is wired into `dev-k8s` permanently and is never
selected as the sole runtime profile.

## ServiceNow read-tier ingestion dev posture

`servicenow-dev` is **not** an LLM provider profile: it is the committed
ServiceNow read-tier ingestion posture for dev environments (SPEC-067
R-6). It carries the thin mock ServiceNow Table-API + `/oauth_token.do`
responder (`servicenow-mock-table-api`, likewise generated off the real
`.py`), its Service and an Ingress-only NetworkPolicy admitting port 8000
from the tool-gateway pod alone, and `servicenow.env` —
`GATEWAY_SERVICENOW_ENABLED=true` plus the base URL, timeout, and
credential-set knobs — which the `dev-k8s` overlay merges into
`platform-runtime-config`. The mock reuses the tool-gateway image (already
`FROM base-uv`, already shipping starlette/uvicorn), so no new image is
built; `deploy-overlay.sh` retags it to the coordinated tag. The mock
speaks the same wire as a real ServiceNow tenant's REST surface, so
swapping it for a live PDI or production instance is a config-only change:
a new `GATEWAY_SERVICENOW_BASE_URL` and a new `token_url` in the credential
set — never a connector-code change and never a model-selected value. The
live-tenant path, including tenant-side provisioning and validation, is the
[ServiceNow Live Integration Guide](../../../../docs/guides/servicenow-integration.md).
`tool-gateway-servicenow-credentials.yaml` is likewise a `dev-k8s` strategic
merge patch, not a profile resource. Credentials are synced out of band via
`sync-servicenow-credentials.sh` (one generator, two sinks: the gateway's
`oauth2_client_credentials` set and the mock's OAuth + bearer gates) into
`tool-gateway-servicenow-credentials` and `servicenow-mock-credentials`;
`SERVICENOW_CLIENT_ID` / `SERVICENOW_CLIENT_SECRET` / `SERVICENOW_TOKEN_URL`
point it at a real tenant and `SKIP_SERVICENOW_CREDENTIALS=true` leaves both
unwritten so neither side runs open. CI makes no live external call (OQ-5):
the mock is what the overlay validates against, and the real-instance check
is a gated operator step. Like the other postures, it is wired into `dev-k8s`
permanently and is never selected as the sole runtime profile.
