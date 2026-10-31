---
kind: error_handling
name: Error Handling — Structured Exception Hierarchy and HTTP Posture Mapping
category: error_handling
scope:
    - '**'
source_files:
    - products/agent-platform/src/agent_service/services/skills_client.py
    - products/agent-platform/src/agent_service/services/incident_client.py
    - products/agent-platform/src/agent_service/api/v2/routes.py
    - products/agent-platform/src/agent_service/app.py
    - products/platform-gateway/src/platform_gateway/app.py
    - products/agent-platform/src/agent_service/providers/base.py
    - products/agent-platform/src/agent_service/runtime_kernel.py
    - products/agent-platform/src/agent_service/services/execution_protocol.py
    - products/agent-platform/src/agent_service/core/telemetry.py
---

## Approach

The Luban platform uses a **structured exception hierarchy** per product, with FastAPI `HTTPException` as the sole transport boundary. There is no centralized error middleware (`@app.exception_handler`) — instead, each route handler catches domain-specific exceptions and maps them to HTTP status codes inline. The pattern is most consistent in the agent-platform's outbound clients (skills-hub, incident-service), where every client defines a small base class plus three or four subclasses that encode the "house posture": dependency-not-configured → 503, transport/upstream-5xx → 502, upstream 4xx passed through, and business errors like `NotFound` mapped to their structural code.

## Key Files and Packages

- `products/agent-platform/src/agent_service/services/skills_client.py` — `SkillsClientError` base + `SkillsDependencyNotConfigured`, `SkillsServiceUnavailable`, `SkillsClientRejected` (with `status_code`, `message` attributes).
- `products/agent-platform/src/agent_service/services/incident_client.py` — `IncidentClientError` base + `IncidentDependencyNotConfigured`, `IncidentServiceUnavailable`, `IncidentNotFound` (with `incident_id` attribute), `IncidentClientRejected`.
- `products/agent-platform/src/agent_service/api/v2/routes.py` — central mapping site; `_validate_skill_markdown` and the incident-draft route translate the above exceptions into 503/502/404/409/`exc.status_code` responses.
- `products/agent-platform/src/agent_service/providers/base.py` — `ProviderConfigurationError(ValueError)` for LLM provider misconfiguration.
- `products/agent-platform/src/agent_service/runtime_kernel.py` — `UnknownModelError(ValueError)`.
- `products/agent-platform/src/agent_service/services/execution_protocol.py` — `ProtocolError(ValueError)`.
- `products/agent-platform/src/agent_service/services/execution_worker_client.py` — `WorkerHandoffError(Exception)`.
- `products/agent-platform/src/agent_service/services/shift_summary.py` — `DigestInputError`, `UnknownSessionError`.
- Per-product equivalents: `audit-service` (`StoreError`, `IngestAuthError`), `identity-broker` (`ExchangeError`), `incident-service` (`SettingsError`, `ConnectorConfigError`, `StoreError`, `NormalizationError`, `QueryAuthError`, `TriageError`), `platform-gateway` (`PolicyLoadError`, `TokenVerificationError`), `skills-hub` (`SettingsError`, `QueryAuthError`, `StoreError`), `tool-gateway` (`CustodyError`, `PolicyLoadError`).

## Architecture and Conventions

1. **Domain exceptions live next to the service layer**, not at the API layer. Each client module owns its exception hierarchy (e.g. `services/skills_client.py`, `services/incident_client.py`).
2. **Base classes are minimal**: either `Exception` (for cross-service clients) or `ValueError` (for configuration/validation failures). They carry no extra behavior beyond the documented attributes (`status_code`, `message`, `incident_id`).
3. **Outbound HTTP calls wrap `httpx.HTTPError`** into `*ServiceUnavailable` and classify response codes: ≥500 → unavailable, 4xx → `*Rejected` carrying the original status code and an extracted `error.message` from the upstream JSON payload (see `_upstream_message` helpers in both clients).
4. **Route handlers perform the posture mapping**. In `api/v2/routes.py`, the `_validate_skill_markdown` helper and the incident-draft route catch each structured exception and raise `HTTPException(status_code=..., detail=...)`. The docstrings explicitly state the invariant: "validation not configured 503, unreachable 502 — an unvalidated draft is never returned."
5. **No global exception handler exists** in any of the main services (`agent_service/app.py`, `platform_gateway/app.py`). Both only register an HTTP logging middleware that records `status_code` after `call_next`; they do not transform exceptions.
6. **Telemetry paths swallow all exceptions** via broad `except Exception:` blocks (e.g. `core/telemetry.py` around metric emission, `entrypoints/runtime.py` around optional imports), so observability failures cannot crash request handling.
7. **Validation/configuration errors use `ValueError`** rather than custom types when they originate from Pydantic-style settings validation (`runtime_settings.py` raises `ValueError` for bad booleans, enums, ranges like `AGENTSCOPE_MAX_ITERS >= 1`).
8. **Test fixtures mirror production patterns**: failure tests under `products/execution-runtime/tests/failure/support/infrastructure.py` define `PrerequisiteError(RuntimeError)` for test setup failures, and `products/skills-hub/tests/support/postgres_infra.py` does the same.

## Conventions and Constraints

- **Observed convention**: Every outbound client defines a base `*ClientError(Exception)` plus `*DependencyNotConfigured`, `*ServiceUnavailable`, and `*ClientRejected` subclasses. This is enforced by the route-level try/except blocks that catch exactly those names — adding a new exception without a corresponding branch leaves it unhandled and would surface as a raw traceback.
- **Observed convention**: Upstream 4xx responses are re-raised as `*ClientRejected(status_code, message)` so the caller can pass the original status through unchanged; this is how unknown incident IDs become the same structural 404 the incidents service returns.
- **Observed constraint**: Skill-draft generation guarantees format validity. The `_validated_draft_sequence` function performs one bounded regeneration on first validation failure and always falls back to a skeleton if the second attempt fails, raising 502 only when even the skeleton fails validation — the comment states "an unvalidated draft is never returned."
- **Observed constraint**: Telemetry/metric emission is wrapped in `try/except Exception:` blocks so failures in OpenTelemetry or Prometheus exporters cannot propagate to request handlers.
- **Not enforced centrally**: There is no shared base error type across products, no global FastAPI exception handler, and no error-code enumeration. Each product independently defines its own `*Error` classes.
- **Author guidelines**: No author directive excludes error handling from knowledge production.