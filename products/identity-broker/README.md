# Identity Broker

## Purpose

`identity-broker` normalizes enterprise identity for the platform.

It is responsible for:

- `Keycloak` integration
- `AD` federation handling
- group and role normalization
- identity context propagation
- service-consumable identity claims

## Ownership

Recommended owner:

- identity and platform access team

## Current Scope

This project covers:

- enterprise `SSO` entry and token normalization
- group-to-role mapping and identity enrichment
- downstream identity context propagation
- platform-wide identity contract alignment

Current implementation artifacts:

- `pyproject.toml`
- `Dockerfile`
- `src/identity_service/app.py`
- `src/identity_service/api/routes/`
- `src/identity_service/core/`
- `src/identity_service/schemas/`
- `src/identity_service/services/`
- `src/identity_service/services/token_service.py` (JWT issuer + JWKS)
- `tests/test_identity_service.py`
- `tests/test_token_service.py`

Current implementation status:

- organizes the `FastAPI` package by app bootstrap, route modules, config helpers, schemas, and normalization services
- keeps `main.py` as a thin runtime bootstrap entrypoint
- centralizes `Keycloak` and `OIDC` login URL construction behind settings-aware service code
- isolates group-to-role mapping and identity normalization from the HTTP route layer
- issues RSA-signed platform JWTs (`POST /api/v1/auth/token`) with configurable TTL
- publishes the public key set at `GET /.well-known/jwks.json` (RFC 7517)
- the OIDC callback (`/auth/callback`) returns a platform JWT as the primary `access_token`
- supports token refresh (`POST /api/v1/auth/refresh`): exchanges a Keycloak refresh_token for a new platform JWT with updated identity claims
- adds focused tests for role normalization, login URL composition, token issuance, JWKS format, and token refresh

Current runtime environment knobs:

- `KEYCLOAK_BASE_URL`, `KEYCLOAK_REALM`
  - Keycloak issuer and realm used to compose login and JWKS URLs
- `OIDC_CLIENT_ID`, `OIDC_REDIRECT_URI`, `OIDC_POST_LOGOUT_REDIRECT_URI`, `OIDC_SCOPES`
  - OIDC client registration knobs
- `IDENTITY_JWT_PRIVATE_KEY_PATH`
  - path to the PEM-encoded RSA signing key; if unset and the path exists it is loaded, otherwise a dev key is generated and persisted
- `IDENTITY_TOKEN_TTL_SECONDS`
  - platform JWT lifetime; defaults to `900`
- `IDENTITY_TOKEN_ISSUER`
  - `iss` claim written into issued tokens; defaults to `luban-identity-broker`
- `OTEL_ENABLED`
  - master switch for the OTLP push pipeline (traces + metrics); defaults to `false`; when disabled, the `/metrics` surface is unaffected
- `OTEL_EXPORTER_OTLP_ENDPOINT`
  - OTLP collector URL used when `OTEL_ENABLED=true`
- `OTEL_SERVICE_NAME`
  - logical service name reported to the collector; defaults to the identity-broker's metadata name

Observability surface (see `SPEC-005` and `shared/shared-contracts/observability-conventions.md`):

- `GET /metrics` — always-on Prometheus exposition endpoint (auth-exempt), reporting standard HTTP RED metrics plus `identity_tokens_issued_total` (incremented on every platform JWT issued)
- opt-in OTLP push via `opentelemetry-instrumentation-fastapi` + `opentelemetry-exporter-otlp` when `OTEL_ENABLED=true`; fail-open
- `x-request-id` remains the log/portal correlation key; when OTel tracing is active it equals the W3C `trace_id`

## Expected Integration Points

- `operator-portal` for login initiation and session establishment
- `agent-platform` for normalized user identity context
- `policy-center` for role and group inputs to authorization
- `shared/shared-contracts` and `shared/shared-sdk` for auth-related models and helpers

## Boundary

This project does not make authorization decisions and does not own operator-facing portal behavior.
