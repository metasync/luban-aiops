---
kind: build_system
name: 'Workspace Build System: Root Makefile + Shared mk Fragments + Per-Product uv/Docker Builds'
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/platform-gateway/Makefile
    - products/operator-portal/Makefile
    - shared/base-images/base-uv/Dockerfile
    - VERSION
---

## Approach

The repository uses a **single root GNU Makefile** as the orchestrator, delegating to per-product `Makefile`s that include shared fragments under `mk/`. There is no CI pipeline file in this workspace (no `.github/workflows`); the author guidelines state `make verify` is the forge-agnostic pre-commit/pre-push gate and runs the same checks locally and under any CI. Image builds use Docker with multi-stage Dockerfiles per product; Python dependencies are managed via `uv` (`pyproject.toml` + `uv.lock`) per product.

## Key Files

- `Makefile` — root orchestrator: declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, overlay lists, coordinated image tag computation, policy sync/validation, dashboard validation, live-checks, e2e suite, and the `verify` gate.
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, etc.) using `?=` so command-line overrides always win.
- `mk/image.mk` — shared container-image targets (`build`, `push`, `lint` via hadolint or docker-run fallback) for every product.
- `mk/python.mk` — shared `sync` / `test` targets running `uv sync --frozen` then `pytest` with OTel exporters disabled.
- `products/<name>/Makefile` — thin wrappers setting `IMAGE_NAME` and including `../../mk/image.mk` (+ `../../mk/python.mk` for Python products).
- `shared/base-images/base-uv/Dockerfile` — shared base image built by `make base-images`.
- `VERSION` — single source of truth for the platform semver used in coordinated image tags.
- `shared/platform-ops/gitops/` — Kustomize overlays rendered by `make overlays`.
- `shared/platform-ops/dashboards/validate_dashboards.py` — offline OpenObserve dashboard validator invoked by `make validate-dashboards`.
- `shared/shared-contracts/scripts/*` — policy, version, secret-vocabulary, password-policy validators invoked from the root Makefile.

## Architecture & Conventions

1. **Two-level Makefile hierarchy.** The root Makefile owns cross-cutting concerns (policy sync, overlay render, dashboard validation, coordinated image tagging, e2e). Each product's `Makefile` is a 3–5 line shim that sets `IMAGE_NAME` and includes `mk/image.mk` (and `mk/python.mk` when applicable). This keeps per-product logic minimal and centralized.

2. **Coordinated image tagging.** The root computes one `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` for clean trees, `<...>-dirty-<timestamp>` for dirty trees. All images produced by `make build` share this tag, and the resulting names are written to `shared/platform-ops/gitops/dev-k8s/.images.env` for `make deploy` to consume.

3. **Product classification.** Products are explicitly enumerated:
   - `PYTHON_PRODUCTS`: agent-platform, audit-service, execution-runtime, identity-broker, incident-service, platform-gateway, skills-hub, tool-gateway.
   - `IMAGE_PRODUCTS`: same eight plus operator-portal (web UI only, no Python test suite).

4. **Python dependency management.** Every Python product has its own `pyproject.toml` + `uv.lock`. `make sync` / `make test` run `uv sync --frozen` inside each product directory, ensuring reproducible installs. Tests disable OTel exporters (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) while keeping the SDK active for tracing tests.

5. **Operator-portal SPA exception.** The portal is a Vite/Vitest/TypeScript SPA served by nginx. Its `Makefile` adds `test` (runs `npm test` in `web-ui/app`) and `web-build` (runs `npm run build`). It is excluded from `PYTHON_PRODUCTS` but included in `IMAGE_PRODUCTS`; `make verify` invokes it via the dedicated `portal-test` target.

6. **Policy-as-code contract.** Canonical policies live in `shared/shared-contracts/policies/`. `make sync-policy` copies them into consumers (`tool-gateway`, `platform-gateway`, GitOps base), and `make validate-policy` / `validate-password-policy` / `validate-version` / `validate-secret-vocabulary` enforce schema and lockstep constraints.

7. **GitOps overlay validation.** `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` against every overlay in `OVERLAYS` (dev-k8s plus runtime profiles). Dashboard configs are validated offline via `make validate-dashboards`.

8. **Live-checks gated by environment variables.** `observability-livecheck`, `diagnosis-livecheck`, `remediation-livecheck` default to mocked-I/O pytest proofs; `LIVE=1` enables read-only cluster pre-flights; `DRIVE_TURN=1` additionally drives one gated billable turn. These are separate from `make e2e`, which runs the demo scripts against a deployed cluster.

9. **Base image pinning.** `BASE_UV_IMAGE=luban-aiops/base-uv`, `BASE_UV_TAG=al2023`, `BASE_UV_UV_VERSION=0.12.1`, `BASE_UV_PYTHON_VERSION=3.12` — all pinned defaults in `mk/defaults.mk`, never `latest`.

10. **Multi-platform support.** `IMAGE_PLATFORM ?= linux/amd64` (with `linux/arm64` documented for native local/kind builds on arm64 hosts). `make base-images` and `make build` both pass `--platform $(IMAGE_PLATFORM)`.

## Conventions & Constraints

- **Forge-agnostic gate:** `make verify` is the canonical pre-commit/pre-push gate; it chains `test`, `overlays`, `validate-dashboards`, `validate-policy`, `validate-policy-scenarios`, `validate-version`, `validate-secret-vocabulary`, `validate-password-policy`, `secret-delivery-demo`, `portal-test`, and four delegated-custody/runtime/multi-process/edge integration tests plus `execution-failure-test`.
- **Single source of truth for versions:** `VERSION` at repo root is the platform release version; `make validate-version` enforces lockstep between `VERSION`, every product version, and the portal.
- **No skip/zero-tests green path for the portal:** `make verify` requires the full Vitest suite and production build to pass; zero tests fails the gate (SPEC-063 R-8c).
- **Samples are out-of-band:** Samples (`samples/acme-admin`, skill samples) are installed via `make deploy-samples` / `deploy-sample-app` and are deliberately not part of the base overlay (SPEC-050 R-11).
- **Image push requires explicit registry:** `REGISTRY` must be set for `make push` to re-tag and push; without it, images remain local under `luban-aiops/<name>:<tag>`.
- **Kind auto-load is opt-in:** `AUTO_LOAD_KIND=true` requires `KIND_CLUSTER_NAME` and loads the nine coordinated images after `make build`.
- **Dockerfile linting falls back gracefully:** If `hadolint` is unavailable, `make lint` tries `docker run hadolint/hadolint`; if neither is available, it skips with a message rather than failing.
- **GNU make required:** The root Makefile header states it requires GNU make (default on macOS and Linux).
- **No CI files in this workspace:** There is no `.github/workflows` directory; CI configuration is expected to invoke the same `make verify` gate described above.