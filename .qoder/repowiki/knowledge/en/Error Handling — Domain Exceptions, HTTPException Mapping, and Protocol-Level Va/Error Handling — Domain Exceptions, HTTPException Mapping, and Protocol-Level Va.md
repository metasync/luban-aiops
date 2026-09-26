---
kind: error_handling
name: Error Handling — Domain Exceptions, HTTPException Mapping, and Protocol-Level Validation Errors
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
---

## Approach

The Luban platform uses a layered Python exception model rather than a single framework-level error system:

1. **Domain / service-layer exceptions** (per-product) represent business failures such as missing configuration, unavailable dependencies, or invalid input.
2. **Protocol-level validation errors** (`ProtocolError`) are used inside the agent-platform's execution protocol layer to signal malformed signed envelopes.
3. **FastAPI `HTTPException`** is the sole transport boundary: route handlers catch domain/protocol exceptions and translate them into HTTP status codes with human-readable `detail` strings.
4. There is no repository-wide custom exception handler registered via `@app.exception_handler`; each product's API routes perform explicit try/except blocks around service calls.
5. No `panic`/`recover` equivalent is used — this is pure Python.

## Key files and packages

- `products/agent-platform/src/agent_service/services/execution_protocol.py` — defines `ProtocolError(ValueError)` with a string `reason` attribute; all envelope/schema/signature/lifetime checks raise it with stable reason codes (`bad_request`, `protocol_unsupported`, `signing_unavailable`, `signature_invalid`, `lifetime_invalid`, `identity_conflict`, `response_invalid`, `metadata_replay`).
- `products/agent-platform/src/agent_service/providers/base.py` — defines `ProviderConfigurationError(ValueError)` for incomplete/invalid provider settings; raised by every concrete provider adapter (dashscope, deepseek, luban, openai).
- `products/agent-platform/src/agent_service/api/v2/routes.py` — the central translation point where `ProtocolError`, `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected`, `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected`, `NoValidatedTriageReport`, `UnknownSessionError`, `DigestInputError` are caught and re-raised as `HTTPException` with an explicit `status_code` and `detail`.
- Per-product `core/runtime.py` (platform-gateway, tool-gateway) silently swallow `ValueError` from environment parsing (e.g. Kubernetes `tcp://IP:PORT` ports) and fall back to defaults — not an error path, but part of the overall resilience pattern.

## Architecture and conventions

### Domain exceptions carry structured context

Domain exceptions in the agent-platform follow a consistent shape:

- `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` — raised by the skills client; `SkillsClientRejected` exposes `status_code` and `message` attributes so the route can pass through the upstream's HTTP code verbatim.
- `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound`, `IncidentClientRejected` — same shape for incident-service calls.
- `UnknownSessionError`, `DigestInputError` — raised by session/document helpers.

These are defined in the relevant service/client modules and imported at the route layer only.

### Route-layer mapping is explicit, not centralized

In `routes.py`, the pattern is uniform:

```python
try:
    return await some_service_call(...)
except SkillsDependencyNotConfigured as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from None
except SkillsServiceUnavailable as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from None
except SkillsClientRejected as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

Key observations:
- `from None` is used on almost every translated `HTTPException` to suppress the internal traceback in production logs while preserving the original exception chain when appropriate (e.g. `IncidentNotFound` keeps `from exc`).
- Client-rejection exceptions (`*ClientRejected`) are passed through with their upstream `status_code` and `message` intact.
- Dependency-not-configured maps to 503; unreachable/unavailable maps to 502; not-found maps to 404; protocol/validation errors map to 400.

### Protocol errors use stable string reason codes

`ProtocolError.reason` is a short machine-parseable token (`bad_request`, `signature_invalid`, etc.). The route layer catches `ProtocolError` generically and returns `400 Invalid recovery query` — the specific reason is logged internally but not exposed over HTTP. This keeps wire responses stable while allowing callers to distinguish failure modes in logs.

### Provider configuration errors are application-level, not HTTP-level

`ProviderConfigurationError` is raised during startup/provider resolution and is not caught by route handlers — it bubbles up as an unhandled exception, which FastAPI renders as a 500. This is intentional: misconfiguration is a deployment-time error, not a per-request user error.

### Schema validation errors become `ProtocolError`

The JSON Schema validators in `execution_protocol.validate()` wrap any `jsonschema` validation failure (plus `ValueError`, `TypeError`, `RecursionError` from canonical JSON serialization) into `ProtocolError("bad_request")`, normalizing third-party library exceptions into the domain error type.

### Conventions observed

- Domain exceptions subclass `ValueError` (not a custom base class), keeping them lightweight and compatible with standard Python control flow.
- Every route that calls another product's service wraps the call in a try/except block that maps each known exception to a specific HTTP status code.
- `from None` is consistently used when translating exceptions to `HTTPException` to avoid leaking stack traces in the response body.
- Stable, lowercase-dashed reason codes are preferred over free-form messages in protocol/domain errors (`bad_request`, `signature_invalid`, `lifetime_invalid`, `identity_conflict`, `response_invalid`, `metadata_replay`).
- Human-facing messages live in `HTTPException.detail`; machine-parseable identifiers live in `.reason` or `.message` attributes of domain exceptions.
- No global exception middleware is registered; error translation is localized to each route function.
- Configuration and startup-time validation errors are allowed to propagate as unhandled exceptions (producing 500s) rather than being converted to 4xx/5xx responses.

### Constraints enforced by the code

- A validated skill draft is never returned without passing format validation: if generation fails, the code falls back to a facts-only skeleton; if even the skeleton fails validation, it raises 502 (`skill-draft skeleton failed format validation`). This invariant is documented in the route docstrings and enforced by `_validated_draft_sequence`.
- Unknown sessions always answer structural 404 regardless of authorization posture; foreign-session ownership is re-checked server-side after gateway authorization.
- Recovery queries that fail protocol validation are rejected with 400 before any state mutation.
- Upstream `*ClientRejected` exceptions preserve their original HTTP status code and message verbatim, ensuring cross-service error semantics are not lost at the boundary.