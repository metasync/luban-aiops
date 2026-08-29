---
kind: error_handling
name: Domain-Specific Exceptions, HTTPException, and Fail-Open Patterns Across Services
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## What system/approach is used

The platform does not define a single shared error type or global FastAPI exception handler. Instead, each product service defines its own small domain exception classes (e.g. `StoreError`, `PolicyLoadError`, `TokenVerificationError`, `ExchangeError`, `TriageError`, `ConnectorConfigError`, `NormalizationError`, `SettingsError`, `ProviderConfigurationError`) that inherit from `Exception` (or `ValueError`). At the API boundary, routes raise FastAPI's built-in `HTTPException` with explicit `status_code` and `detail` strings — there are no custom response models for errors, so clients receive the default FastAPI JSON `{"detail": ...}` envelope.

For cross-service calls (e.g. incident-service calling agent-platform), failures are translated into the local domain exception rather than propagated as raw HTTP status codes.

## Key files and packages

- Domain exceptions per service:
  - `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError`
  - `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`
  - `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`
  - `products/incident-service/src/incident_service/services/triage.py` — `TriageError`
  - `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`
  - `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError` (with a `detail` attribute)
  - `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError(detail, status_code)`
  - `products/skills-hub/src/skills_hub/services/skill_store.py` — `StoreError`
  - `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — `PolicyLoadError`
  - `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError`
  - `products/incident-service/src/incident_service/core/config.py` — `SettingsError`
  - `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`
  - `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError`
  - `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError`
  - `products/incident-service/src/incident_service/services/incident_store.py` — `StoreError`
  - `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`

- HTTP boundary usage:
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — raises `HTTPException(401, 404, 409, 410)` for auth, session conflicts, expired confirmations, missing sessions.
  - `products/agent-platform/src/agent_service/services/session_service.py` — raises `HTTPException(404)` for unknown/foreign sessions.

- Cross-service error translation:
  - `products/incident-service/src/incident_service/services/triage.py` — catches `httpx.HTTPError` and non-200 responses from agent-platform, wraps them in `TriageError`, then marks the incident `triage_failed` instead of bubbling up.

## Architecture and conventions

1. **Per-service domain exceptions**: Each service owns its failure types. There is no shared base class beyond `Exception`; naming follows `<Area>Error` (e.g. `StoreError`, `PolicyLoadError`, `TokenVerificationError`). This keeps callers in the same service able to catch precise failure modes without importing across services.

2. **HTTPException at route boundaries only**: Only the `agent-platform` v2 routes currently raise `HTTPException`. Other services' routes do not appear to wrap their domain exceptions into HTTP responses via a central exception handler; they either return normal responses or let exceptions propagate to the framework's default handler. The `platform-gateway` and `tool-gateway` policy engines return structured `PolicyDecision` dataclasses rather than raising on deny-by-default — denial is modeled as a value (`decision="deny"`) not an exception.

3. **Fail-open / fail-safe patterns for side effects**:
   - Connector dispatch (`incident_service/services/connectors.py:dispatch_report`) catches `Exception` around each connector call and records it as a failed dispatch instead of aborting the triage path. The comment explicitly states: "a connector outage must not turn a successful triage into a failure."
   - Session workspace bookkeeping (`session_service.py:mark_session_title/touch_session`) swallows exceptions and logs a warning — bookkeeping never fails a turn.
   - Session deletion (`session_service.py:delete_session`) treats state-store cleanup as best-effort after the session is already gone.
   - Store `ready()` methods (`PostgresAuditStore.ready`, `PostgresSkillStore.ready`) catch all exceptions and return `False` — readiness checks must never raise.

4. **Opaque identity semantics**: Foreign-owned sessions are surfaced as `404 session not found` rather than `403 forbidden` (`_assert_session_owner` in `session_service.py`), making unauthorized access indistinguishable from unknown IDs.

5. **Structured denials over exceptions**: Policy evaluation (`policy_engine.py` in both gateway and tool-gateway) returns a frozen `PolicyDecision` dataclass with `decision="allow"|"deny"`, `matched_rule_ids`, and `reason`. Denial is a normal return value, not an exception — this lets callers map the decision to appropriate HTTP status codes while preserving auditability.

6. **Cross-service error wrapping**: When one service calls another over HTTP (incident-service → agent-platform), transport-level failures (`httpx.HTTPError`) and non-2xx statuses are wrapped into the caller's domain exception (`TriageError`) so the rest of the pipeline stays agnostic of the underlying protocol.

7. **No repository-wide exception handler**: No `@app.exception_handler` was found in any service's `app.py` or router files; error formatting relies on FastAPI's defaults plus explicit `HTTPException` construction at the few places that need custom status codes.

## Conventions and constraints observed

- Domain exceptions are raised in service-internal logic; HTTP concerns live in routes.
- Configuration/validation failures raise dedicated `*Error` types (e.g. `SettingsError`, `ConnectorConfigError`, `ProviderConfigurationError`) during startup or early validation, failing fast before the request path starts.
- External dependency failures (connectors, stores, downstream services) are isolated: they are caught locally, recorded via metrics/observability, and converted into either a structured result (connector dispatch) or a domain exception that the caller handles gracefully.
- Deny-by-default authorization is expressed as a data return value (`PolicyDecision.decision == "deny"`) rather than an exception, enforcing the principle that authorization decisions are part of the normal control flow.
- Readiness probes must never raise (`except Exception: return False` in store backends).
- Identity-related failures use opaque responses (404 for foreign sessions, `authenticated: false` for invalid tokens) to avoid leaking existence information.