---
kind: error_handling
name: 'Error Handling Across Luban Services: FastAPI HTTPException + Domain-Specific Exception Classes'
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/services/execution_worker_client.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/platform-gateway/src/platform_gateway/services/token_verifier.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/api/routes/auth.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/session_service.py
    - products/identity-broker/src/identity_service/services/exchange_service.py
    - products/incident-service/src/incident_service/core/config.py
---

## Approach

The Luban workspace is a multi-product Python platform (FastAPI services) with no single shared error package. Error handling is implemented per product using two complementary patterns:

1. **HTTP boundary errors** — `fastapi.HTTPException` raised directly in route handlers to translate domain failures into HTTP status codes.
2. **Domain / transport-layer exceptions** — per-service exception classes that carry structured metadata (often a `reason` string) and are caught by callers, which then map them to either `HTTPException` or structured responses.

There is no repository-wide base error class, no centralized exception-to-HTTP mapping middleware, and no `panic`/`recover` equivalent (Python has none). Each service owns its own error taxonomy.

## Key Files and Packages

### Agent Platform (`products/agent-platform/src/agent_service/`)

- `src/agent_service/api/v2/routes.py` — the primary place where domain exceptions are converted to `HTTPException`. It raises `401` for missing/invalid identity headers, `404` for missing sessions/incidents/documents, `422` for validation gaps, `502`/`503` for downstream transport failures, and re-raises an upstream exception's `status_code`/`message` when available.
- `src/agent_service/services/execution_worker_client.py` — defines `WorkerHandoffError(Exception)` and `WorkerHandoffTimeout(Exception)`, both carrying a `reason` attribute; the module-level constant `REASON_WORKER_UNAVAILABLE = "worker_unavailable"` is the canonical fail-closed reason used when configuration is missing or the worker is unreachable.
- `src/agent_service/services/execution_protocol.py` — defines `ProtocolError(ValueError)` used as the protocol-layer sentinel for signed execution handoff validation failures.
- Per-domain exception classes scattered under `services/`: `AgentRoleError`, `DelegatedIdentityError`, `DigestInputError`, `UnknownSessionError`, `SkillsClientError`, `IncidentClientError`, `ProviderConfigurationError`, `UnknownModelError`.

### Platform Gateway (`products/platform-gateway/src/platform_gateway/`)

- `src/platform_gateway/services/token_verifier.py` — defines `TokenVerificationError(Exception)`; callers catch it and return `{"authenticated": False}` rather than raising (e.g. `auth.py`).
- `src/platform_gateway/services/policy_engine.py` — defines `PolicyLoadError(Exception)` for policy loading failures.
- Routes in this service generally do not raise `HTTPException`; they propagate domain exceptions upward or return structured dicts.

### Other Products

- `identity-broker`: `ExchangeError` in `exchange_service.py`; `HTTPException(502)` for OIDC exchange failures.
- `incident-service`: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError` — one per service file.
- `audit-service`: `StoreError`, `IngestAuthError`.
- `skills-hub`: `SettingsError`.
- `execution-runtime`: `ProtocolError` mirroring the agent-platform counterpart.

## Architecture and Conventions

### Two-tier exception model

Callers distinguish between *rejection* (the request is invalid or unauthorized) and *failure* (a dependency is unavailable):

```python
# Fail-closed transport failure → WorkerHandoffError(reason="worker_unavailable")
except httpx.HTTPError as exc:
    LOGGER.warning("execution handoff transport failure: %s", exc.__class__.__name__)
    raise WorkerHandoffError(REASON_WORKER_UNAVAILABLE, "execution worker is unreachable") from exc
```

A timeout is kept separate from a rejection so the resumed stream can surface a structured `timeout` receipt instead of treating it as a normal refusal:

```python
except httpx.TimeoutException as exc:
    raise WorkerHandoffTimeout("execution handoff timed out before the worker answered") from exc
```

### Structured reasons

Domain exceptions carry a machine-readable `reason` string alongside a human-readable message. The caller maps these to HTTP responses:

```python
raise HTTPException(status_code=exc.status_code, detail=exc.message) from None
```

This pattern appears in the agent-platform routes when forwarding upstream errors from the incident client, skills hub, and tool gateway.

### No global exception handler

No `@app.exception_handler` decorator is registered at the FastAPI app level across the codebase (only one occurrence exists in `samples/acme-admin/app/src/acme_admin/main.py`). Errors reach the FastAPI default JSON error response. There is no central error serialization layer.

### Logging convention on failures

Transport and network failures log via `LOGGER.warning(...)` before re-raising, and explicitly avoid logging raw payloads or URLs because they may contain credentials. For example:

```python
LOGGER.warning(
    "execution handoff transport failure: %s", exc.__class__.__name__
)
```

and

```python
LOGGER.warning("execution handoff rejected with status %d", response.status_code)
```

### Fail-closed posture

The `execution_worker_client.py` docstring documents the invariant: missing worker URL or handoff token raises before any network call with reason `worker_unavailable`; timeouts raise `WorkerHandoffTimeout`; transport errors raise `WorkerHandoffError`; verification rejections (4xx) carry the worker's reason back to the invocation boundary. There is no in-process fallback.

### Token verification returns booleans, not exceptions

In `platform_gateway/api/routes/auth.py`, `TokenVerificationError` is caught and translated to `{"authenticated": False}` rather than propagated, making authentication absence a normal control-flow result.

## Conventions and Constraints

- **Per-service exception classes**: each service defines its own `*Error` subclasses of `Exception` (or `ValueError` for value-validation cases like `ProtocolError`, `ProviderConfigurationError`, `UnknownModelError`). There is no shared base class.
- **Structured reasons**: domain exceptions that cross process boundaries include a `reason` attribute (see `WorkerHandoffError`) so callers can classify failures without parsing messages.
- **Route handlers raise `HTTPException` with explicit `status_code` and `detail`**; there is no custom exception-to-status-code registry.
- **Downstream transport failures are mapped to `502`/`503`** in the agent-platform routes, while `4xx` rejections from upstream services are forwarded verbatim via `exc.status_code`/`exc.message`.
- **Credentials are never logged**: the `execution_worker_client.py` comment and warning calls explicitly avoid logging URLs or payload content.
- **No global error middleware**: FastAPI's default exception handling is used; no repository-wide `exception_handler` registration was found outside samples.
- **Fail-closed is documented as an invariant** in `execution_worker_client.py` and enforced by raising before any I/O when configuration is absent.