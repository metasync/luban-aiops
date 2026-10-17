---
kind: error_handling
name: 'Error Handling Across Luban Services: Domain Exceptions, HTTPException Gateways, and Structured Tool Results'
category: error_handling
scope:
    - '**'
source_files:
    - products/tool-gateway/src/tool_gateway/tools/base.py
    - products/tool-gateway/src/tool_gateway/services/gateway_service.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - products/platform-gateway/src/platform_gateway/api/routes/audit.py
    - products/platform-gateway/src/platform_gateway/api/routes/incidents.py
    - products/platform-gateway/src/platform_gateway/api/routes/policy.py
    - products/platform-gateway/src/platform_gateway/api/routes/tools.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/incident-service/src/incident_service/services/connectors.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
---

## Overview

The Luban platform uses a layered error model that separates three concerns:

1. **Domain-level exceptions** raised inside services (per-product `*Error` classes).
2. **HTTP-layer errors** surfaced by FastAPI routes via `fastapi.HTTPException`.
3. **Structured tool-result envelopes** (`ToolResult`) used for tool invocations, policy denials, and redaction failures.

There is no repository-wide exception base class, no centralized `errors/` package, and no global `exception_handler` registration — each product owns its own exception hierarchy and its own route-level error mapping.

## Domain Exception Classes

Each Python product defines small, purpose-specific exception subclasses of `Exception` or `ValueError`, typically one per service module:

- `agent-platform`: `ProviderConfigurationError`, `UnknownModelError`, `ProtocolError`, `WorkerHandoffError`, `IncidentClientError`, `SkillsClientError`, `DigestInputError`, `UnknownSessionError`
- `execution-runtime`: `ProtocolError(ValueError)` with a stable `reason` attribute; only closed reason codes cross the service/logging boundary (`bad_request`, `protocol_unsupported`, `signing_unavailable`, `signature_invalid`, `lifetime_invalid`, `identity_conflict`).
- `audit-service`: `StoreError`, `IngestAuthError`
- `incident-service`: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`
- `platform-gateway`: `PolicyLoadError`, `TokenVerificationError`
- `identity-broker`: `ExchangeError`

These are raised in business logic and caught at the API layer where they are translated into HTTP responses. There is no shared inheritance between products' error types.

## HTTP Layer: `HTTPException` as the Outbound Boundary

FastAPI's `HTTPException` is the universal outbound error type. Routes raise it directly with explicit `status_code` and human-readable `detail` strings. The pattern is consistent across all gateway-style services:

- `401` for missing/malformed/bearer-token verification failures (`tool_gateway/services/gateway_service.py`, `platform_gateway/api/routes/*.py`).
- `403` for policy denials (`enforce_policy` raises `HTTPException(status_code=403, detail={...})` carrying `action`, `reason`, and matched rule IDs).
- `400` for malformed requests / validation failures.
- `502` for upstream service transport errors (`httpx.HTTPError` caught and re-raised as `"service unavailable"`).
- `503` for configuration-missing states (e.g. `audit service not configured`).

The platform-gateway proxy routes (`products/platform-gateway/src/platform_gateway/api/routes/audit.py`) implement a deliberate passthrough rule: client errors from downstream services (4xx) are forwarded with their original status code so operators can distinguish bad input from an outage, while 5xx and network errors are collapsed to `502 audit service query/summary/export failed`. This is documented inline in the source comments.

No `@app.exception_handler` decorators exist anywhere in the codebase; FastAPI's default JSON error response format is used.

## Structured Tool Results

The tool execution framework has its own non-HTTP error representation defined in `products/tool-gateway/src/tool_gateway/tools/base.py`:

```python
@dataclass
class ToolResult:
    tool_name: str
    status: str  # "success" | "error" | "denied"
    data: dict | None = None
    evidence: dict = field(default_factory=dict)
    error: dict | None = None
```

Two factory functions build canonical error/denial envelopes:

- `make_error_result(tool_name, code, message, risk_level, source_system, duration_ms)` → `status="error"` with `error={"code": ..., "message": ...}`.
- `make_denied_result(tool_name, reason, risk_level)` → `status="denied"` with `error={"code": "POLICY_DENIED", "message": reason}`.

`BaseTool.execute()` returns `ToolResult`; there is no convention of raising exceptions from tool implementations. Errors are represented as structured data, which lets the caller map them to HTTP status codes uniformly:

```python
status_code = 200 if result.status == "success" else 400
if result.status == "denied":
    status_code = 403
return JSONResponse(content=result.to_dict(), status_code=status_code)
```

Redaction overflow is treated as a tool error with code `REDACTION_OVERFLOW` rather than an exception, keeping the response envelope consistent.

## Error Propagation Between Services

Cross-service communication goes through `httpx.AsyncClient` calls wrapped in try/except blocks that catch `httpx.HTTPError` and convert it to `HTTPException(502, ...)`. Downstream service responses are inspected by status-code range before being passed through or mapped. No custom retry or circuit-breaker wrapper is present in the observed routes.

Within a single process, domain exceptions propagate up the call stack until a route handler catches them and translates them to `HTTPException`. There is no middleware-based interceptor.

## Observability Integration

Errors are not just returned — they are logged with structured context via `log_event` / `LOGGER.warning` before being raised or returned. Policy denials, token verification failures, redaction overflows, and upstream outages all emit structured logs including `request_id`, `subject`, `username`, `roles`, and the failing action. The execution-runtime's `ProtocolError` comment explicitly documents the design choice: "Only closed reason codes cross the service/logging boundary."

## Conventions Observed

- Domain exceptions are narrow, per-module classes inheriting from `Exception` or `ValueError`; there is no shared base.
- HTTP boundaries use `fastapi.HTTPException` with explicit numeric `status_code` values; no custom exception-to-status mapping exists.
- Tool execution results never raise exceptions outward — they return `ToolResult` with `status ∈ {"success", "error", "denied"}`.
- Policy denials consistently produce `403` with a structured `detail` payload containing `action`, `reason`, and `matched_rule_ids`.
- Upstream transport failures are normalized to `502`; missing configuration normalizes to `503`.
- Cross-service protocol validation errors use closed string reason codes (`ProtocolError.reason`) rather than leaking raw exception messages.
- Redaction overflow is modeled as a tool error (`REDACTION_OVERFLOW`) rather than an exception, preserving the tool-result contract.
- Tests assert on these error surfaces (e.g. `test_chat_stream_modality.py` `ChatStreamErrorPropagationTests`, `test_incidents_proxy.py` `IncidentsProxyErrorTests`, failure-test matrix under `execution-runtime/tests/failure/`).

## Constraints Enforced by Code

- `VALID_RISK_LEVELS = frozenset({"read", "write", "admin"})` in `tools/base.py` enforces the static risk-tier vocabulary.
- `ProtocolError` in `execution_runtime/services/execution_protocol.py` is the only allowed exception type crossing the signed-envelope boundary; all validation paths funnel through it with closed reason strings.
- `ToolResult.status` is constrained by callers to map exactly to 200/400/403.
- Proxy routes in `platform_gateway/api/routes/audit.py` enforce the 4xx-pass-through / 5xx→502 rule documented in the route comments.