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
- Proxies the incidents surface (`/api/v1/incidents/*`: list, get, report,
  create, triage) to `incident-service`, gated by the `incident:read` /
  `incident:create` / `incident:triage` policy actions (SPEC-015). Queries
  use the gateway's incident-service credential; triage additionally relays
  `X-User-ID` and the operator's delegated bearer. Unset upstream fails
  closed (503).
- Proxies HITL confirmation decisions (`POST /api/v1/chat/confirm`) to
  `agent-platform`, gated by the deny-by-default `chat:confirm` action
  (granted to `platform-admin`, `approver`, `operator`, `developer`;
  `read-only-observer` excluded); the confirm response is the resumed SSE
  stream, and a durable `confirmation_decided` audit event is emitted when
  the kernel-applied `confirmation_result` frame passes through (SPEC-020).
- Proxies the session workspace lifecycle (SPEC-022 R-1):
  `GET /api/v1/sessions` (gated by `session:list`) and
  `DELETE /api/v1/sessions/{session_id}` (gated by `session:delete`,
  emitting a durable `session_deleted` audit event); upstream `4xx`
  (unknown/foreign session, parked confirmation) passes through unchanged.
  Chat requests carry an optional `input_modality` (`text` | `voice`)
  forwarded as metadata only — logged and audited, never decision-bearing
  (SPEC-022 R-2).
- Relays model discovery and per-turn model selection to `agent-platform`
  (SPEC-024): `GET /api/v1/models` is gated by the `models:list` action
  (mirroring the chat scope) and returns the discovery-safe catalog
  (id/label/provider/default — never credentials); chat requests carry an
  optional `model` (POST body / stream query parameter) relayed verbatim
  with upstream 4xx pass-through — validation is fail-closed runtime-side.
  Audit enrichment records the requested model on `chat_started` and the
  serving model (teed from the `message_end` frame) on `chat_completed`
  for both chat surfaces.
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
| `PLATFORM_GATEWAY_INCIDENT_SERVICE_URL` | (empty) | incident-service upstream; empty keeps the incidents routes fail-closed (503) |
| `PLATFORM_GATEWAY_INCIDENT_CLIENT_ID` | `platform-gateway` | incident query client id |
| `PLATFORM_GATEWAY_INCIDENT_CLIENT_SECRET` | (empty) | incident query credential (matches `INCIDENT_QUERY_CLIENTS`) |
| `PLATFORM_GATEWAY_INCIDENT_TRIAGE_TIMEOUT_SECONDS` | `120` | triage proxy timeout |
