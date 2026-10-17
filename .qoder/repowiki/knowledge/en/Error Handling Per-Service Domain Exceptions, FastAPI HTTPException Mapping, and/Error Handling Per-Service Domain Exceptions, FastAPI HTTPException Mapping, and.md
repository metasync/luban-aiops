---
kind: error_handling
name: 'Error Handling: Per-Service Domain Exceptions, FastAPI HTTPException Mapping, and Protocol-Level Reason Codes'
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/services/policy_engine.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/execution-runtime/src/execution_runtime/services/execution_protocol.py
    - products/audit-service/src/audit_service/services/audit_store.py
    - products/incident-service/src/incident_service/services/triage.py
    - products/skills-hub/src/skills_hub/services/skill_store.py
---

## Approach

The Luban platform does not use a single shared error hierarchy. Each Python product service defines its own small set of domain exception classes (typically `*Error(Exception)` or `*Error(ValueError)`) and converts them to HTTP responses at the API boundary using FastAPI's `HTTPException`. There is no repository-wide base error class, no centralized exception handler, and no `panic`/`recover` equivalent — Python exceptions are the sole mechanism.

FastAPI's default exception handling is used; services register only an `http` middleware for request logging (`agent_service/app.py`, `platform_gateway/app.py`). The only custom `@app.exception_handler` in the repo lives in the sample app (`samples/acme-admin/app/src/acme_admin/main.py`), not in any production service.

## Key Files and Packages

**Agent Platform (`products/agent-platform/src/agent_service/`)**
- `services/execution_protocol.py` — defines `ProtocolError(ValueError)` with a string `reason` attribute; this is the canonical wire-level error type for signed execution envelopes. It carries reason codes such as `bad_request`, `protocol_unsupported`, `signing_unavailable`, `signature_invalid`, `lifetime_invalid`, `identity_conflict`, `response_invalid`, `metadata_replay`.
- `api/v2/routes.py` — the route layer that catches domain exceptions and raises `HTTPException(status_code=..., detail=...)`; it also maps `ProtocolError` to `400` (line 965) and re-raises client errors from downstream services by forwarding their `.status_code` and `.message` attributes (lines 1075–1080, 1244–1251).
- `runtime_kernel.py` — defines `UnknownModelError(ValueError)` with a docstring documenting the "selection fails closed" policy (SPEC-024 R-1).
- `providers/base.py` — defines `ProviderConfigurationError(ValueError)` raised when model provider configuration is invalid.
- `services/execution_worker_client.py` — `WorkerHandoffError(Exception)`.
- `services/incident_client.py` — `IncidentClientError(Exception)`.
- `services/skills_client.py` — `SkillsClientError(Exception)`.
- `services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`.

**Platform Gateway (`products/platform-gateway/src/platform_gateway/`)**
- `services/policy_engine.py` — `PolicyLoadError(Exception)` raised during YAML bundle parsing/validation.
- `services/token_verifier.py` — `TokenVerificationError(Exception)`.

**Other Services**
- `audit-service`: `StoreError`, `IngestAuthError`.
- `incident-service`: `SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`.
- `skills-hub`: `SettingsError`, `QueryAuthError`, `StoreError`.
- `execution-runtime`: `ProtocolError(ValueError)` mirroring the agent-platform protocol error shape.

## Architecture and Conventions

1. **Domain exceptions live next to the code that raises them.** There is no shared `errors/` package. Each product's `services/` directory contains its own `*Error` classes, typically one per subsystem (store, auth, config, triage, etc.).

2. **Two-tier error taxonomy:**
   - Configuration / validation failures subclass `ValueError` (e.g. `ProviderConfigurationError`, `UnknownModelError`, `ProtocolError`). This lets callers distinguish user-input/config problems from unexpected runtime failures.
   - Client-call / infrastructure failures subclass plain `Exception` (e.g. `IncidentClientError`, `SkillsClientError`, `WorkerHandoffError`, `PolicyLoadError`).

3. **Wire-level protocol errors carry a stable reason code.** `ProtocolError.reason` is a short string constant (`bad_request`, `signature_invalid`, …). Callers match on the exception type rather than inspecting the message, so the reason code is for observability/logging, not branching logic.

4. **HTTP mapping is explicit at each route.** Routes catch known domain exceptions and raise `HTTPException` with a concrete status code:
   - `400` for bad input / `ProtocolError`.
   - `401` for missing auth headers.
   - `404` for foreign/unknown resources (the "anti-enumeration house convention", documented in route docstrings).
   - `409` for conflict states (parked confirmations, missing validated triage report).
   - `502` for unreachable upstreams.
   - `503` for features not configured (skills validation, incident service, model discovery).
   - Downstream client errors are forwarded via `exc.status_code` / `exc.message` when the client wrapper exposes those attributes.

5. **Failure-degradation patterns are documented in route docstrings.** Examples include SPEC-044 skill-draft generation: generation never raises — failures degrade to a facts-only skeleton, a second validation failure returns `502`, and an unvalidated draft is never returned. Similar language appears across routes for session deletion, title renaming, and recovery queries.

6. **No global exception handler.** FastAPI's default JSON error response is used. Logging happens uniformly through the `log_requests` middleware which records `method`, `path`, `status_code`, `duration_ms`, and `request_id` for every response, including error responses.

7. **Structured logging over exception strings.** Errors are logged via `log_event` (from `core/observability.py`) with structured fields (`service`, `request_id`, `session_id`, `user_id`, etc.) rather than raw traceback dumps.

## Conventions and Constraints

- **Observed convention:** Domain-specific failures are modeled as dedicated exception subclasses rather than reused `ValueError`/`RuntimeError` instances. This pattern holds across all nine Python products.
- **Observed convention:** `ProtocolError` is the shared vocabulary for signed-execution envelope validation failures and is defined independently in both `agent_platform` and `execution_runtime`.
- **Observed convention:** Route handlers convert domain exceptions to `HTTPException` with explicit status codes; they do not let domain exceptions bubble out of the router.
- **Observed convention:** Unknown or foreign resource IDs return structural `404`s (documented as the "anti-enumeration house convention") instead of leaking existence information.
- **Documented rule (SPEC-024 R-1):** Model selection fails closed — `UnknownModelError` must be mapped to a 4xx response; the kernel never silently falls back to the default model.
- **Documented rule (SPEC-044, route docstrings):** Skill-draft generation degrades to a skeleton on failure; a second validation failure answers `502`; an unvalidated draft is never returned.
- **Enforced by implementation:** `VerifiedOriginal` in `execution_protocol.py` rejects copy/deepcopy/reduction operations (`TypeError`) and cross-process replay (`ProtocolError("response_invalid")`), enforcing that validated original responses cannot leave their process boundary.
- **Not enforced centrally:** There is no lint rule, CI check, or base class requiring new errors to inherit from a common root. The convention is cultural, not structural.