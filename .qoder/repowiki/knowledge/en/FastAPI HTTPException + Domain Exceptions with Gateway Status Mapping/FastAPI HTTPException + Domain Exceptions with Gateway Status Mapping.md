---
kind: error_handling
name: FastAPI HTTPException + Domain Exceptions with Gateway Status Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/platform-gateway/src/platform_gateway/app.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
---

## Overview

The Agentic AIOps Platform uses a layered error-handling model built on FastAPI's `HTTPException` for HTTP boundaries, domain-specific Python exceptions for internal service logic, and explicit status-code mapping at the platform-gateway proxy layer. There is no centralized exception-to-HTTP-status registry; instead each product service raises `HTTPException` directly from its route or service layer, and the gateway translates upstream transport failures into standardized 502 responses.

## HTTP Boundary Errors (FastAPI)

All public-facing services are FastAPI applications (`app.py` in each product). Errors surface to callers via `fastapi.HTTPException`, raised from routes or service functions:

- **Authentication / identity**: missing `X-User-ID` header → 401 (`agent_service/api/v2/routes.py:_user_id`); malformed `Authorization` header → 401 (`platform_gateway/services/gateway_service.py:resolve_request_identity`); expired/invalid JWT → 401 via `TokenVerificationError` caught and re-raised as 401 (`platform_gateway/services/token_verifier.py`).
- **Authorization**: policy denial → 403 with structured `{detail, action, reason}` payload (`platform_gateway/services/gateway_service.py:enforce_policy`).
- **Resource not found**: session lookups raise 404 with `"session not found"`; foreign-session ownership checks deliberately return 404 (not 403) so enumeration is impossible — this is an anti-enumeration convention documented in `_assert_session_owner` (`agent_service/services/session_service.py`).
- **Conflict**: parked HITL confirmations block new turns → 409 (`_reject_if_parked`); deleting a session that still has a parked confirmation → 409; duplicate confirm attempts → 409.
- **Validation**: unknown model id → 422 (`_resolve_model`); expired confirmation → 410.
- **Upstream failure**: the gateway maps any non-4xx upstream `httpx.HTTPStatusError` or generic `httpx.HTTPError` to 502 with a `"agent service unavailable"` detail (`get_session`, `list_sessions`, `delete_session`, `chat_stream`, `chat_confirm`).

No custom global exception handler is registered in any `app.py`; FastAPI's default JSON error response format is used.

## Domain Exceptions (Internal Propagation)

Domain logic raises typed exceptions that are caught closer to the boundary and mapped to HTTP status codes:

| Exception | Module | Meaning | Mapped To |
|---|---|---|---|
| `ConfirmationExpired` | `agent_service/services/hitl_confirmations.py` | HITL confirmation TTL elapsed | 410 Gone |
| `ConfirmationNotFound` | same | Confirmation entry missing | 404 Not Found |
| `ConfirmationOwnerMismatch` | same | Confirming user ≠ session owner | Stream error frame (SSE), not HTTP |
| `TokenVerificationError` | `platform_gateway/services/token_verifier.py` | JWKS/JWT verification failure | 401 Unauthorized |
| `PolicyLoadError` | `platform_gateway/services/policy_engine.py` | Policy bundle load failure | Degraded readiness probe only |

These exceptions never leak across service boundaries — they are caught inside the owning service and converted to either `HTTPException` or protocol-level frames (see SSE below).

## Streaming Error Handling (SSE)

For Server-Sent Events (`/chat/stream`, `/chat/confirm`), errors that occur after headers are already sent cannot use `HTTPException`. Instead they are emitted as structured `AgentStreamEvent` frames of type `error` with a `code` and `message` field. The canonical example is `ConfirmationOwnerMismatch` during `resume_confirmation`, which yields an `error` event rather than aborting the stream (`agent_service/api/v2/routes.py:286-299`).

## Fail-Open vs Fail-Closed Conventions

The codebase documents and enforces two complementary patterns:

1. **Fail-open bookkeeping**: Non-critical side effects (session title pinning, evidence store reads, agent state cleanup) are wrapped in `try/except Exception` and logged via `LOGGER.warning`; failures degrade functionality but never fail the caller request. See `mark_session_turn`, `pin_session_model`, `_load_evidence_turns`, and `delete_session`'s cascading cleanup in `agent_service/services/session_service.py`.
2. **Fail-closed validation**: Input validation (unknown model ids, missing auth headers, invalid tokens) fails fast with appropriate 4xx codes before any downstream work begins.

## Gateway Proxy Posture

The platform-gateway acts as a strict translator between external clients and backend services. Its posture is consistently documented in docstrings:

- Upstream 4xx errors pass through unchanged (client errors remain client errors).
- Transport failures and upstream 5xx map to 502 `"agent service unavailable"`.
- This pattern is repeated verbatim for every proxied endpoint: `get_session`, `list_sessions`, `delete_session`, `chat_stream`, `chat_confirm`.

Readiness probes (`ready_status`) catch `httpx.HTTPError` and `PolicyLoadError` and report `status: "degraded"` instead of failing the process, allowing Kubernetes liveness/readiness to distinguish transient outages from permanent misconfiguration.

## Key Files

- `products/platform-gateway/src/platform_gateway/app.py` — FastAPI app bootstrap, HTTP middleware logs `response.status_code` for all requests.
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — Central place where upstream errors are mapped to 4xx/502; policy denial → 403.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError` domain exception for JWT failures.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — Route-layer error mapping (401/404/409/410/422) and SSE `error` frames.
- `products/agent-platform/src/agent_service/services/session_service.py` — Anti-enumeration 404 convention, fail-open bookkeeping.
- `products/agent-platform/src/agent_service/services/hitl_confirmations.py` — Domain exceptions `ConfirmationExpired`, `ConfirmationNotFound`, `ConfirmationOwnerMismatch`.

## Conventions Observed

- Raise `HTTPException(status_code=..., detail=...)` at the HTTP boundary; do not return tuples like `(body, status)`.
- Use domain exceptions internally; convert them to `HTTPException` at the boundary.
- Never expose 403 for resource ownership — always 404 to prevent enumeration.
- Degrade optional stores (evidence, transcript, session metadata) by logging and returning `None` rather than raising.
- Gateway proxies never swallow upstream 4xx; they only translate transport/5xx to 502.
- Streaming errors after headers are emitted as typed SSE frames, not HTTP exceptions.