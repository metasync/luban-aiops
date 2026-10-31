---
kind: error_handling
name: 'Cross-Service Error Handling: Domain Exceptions, FastAPI HTTPException Mapping, and Upstream Posture Normalization'
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/platform-gateway/src/platform_gateway/services/gateway_service.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/audit-service/src/audit_service/services/ingest_auth.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/incident_store.py
    - products/incident-service/src/incident_service/services/normalization.py
    - products/incident-service/src/incident_service/services/query_auth.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/skills-hub/src/skills_hub/core/config.py
    - products/skills-hub/src/skills_hub/services/query_auth.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
    - products/tool-gateway/src/tool_gateway/services/policy_engine.py
    - products/tool-gateway/src/tool_gateway/services/token_verifier.py
    - products/tool-gateway/src/tool_gateway/tools/password_policy.py
---

## Overview

The Luban platform is a multi-product Python workspace (agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway) that uses a consistent, layered error-handling model:

1. **Domain-level exceptions** — per-service `*Error` classes raised inside business logic.
2. **Wire-level protocol exceptions** — a small set of string-reason exceptions for inter-process contracts.
3. **HTTP boundary mapping** — routes convert domain/protocol exceptions into FastAPI `HTTPException`s with explicit status codes.
4. **Gateway posture normalization** — the platform-gateway translates upstream httpx failures into a stable house posture (4xx pass-through, transport/5xx → 502).

There is no centralized exception base class or global exception handler; each product defines its own hierarchy and maps at the route layer.

## Domain Exception Hierarchy

Each service declares one or more root exception types under which specific failure modes subclass:

| Service | Root exception | Notable subclasses |
|---|---|---|
| agent-platform | `IncidentClientError`, `SkillsClientError`, `WorkerHandoffError`, `DigestInputError`, `UnknownSessionError` | `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`; `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` |
| agent-platform providers | `ProviderConfigurationError(ValueError)` | raised from every provider adapter (`dashscope`, `deepseek`, `luban`, `openai`) when settings are missing |
| agent-platform kernel | `UnknownModelError(ValueError)` | selection fails closed — routes map to 4xx, never silently fall back |
| agent-platform execution protocol | `ProtocolError(ValueError)` with `.reason` | `bad_request`, `protocol_unsupported`, `signing_unavailable`, `signature_invalid`, `lifetime_invalid`, `identity_conflict`, `response_invalid`, `metadata_replay` |
| audit-service | `StoreError(Exception)`, `IngestAuthError(Exception)` |
| execution-runtime | `ProtocolError(ValueError)` (parallel to agent-platform) |
| identity-broker | `ExchangeError(Exception)` |
| incident-service | `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` |
| platform-gateway | `PolicyLoadError(Exception)`, `TokenVerificationError(Exception)` |
| skills-hub | `SettingsError`, `QueryAuthError`, `StoreError` |
| tool-gateway | `PolicyLoadError`, `TokenVerificationError`, `PasswordPolicyError` |

The shared pattern is `class XxxError(Exception)` (or `ValueError` for configuration/protocol cases) with a docstring describing the invariant violated. There is no single `PlatformError` base class.

## Protocol-Level Errors

`agent_service/services/execution_protocol.py` and `execution_runtime/services/execution_protocol.py` define a `ProtocolError(ValueError)` whose constructor takes a string `reason`. Validation helpers (`validate`, `timestamp`, `request_id`, `validate_request`, `validate_observation`, `_validate_original`) catch low-level `ValueError`/`TypeError`/`KeyError`/`RecursionError` and re-raise as `ProtocolError("bad_request" | "response_invalid" | …)`. This is the canonical wire-level error type between the agent platform and the execution worker; it carries a machine-readable reason rather than a human message.

## HTTP Boundary Mapping

FastAPI `HTTPException` is raised directly in route handlers. The primary example is `products/agent-platform/src/agent_service/api/v2/routes.py`, where client-facing endpoints follow a uniform shape:

```python
try:
    return await downstream_call(...)
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

Status-code semantics observed across the agent-platform routes:

- `401` — missing/invalid auth header (`X-User-ID`, bearer token).
- `404` — unknown/foreign session or incident (anti-enumeration posture).
- `409` — deterministic conflict (e.g. missing validated triage report before skill-draft generation).
- `422` — invalid recovery query / malformed input.
- `502` — upstream unreachable or 5xx response from a downstream service.
- `503` — optional dependency not configured (skills validation, incident ingestion).

The `from None` chaining suppresses the original traceback in the HTTP response body while preserving the cause chain internally.

## Gateway Posture Normalization

`platform_gateway/services/gateway_service.py` implements the cross-cutting house proxy error model. Every outbound call to a backend service follows the same pattern:

```python
try:
    return await agent_client.<op>(...)
