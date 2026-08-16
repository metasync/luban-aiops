# Configuration Reference

A definitive cross-service environment variable dependency map for the Luban AIOps platform.
This document shows which variables interact across service boundaries, what each feature
requires, and where each value originates.

## Feature Activation Matrix

The table below maps platform capabilities to the environment variables and secrets that
activate them. A feature is **active** when all required variables are set to non-empty values.

| Capability | Required Variables | Service(s) | Default (dev-k8s) |
|---|---|---|---|
| **Chat and sessions** | `AGENT_SERVICE_URL`, `SESSION_STORE_BACKEND`, `SESSION_REDIS_HOST` | platform-gateway, agent-service | enabled |
| **Portal authentication** | `PLATFORM_GATEWAY_REQUIRE_AUTH=true`, `IDENTITY_TOKEN_AUDIENCE` | platform-gateway, identity-service | enabled |
| **Token delegation** | `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` ↔ `IDENTITY_SERVICE_CLIENTS` | platform-gateway ↔ identity-service | **must be provisioned** |
| **Kubernetes tools** | `GATEWAY_K8S_ENABLED=true`, `GATEWAY_K8S_NAMESPACE` | tool-gateway | enabled (`dev-luban-aiops`) |
| **Elastic observability** | `GATEWAY_ELASTIC_ENABLED=true`, `GATEWAY_ELASTIC_URL`, auth (`_API_KEY` or `_USERNAME`+`_PASSWORD`) | tool-gateway | disabled |
| **Output redaction** | `GATEWAY_REDACTION_ENABLED` | tool-gateway | enabled (`true`) |
| **Policy enforcement** | `GATEWAY_POLICY_PATH`, `PLATFORM_GATEWAY_POLICY_PATH` | tool-gateway, platform-gateway | `/etc/luban/policy/policy.yaml` |
| **OpenTelemetry push** | `OTEL_ENABLED=true`, `OTEL_EXPORTER_OTLP_ENDPOINT` | all services | disabled |
| **LLM runtime** | `AGENTSCOPE_PROVIDER`, `AGENTSCOPE_MODEL_NAME`, `AGENTSCOPE_API_KEY` | agent-service | via runtime profile |
| **Workload identity** | `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH`, `IDENTITY_WORKLOAD_ISSUER_URL`, `IDENTITY_WORKLOAD_CLIENTS` | platform-gateway, identity-service | disabled (dev) |
| **Durable audit trail** | `*_AUDIT_SERVICE_URL`, `*_AUDIT_CLIENT_SECRET` ↔ `AUDIT_INGEST_CLIENTS` | audit-service, tool-gateway, platform-gateway, identity-service | **must be provisioned** (`sync-audit-secrets.sh`) |
| **Skills and grounded guidance** | `SKILLS_SOURCES`, `GATEWAY_SKILLS_SERVICE_URL`, `GATEWAY_SKILLS_CLIENT_SECRET` ↔ `SKILLS_QUERY_CLIENTS` | skills-hub, tool-gateway | **must be provisioned** (`sync-skills-secrets.sh`) |

## Cross-Service Dependency Chains

### Token Delegation Chain

The most critical cross-service dependency. Without it, the agent cannot invoke tools.

```
platform-gateway                          identity-service
┌──────────────────────┐                  ┌──────────────────────┐
│ PLATFORM_GATEWAY_    │                  │ IDENTITY_SERVICE_    │
│ SERVICE_CLIENT_ID    │─── must match ──►│ CLIENTS entry:       │
│ PLATFORM_GATEWAY_    │   client_id      │ platform-gateway:    │
│ SERVICE_CLIENT_      │                  │   <secret>:          │
│ SECRET               │─── must match ──►│   tool-gateway       │
│ PLATFORM_GATEWAY_    │                  │                      │
│ DELEGATION_AUDIENCE  │─── becomes aud ──►│ (delegated token)    │
│   = tool-gateway     │                  │                      │
└──────────────────────┘                  └──────────────────────┘
```

**Secret contract:**
- `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` (in `platform-gateway-runtime-secrets`)
- Must match the secret in `IDENTITY_SERVICE_CLIENTS` (in `identity-service-runtime-secrets`)
- Format of `IDENTITY_SERVICE_CLIENTS`: `client_id:client_secret:audience1|audience2`
- Example: `platform-gateway:my-shared-secret:tool-gateway`

**Provisioning:** `make deploy` calls `sync-delegation-secrets.sh` which generates a random
shared secret (or uses `DELEGATION_CLIENT_SECRET` if exported) and creates both K8s secrets.

