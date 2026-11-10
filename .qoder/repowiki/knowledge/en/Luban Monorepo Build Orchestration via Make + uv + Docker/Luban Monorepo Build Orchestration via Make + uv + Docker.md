---
kind: build_system
name: Luban Monorepo Build Orchestration via Make + uv + Docker
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/python.mk
    - mk/image.mk
    - products/platform-gateway/Makefile
    - products/platform-gateway/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - VERSION
---

## What system/approach is used

The Luban workspace uses a **Makefile-driven monorepo orchestration** layered on top of three per-product build primitives:

- **Python packages**: `uv` (lockfile-frozen) with `pytest` for tests, declared in each product's `pyproject.toml` / `uv.lock`.
- **Container images**: `docker build` against a per-product `Dockerfile`, all based on the shared `luban-aiops/base-uv:al2023` image built from `shared/base-images/base-uv/Dockerfile`.
- **Kubernetes deployment**: Kustomize overlays under `shared/platform-ops/gitops/`, deployed via `make deploy` which delegates to `shared/platform-ops/gitops/dev-k8s/deploy.sh`.

There are no CI workflow files under `.github/workflows`; the root `Makefile` is explicitly forge-agnostic and intended to be the pre-commit/pre-push gate (`make verify`) run locally or inside any CI. The verification gate also runs policy validation scripts, dashboard schema checks, overlay rendering, portal SPA tests, and several integration/e2e proofs.

## Key files and packages

