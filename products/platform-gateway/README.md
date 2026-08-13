# platform-gateway

Portal-facing edge service of the Luban AIOps platform (extracted from the
combined api-gateway by SPEC-010, per ADR-0005).

## Responsibilities

- Verifies portal bearer tokens (issuer/audience JWKS validation; audience
  `platform-gateway`) and applies the deny-by-default action policy bundle to
  every portal-facing action (`agent:chat`, `sessions:*`, …).
- Proxies chat and session traffic to `agent-platform`, exchanging the portal
  token for a short-lived delegated token (`aud = tool-gateway`,
  `act.sub = platform-gateway`) via identity-broker before forwarding.
- Relays auth/identity/runtime endpoints to identity-broker and agent-platform.
- Proxies the durable audit trail query (`/api/v1/audit/*`) to `audit-service`,
  gated by the `audit:read` policy action (granted to `auditor` and
  `platform-admin` only, SPEC-013).
- Forwards policy decision, session, and chat lifecycle audit events to
  `audit-service` fire-and-forget when `PLATFORM_GATEWAY_AUDIT_SERVICE_URL`
  is set (log-only otherwise; SPEC-013).
- Exposes `/health/live`, `/health/ready`, and `/metrics`.

Tool registry, connectors, `tools:list` / `tools:invoke`, and output redaction
live in [tool-gateway](../tool-gateway/README.md), which agent-platform calls
directly with delegated tokens.

## Run locally

```sh
uv sync
uv run pytest
uv run platform-gateway
```

## Configuration

Environment-driven; see `src/platform_gateway/core/config.py`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `AGENT_SERVICE_URL` | `http://agent-service:8000` | agent-platform upstream |
| `IDENTITY_SERVICE_URL` | `http://identity-service:8000` | identity-broker upstream |
| `IDENTITY_JWKS_URL` | `…/.well-known/jwks.json` | portal token JWKS |
| `PLATFORM_GATEWAY_TOKEN_AUDIENCE` | `platform-gateway` | expected portal token audience |
| `PLATFORM_GATEWAY_SERVICE_CLIENT_ID` | `platform-gateway` | broker client id for delegation |
| `PLATFORM_GATEWAY_SERVICE_CLIENT_SECRET` | (empty) | broker client secret (dev only; prefer workload token) |
| `PLATFORM_GATEWAY_WORKLOAD_TOKEN_PATH` | (empty) | projected service-account token; preferred over static secret |
| `PLATFORM_GATEWAY_DELEGATION_AUDIENCE` | `tool-gateway` | audience of delegated tokens |
| `PLATFORM_GATEWAY_POLICY_PATH` | packaged default | action policy bundle path |
| `PLATFORM_GATEWAY_REQUIRE_AUTH` | `true` | dev fallback issues a synthetic identity when off |
| `PLATFORM_GATEWAY_DEV_USER` / `PLATFORM_GATEWAY_DEV_SIGNING_KEY_PATH` | see code | local-dev login shortcut |
| `PLATFORM_GATEWAY_AUDIT_SERVICE_URL` | (empty) | audit-service ingest URL; empty keeps log-only auditing |
| `PLATFORM_GATEWAY_AUDIT_CLIENT_ID` | `platform-gateway` | audit ingest client id |
| `PLATFORM_GATEWAY_AUDIT_CLIENT_SECRET` | (empty) | audit ingest credential (matches `AUDIT_INGEST_CLIENTS`) |
