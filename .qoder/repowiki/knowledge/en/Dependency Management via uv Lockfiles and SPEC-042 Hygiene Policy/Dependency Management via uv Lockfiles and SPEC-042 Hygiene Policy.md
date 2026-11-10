---
kind: dependency_management
name: Dependency Management via uv Lockfiles and SPEC-042 Hygiene Policy
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/defaults.mk
    - Makefile
    - CONTRIBUTING.md
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/tool-gateway/pyproject.toml
    - products/operator-portal/web-ui/app/package.json
    - docs/specs/SPEC-042-dependency-hygiene/spec.md
---

## Approach

The Luban workspace manages dependencies through two parallel, independently-versioned surfaces:

- **Python services** (8 products under `products/`): declared in per-product `pyproject.toml` with ranges, resolved into per-product `uv.lock` files, installed via `uv sync --frozen`. The build backend is `uv_build>=0.8.14,<0.9.0`.
- **Operator portal SPA** (`products/operator-portal/web-ui/app/package.json`): npm + vite + vitest + TypeScript, locked by `package-lock.json`, Node floor `>=22.22.2`.

There is no vendored third-party code, no private PyPI registry, no `UV_PYPI_INDEX_URL` / `PYPI_MIRROR` / `PIP_INDEX_URL` configuration, and no `uv.toml` workspace file at the repository root — all packages resolve from the public PyPI index.

## Key Files

- `mk/python.mk` — shared `sync` / `test` targets that run `uv sync --frozen` then `uv run pytest`; this is the single entry point every product Makefile delegates to.
- `mk/defaults.mk` — pins the base image toolchain: `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`.
- Root `Makefile` — aggregates per-product `sync` / `test` across `PYTHON_PRODUCTS := agent-platform audit-service execution-runtime identity-broker incident-service platform-gateway skills-hub tool-gateway`.
- Per-product `pyproject.toml` — declares runtime dependencies as PEP 508 ranges (e.g. `agentscope>=2.0.4,<3.0`, `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `cryptography>=43.0,<51.0`, `redis>=5.0,<7.0`, `elasticsearch>=8.0,<9.0`).
- Per-product `uv.lock` — frozen resolution of those ranges; consumed by `uv sync --frozen`.
- `products/operator-portal/web-ui/app/package.json` — declares React 19, antd 6.x, vite 8.x, vitest 4.x, TypeScript ~5.9.3.
- `docs/specs/SPEC-042-dependency-hygiene/spec.md` — the authoritative policy document governing how dependencies are adopted and refreshed.

## Architecture and Conventions

### Python dependency ranges

All eight Python products use broad major-version caps (`<next_major`) with lower bounds pinned to a specific minor/patch, e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `opentelemetry-sdk>=1.25,<2.0`, `PyJWT>=2.8,<3.0`. This lets `uv lock` pick the latest stable within range while keeping major upgrades explicit.

### Frozen installs

Every install path goes through `uv sync --frozen` (root `make sync`, per-product `make sync`, per-product `make test`). No network resolution is allowed at install time — the lockfile is the source of truth.

### Base image pinning

The Docker images are built on top of a shared `shared/base-images/base-uv` image whose `UV_VERSION` and `PYTHON_VERSION` come from `mk/defaults.mk` (`BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12`). All product Dockerfiles inherit this base.

### Portal frontend stack

React 19.2.8, antd 6.6.2+, @ant-design/x ^2.9.0, vite 8.2.2 + @vitejs/plugin-react 6.1.1, vitest 4.1.11, jsdom 30.0.1, TypeScript ~5.9.3, Node >=22.22.2. These versions were set by SPEC-042 R-3/R-4 and are not free-form — they are the "recorded adopt set".

### Dependency hygiene policy (SPEC-042)

Adopted versions must be **latest stable only** — no alpha, beta, RC, or dev builds. One recorded exception: OpenTelemetry instrumentation packages (`opentelemetry-instrumentation-fastapi`, `-httpx`, `-logging`) stay on their permanent `0.xb` upstream channel because the SDK/API/exporter side is fully stable but the instrumentation packages have no stable release line.

Adjudicated range caps (from SPEC-042):
- `cryptography>=43.0,<51.0` — raised from `<45.0` after JWT/signing call-site review.
- `redis>=5.0,<7.0` — cap parked; deployed server is redis 7.2, client majors 7/8 were API-removal releases.
- `elasticsearch>=8.0,<9.0` — cap parked; client major follows server major and no Elasticsearch server runs in dev.

### agentscope kernel treatment

`agentscope` is treated specially as the runtime kernel. ADR-0002 positions it as the substrate, and SPEC-042 R-5 pairs any agentscope bump with the full `make verify` gate plus a live check of chat, HITL confirmation, and mutating paths — it is not treated as routine churn.

### Verification gates

- `make verify` runs every product's tests, overlay rendering, policy validation, version lockstep, secret vocabulary, password policy, portal Vitest suite + production build, and delegated-custody/runtime/multiproc/edge integration proofs.
- `make validate-version` enforces that every `products/*/pyproject.toml` version, every `metadata.py` `SERVICE_VERSION`, and the portal's `PLATFORM_VERSION` equal the root `VERSION` file.

## Conventions and Constraints

- **Frozen lockfiles**: `uv sync --frozen` is the only supported install command; `mk/python.mk` enforces it for both `sync` and `test`.
- **Latest-stable-only adoption**: SPEC-042 requires every adopted version to be a final stable release; prereleases/betas/RCs are rejected except the documented OTel instrumentation `0.xb` exception.
- **No private registries**: there is no `uv.toml`, no `index-url`, no `UV_DEFAULT_INDEX_URL`, no `PYPI_MIRROR`, no `PIP_INDEX_URL`, and no `GOPRIVATE` anywhere in the repo.
- **Range-based declarations, lockfile-bound resolutions**: `pyproject.toml` carries human-readable ranges; `uv.lock` carries the exact resolved tree consumed by CI.
- **Per-product isolation**: each Python product owns its own `pyproject.toml` + `uv.lock`; there is no shared workspace-level dependency manifest.
- **Portal deps managed separately**: the operator portal uses npm/vite/vitest and is not part of the Python `PYTHON_PRODUCTS` list; its refresh was governed by SPEC-042 R-3/R-4.
- **Version lockstep**: `make validate-version` (part of `make verify`) enforces that all product versions match the root `VERSION` file; this applies to package versions, not just dependency versions.
- **Deprecation zero-tolerance for the portal**: SPEC-042 R-2 mandates that the vitest setup fails when any antd deprecation warning appears in test output — future deprecations surface at the introducing PR rather than accumulating.