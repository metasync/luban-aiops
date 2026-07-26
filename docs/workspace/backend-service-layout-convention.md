# Backend Service Layout Convention

This document defines the recommended repository layout for backend products that expose HTTP service boundaries in this workspace.

## Goal

Use a consistent structure for backend services so that:

- route surfaces stay small and easy to review
- configuration is centralized
- business and integration logic stay outside `FastAPI` route handlers
- tests can target route, service, and logic layers independently
- new products start from the same baseline instead of inventing a different layout every time

## Scope

This convention applies to backend products such as:

- `tool-gateway`
- `identity-broker`
- future service-oriented implementations of `policy-center`, `skills-hub`, and the HTTP edge of `execution-runtime`

This convention does not strictly apply to:

- `operator-portal`, which is currently frontend-oriented
- `agent-platform`, whose internal structure is partly runtime-engine oriented because it must host both transitional and native `AgentScope` entrypoints

## Recommended Layout

```text
src/<service_package>/
  __init__.py
  main.py
  app.py
  api/
    __init__.py
    router.py
    routes/
      __init__.py
      health.py
      ...
  core/
    __init__.py
    config.py
    ...
  schemas/
    __init__.py
    ...
  services/
    __init__.py
    ...
  clients/
    __init__.py
    ...
tests/
  ...
```

## Layer Responsibilities

### `main.py`

- thin runtime bootstrap only
- should primarily expose `run()` and reference the assembled app
- should avoid carrying route, config, or business logic

### `app.py`

- creates the `FastAPI` application
- wires the top-level router
- owns application metadata such as service title and version
- should prefer human-facing metadata such as `SERVICE_TITLE`

### `api/router.py`

- aggregates route modules into the application router
- should not contain downstream integration or orchestration logic

### `api/routes/`

- one route module per cohesive HTTP surface
- route handlers should stay thin
- route handlers may:
  - read request data
  - resolve dependencies
  - call service-layer functions
- route handlers should not own orchestration logic or provider-specific decision trees

### `core/`

- shared infrastructure concerns for the service package
- examples:
  - env-backed settings
  - runtime host and port settings
  - request context helpers
  - shared dependency factories

### Metadata naming

- `SERVICE_NAME`
  - stable machine-facing service identifier for health payloads, runtime payloads, and internal metadata
- `SERVICE_TITLE`
  - human-facing label for `FastAPI(title=...)`, generated docs, and similar presentation-oriented surfaces

### Surface-specific environment names

- when a product exposes more than one runtime surface, prefer surface-specific env names over overloaded shared names
- remove old env names entirely once the project is still pre-release and the new surface-specific names are established
- example:
  - transitional HTTP surface: `AGENT_TRANSITIONAL_*`
  - native runtime surface: `AGENT_NATIVE_*`

### `schemas/`

- request and response models
- protocol-facing typed objects
- keeps route contracts separate from orchestration and integration code

### `services/`

- application and orchestration logic
- examples:
  - identity normalization logic
  - backend resolution
  - request translation
  - provider selection

### `clients/`

- optional package for downstream HTTP or SDK integrations
- add this layer when a service begins calling other services or external providers in more than a trivial way
- do not add it preemptively when no real client abstraction exists yet

### `tests/`

- focused tests that match the current level of implementation maturity
- prefer targeted tests for:
  - service-layer logic
  - config parsing
  - route behavior that encodes contract decisions

## Decision Rules

Use these rules when deciding whether to create a new module:

- create a new route module when an endpoint group forms a distinct API surface
- create a new service module when logic is reused or when route handlers become orchestration-heavy
- create a `clients/` package only when downstream integration code becomes a real subsystem
- do not split into many tiny files unless there is clear behavioral or ownership value

## Current Reference Implementations

- `products/tool-gateway`
  - reference pattern for `FastAPI` service layering with route, core, and service modules
- `products/identity-broker`
  - reference pattern for a smaller backend service using the same layering
- `products/agent-platform`
  - special-case runtime service that still benefits from the spirit of this convention, but should preserve its runtime-oriented package split

## Adoption Guidance

Apply this convention incrementally:

1. start with `main.py`, `app.py`, `api/routes/`, `core/`, and `services/`
2. add `schemas/` when request and response models grow beyond a few inline classes
3. add `clients/` when the service owns nontrivial downstream integrations
4. keep the package flatter if the service remains intentionally small

The objective is consistency and clarity, not uniformity for its own sake.

## Python Toolchain Convention

For Python backend products in this workspace:

- standardize on `uv` for interpreter, virtual environment, and package management
- pin the preferred Python interpreter with `.python-version`
- keep a product-local `.python-version` when container builds use the product directory as the Docker build context
- use `uv.lock` with `uv sync --frozen` in deterministic build paths

The current backend container images still use the official `uv` Python base image for simplicity and compatibility. A future CI-aligned container strategy may install `uv` on top of an environment-specific base image and allow `uv` to resolve the interpreter from `.python-version`, as long as the resulting images remain reproducible and operationally supportable.

See `python-container-strategy.md` for the current recommendation, trade-offs, and migration criteria.