### Identity Verification Chain

```
identity-service                          platform-gateway & tool-gateway
┌──────────────────────┐                  ┌──────────────────────┐
│ IDENTITY_TOKEN_      │                  │ IDENTITY_TOKEN_      │
│ ISSUER               │◄── must match ──│ ISSUER (or default)  │
│ IDENTITY_TOKEN_      │                  │ PLATFORM_GATEWAY_    │
│ AUDIENCE             │◄── must match ──│ TOKEN_AUDIENCE       │
│                      │                  │ GATEWAY_TOKEN_       │
│ /.well-known/jwks.json│◄── fetched via ─│ AUDIENCE             │
│ (public keys)        │   JWKS URL       │ IDENTITY_JWKS_URL    │
└──────────────────────┘                  └──────────────────────┘
```

### Tool Relay Chain

```
platform-gateway          agent-service               tool-gateway
┌──────────────┐          ┌──────────────┐            ┌──────────────┐
│ AGENT_       │          │ TOOL_GATEWAY_ │            │ listens on   │
│ SERVICE_URL  │──relay──►│ URL           │──invoke───►│ :8000        │
│ = agent-     │          │ = http://tool-│            │              │
│   service:   │          │   gateway:8000│            │              │
│   8000       │          │              │            │              │
└──────────────┘          └──────────────┘            └──────────────┘
```

### Audit Ingestion Chain

Fire-and-forget audit delivery (SPEC-013). Unreachable audit-service degrades
to log-only auditing; user-facing requests are never blocked.

```
tool-gateway / platform-gateway / identity-service          audit-service
┌─────────────────────────────────────────┐                 ┌──────────────────────┐
│ *_AUDIT_SERVICE_URL                     │── POST events ──►│ listens on :8000     │
│ = http://audit-service:8000             │                 │ AUDIT_INGEST_CLIENTS │
│ *_AUDIT_CLIENT_ID                       │── must match ──►│ entry:               │
│ *_AUDIT_CLIENT_SECRET                   │── must match ──►│ <client_id>=<secret> │
└─────────────────────────────────────────┘                 └──────────────────────┘
```

**Secret contract:**
- Each emitter's `*_AUDIT_CLIENT_SECRET` (in its `*-runtime-secrets`)
- Must match the secret registered for its client id in `AUDIT_INGEST_CLIENTS`
  (in `audit-service-runtime-secrets`), format `client_id=client_secret,...`

**Provisioning:** `make deploy` calls `sync-audit-secrets.sh` which generates
one random shared secret (or uses `AUDIT_INGEST_SECRET` if exported) and writes
all four K8s secrets. `SKIP_AUDIT_SECRETS=true` opts out; unsetting an
emitter's `*_AUDIT_SERVICE_URL` falls back to log-only auditing.

**Known limitation (shared query credential):** the audit-service query API
(`GET /api/v1/audit/events`) authenticates against the same
`AUDIT_INGEST_CLIENTS` registry as ingest, so any caller holding an ingest
credential can also query the trail directly. End-user authorization is
enforced upstream — platform-gateway gates the proxied route behind the
deny-by-default `audit:read` policy (granted to `auditor` and
`platform-admin` only) — so this is acceptable for the dev overlay. For the
first non-dev deployment, split the registries: a separate query-credential
registry (e.g. `AUDIT_QUERY_CLIENTS`) so ingest clients cannot read the
trail, keeping ingest-only services from gaining query capability.

### Skills Retrieval Chain

Grounded guidance delivery (SPEC-014). The agent consults team-owned skills
through the tool-gateway's read-only skills tools; with no
`GATEWAY_SKILLS_SERVICE_URL` configured the connector stays unregistered and
the agent answers without guidance.

```
agent-service          tool-gateway                          skills-hub
┌──────────────┐       ┌──────────────────────┐              ┌──────────────────────┐
│ skills.search│       │ GATEWAY_SKILLS_      │── GET search ─►│ listens on :8000     │
│ skills.get   │invoke►│ SERVICE_URL          │   / get / list │ SKILLS_QUERY_CLIENTS │
│ skills.list  │       │ = http://skills-hub: │              │ entry:               │
│ (auto-allow) │       │   8000               │              │ <client_id>=<secret> │
│              │       │ GATEWAY_SKILLS_      │── must match ─►│                      │
│              │       │ CLIENT_ID / _SECRET  │              │                      │
└──────────────┘       └──────────────────────┘              └──────────────────────┘
```

