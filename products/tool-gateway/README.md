# Tool Gateway

## Purpose

`tool-gateway` is the standardized tool and connector access layer for the platform.

It is responsible for:

- connector normalization
- `MCP` and tool integration
- Kubernetes and observability connectors
- collaboration and ticketing connectors
- stable tool contracts and execution metadata

## Transitional Role Versus Target Role

What this product runs today differs from its documented target boundary:

- current transitional role: the portal-facing API gateway (`api_gateway` package) that authenticates requests against `identity-broker`, validates contract payloads, and proxies session/chat traffic to `agent-platform`
- target role: the normalized tool and connector gateway described above; the portal/API gateway responsibility migrates toward dedicated edge components as the platform grows
- renaming the product directory or the `api_gateway` package is explicitly deferred to a future ADR (see `SPEC-001` non-goals)

The boundary definitions for both roles live in the workspace model: [workspace-model.md](../../docs/workspace/workspace-model.md).

## Ownership

Recommended owner:

- integrations or platform connectors team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- connector abstraction and normalization
- `MCP`-compatible tool exposure
- read-only and future bounded-action connector pathways
- connector execution metadata and health reporting

Current implementation artifacts:

- `pyproject.toml`
- `Dockerfile`
- `src/api_gateway/app.py`
- `src/api_gateway/api/routes/`
- `src/api_gateway/core/`
- `src/api_gateway/services/`

Current scaffold status:

- proxies the current portal contract to backend services
- targets the platform-owned agent-service contract (`/api/v2/`) directly; no dual-backend resolution
- routes session and chat bridging through a single `agent_client` module
- verifies bearer tokens locally via JWKS (no per-request network call to identity-broker)
- validates the `iss` claim against `IDENTITY_TOKEN_ISSUER`; rejects expired/malformed tokens with `401`
- derives `X-User-ID` exclusively from verified token claims; caller-asserted headers are ignored
- when auth is optional and no token is present, injects a synthetic dev identity (logged as `synthetic: true`)
- enforces deny-by-default authorization on business routes (`chat`, `session:create`, `session:read`) against a versioned role→action policy bundle; denials return a structured `403` and are audit-logged
- loads the policy bundle from `GATEWAY_POLICY_PATH`, falling back to a packaged default kept in sync with `shared/shared-contracts`
- organizes the FastAPI package by app bootstrap, route modules, shared request/config helpers, and service orchestration
- validates chat and session request bodies against `shared/shared-contracts` aligned `pydantic` models (`422` on malformed input)

Current runtime environment knobs:

- `AGENT_SERVICE_URL`, `IDENTITY_SERVICE_URL`
  - backend service endpoints; default to in-cluster service DNS names
- `IDENTITY_JWKS_URL`
  - JWKS endpoint for local token verification; defaults to `http://identity-service:8000/.well-known/jwks.json`
- `IDENTITY_JWKS_CACHE_SECONDS`
  - JWKS cache refresh interval; defaults to `300`
- `IDENTITY_TOKEN_ISSUER`
  - expected `iss` claim value; defaults to `luban-identity-broker`
- `CHAT_RESPONSE_TIMEOUT_SECONDS`
  - bounded read timeout for non-streaming chat requests; defaults to `30` (streaming keeps unbounded read with a bounded connect timeout)
- `GATEWAY_REQUIRE_AUTH`
  - when `true`, all protected routes require a valid bearer token; defaults to `false`
- `GATEWAY_DEV_USER`
  - synthetic identity username when auth is optional and no token is present; defaults to `dev.operator`
- `GATEWAY_POLICY_PATH`
  - path to the action-authorization policy bundle (YAML); when unset, the packaged default bundle is used; a configured-but-invalid path fails readiness rather than falling back
- `OTEL_ENABLED`
  - master switch for the OTLP push pipeline (traces + metrics); defaults to `false`; when disabled, the `/metrics` surface is unaffected
- `OTEL_EXPORTER_OTLP_ENDPOINT`
  - OTLP collector URL used when `OTEL_ENABLED=true` (e.g. Elastic APM endpoint); unused otherwise
- `OTEL_SERVICE_NAME`
  - logical service name reported to the collector; defaults to the gateway's metadata name

Observability surface (see `SPEC-005` and `shared/shared-contracts/observability-conventions.md`):

- `GET /metrics` — always-on Prometheus exposition endpoint (auth-exempt, policy-exempt), reporting standard HTTP RED metrics (`http_requests_total{method,handler,status}`, `http_request_duration_seconds{method,handler}`) plus `gateway_policy_decisions_total{action,decision}` and `gateway_token_verification_total{result}` (valid | invalid | expired | missing)
- opt-in OTLP push via `opentelemetry-instrumentation-fastapi` + `opentelemetry-exporter-otlp` when `OTEL_ENABLED=true`; fail-open — an unreachable collector drops telemetry without affecting requests
- `x-request-id` remains the log/portal correlation key; when OTel tracing is active it equals the W3C `trace_id`

## Expected Integration Points

- `agent-platform` for tool invocation requests
- `execution-runtime` for approved bounded-action adapters
- external systems such as Kubernetes, observability, and ticketing platforms
- `shared/shared-contracts` for tool request and response schemas

## Boundary

This project does not own approval logic, session orchestration, or operator-facing UI flows.
