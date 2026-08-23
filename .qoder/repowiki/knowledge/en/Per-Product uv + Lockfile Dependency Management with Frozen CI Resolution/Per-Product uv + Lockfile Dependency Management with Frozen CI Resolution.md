---
kind: dependency_management
name: Per-Product uv + Lockfile Dependency Management with Frozen CI Resolution
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - products/agent-platform/pyproject.toml
    - products/agent-platform/uv.lock
    - products/platform-gateway/pyproject.toml
    - products/platform-gateway/uv.lock
    - products/audit-service/pyproject.toml
    - products/audit-service/uv.lock
    - products/identity-broker/pyproject.toml
    - products/identity-broker/uv.lock
    - products/incident-service/pyproject.toml
    - products/incident-service/uv.lock
    - products/skills-hub/pyproject.toml
    - products/skills-hub/uv.lock
    - products/tool-gateway/pyproject.toml
    - products/tool-gateway/uv.lock
    - products/operator-portal/web-ui/app/package.json
    - products/operator-portal/web-ui/app/package-lock.json
    - shared/base-images/base-uv/Dockerfile
---

## System Overview

This monorepo manages dependencies per product using **uv** (Python) and **npm** (Node), each with its own `pyproject.toml` / `uv.lock` or `package.json` / `package-lock.json`. There is no workspace-level lockfile; every service under `products/` declares its own dependency graph, and shared Python packages are consumed as published versions from PyPI rather than via local path or editable installs.

## Python Dependencies (uv)

### Declaration files
- Each product has a `pyproject.toml` declaring runtime `dependencies`, optional `[dependency-groups].dev` for test-only packages, and a `[build-system]` pinning `uv_build>=0.8.14,<0.9.0` as the build backend.
- A matching `uv.lock` file lives alongside each `pyproject.toml` (e.g. `products/agent-platform/uv.lock`, `products/platform-gateway/uv.lock`, `products/audit-service/uv.lock`, `products/identity-broker/uv.lock`, `products/incident-service/uv.lock`, `products/skills-hub/uv.lock`, `products/tool-gateway/uv.lock`).
- The root `.python-version` pins the interpreter version used by the repo.

### Versioning conventions observed across all products
- All services target `requires-python = ">=3.11"`.
- Runtime dependencies use **pessimistic major-version pinning** (e.g. `fastapi>=0.115,<1.0`, `httpx>=0.27,<1.0`, `pydantic>=2.7,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `prometheus-client>=0.20,<1.0`, `uvicorn[standard]>=0.30,<1.0`, `PyJWT>=2.8,<3.0`, `cryptography>=43.0,<45.0`, `psycopg[binary]>=3.2,<4.0`, `redis>=6.2,<7.0`, `elasticsearch>=8.0,<9.0`, `kubernetes>=30.0,<33.0`). This allows patch/minor updates but blocks breaking changes.
- Dev-only tooling (`pytest`, `jsonschema`) is isolated in `[dependency-groups].dev` rather than mixed into runtime deps.
- Shared observability stack (`opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`, `opentelemetry-instrumentation-logging`, `opentelemetry-sdk`, `prometheus-client`) is pinned identically across every service.

### Resolution and reproducibility
- The shared Makefile include `mk/python.mk` defines `sync` and `test` targets that run `uv sync --frozen`, which enforces resolution strictly against the committed `uv.lock` — no network resolution at install time.
- The `test` target additionally sets `OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none` so OTLP exporters stay initialized for tracing tests without emitting telemetry during CI.

### No vendoring or private registry configuration found
- There is no `uv.toml`, `pip.conf`, `setup.cfg`, or `.netrc` in the repository configuring a private index or `GOOGLE_API_KEY`-style registry. Dependencies resolve from the public PyPI index.
- No `vendor/` directories exist; third-party code is not vendored.
- Internal cross-product imports are resolved through installed package names (e.g. `agentscope`, `agentscope-runtime`) rather than relative paths, indicating these are treated as published packages.

## Node.js Dependencies (npm)

The operator portal frontend lives under `products/operator-portal/web-ui/app/`:
- `package.json` declares runtime dependencies (`react`, `react-dom`, `antd`, `@ant-design/x`, `@ant-design/icons`, `dayjs`) and dev dependencies (`vite`, `vitest`, `typescript`, `@testing-library/*`).
- `package-lock.json` locks exact versions for reproducible builds.
- `engines.node = ">=22"` constrains the Node runtime.
- Build/test scripts delegate to Vite/Vitest; there is no custom dependency update workflow beyond standard npm commands.

## Docker / Build Integration

Each product ships a `Dockerfile` that builds on top of a shared base image under `shared/base-images/base-uv/Dockerfile`. The base image is built once and reused, ensuring consistent Python/uv environments across services. Product `Makefile`s invoke the shared `mk/image.mk` targets to assemble images after `uv sync --frozen` resolves the lockfile.

## Conventions and Constraints

1. **One lockfile per product**: Every service owns its own `uv.lock`; there is no monorepo-wide lock aggregation.
2. **Frozen resolution in CI**: `mk/python.mk` uses `uv sync --frozen`, so any drift between `pyproject.toml` and `uv.lock` fails the build — the lockfile is the source of truth for installed versions.
3. **Major-version caps on all runtime deps**: Every dependency uses a `<next_major>` upper bound, preventing accidental breaking upgrades.
4. **Dev vs runtime separation**: Test-only packages live exclusively in `[dependency-groups].dev`; they are not shipped into production images.
5. **Shared observability baseline**: All services pin the same OpenTelemetry and Prometheus client versions, keeping cross-service metrics/traces compatible.
6. **No private registries or vendoring**: The repository relies on public PyPI/npm indexes and does not vendor third-party code.