**Secret contract:**
- `GATEWAY_SKILLS_CLIENT_SECRET` (in `tool-gateway-runtime-secrets`)
- Must match the secret registered for client `tool-gateway` in
  `SKILLS_QUERY_CLIENTS` (in `skills-hub-runtime-secrets`), format
  `client_id=client_secret,...`

**Provisioning:** `make deploy` calls `sync-skills-secrets.sh` which creates
the `skills` database idempotently, generates one random shared secret, and
writes both K8s secrets. `SKIP_SKILLS_SECRETS=true` opts out; unsetting
`GATEWAY_SKILLS_SERVICE_URL` leaves the skills tools unregistered. Unlike the
audit-service query path, skills-hub uses a dedicated query-credential
registry from day one (no shared ingest/query credential).

## Per-Service Environment Variables

### agent-service

Source: `products/agent-platform/src/agent_service/runtime_settings.py`
Config fragment: `shared/platform-ops/gitops/dev-k8s/base/agent-platform/runtime-config.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `AGENTSCOPE_PROVIDER` | LLM backend: `dashscope`, `deepseek`, or `openai` | *(from profile)* | profile ConfigMap |
| `AGENTSCOPE_PROFILE` | Active profile name (must match provider) | *(from profile)* | profile ConfigMap |
| `AGENTSCOPE_MODEL_NAME` | Model identifier | *(from profile)* | profile ConfigMap |
| `AGENTSCOPE_BASE_URL` | Provider API endpoint | *(from profile)* | profile ConfigMap |
| `AGENTSCOPE_API_KEY` | Provider API key | *(none)* | **runtime-secrets** |
| `AGENTSCOPE_AGENT_NAME` | Agent identifier | `LubanOpsRuntime` | runtime-config |
| `AGENTSCOPE_REDIS_HOST` | Redis host for AgentScope coordination | `redis` | runtime-config |
| `AGENTSCOPE_REDIS_PORT` | Redis port | `6379` | runtime-config |
| `AGENTSCOPE_REDIS_DB` | Redis database number | `0` | runtime-config |
| `AGENTSCOPE_WORKSPACE_DIR` | Working directory for session files | `/var/lib/luban-aiops/workspaces/agent-platform` | runtime-config |
| `AGENTSCOPE_WORKSPACE_TTL_SECONDS` | Workspace cleanup TTL | `3600` | runtime-config |
| `SESSION_STORE_BACKEND` | Session persistence backend | `redis` | runtime-config |
| `SESSION_REDIS_HOST` | Redis host for sessions | `redis` | runtime-config |
| `SESSION_REDIS_PORT` | Redis port for sessions | `6379` | runtime-config |
| `SESSION_REDIS_DB` | Redis database for sessions | `1` | runtime-config |
| `TOOL_GATEWAY_URL` | Upstream tool-gateway URL | `http://tool-gateway:8000` | runtime-config |

### platform-gateway

Source: `products/platform-gateway/src/platform_gateway/core/config.py`
Config fragment: `shared/platform-ops/gitops/dev-k8s/base/platform-gateway/runtime-config.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `AGENT_SERVICE_URL` | Upstream agent-service URL | `http://agent-service:8000` | runtime-config |
| `PLATFORM_GATEWAY_REQUIRE_AUTH` | Require bearer token on requests | `true` | runtime-config |
| `PLATFORM_GATEWAY_DEV_USER` | Synthetic identity when auth is off | `dev.operator` | runtime-config |
| `PLATFORM_GATEWAY_POLICY_PATH` | Path to policy bundle YAML | `/etc/luban/policy/policy.yaml` | runtime-config |
| `PLATFORM_GATEWAY_TOKEN_AUDIENCE` | Expected JWT audience claim | `platform-gateway` | runtime-config |
| `PLATFORM_GATEWAY_DELEGATION_AUDIENCE` | Audience for delegated tokens | `tool-gateway` | runtime-config |
| `PLATFORM_GATEWAY_SERVICE_CLIENT_ID` | Client ID for token exchange | `platform-gateway` | runtime-config |
| `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` | Client secret for token exchange | *(none)* | **runtime-secrets** |
| `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH` | Projected SA token file (prod) | *(none)* | runtime-secrets |
| `IDENTITY_SERVICE_URL` | Identity broker URL | `http://identity-service:8000` | shared/runtime.env |
| `IDENTITY_JWKS_URL` | JWKS public key endpoint | `http://identity-service:8000/.well-known/jwks.json` | derived |
| `IDENTITY_TOKEN_ISSUER` | Expected JWT issuer | `http://identity-service:8000` | derived |
| `IDENTITY_JWKS_CACHE_SECONDS` | JWKS key cache TTL | `300` | code default |
| `CHAT_RESPONSE_TIMEOUT_SECONDS` | Upstream chat timeout | `30` | code default |
| `PLATFORM_GATEWAY_AUDIT_SERVICE_URL` | Audit-service ingest URL (unset = log-only) | `http://audit-service:8000` | runtime-config |
| `PLATFORM_GATEWAY_AUDIT_CLIENT_ID` | Audit ingest client id | `platform-gateway` | runtime-config |
| `PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET` | Audit ingest credential | *(none)* | **runtime-secrets** |

