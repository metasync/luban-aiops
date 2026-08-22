---
kind: build_system
name: Root Makefile + Shared Fragments Orchestrating Per-Product uv Builds, Docker Images, and GitOps Deploy
category: build_system
scope:
    - '**'
source_files:
    - Makefile
    - mk/defaults.mk
    - mk/image.mk
    - mk/python.mk
    - products/agent-platform/Makefile
    - products/agent-platform/Dockerfile
    - shared/base-images/base-uv/Dockerfile
    - shared/platform-ops/gitops/dev-k8s/deploy.sh
    - shared/shared-contracts/scripts/validate_version.py
    - shared/shared-contracts/scripts/validate_policy.py
    - VERSION
---

## What system/approach is used

The workspace uses a **root Makefile** that delegates to per-product Makefiles, which in turn include shared fragments under `mk/`. Python products are built with **uv** (lockfile-frozen) and packaged into **Docker images** using a common base image (`luban-aiops/base-uv`). Deployment is driven by **Kustomize overlays** under `shared/platform-ops/gitops/` and a `deploy.sh` script that also provisions secrets. A single root `make verify` target runs tests, Kustomize overlay renders, policy validation, and version lockstep checks — intended as the pre-commit/pre-push gate.

## Key files and packages

- `Makefile` — master entry point; defines product lists, coordinated image tag computation, `sync`, `test`, `lint`, `base-images`, `build`, `push`, `overlays`, `verify`, `deploy`, `e2e`, `clean`, plus policy/version helpers.
- `mk/defaults.mk` — single source of overridable build settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`, `REGISTRY`, `AUTO_LOAD_KIND`, `BASE_UV_*`); guard against double inclusion via `LUBAN_DEFAULTS_INCLUDED`.
- `mk/image.mk` — shared Docker targets (`build`, `push`, `lint`) consumed by every product Makefile; computes `IMAGE_REF` from `IMAGE_NAME` and optional `REGISTRY`; falls back to local `hadolint` or `docker run hadolint/hadolint`.
- `mk/python.mk` — shared `uv sync --frozen` and `pytest` targets; disables OTel exporters during test runs so tracing tests stay noise-free while the SDK stays active.
- `products/*/Makefile` — minimal wrappers that set `IMAGE_NAME` and include `../../mk/image.mk` and `../../mk/python.mk`.
- `products/*/Dockerfile` — multi-stage style: `FROM luban-aiops/base-uv:al2023`, copy `.python-version pyproject.toml uv.lock src`, run `uv sync --frozen --no-dev`, expose port, `CMD ["uv", "run", ...]`.
- `shared/base-images/base-uv/Dockerfile` — builds the shared Python+uv base image.
- `shared/platform-ops/gitops/dev-k8s/deploy.sh` — wraps `deploy-overlay.sh`, then sequentially calls secret-sync scripts for delegation, audit, skills, incidents, sessions DB, OTel, and optionally reconciles Keycloak realm / portal OIDC client.
- `shared/shared-contracts/scripts/validate_version.py` — enforces that `VERSION` (semver) matches every `products/*/pyproject.toml` `[project] version`, each product's `src/*/metadata.py` `SERVICE_VERSION`, any `__version__` in package roots, and `operator-portal/web-ui/app.js` `PLATFORM_VERSION`.
- `shared/shared-contracts/scripts/validate_policy.py` — validates canonical policy YAML against JSON schema.
- `VERSION` — single source of truth for platform semver.

## Architecture and conventions

1. **Two-level Makefile hierarchy.** The root Makefile owns cross-cutting orchestration (product iteration, coordinated tagging, overlay rendering, deploy). Each product Makefile is a thin shim declaring `IMAGE_NAME` and including the shared fragments. This lets you run `make -C products/<name>` standalone or go through the root.

2. **Coordinated image tagging.** The root computes one `IMAGE_TAG` once: `<semver>-<prefix>[-<profile>]-<gitsha>` (or `-dirty-<timestamp>` if `git status --porcelain` reports changes). All images produced by `make build` share this tag, and an `.images.env` file under `shared/platform-ops/gitops/dev-k8s/` records the exact tags for the deploy step.

3. **Per-product isolation with shared tooling.** Every Python product has its own `pyproject.toml` + `uv.lock`, installed via `uv sync --frozen`. Tests run with OTEL exporters disabled at runtime but the SDK remains loaded so tracing tests can assert on spans.

4. **Base image strategy.** A single `shared/base-images/base-uv` image pins `UV_VERSION` and `PYTHON_VERSION` (default 0.12.1 / 3.12) and is referenced by all product Dockerfiles. Image platform defaults to `linux/amd64` but is overridable via `IMAGE_PLATFORM`.

5. **GitOps-first deployment.** `make deploy` invokes `shared/platform-ops/gitops/dev-k8s/deploy.sh`, which runs `kustomize build` against the `dev-k8s` overlay and then calls a fixed sequence of secret-provisioning scripts. Overlays for different runtime profiles (`dashscope`, `deepseek`, `openai`, `mutating-dev`) are validated via `make overlays`.

6. **Version lockstep enforcement.** `make validate-version` runs `shared/shared-contracts/scripts/validate_version.py` against the repo root; it parses `VERSION` as strict semver and asserts equality across every product manifest and the operator portal UI constant. `make validate-policy` validates the canonical policy bundle against its JSON schema.

7. **Policy synchronization.** `make sync-policy` copies `shared/shared-contracts/policies/policy-default.yaml` into the two gateway consumers (`tool-gateway`, `platform-gateway`) and the deployed Kustomize overlay, keeping policy bundles in sync.

8. **Kind integration.** When `AUTO_LOAD_KIND=true` and `KIND_CLUSTER_NAME` is set, `make build` automatically loads all built images into the named kind cluster after building them.

## Conventions and constraints

- **GNU make required.** The root Makefile header states it requires GNU make (default on macOS/Linux).
- **Single source of truth for version:** `VERSION` must be valid semver (`MAJOR.MINOR.PATCH`); drift against any product manifest causes `make validate-version` to fail.
- **Frozen dependencies:** Python products always use `uv sync --frozen`; no ad-hoc `pip install` outside the lockfile.
- **Image naming:** Local images are tagged `luban-aiops/<image-name>:<tag>`; when `REGISTRY` is set they are re-tagged to `<registry>/luban-aiops/<image-name>:<tag>` before push.
- **Dockerfile linting:** `make lint` runs `hadolint` if available, otherwise falls back to `docker run hadolint/hadolint`; if neither is present it skips with a warning.
- **Overlay validation:** `make overlays` runs `kustomize build --load-restrictor LoadRestrictionsNone` on every overlay listed in `OVERLAYS`; failures abort the verification gate.
- **Deploy prerequisites:** `make e2e` requires `make deploy` to have completed and port-forwards for `platform-gateway` (18083) and `identity-service` (18081) to be running.
- **Secret provisioning toggles:** Secret-sync scripts accept `SKIP_*_SECRETS=true` environment variables to skip provisioning in CI environments where secrets are injected externally.
- **No CI pipeline files found in `.github/`** beyond issue templates and PR template; the root Makefile is designed to be the forge-agnostic gate (`make verify`) expected to run in any CI.