except httpx.HTTPStatusError as exc:
    status = exc.response.status_code
    if 400 <= status < 500:
        raise HTTPException(status_code=status, detail=_upstream_detail(exc, ...)) from exc
    raise HTTPException(status_code=502, detail=...) from exc
except httpx.HTTPError as exc:
    raise HTTPException(status_code=502, detail="agent service unavailable") from exc
```

Rules enforced by this layer:

- Upstream 4xx (client errors such as unknown session, foreign-session denial, malformed input) pass through verbatim so anti-enumeration 404s and operator-refusal 409s reach the caller unchanged.
- Upstream 5xx and transport failures become `HTTPException(502, …)` — the gateway never answers a raw 500 to an operator.
- For draft/graduation/document paths, 502 and 503 are explicitly allowed to pass through because they carry the distinction between "unreachable" and "validation leg not configured", and an unvalidated draft is never returned regardless.
- `_upstream_detail` extracts the upstream JSON `detail` field when present; otherwise it falls back to a fixed English message.

Identity-specific behavior lives in `_identity_leg`: 4xx from the identity service pass through with their status and normalized detail; 5xx and transport errors become `HTTPException(502, "identity service unavailable — retry the sign-in")`.

## Configuration and Startup Errors

Per-service `SettingsError` (incident-service, skills-hub) and `ProviderConfigurationError` (agent-platform providers) signal startup-time misconfiguration. These are caught at readiness/liveness boundaries rather than propagated to clients — e.g., `gateway_service.ready_status` wraps policy bundle loading and agent health checks, returning `{"status": "degraded", …}` on `PolicyLoadError` or `httpx.HTTPError` instead of failing the process.

## Conventions Observed

- Domain exceptions are raised in services; HTTP conversion happens at the route/proxy layer. No service leaks raw domain exceptions to the wire.
- Client-facing errors use FastAPI `HTTPException` with explicit `status_code` and `detail`; there is no custom JSON envelope serializer.
- Downstream dependency failures are classified into three categories: `*DependencyNotConfigured` (503), `*ServiceUnavailable` (502), `*ClientRejected` (passthrough status + `exc.message`).
- Transport-layer failures (`httpx.HTTPError`) are always mapped to 502 in the gateway; only `httpx.HTTPStatusError` branches distinguish 4xx vs 5xx.
- Protocol-level validation errors use a string `reason` on `ProtocolError` rather than raising framework exceptions, enabling callers to inspect machine-readable failure modes.
- `UnknownModelError` enforces a fail-closed model-selection policy: routes must map it to 4xx; the kernel never silently falls back to a default model.
- `from None` is used consistently when converting domain exceptions to `HTTPException` to avoid leaking internal stack traces in the response body.
- No `try/except` around entire request handlers; error handling is localized to the function performing the failing operation.
- No `panic`/`recover` equivalent (Python); `RuntimeError` is reserved for unrecoverable conditions (e.g. empty LLM reply, runtime setup failures).

## Key Files

- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError` base for all provider adapters.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError` and kernel-level domain errors.
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError` and wire contract validation.
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError` hierarchy.
- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError` hierarchy.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — primary HTTP-to-domain exception mapper.
- `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — house proxy posture normalization (4xx passthrough, 5xx→502).
- `products/audit-service/src/audit_service/services/audit_store.py` — `StoreError`.
- `products/audit-service/src/audit_service/services/ingest_auth.py` — `IngestAuthError`.
- `products/execution-runtime/src/execution_runtime/services/execution_protocol.py` — parallel `ProtocolError`.
- `products/identity-broker/src/identity_service/services/exchange_service.py` — `ExchangeError`.
- `products/incident-service/src/incident_service/core/config.py` — `SettingsError`.
- `products/incident-service/src/incident_service/services/connectors.py` — `ConnectorConfigError`.
- `products/incident-service/src/incident_service/services/incident_store.py` — `StoreError`.
- `products/incident-service/src/incident_service/services/normalization.py` — `NormalizationError`.
- `products/incident-service/src/incident_service/services/query_auth.py` — `QueryAuthError`.
- `products/incident-service/src/incident_service/services/triage.py` — `TriageError`.
- `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — `PolicyLoadError`.
- `products/platform-gateway/src/platform_gateway/services/token_verifier.py` — `TokenVerificationError`.
- `products/skills-hub/src/skills_hub/core/config.py` — `SettingsError`.
- `products/skills-hub/src/skills_hub/services/query_auth.py` — `QueryAuthError`.
- `products/skills-hub/src/skills_hub/services/skill_store.py` — `StoreError`.
- `products/tool-gateway/src/tool_gateway/services/policy_engine.py` — `PolicyLoadError`.
- `products/tool-gateway/src/tool_gateway/services/token_verifier.py` — `TokenVerificationError`.
- `products/tool-gateway/src/tool_gateway/tools/password_policy.py` — `PasswordPolicyError`.