---
kind: error_handling
name: Structured HTTP Error Handling with Domain-Specific Exceptions and FastAPI Routes
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/agent-platform/src/agent_service/entrypoints/runtime.py
    - products/identity-broker/src/identity_service/api/routes/auth.py
    - products/audit-service/src/audit_service/api/routes/ingest.py
    - products/skills-hub/src/skills_hub/api/routes/skills.py
    - products/incident-service/src/incident_service/api/routes/incidents.py
---

## Overview

The Luban AIOps Platform uses a consistent, layered error-handling approach across all Python services (agent-platform, platform-gateway, tool-gateway, audit-service, incident-service, skills-hub, identity-broker). Errors are expressed as domain-specific exception classes raised within service layers and converted to HTTP responses at the route boundary using FastAPI's `HTTPException` or explicit `JSONResponse` objects. There is no global exception handler; each route handles its own errors explicitly.

## Exception Hierarchy by Service

**Agent Platform (`agent_service`)**
- `ProviderConfigurationError(ValueError)` — invalid/missing provider settings in `providers/base.py`
- `UnknownModelError(ValueError)` — requested model absent from credential-gated catalog in `runtime_kernel.py`; routes map this to 422 per SPEC-024 R-1
- `WorkerHandoffError(Exception)` — execution worker handoff failures in `services/execution_worker_client.py`
- `IncidentClientError` hierarchy: base + `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound(incident_id)`, `IncidentClientRejected(status_code, message)` in `services/incident_client.py`; callers map these to 503/502/4xx respectively
- `ConfirmationExpired`, `ConfirmationNotFound` in `services/hitl_confirmations.py`; caught in routes and mapped to 409/404
- `DigestInputError`, `UnknownSessionError`, `ForeignSessionDenied` in `services/shift_summary.py`
- `NoValidatedTriageReport` in `services/skill_draft.py`
- `SkillsClientRejected`, `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable` in `services/skills_client.py`

**Identity Broker (`identity_service`)**
- `ExchangeError` — token exchange failures with `.status_code` and `.detail`; routes re-raise as `HTTPException(exc.status_code, detail=exc.detail)` after emitting an audit event with outcome "deny"

**Audit, Skills, Incident Services**
- `IngestAuthError` / `QueryAuthError` — authentication failures caught in routes and returned as 401 `JSONResponse`

## Route-Level Error Patterns

FastAPI routes follow two patterns depending on the service:

1. **HTTPException pattern** (agent-platform): routes raise `HTTPException(status_code=..., detail=...)` directly. Examples include 401 for missing `X-User-ID`, 409 for parked-session conflicts, 422 for unknown model ids, 404 for missing sessions/documents/confirmations, 410 for expired confirmations, 502/503 for upstream transport failures, and pass-through of `exc.status_code`/`exc.message` from client exceptions like `IncidentClientRejected`.

2. **Explicit JSONResponse pattern** (audit-service, skills-hub, incident-service): routes define a local `_error(status_code, code, message)` helper returning `JSONResponse(content={"error": {"code": ..., "message": ...}})`. This produces a uniform `{error: {code, message}}` envelope for validation errors (400), auth failures (401), parameter violations (400), and not-found cases (404).

## Upstream Dependency Error Mapping

External calls wrap transport and response codes into domain exceptions so callers can map them deterministically:

- `incident_client.fetch_incident_bundle`: `httpx.HTTPError` → `IncidentServiceUnavailable` (502); 404 → `IncidentNotFound`; 5xx → `IncidentServiceUnavailable`; other 4xx → `IncidentClientRejected(status_code, message)`; unconfigured deps → `IncidentDependencyNotConfigured` (503)
- `identity_service.exchange_token`: `ExchangeError` with `status_code`/`detail` surfaced verbatim
- Agent runtime streaming wraps provider errors via `kernel.remember_error(exc)` and returns a user-facing error message instead of propagating raw traces

## Fail-Open vs Fail-Closed Conventions

- **Fail-closed**: Unknown model selection raises `UnknownModelError` (never silently falls back to default per SPEC-024 R-1); unknown session IDs return 404 rather than 403 to prevent enumeration (anti-enumeration convention in `session_service._assert_session_owner`) 
- **Fail-open**: Session bookkeeping (`mark_session_turn`, `pin_session_model`) catches exceptions and logs warnings without failing the turn; session deletion cascades cleanup through multiple stores with individual try/except blocks that swallow failures since the session is already gone
- **Best-effort cleanup**: Evidence store, confirmation records, execution records, agent state store deletions during session teardown are wrapped in bare `except Exception:` blocks

## Streaming Error Handling

The agent-platform runtime entrypoint (`entrypoints/runtime.py`) streams replies from AgentScope and wraps the entire stream in `try/except Exception` to capture provider errors mid-stream, calling `kernel.remember_error(exc)` and yielding a constructed error message block instead of aborting the stream abruptly. The kernel tracks `_last_error` and exposes `runtime_state()` returning `provider_error` when set.

## Configuration-Time Errors

Provider `validate(settings)` raises `ProviderConfigurationError` when settings are incomplete (e.g., missing `AGENTSCOPE_API_KEY`). Import-time guards in `entrypoints/runtime.py` catch missing `agentscope-runtime` dependencies and raise `RuntimeError` with a descriptive message before the app starts.

## No Global Middleware

There is no repository-wide FastAPI exception middleware. Each route handles its own errors inline. The only cross-cutting concern is structured logging via `log_event` and audit emission via `emit_audit_event`, which are called around successful operations and around rejected exchanges but not as a blanket error interceptor.