### tool-gateway

Source: `products/tool-gateway/src/tool_gateway/core/config.py`
Config fragment: `shared/platform-ops/gitops/dev-k8s/base/tool-gateway/runtime-config.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `GATEWAY_REQUIRE_AUTH` | Require bearer token on requests | `true` | runtime-config |
| `GATEWAY_DEV_USER` | Synthetic identity when auth is off | `dev.operator` | runtime-config |
| `GATEWAY_POLICY_PATH` | Path to policy bundle YAML | `/etc/luban/policy/policy.yaml` | runtime-config |
| `GATEWAY_TOKEN_AUDIENCE` | Expected JWT audience claim | `tool-gateway` | runtime-config |
| `GATEWAY_K8S_ENABLED` | Enable Kubernetes connector | `true` | runtime-config |
| `GATEWAY_K8S_NAMESPACE` | Default namespace for K8s tools | `dev-luban-aiops` | runtime-config |
| `GATEWAY_REDACTION_ENABLED` | Enable output redaction | `true` | code default |
| `GATEWAY_REDACTION_OVERFLOW_FRACTION` | Fail-closed redaction threshold | `0.2` | code default |
| `GATEWAY_ELASTIC_ENABLED` | Enable Elastic connector | `false` | runtime-config |
| `GATEWAY_ELASTIC_URL` | Elasticsearch cluster URL | *(none)* | runtime-config |
| `GATEWAY_ELASTIC_API_KEY` | Elastic API key (base64) | *(none)* | runtime-config |
| `GATEWAY_ELASTIC_USERNAME` | Elastic basic-auth username | *(none)* | runtime-config |
| `GATEWAY_ELASTIC_PASSWORD` | Elastic basic-auth password | *(none)* | runtime-config |
| `GATEWAY_ELASTIC_VERIFY_TLS` | Verify Elastic TLS certificates | `true` | code default |
| `GATEWAY_ELASTIC_ALERTS_INDEX` | Elastic alerts index pattern | `.alerts-*` | code default |
| `GATEWAY_WORKLOAD_TOKEN_PATH` | Projected SA token file (prod) | *(none)* | runtime-secrets |
| `GATEWAY_AUDIT_SERVICE_URL` | Audit-service ingest URL (unset = log-only) | `http://audit-service:8000` | runtime-config |
| `GATEWAY_AUDIT_CLIENT_ID` | Audit ingest client id | `tool-gateway` | runtime-config |
| `GATEWAY_AUDIT_CLIENT_SECRET` | Audit ingest credential | *(none)* | **runtime-secrets** |
| `GATEWAY_SKILLS_SERVICE_URL` | skills-hub base URL (unset = connector off) | `http://skills-hub:8000` | runtime-config |
| `GATEWAY_SKILLS_CLIENT_ID` | Skills query client id | `tool-gateway` | runtime-config |
| `GATEWAY_SKILLS_CLIENT_SECRET` | Skills query credential | *(none)* | **runtime-secrets** |
| `IDENTITY_SERVICE_URL` | Identity broker URL | `http://identity-service:8000` | shared/runtime.env |

### identity-service

