---
kind: error_handling
name: Structured Domain Exceptions, HTTPException Mapping, and Tool Result Envelopes
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/shift_summary.py
    - products/agent-platform/src/agent_service/services/hitl_confirmations.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool-gateway/services/policy_engine.py
    - products/tool-gateway/src/tool-gateway/services/token_verifier.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## Overview

The Luban platform uses a layered error-handling strategy across its nine product services. At the service boundary (FastAPI routers), errors are raised as `fastapi.HTTPException` with explicit status codes. In domain and client layers, each service defines a small hierarchy of typed exceptions that encode semantic failure modes (configuration missing, upstream unavailable, not found, client-rejected). Cross-service clients wrap HTTP responses into these typed exceptions so callers can branch on semantics rather than inspecting raw status codes. For tool execution, failures are returned as structured `ToolResult` envelopes (`status: "error"` or `"denied"`) instead of raising, keeping tool invocations deterministic for agents.

## Exception hierarchies per service

Each product service defines domain-specific exception classes in its `services/` modules:

- **agent-platform**: `ProviderConfigurationError(ValueError)`, `UnknownModelError(ValueError)`; `WorkerHandoffError`, `IncidentClientError` with subclasses `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`; `SkillsClientError` with `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`; `DigestInputError`, `UnknownSessionError`, `ForeignSessionDenied`, `DevelopmentSessionRejected`; `ConfirmationNotFound`, `ConfirmationExpired` (both subclass `LookupError`).
- **incident-service**: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- **platform-gateway** and **tool-gateway**: `PolicyLoadError`, `TokenVerificationError`.
- **skills-hub**: `SettingsError`, `QueryAuthError`, `StoreError`.
- **audit-service**: `StoreError`, `IngestAuthError`.
- **identity-broker**: `ExchangeError`.

These classes carry only the minimal payload needed by the caller (e.g. `IncidentNotFound.incident_id`, `SkillsClientRejected.status_code/message`, `UnknownSessionError.session_ids`). No service exposes raw stack traces to callers.

## Cross-service client pattern

Clients such as `agent_service/services/incident_client.py` and `agent_service/services/skills_client.py` follow an identical shape:

1. Check configuration via an `is_configured(settings)` helper; raise `<Service>DependencyNotConfigured` if knobs are absent.
2. Build an `httpx.AsyncClient` call with timeout and auth headers.
3. On transport `httpx.HTTPError`, log at warning level and raise `<Service>ServiceUnavailable`.
4. On response ≥ 500, raise `<Service>ServiceUnavailable`.
5. On 404, raise a dedicated `<Service>NotFound`.
6. On other 4xx, raise `<Service>ClientRejected(status_code, message)` carrying the upstream message extracted from `{"error": {"message": ...}}` when present.

Callers then map these exceptions to HTTP responses using a consistent posture documented in comments: dependency-not-configured → 503, transport/upstream 5xx → 502, 4xx passed through verbatim. This is visible in `agent_service/api/v2/routes.py` where `_validate_skill_markdown` and incident assembly routes catch and re-raise as `HTTPException`.

## Route-level mapping to HTTP

Routers raise `fastapi.HTTPException(status_code=..., detail=...)` directly for user-facing errors (missing `X-User-ID` → 401, session/incident/document not found → 404, policy violations → 409). There are no global exception handlers registered — every route handler is responsible for converting domain exceptions into the appropriate HTTP status code before they escape. The `from None` chaining is used deliberately to drop the Python traceback from the logged exception chain when wrapping upstream errors into HTTP responses.

## Tool execution result envelope

The tool execution framework (SPEC-007) does not use exceptions for tool failures. Instead, `tool_gateway/tools/base.py` defines a frozen `ToolResult` dataclass with fields `tool_name`, `status` (`"success" | "error" | "denied"`), optional `data`, `evidence`, and optional `error` dict containing `code` and `message`. Two helpers construct canonical results:

- `make_error_result(tool_name, code, message, risk_level, source_system, duration_ms)` — returns `status="error"` with an evidence envelope built by `build_evidence()`.
- `make_denied_result(tool_name, reason, risk_level)` — returns `status="denied"` with `error.code = "POLICY_DENIED"`.

This keeps agent-side tool invocation deterministic: tools always return a `ToolResult`, never raise, so the execution runtime can record receipts uniformly.

## Degradation and bounded failure

Several paths implement explicit degradation:

- Shift summary reads secondary stores via `_safe_read(read)` which catches any exception, logs a warning, and returns `None` / `UNAVAILABLE`, allowing the digest to be assembled even when evidence sources fail.
- Skill-draft generation runs a generate → validate → one bounded regenerate → skeleton fallback sequence; if both generated and skeleton drafts fail validation, only then is a 502 raised. An unvalidated draft is never returned.
- Policy denials are surfaced as `ToolResult.status="denied"` rather than exceptions, so policy enforcement is part of the normal tool result stream.

## Conventions observed

- Domain errors are typed exceptions grouped under a per-module base class; raw `Exception` is avoided except for generic input-validation cases.
- Cross-service clients translate HTTP status codes into typed exceptions so callers branch on semantics.
- Routers convert those typed exceptions back into `HTTPException` with a stable status-code posture (503 for not configured, 502 for upstream failure, pass-through 4xx).
- Tool execution returns structured result envelopes (`ToolResult`) instead of raising, enabling deterministic agent control flow.
- Evidence envelopes accompany tool results to capture `executed_at`, `duration_ms`, `risk_level`, and `source_system` for auditability.
- Secrets are redacted before being included in error messages or display payloads via the `secret_params` module.