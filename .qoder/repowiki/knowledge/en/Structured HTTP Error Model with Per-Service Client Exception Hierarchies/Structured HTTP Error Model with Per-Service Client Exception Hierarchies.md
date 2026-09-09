---
kind: error_handling
name: Structured HTTP Error Model with Per-Service Client Exception Hierarchies
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/tool-gateway/src/tool_gateway/api/routes/tools.py
    - products/platform-gateway/src/platform_gateway/api/routes/chat.py
---

## Overview

The Luban AIOps platform uses a consistent, structured error-handling model across all Python services (agent-platform, platform-gateway, tool-gateway, execution-runtime, identity-broker, audit-service, incident-service, skills-hub). Errors are expressed as typed Python exceptions that are mapped to well-defined HTTP status codes at the API boundary. There is no global `@app.exception_handler` — instead, each service's route handlers and gateway legs explicitly catch domain-specific exceptions and raise FastAPI `HTTPException`s with appropriate status codes.

## Core Pattern: Domain-Specific Exception Hierarchies

Each outbound client in agent-platform defines a small exception hierarchy under a base class, so callers can map upstream failures to a stable "house posture":

- **Incident client** (`products/agent-platform/src/agent_service/services/incident_client.py`): `IncidentClientError` base → `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`. The module docstring states the contract: "503 when the dependency is not configured, 502 on transport failure or upstream 5xx, and 4xx passed through".
- **Skills client** (`products/agent-platform/src/agent_service/services/skills_client.py`): `SkillsClientError` base → `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`. Same mapping rule documented in its module docstring.

These hierarchies are raised from `httpx` calls and caught by the calling routes, which translate them into `HTTPException(status_code=..., detail=...)` responses. For example, `_validate_skill_markdown` catches `SkillsDependencyNotConfigured` → 503, `SkillsServiceUnavailable` → 502, `SkillsClientRejected` → pass-through status code; the same pattern applies to incident draft generation.

## Gateway-Leg Error Normalization

The platform-gateway centralizes outbound error normalization in `_identity_leg` (`platform_gateway/services/gateway_service.py`). It wraps every call to the identity service behind a single helper that:
- Passes through 4xx responses from the identity service with their original status and extracted `detail` field.
- Converts any 5xx or transport failure into a structured `HTTPException(status_code=502, detail="identity service unavailable/unreachable")`.
- Never lets raw stack traces leak to clients.

This ensures the sign-in surface never answers a raw 500 when a downstream leg races during rollout.

## Policy Enforcement Errors

Both `platform_gateway` and `tool_gateway` enforce access via a shared `enforce_policy(settings, identity, action, request_id)` function that evaluates the policy bundle and raises `HTTPException(status_code=403, detail={...})` on deny. The detail includes the denied action and the matching rule reason. Policy load failures surface as `PolicyLoadError`, which is caught by readiness endpoints and reported as `status: degraded` rather than failing the service.

## Token Verification Errors

Identity resolution in both gateways (`resolve_request_identity`) raises `HTTPException(status_code=401, ...)` for malformed authorization headers, expired/invalid tokens (`TokenVerificationError`), and missing auth when `require_auth` is enabled. Metrics record verification outcomes as `valid`, `expired`, `invalid`, or `missing`.

## Route-Level Error Handling

Routes use explicit `try/except` blocks around service calls to convert domain exceptions into HTTP responses. In `agent_service/api/v2/routes.py`:
- Confirmation lifecycle errors raise `HTTPException(409, ...)` for conflicts, `410 Gone` for expired confirmations, `404 Not Found` for missing confirmations.
- Session creation returns `409 Conflict` for duplicate sessions and `404 Not Found` for unknown sessions.
- Skill-draft generation falls back to a facts-only skeleton on first validation failure, then answers `502` only if even the skeleton fails format validation — guaranteeing the operator always receives a valid artifact.

## Audit Emission Failures

Outbound audit emission in multiple services (`audit_emitter.py` under agent-platform, execution-runtime, identity-broker) wraps the HTTP call and raises `RuntimeError(f"ingest rejected with {response.status_code}")` when the audit service responds with ≥300. This is an internal failure path — audit loss degrades the operation but does not crash the caller.

## Readiness/Liveness Surfaces

Services expose `/health/live` returning `{status: ok}` and `/health/ready` that probes dependencies. If a dependency check fails (e.g., policy bundle load, agent health probe), the ready endpoint returns `{status: degraded, ...error fields}` instead of raising — enabling Kubernetes liveness/readiness probes to distinguish transient degradation from fatal startup failure.

## Conventions Observed

- **No global exception handler**: Each route/service layer catches and maps exceptions explicitly; there is no repository-wide `@app.exception_handler` registered.
- **House posture over raw traces**: Outbound client errors are never surfaced verbatim — they are wrapped in typed exceptions and translated to stable HTTP postures (503 = not configured, 502 = unreachable/upstream 5xx, 4xx passthrough).
- **Structured 403 details**: Policy denials include `{action, reason}` in the response body, not just a generic message.
- **Audit loss is non-fatal**: Audit emit failures raise `RuntimeError` but do not propagate to the caller's HTTP response.
- **Readiness surfaces report degradation**: Health endpoints return `status: degraded` with error context rather than failing hard.
- **FastAPI `HTTPException` is the canonical HTTP error type**: All routes raise it with explicit `status_code` and `detail`; no custom JSONResponse wrappers are used for error cases.