Source: `products/identity-broker/src/identity_service/core/config.py`
Config fragment: `shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `KEYCLOAK_BASE_URL` | Keycloak server URL | `https://idp.apps.metasync.cc` | runtime-config |
| `KEYCLOAK_REALM` | Keycloak realm name | `luban-aiops` | runtime-config |
| `OIDC_CLIENT_ID` | OIDC browser client ID | `luban-aiops-portal` | runtime-config |
| `OIDC_CLIENT_SECRET` | OIDC client secret (confidential clients) | *(none)* | **runtime-secrets** |
| `OIDC_SCOPES` | Requested OIDC scopes | `openid groups` | runtime-config |
| `OIDC_REDIRECT_URI` | Primary browser callback URI | `https://aiops.luban.metasync.cc/callback` | runtime-config |
| `OIDC_POST_LOGOUT_REDIRECT_URI` | Primary post-logout redirect | `https://aiops.luban.metasync.cc/` | runtime-config |
| `OIDC_EXTRA_REDIRECT_URIS` | Comma-separated extra callback URIs | gateway `.orb.local` + `localhost:18080` | runtime-config |
| `OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS` | Comma-separated extra post-logout redirects | gateway `.orb.local` + `localhost:18080` | runtime-config |
| `IDENTITY_TOKEN_AUDIENCE` | JWT audience for portal tokens | `platform-gateway` | runtime-config |
| `IDENTITY_TOKEN_TTL_SECONDS` | Portal JWT TTL | `3600` | code default |
| `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` | Delegated token TTL | `300` | runtime-config |
| `IDENTITY_JWT_ISSUER` | JWT issuer claim | `http://identity-service:8000` | code default |
| `IDENTITY_JWT_PRIVATE_KEY_PATH` | RSA private key file (prod) | *(auto-generate)* | code default |
| `IDENTITY_SERVICE_CLIENTS` | Registered service callers | *(none)* | **runtime-secrets** |
| `IDENTITY_WORKLOAD_ISSUER_URL` | Cluster OIDC issuer (prod) | *(none, disabled)* | runtime-secrets |
| `IDENTITY_WORKLOAD_AUDIENCE` | Projected token audience | `identity-broker` | code default |
| `IDENTITY_WORKLOAD_CLIENTS` | SA subject→client mapping | *(none)* | runtime-secrets |
| `IDENTITY_AUDIT_SERVICE_URL` | Audit-service ingest URL (unset = log-only) | `http://audit-service:8000` | runtime-config |
| `IDENTITY_AUDIT_CLIENT_ID` | Audit ingest client id | `identity-broker` | runtime-config |
| `IDENTITY_AUDIT_CLIENT_SECRET` | Audit ingest credential | *(none)* | **runtime-secrets** |

### audit-service

Source: `products/audit-service/src/audit_service/core/config.py`
Config fragment: `shared/platform-ops/gitops/dev-k8s/base/audit-service/runtime-config.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `AUDIT_STORE_BACKEND` | Store backend: `memory` or `postgres` | `postgres` (dev-k8s) | runtime-config |
| `AUDIT_DB_URL` | PostgreSQL connection URL (postgres backend) | in-cluster `postgres` service | runtime-config |
| `AUDIT_INGEST_CLIENTS` | Registered ingest callers (`client_id=secret,...`) | *(none)* | **runtime-secrets** |
| `AUDIT_WORKLOAD_ISSUER_URL` | Cluster OIDC issuer for workload tokens (prod) | *(none, disabled)* | runtime-secrets |
| `AUDIT_WORKLOAD_AUDIENCE` | Projected token audience | `audit-service` | code default |
| `AUDIT_WORKLOAD_CLIENTS` | SA subject→client mapping | *(none)* | runtime-secrets |
| `AUDIT_RETENTION_DAYS` | Retention window for eviction | `30` | runtime-config |
| `AUDIT_MAX_EVENTS` | Hard store-size cap | `100000` | runtime-config |
| `AUDIT_EVICTION_INTERVAL_SECONDS` | Eviction task period | `3600` | runtime-config |
| `AUDIT_EVICTION_BATCH_SIZE` | Batched delete size (postgres) | `1000` | code default |
| `AUDIT_MAX_BATCH` | Max events per ingest request | `50` | code default |

### skills-hub

Source: `products/skills-hub/src/skills_hub/core/config.py`
Config fragment: `shared/platform-ops/gitops/dev-k8s/base/skills-hub/runtime-config.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `SKILLS_SOURCES` | Federated source list (JSON: `source_id`, `type` `local`/`git`, `path`/`url`/`ref`) | two local sample sources | runtime-config |
| `SKILLS_GIT_TOKENS` | Per-source git tokens (JSON map) | *(none)* | runtime-secrets |
| `SKILLS_SYNC_INTERVAL_SECONDS` | Per-source sync loop period | `300` | runtime-config |
| `SKILLS_DATA_PATH` | Working dir for git checkouts | `/var/lib/skills-hub` | runtime-config |
| `SKILLS_STORE_BACKEND` | Store backend: `memory` or `postgres` | `postgres` (dev-k8s) | runtime-config |
| `SKILLS_DB_URL` | PostgreSQL connection URL (database `skills`) | in-cluster `postgres` service | runtime-config |
| `SKILLS_QUERY_CLIENTS` | Registered query callers (`client_id=secret,...`) | *(none)* | **runtime-secrets** |
| `SKILLS_WORKLOAD_ISSUER_URL` | Cluster OIDC issuer for workload tokens (prod) | *(none, disabled)* | runtime-secrets |
| `SKILLS_WORKLOAD_AUDIENCE` | Projected token audience | `skills-hub` | code default |
| `SKILLS_WORKLOAD_CLIENTS` | SA subject→client mapping | *(none)* | runtime-secrets |

