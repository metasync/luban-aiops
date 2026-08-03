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

This project covers:

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

Current implementation status:

- proxies the current portal contract to backend services
- targets the platform-owned agent-service contract (`/api/v2/`) directly; no dual-backend resolution
- routes session and chat bridging through a single `agent_client` module
- verifies bearer tokens locally via JWKS (no per-request network call to identity-broker)
- validates the `iss` claim against `IDENTITY_TOKEN_ISSUER` and the `aud` claim against `GATEWAY_TOKEN_AUDIENCE`; rejects expired/malformed/wrong-audience tokens with `401`
- derives `X-User-ID` exclusively from verified token claims; caller-asserted headers are ignored
- when auth is optional and no token is present, injects a synthetic dev identity (logged as `synthetic: true`)
- performs broker-mediated token delegation (SPEC-008 / ADR-0004): on a verified chat request it exchanges the user token for a short-lived delegated token (cached per user subject) and forwards it downstream to `agent-platform` as `Authorization: Bearer`; exchange failure is non-fatal (chat proceeds tool-less)
- enforces deny-by-default authorization on business routes (`chat`, `session:create`, `session:read`, `tools:list`, `tools:invoke`) against a versioned role→action policy bundle; denials return a structured `403` and are audit-logged
- loads the policy bundle from `GATEWAY_POLICY_PATH`, falling back to a packaged default kept in sync with `shared/shared-contracts`
- provides a tool execution framework (`src/api_gateway/tools/`) with a `ToolRegistry`, `BaseTool` abstraction, and structured evidence envelope (SPEC-007)
- ships a Kubernetes read-only connector (`k8s.list_pods`, `k8s.get_pod`, `k8s.get_events`, `k8s.get_pod_logs`) using `kubernetes-client/python`
- exposes `GET /api/v2/tools` (tool discovery, gated by `tools:list`) and `POST /api/v2/tools/invoke` (tool execution gated by `tools:invoke`); both derive identity solely from the verified token — any identity in a request body is never trusted
- redacts credential-shaped spans (JWTs, `Bearer`/`Basic` values, PEM private keys, key-list fields such as `token`/`password`/`api_key`) from every tool result at the single invoke choke point before both the response and the audit log; when the redacted fraction exceeds `GATEWAY_REDACTION_OVERFLOW_FRACTION` the output is withheld with a `REDACTION_OVERFLOW` error (fail-closed, SPEC-009)
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
  - when `true`, all protected routes require a valid bearer token; defaults to `true` (set `false` explicitly for local development without SSO)
- `GATEWAY_DEV_USER`
  - synthetic identity username when auth is optional and no token is present; defaults to `dev.operator`
- `GATEWAY_POLICY_PATH`
  - path to the action-authorization policy bundle (YAML); when unset, the packaged default bundle is used; a configured-but-invalid path fails readiness rather than falling back
- `GATEWAY_K8S_ENABLED`
  - when `true`, registers the Kubernetes read-only connector; defaults to `false`
- `GATEWAY_K8S_NAMESPACE`
  - default namespace for K8s tool operations; when unset, tools use the `namespace` parameter or fall back to `default`
- `GATEWAY_TOKEN_AUDIENCE`
  - expected `aud` claim value enforced on inbound tokens; defaults to `tool-gateway`
- `GATEWAY_SERVICE_CLIENT_ID`, `GATEWAY_SERVICE_CLIENT_SECRET`
  - static service credential used to authenticate to the identity-broker exchange endpoint for token delegation (SPEC-008); the secret is loaded from a K8s Secret, not committed; kept as the dev fallback when the projected workload token is configured; when both this and `GATEWAY_WORKLOAD_TOKEN_PATH` are unset, delegation is skipped and the agent runs tool-less
- `GATEWAY_WORKLOAD_TOKEN_PATH`
  - path to a Kubernetes projected service-account token file (SPEC-009); when set, the file is re-read per exchange (kubelet rotates it in place) and sent as `Bearer` instead of the static credential; when unset, behavior is the static-secret path
- `GATEWAY_REDACTION_ENABLED`
  - master switch for tool-output redaction; defaults to `true`; the `false` setting is a dev-debugging opt-out only
- `GATEWAY_REDACTION_OVERFLOW_FRACTION`
  - redacted-character fraction above which tool output is withheld with `REDACTION_OVERFLOW`; defaults to `0.2`
- `GATEWAY_DELEGATION_AUDIENCE`
  - audience requested for delegated tokens; defaults to `tool-gateway`
- `GATEWAY_DEV_SIGNING_KEY_PATH`
  - optional PEM key used to sign the synthetic dev subject token exchanged under the no-SSO path; when unset an ephemeral key is used
- `OTEL_ENABLED`
  - master switch for the OTLP push pipeline (traces + metrics); defaults to `false`; when disabled, the `/metrics` surface is unaffected
- `OTEL_EXPORTER_OTLP_ENDPOINT`
  - OTLP collector URL used when `OTEL_ENABLED=true` (e.g. Elastic APM endpoint); unused otherwise
- `OTEL_SERVICE_NAME`
  - logical service name reported to the collector; defaults to the gateway's metadata name

Observability surface (see `SPEC-005` and `shared/shared-contracts/observability-conventions.md`):

- `GET /metrics` — always-on Prometheus exposition endpoint (auth-exempt, policy-exempt), reporting standard HTTP RED metrics (`http_requests_total{method,handler,status}`, `http_request_duration_seconds{method,handler}`) plus `gateway_policy_decisions_total{action,decision}`, `gateway_token_verification_total{result}` (valid | invalid | expired | missing), delegation metrics `delegation_exchange_total{result}` and `delegation_cache_total{result}` (SPEC-008), and `gateway_tool_redacted_spans_total{tool}` (credential spans redacted from tool results, SPEC-009)
- opt-in OTLP push via `opentelemetry-instrumentation-fastapi` + `opentelemetry-exporter-otlp` when `OTEL_ENABLED=true`; fail-open — an unreachable collector drops telemetry without affecting requests
- `x-request-id` remains the log/portal correlation key; when OTel tracing is active it equals the W3C `trace_id`

## Expected Integration Points

- `agent-platform` for tool invocation requests
- `execution-runtime` for approved bounded-action adapters
- external systems such as Kubernetes, observability, and ticketing platforms
- `shared/shared-contracts` for tool request and response schemas

## Boundary

This project does not own approval logic, session orchestration, or operator-facing UI flows.
