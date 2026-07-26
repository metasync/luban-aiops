# Identity Broker

## Purpose

`identity-broker` normalizes enterprise identity for the platform.

It is responsible for:

- `Keycloak` integration
- `AD` federation handling
- group and role normalization
- identity context propagation
- service-consumable identity claims

## Ownership

Recommended owner:

- identity and platform access team

## Current Scope

This project currently provides the workspace placeholder and boundary definition for:

- enterprise `SSO` entry and token normalization
- group-to-role mapping and identity enrichment
- downstream identity context propagation
- platform-wide identity contract alignment

Current implementation artifacts:

- `pyproject.toml`
- `Dockerfile`
- `src/identity_service/app.py`
- `src/identity_service/api/routes/`
- `src/identity_service/core/`
- `src/identity_service/schemas/`
- `src/identity_service/services/`
- `tests/test_identity_service.py`

Current scaffold status:

- organizes the `FastAPI` package by app bootstrap, route modules, config helpers, schemas, and normalization services
- keeps `main.py` as a thin runtime bootstrap entrypoint
- centralizes `Keycloak` and `OIDC` login URL construction behind settings-aware service code
- isolates group-to-role mapping and identity normalization from the HTTP route layer
- adds focused tests for role normalization and login URL composition

## Expected Integration Points

- `operator-portal` for login initiation and session establishment
- `agent-platform` for normalized user identity context
- `policy-center` for role and group inputs to authorization
- `shared/shared-contracts` and `shared/shared-sdk` for auth-related models and helpers

## Boundary

This project does not make authorization decisions and does not own operator-facing portal behavior.
