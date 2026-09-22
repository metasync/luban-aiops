---
kind: dependency_management
name: Per-Product uv Lockfiles with Shared base-uv Image and Frozen Sync
category: dependency_management
scope:
    - '**'
source_files:
    - mk/python.mk
    - mk/defaults.mk
    - shared/base-images/base-uv/Dockerfile
    - products/agent-platform/pyproject.toml
    - products/platform-gateway/pyproject.toml
    - products/agent-platform/.python-version
    - products/platform-gateway/.python-version
    - docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md
---

## What system/approach is used

The Luban workspace manages dependencies exclusively through **Python `uv`** (Astral) at the per-product level. Each of the eight backend services under `products/` ships its own `pyproject.toml` declaring runtime and dev dependency ranges, a co-located `uv.lock` pinning exact versions, and a `.python-version` file fixing the interpreter to Python 3.12. The root Makefile orchestrates dependency installation across all products via `make sync`, which delegates to each product's `make sync` that runs `uv sync --frozen`. There are no `requirements.txt`, `poetry.lock`, `Pipfile`, or vendored third-party packages — `uv` resolves from PyPI using the lockfile.

Container images are built on a shared base image `shared/base-images/base-uv/Dockerfile` (Amazon Linux 2023 minimal) that installs a pinned `uv` version (`BASE_UV_UV_VERSION ?= 0.12.1`) and sets `UV_PYTHON_INSTALL_DIR=/app/.python` so `uv sync` installs the interpreter into the image rather than relying on a system Python. The build defaults for this image live in `mk/defaults.mk`.

The operator-portal frontend uses npm/yarn-style tooling (Node, Vite, Vitest, antd, React 19) managed separately; it is not part of the Python `uv` dependency surface.

## Key files and packages

- Per-product manifests: `products/*/pyproject.toml` (runtime + `[dependency-groups].dev`), `products/*/uv.lock`, `products/*/.python-version`
- Shared build fragments: `mk/python.mk` (`sync` = `uv sync --frozen`; `test` = `uv run pytest` with OTel exporters disabled), `mk/defaults.mk` (pinned `BASE_UV_UV_VERSION`, `BASE_UV_PYTHON_VERSION`)
- Shared base image: `shared/base-images/base-uv/Dockerfile` (pins `UV_VERSION=0.12.1`, `PYTHON_VERSION=3.12`, non-root `app` user)
- Root orchestration: `Makefile` (`PYTHON_PRODUCTS` list, `make sync`, `make verify` which includes `uv sync --frozen` indirectly via per-product `make test`)
- Policy/spec references: `docs/specs/SPEC-042-dependency-hygiene/` and `docs/agentic-aiops-platform/release-notes/2026-08-28-dependency-hygiene.md` codify the adoption posture.

## Architecture and conventions

1. **One lockfile per product.** Each service declares its own dependency ranges in `pyproject.toml` and pins them in a committed `uv.lock`. There is no workspace-level `uv.lock` or monorepo dependency resolver — upgrades are done per-product.
2. **Frozen resolution everywhere.** Both development (`make sync`) and CI/test paths use `uv sync --frozen`, meaning builds fail if the lockfile drifts from `pyproject.toml`. This enforces that dependency changes go through explicit re-locking commits.
3. **Interpreter pinned per product.** `.python-version = 3.12` in every product directory; the shared base image sets `UV_PYTHON=3.12` as a fallback, so both local and container environments resolve the same CPython.
4. **Dependency ranges use caret-style bounds.** Runtime dependencies declare upper bounds (e.g. `fastapi>=0.115,<1.0`, `pydantic>=2.8,<3.0`, `agentscope>=2.0.4,<3.0`, `cryptography>=43.0,<51.0`). Dev dependencies are isolated under `[dependency-groups].dev` (pytest, fakeredis, jsonschema).
5. **Build backend pinned.** Every product sets `[build-system] requires = ["uv_build>=0.8.14,<0.9.0"]` with `build-backend = "uv_build"`, ensuring reproducible sdist/wheel builds.
6. **Adoption policy: latest stable only.** The release note for SPEC-042 states the adopted posture is "latest stable only — no alpha, beta, RC, or dev builds", with one recorded exception: OpenTelemetry instrumentation packages stay on their permanent `0.xb` channel paired with the locked SDK.
7. **Coordinated image tagging.** While dependency versions are per-product, container images share a coordinated tag derived from the root `VERSION` file, applied uniformly to all nine images by `make build`.
8. **No private registry configured.** Dependencies resolve from PyPI; there is no `pip.conf`, `PYPI_URL`, `UV_INDEX_URL`, or `go.mod`/`GOPRIVATE` equivalent in this repo.

## Conventions and constraints

- **`uv sync --frozen` is the canonical install command.** It appears in `mk/python.mk`, the root `Makefile`'s `sync` target, and the getting-started guide. Any deviation would bypass the lockfile guarantee.
- **Python version is fixed at 3.12 across all products.** Enforced by per-product `.python-version` and the shared base image's `UV_PYTHON=3.12`.
- **Dependency ranges must include an upper bound.** Observed consistently across all products (e.g. `<3.0`, `<1.0`, `<51.0`); major-version bumps require explicit range updates and full re-lock.
- **Dev-only tools belong in `[dependency-groups].dev`.** pytest, fakeredis, jsonschema are declared there and excluded from runtime images.
- **OpenTelemetry instrumentation packages are exempt from the "latest stable" rule** because upstream publishes them on a permanent `0.xb` channel; they remain pinned to their SDK pairing rather than chased to newer releases.
- **Redis and Elasticsearch client caps are intentionally parked** below server-major boundaries (`redis<7.0`, `elasticsearch<9.0`) because the deployed servers are older and client majors align with server majors.
- **Cryptography upper bound was adjudicated up to `<51.0`** after a call-site review confirmed the JWT/signing surface (`rsa.generate_private_key`, PEM/DER serialization, PKCS8/SubjectPublicKeyInfo formats) remained unchanged through 50.x.
- **Verification gate enforces dependency hygiene.** `make verify` runs tests against frozen deps, validates overlays, policies, versions, secret vocabulary, password policy, and the local secret-delivery demo — any dependency break fails the gate.