---
kind: error_handling
name: Structured Domain Exceptions and HTTP Error Mapping in a FastAPI Monorepo
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/identity-broker/src/identity_service/api/routes/identity.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - shared/shared-contracts/schemas/policy-decision.schema.json
---

## Overview

The Luban platform uses a layered error model across eight Python services (agent-platform, audit-service, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway, execution-runtime). Each service defines small domain-specific exception classes that bubble up to the FastAPI boundary, where they are mapped to HTTP responses. There is no global exception handler; instead, routes and gateway proxies explicitly raise `fastapi.HTTPException` with explicit status codes and structured `detail` payloads.

## Domain Exception Classes

Each product package declares its own exception types near the code that raises them:

- **agent-platform**: `ProviderConfigurationError`, `UnknownModelError`, `WorkerHandoffError`, `DigestInputError`, `UnknownSessionError`, `ForeignSessionDenied`, `ConfirmationNotFound`, `ConfirmationExpired` — all raised by services and caught at route boundaries to produce 400/401/403/404/409/410 responses.
- **audit-service**: `StoreError`, `IngestAuthError` — raised by store/auth layers; routes translate them into 5xx or 401 responses.
- **incident-service**: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` — each scoped to its subsystem.
- **platform-gateway**: `PolicyLoadError`, `TokenVerificationError` — raised during policy bundle loading and JWT verification; caught by `resolve_request_identity` and `enforce_policy` to emit 401/403.
- **skills-hub / tool-gateway**: mirror the same pattern (`SettingsError`, `StoreError`, `QueryAuthError`, `PolicyLoadError`, `TokenVerificationError`).

These exceptions are intentionally narrow: they carry enough context for logging but never leak internal state into the response body. The route layer is the single place where domain exceptions are converted to HTTP semantics.

## HTTP Boundary Conventions

### Status-code mapping

Routes consistently use these mappings:
- `401` — missing `X-User-ID` header, malformed/bearer token, authentication required, invalid bearer token.
- `400` — input validation failures (e.g. title too long, unknown model id), digest input errors.
- `403` — foreign session access denied, policy deny, self-approval blocked, not a designated approver.
- `404` — session/document/confirmation not found; anti-enumeration convention deliberately makes foreign IDs indistinguishable from unknown ones.
- `409` — parked confirmation conflict, already published document, already resolved confirmation.
- `410` — expired confirmation.
- `502` — upstream agent/tool/incident/skills hub unavailable or transport failure.
- `503` — optional feature unavailable (e.g. audit service not configured).

### Structured detail payloads

Errors return structured JSON bodies rather than plain strings. For example, an already-resolved confirmation returns `{"reason": "already_resolved", "status": ..., "decider_user_id": ..., "decision": ..., "decided_at": ...}`; a policy denial returns `{"detail": "action denied by policy", "action": ..., "reason": ...}`; a blocked approval tier returns `{"action": ..., "reason": "not_a_designated_approver"|"self_approval", "requirement": "require_approval", "approval_tier": ...}`. This lets clients (especially the operator portal) render actionable messages without parsing opaque strings.

### Gateway proxy posture

The platform-gateway enforces a uniform rule for every downstream call: upstream `4xx` passes through unchanged (preserving anti-enumeration and structured details like `already_resolved`), while `httpx.HTTPStatusError` with `5xx` or generic `httpx.HTTPError` is translated to `HTTPException(status_code=502, detail="...")`. This is repeated verbatim in `get_session`, `list_sessions`, `delete_session`, `update_session_title`, `create_document`, `list_documents`, `fetch_document`, `publish_document`, `delete_document`, `chat_stream`, and `chat_confirm`.

## Fail-open vs Fail-closed Patterns

The codebase distinguishes two modes:

- **Fail-closed on critical paths**: authentication, authorization, policy evaluation, and confirmation resolution always fail closed. Missing headers → 401; unknown model → 422; expired confirmation → 410; policy deny → 403; unconfigured policy path → startup `PolicyLoadError`.
- **Fail-open on auxiliary side effects**: bookkeeping operations (session title pinning, evidence loading, confirmation record claim-time writes, execution record reads) are wrapped in `try/except Exception` blocks that log via `LOGGER.warning` and degrade gracefully — returning `None`, empty lists, or proceeding without the side effect. A comment in `_load_evidence_turns` states this explicitly: "degrades like `transcript_available=false`, never a 500".

## Streaming Error Handling

SSE chat streams handle errors differently than regular requests. The gateway opens the upstream stream only after verifying it is not a 4xx rejection; then it parses frames inline to detect `message_end` and `confirmation_result` events for audit emission. If the upstream closes early without a `message_end`, the gateway emits a fallback audit using the requested model. Errors inside the stream generator surface as HTTP errors because the underlying `httpx` iterator raises when the connection fails.

## No Global Middleware

There is no custom FastAPI exception middleware registered. Error handling is localized: each route catches specific domain exceptions and raises `HTTPException`; each gateway proxy wraps downstream calls in try/except blocks. This keeps error semantics explicit per endpoint rather than centralized in a handler.

## Shared Contracts and Schemas

Cross-service error shapes are partially codified in `shared/shared-contracts/schemas/`. While there is no dedicated `error.schema.json`, the `policy-decision.schema.json` and `tool-result.schema.json` define the shape of structured error-like payloads (`decision`, `matched_rule_ids`, `reason`) that flow between services. Tests validate contract conformance for both success and error paths.

## Key Files

- `products/agent-platform/src/agent_service/api/v2/routes.py` — primary HTTP boundary; maps domain exceptions to 400/401/403/404/409/410 with structured details.
- `products/agent-platform/src/agent_service/services/hitl_confirmations.py` — defines `ConfirmationNotFound`, `ConfirmationExpired`, and the in-memory registry that gates parked confirmations.
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — uniform proxy error posture: pass 4xx, map transport failures to 502, enforce policy with structured 403.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError` and the three-way decision model (`allow`/`deny`/`require_approval`).
- `products/agent-platform/src/agent_service/services/session_service.py` — demonstrates fail-open bookkeeping and anti-enumeration 404 convention.
- `products/identity-broker/src/identity_service/api/routes/auth.py` and `identity.py` — show consistent 401 mapping for OIDC/token errors.
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError` hierarchy for workload identity failures.
- `products/incident-service/src/incident_service/services/query_auth.py` — mirrored auth error pattern.
- `shared/shared-contracts/schemas/policy-decision.schema.json` — structured error-like payload schema used by policy decisions.