### Shared (all pods)

Source: `shared/platform-ops/gitops/dev-k8s/base/shared/runtime.env`

| Variable | Purpose | Default | Source |
|---|---|---|---|
| `OTEL_ENABLED` | Enable OpenTelemetry push pipeline | `false` | shared/runtime.env |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | *(commented out)* | shared/runtime.env |
| `IDENTITY_SERVICE_URL` | Identity broker URL (shared) | `http://identity-service:8000` | shared/runtime.env |

## Secret Contracts

Secrets are provisioned as Kubernetes `Secret` objects, never committed to Git.

### `agent-platform-runtime-secrets`

| Key | Purpose | How to Provision |
|---|---|---|
| `AGENTSCOPE_API_KEY` | LLM provider API key | `sync-runtime-secret.sh <profile>` |

### `platform-gateway-runtime-secrets`

| Key | Purpose | How to Provision |
|---|---|---|
| `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` | Token exchange credential | `sync-delegation-secrets.sh` |
| `PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET` | Audit ingest credential | `sync-audit-secrets.sh` |

### `identity-service-runtime-secrets`

| Key | Purpose | How to Provision |
|---|---|---|
| `OIDC_CLIENT_SECRET` | Keycloak confidential client secret | Manual or CI |
| `IDENTITY_SERVICE_CLIENTS` | Service client registry | `sync-delegation-secrets.sh` |
| `IDENTITY_AUDIT_CLIENT_SECRET` | Audit ingest credential | `sync-audit-secrets.sh` |

### `tool-gateway-runtime-secrets`

| Key | Purpose | How to Provision |
|---|---|---|
| `GATEWAY_AUDIT_CLIENT_SECRET` | Audit ingest credential | `sync-audit-secrets.sh` |
| `GATEWAY_SKILLS_CLIENT_SECRET` | Skills query credential | `sync-skills-secrets.sh` |

### `audit-service-runtime-secrets`

| Key | Purpose | How to Provision |
|---|---|---|
| `AUDIT_INGEST_CLIENTS` | Ingest client registry (`client_id=secret,...`) | `sync-audit-secrets.sh` |

### `skills-hub-runtime-secrets`

| Key | Purpose | How to Provision |
|---|---|---|
| `SKILLS_QUERY_CLIENTS` | Query client registry (`client_id=secret,...`) | `sync-skills-secrets.sh` |

## Runtime Profiles

The agent-service supports pluggable LLM backends through Kustomize profile overlays.
Only one profile is active at a time.

| Profile | Provider | Model | ConfigMap |
|---|---|---|---|
| `deepseek` | `deepseek` | `deepseek-v4-flash` | `runtime-profiles/deepseek/configmap.yaml` |
| `dashscope` | `dashscope` | `qwen-plus` | `runtime-profiles/dashscope/configmap.yaml` |
| `openai` | `openai` | `gpt-4.1-mini` | `runtime-profiles/openai/configmap.yaml` |

Switch profiles with:

```bash
shared/platform-ops/gitops/select-runtime-profile.sh <profile-name>
```

Each profile also has a `runtime-secrets.example.env` documenting the required API key variable.

## Policy Management

The policy bundle controls which roles can perform which actions.

**Canonical source:** `shared/shared-contracts/policies/policy-default.yaml`

**Workflow:**

1. Edit the canonical file
2. Validate against the JSON schema: `make validate-policy`
3. Sync to all consumer locations: `make sync-policy`
4. Rebuild images and redeploy (or re-apply the Kustomize overlay)

**Consumer locations** (must stay byte-identical):

- `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`
- `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`
- `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`

See the [Architecture Overview](architecture-overview.md) for the RBAC model and default
policy rules.