- Root orchestrator: `Makefile` — declares `PYTHON_PRODUCTS`, `IMAGE_PRODUCTS`, `OVERLAYS`, coordinated `IMAGE_TAG` computation, and cross-cutting targets (`sync`, `test`, `lint`, `build`, `push`, `overlays`, `validate-dashboards`, `verify`, `deploy`, `e2e`).
- Shared defaults: `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `REGISTRY`, `BASE_UV_*`, `AUTO_LOAD_KIND`, `KIND_CLUSTER_NAME`).
- Shared fragments: `mk/python.mk` (`sync`/`test` via `uv sync --frozen` + `uv run pytest`), `mk/image.mk` (`build`/`push`/`lint` for Dockerfiles).
- Per-product Makefiles: one-line wrappers that set `IMAGE_NAME` and `include ../../mk/image.mk; include ../../mk/python.mk` (e.g. `products/platform-gateway/Makefile`).
- Per-product Dockerfiles: minimal multi-stage-free images starting from `FROM luban-aiops/base-uv:al2023`, copying `src/`, running `uv sync --frozen --no-dev`, and `CMD ["uv", "run", "<entrypoint>"]`.
- Base image definition: `shared/base-images/base-uv/Dockerfile`.
- Version pin: `VERSION` (currently `0.56.0`), consumed by the root Makefile as `PLATFORM_VERSION` and enforced lockstep by `make validate-version`.
- Policy & contract validation scripts under `shared/shared-contracts/scripts/` invoked from the root Makefile.
- GitOps overlays: `shared/platform-ops/gitops/<overlay>/` rendered via `kustomize build --load-restrictor LoadRestrictionsNone`.
- E2E/demo harness: `shared/platform-ops/e2e/*.sh` and `samples/acme-admin/*`.

## Architecture and conventions

1. **Two-level Makefile hierarchy.** The root `Makefile` owns cross-cutting concerns (image tagging, policy sync, overlay rendering, dashboard validation, e2e demo orchestration). Each product has a thin `Makefile` that only sets `IMAGE_NAME` and includes the shared fragments. This lets `make -C products/<name>` work standalone while `make test`/`make build` at the repo root dispatches across all products.

2. **Coordinated image tagging.** The root computes a single `IMAGE_TAG` once using the formula `<semver>-<prefix>[-<profile>]-<gitsha>` (dirty trees append `-dirty-<timestamp>`). All product images are tagged under `luban-aiops/<product>:<IMAGE_TAG>` and written into `shared/platform-ops/gitops/dev-k8s/.images.env` so the deploy step consumes a consistent set of images.

3. **Single base image strategy.** Every product Dockerfile inherits from `luban-aiops/base-uv:al2023`, whose Python and `uv` versions are pinned in `mk/defaults.mk` (`BASE_UV_PYTHON_VERSION ?= 3.12`, `BASE_UV_UV_VERSION ?= 0.12.1`). The base image is built first via `make base-images`.

4. **Lockfile-frozen Python builds.** Both development (`uv sync --frozen`) and production (`uv sync --frozen --no-dev`) use `--frozen`, pinning dependencies to `uv.lock`. Tests disable OTel exporters (`OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none`) so tracing remains active without network noise.

5. **Policy bundle canonicalization.** `shared/shared-contracts/policies/policy-default.yaml` and `password-policy.yaml` are the single sources of truth; `make sync-policy` copies them into every consumer location (`products/tool-gateway/src/tool_gateway/policies/`, `products/platform-gateway/src/platform_gateway/policies/`, `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`). Consumers are validated against JSON schemas via scripts in `shared/shared-contracts/scripts/`.

6. **Version lockstep enforcement.** `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root, ensuring the root `VERSION` file stays in lockstep with every product version and the operator portal.

7. **Secret vocabulary lockstep.** `make validate-secret-vocabulary` runs `shared/shared-contracts/scripts/validate_secret_vocabulary.py` to keep secret literal declarations synchronized between `agent-platform`, `tool-gateway`, and `skills-hub`.

8. **GitOps overlay validation.** `make overlays` renders every overlay listed in `OVERLAYS` (`dev-k8s`, `runtime-profiles/default|mutating-dev|browser-dev|ansible-dev|servicenow-dev|delegated-dev`) through `kustomize build --load-restrictor LoadRestrictionsNone`.

9. **Dashboard-as-code validation.** `make validate-dashboards` runs `shared/platform-ops/dashboards/validate_dashboards.py` to parse OpenObserve dashboards, validate envelope/panel schemas, and assert every metric reference resolves to an emitted `OTEL_MIRROR_FAMILIES` stream (SPEC-065 R-3).

10. **Portal SPA treated separately.** The operator-portal is not a uv product; its unit suite and production build are gated by `make portal-test` (vitest + tsc/vite) rather than `make test`.

11. **Kind auto-loading.** When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all nine built images into the kind cluster after building.

## Conventions and constraints

- **GNU make required.** The root Makefile header states it requires GNU make (default on macOS and Linux); all per-product Makefiles follow the same two-fragment include pattern.
- **No `latest` tags.** `mk/defaults.mk` documents that pinned values are defaults for reproducible builds — never `latest`. Image tags are derived from `VERSION` + git SHA.
- **Registry re-tagging is opt-in.** `REGISTRY` is empty by default; when set, `make push` re-tags images to `$(REGISTRY)/luban-aiops/<product>:$(IMAGE_TAG)` before pushing.
- **Cross-platform builds default to `linux/amd64`.** `IMAGE_PLATFORM ?= linux/amd64`; `linux/arm64` is documented for native local/kind builds on arm64 hosts.
- **Verification gate composition.** `make verify` is the authoritative pre-commit/pre-push gate and composes: product tests, overlay rendering, dashboard validation, policy validation (schema + scenarios), version lockstep, secret vocabulary, password policy, secret-delivery demo, portal SPA tests, audit contract test, delegated custody/runtime/multi-process/edge tests, and execution failure test.
- **Samples are out-of-band from the base overlay.** `make deploy` never names a sample; samples are installed separately via `make deploy-samples` and the acme-admin app via `make deploy-sample-app` (SPEC-050 R-11).
- **Integration tests use disposable Postgres.** Several `make *-test` targets (audit-contract-test, delegated-custody-test, delegated-runtime-test, delegated-multiproc-test, delegated-edge-test, execution-failure-test) spin up disposable databases and independent processes to prove crash safety and cross-replica behavior.
- **SPEC references are embedded in comments.** Cross-cutting validations cite their spec requirement inline (e.g. SPEC-062 R-2, SPEC-065 R-3/R-4, SPEC-063 R-8c, SPEC-050 R-11), making the build rules themselves traceable to requirements.