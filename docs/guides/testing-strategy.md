# Testing Strategy

A contributor-facing map of the platform's multi-tier test architecture: what
runs at each tier, how to invoke it, and the conventions that keep the suite
reliable across nine products. This is the deep reference; the short policy —
how to run tests and what a change is expected to carry — lives in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#testing), and the tool-specific test
shape is worked through in
[Adding a Tool to the Tool Gateway](adding-a-tool.md).

The suite is deliberately split into tiers with different hermeticity. Fast,
dependency-free unit and contract tests run under `pytest` per product; the
behaviour that genuinely needs a real database, real concurrency, or a real
browser edge is proven by separate standalone harnesses. `make verify` runs all
of them together as the pre-commit/pre-push gate.

## The verification gate (`make verify`)

`make verify` (root [`Makefile`](../../Makefile)) is the single gate to run
before any commit that touches code, manifests, or policy. It is the source of
truth for what "verified" means; the components below mirror its target list.

| Component | What it proves |
|---|---|
| `test` | Every Python product's `pytest` suite (see tier 1) |
| `overlays` | Every GitOps overlay renders (`kustomize build`) |
| `validate-dashboards` | OpenObserve dashboards import and reference emitted metrics (SPEC-065 R-3) |
| `validate-policy` / `validate-policy-scenarios` | Canonical policy bundle validates against schema, and scenario expectations hold in both engines |
| `validate-version` | Version lockstep across `VERSION`, products, and portal |
| `validate-secret-vocabulary` / `validate-password-policy` | Secret-literal lockstep and the password-policy contract (SPEC-062 R-2) |
| `secret-delivery-demo` | Local sample handoff proof (no cluster) |
| `portal-test` | Operator-portal SPA suite and production build (see tier 4) |
| `audit-contract-test`, `delegated-custody-test`, `delegated-runtime-test`, `delegated-multiproc-test`, `delegated-edge-test` | Disposable-Postgres integration proofs (see tier 2) |
| `execution-failure-test` | Crash-safety proof (see tier 3) |

Run the whole gate from the repository root, or a single product's suite from
inside that product's directory (`make -C products/<name> test`).

## Tier 1 — Per-product unit and contract tests (`pytest`)

Each Python product keeps its tests co-located under `products/<name>/tests/`.
The agent-platform and tool-gateway suites are by far the largest; the others
are smaller but follow the same shape.

**Invocation.** Every product's `Makefile` includes
[`mk/python.mk`](../../mk/python.mk), whose `test` target runs:

```sh
uv sync --frozen
OTEL_TRACES_EXPORTER=none OTEL_METRICS_EXPORTER=none OTEL_LOGS_EXPORTER=none \
  uv run pytest
```

The no-op OTLP exporters keep test output free of export-retry noise while the
OpenTelemetry SDK stays active for tracing tests — `OTEL_SDK_DISABLED` would
break those, so the exporters are silenced individually instead. `uv sync
--frozen` before every run means the committed `uv.lock` is authoritative; tests
never resolve against an unfrozen tree.

**Patterns used across the suite.**

- **In-process app driving** — tests build the application object
  (`create_app()`) and exercise it through FastAPI's `TestClient`, asserting
  contract stability: status codes, response shapes, evidence fields, and the
  structured error envelope.
- **Controlled identity** — authorization flows mint RS256-signed delegated
  tokens with a test key and patch the JWKS verifier, so audience and
  role-based checks (`operator`, `developer`, `observer`, `approver`) are
  exercised deterministically without a live identity provider.
- **Faked persistence** — store-backed tests inject in-memory or fake
  connectors (a fake cursor/connection that captures executed SQL and returns
  controlled rows) to assert filtering, scoping, and pagination at the query
  layer without a real database. Redis-backed session stores use `fakeredis`.
- **Explicit isolation** — shared state (policy engine, token verifier) is
  reset in `setUp`/`tearDown` so tests cannot pollute one another.
- **Per-test configuration** — environment overrides select backends and flip
  feature flags (for example auth enforcement, or `GATEWAY_MUTATING_TOOLS_ENABLED`
  to admit write/admin tools for a registration test).

**What to assert.** New endpoints and tools carry tests for the deny and error
paths — authentication failure, policy deny, upstream failure — not only the
happy path. For tool-gateway tools the expected shape (including the error
envelope and evidence) is walked through in
[Adding a Tool to the Tool Gateway](adding-a-tool.md).

## Tier 2 — Disposable-Postgres integration proofs

Some guarantees cannot be proven hermetically: real SQL against a real
Postgres, publication fencing, and behaviour across independently started
processes (cross-replica callback, restart, revocation). These live as
**standalone Python scripts** under `products/<name>/tests/integration/`, run
directly rather than through `pytest`:

```sh
uv run --frozen --project products/<product> \
  python products/<product>/tests/integration/<name>.py
```

Each is wired into `make verify` under a named target. The harness pattern is
consistent: it provisions a **disposable Dockerized Postgres** with an isolated
role, accepts **no external database input**, drives the **real** store code
(`psycopg`) across **independent processes** (`multiprocessing`), and fakes
external providers only at the boundary — so the proof exercises the custody or
durability mechanism, not a live third-party OAuth flow.

| Target | Proof |
|---|---|
| `audit-contract-test` | Audit delegation filtering and legacy migration |
| `delegated-custody-test` | Delegated custody and publication fencing |
| `delegated-runtime-test` | Real delegated runtime: routes, HTTP/MCP adapters, and the cross-user approval matrix against fixture OAuth/TLS |
| `delegated-multiproc-test` | Independently started gateway processes against shared custody: cross-replica callback/refresh, restart, revocation, configuration removal |
| `delegated-edge-test` | Platform-gateway browser edge over generated TLS: cookie-bound navigation, authorized return, fail-closed on different-browser/expiry, secret-safe edge logs |

## Tier 3 — Crash-safety end-to-end (`execution-failure-test`)

`shared/platform-ops/e2e/execution-failure-test.sh` proves crash safety
(SPEC-063) with a disposable Postgres and independently started processes —
that an interrupted execution leaves a recoverable, non-double-executing state.
It runs as part of `make verify`.

## Tier 4 — Operator-portal SPA gate (`portal-test`)

The operator portal is **not** a uv product, so `make test` never covers it
(SPEC-063 R-8c). `portal-test` runs the portal's two targets in sequence —
`make -C products/operator-portal test` then `web-build` — which together
execute:

- the full **Vitest** suite — configured to **fail on zero tests**, so there is
  no skip/empty-green path; and
- a **typechecked production build** (`tsc --noEmit && vite build`), so a type
  error or a broken build fails the gate.

## Tier 5 — Live-checks and demos (mocked by default)

The scripts under `shared/platform-ops/e2e/` double as demos and live-checks.
They follow one opt-in escalation model so the default path is safe and free:

- **Default (`--local`)** — runs a mocked-I/O `pytest` proof of the pipeline
  logic: no cluster, no network, no paid model call. These proofs are also
  collected by `make test`, so the logic is covered on every run.
- **`LIVE=1`** — a read-only pre-flight against a running cluster (for example
  the two-tier route pre-flight).
- **`LIVE=1 DRIVE_TURN=1`** — the gated, billable path that drives one real
  turn (for example the observability token/cost correlation, the bounded
  read-only diagnosis fan-out, or the remediation park-and-zero-dispatch proof).

Examples: `observability-livecheck` (SPEC-065 R-4), `diagnosis-livecheck`
(SPEC-076 R-8), `remediation-livecheck` (SPEC-077 R-8), plus the
`documents`/`incident`/`mutating`/`skills`/`http-check` demos and
`secret-delivery-demo` (in `make verify`).

## Contract-parity testing

Changes to `shared/shared-contracts` schemas carry a contract-parity test in
**every consuming service**. In particular, enum vocabulary must be asserted for
**value-set equality** between the JSON schema and the consuming pydantic
`Literal` — not merely property-name parity — so a contract drift cannot slip
through as a matching field name with a divergent value set. See
[`CONTRIBUTING.md`](../../CONTRIBUTING.md#testing) and the policy model in
[Policy Specification](../agentic-aiops-platform/policy-specification.md).

## Conventions and the traceability rule

- **Pin the bug, not just the fix.** A behaviour change or bug fix carries a
  regression test that fails without the change.
- **No numeric coverage bar.** There is no `pytest-cov` threshold and no
  coverage gate in CI; reviewers judge whether the risky branches of a change
  are exercised. (Generic "enforce `--cov-fail-under`" advice does not apply
  here.)
- **Organization and naming.** Roughly one test file per module or feature
  area; classes group related tests that share `setUp`/`tearDown`; method names
  describe scenario and expected outcome (for example
  `test_invoke_rejects_wrong_audience_before_policy`).
- **Traceability (ADR-0008).** A spec advances to `delivered` only when every
  `R-x` acceptance criterion maps to at least one asserting test — recorded in
  the spec's `tasks.md` — and any `samples/` demo the spec ships is exercised by
  its own demo script in the verification path. "Declared delivered" must equal
  "demonstrably delivered." See
  [ADR-0008](../adr/0008-spec-delivery-traceability-gate.md).

## Choosing a tier for a new change

| Change | Where the test belongs |
|---|---|
| New endpoint or service logic | Tier 1 `pytest`, including deny/error paths |
| New or changed tool in tool-gateway | Tier 1, following [adding-a-tool.md](adding-a-tool.md) |
| `shared/shared-contracts` schema change | Contract-parity tests in every consumer |
| Custody, publication fencing, durability, cross-process behaviour | Tier 2 disposable-Postgres proof |
| Crash/recovery semantics | Tier 3 `execution-failure-test` |
| Portal UI or SPA behaviour | Tier 4 Vitest (+ build) |
| Pipeline/observability/diagnosis logic | Tier 5 mocked `--local` proof, with a gated `LIVE=1` path where a real turn matters |

## Related documentation

- [`CONTRIBUTING.md`](../../CONTRIBUTING.md#testing) — how to run tests and what a change must carry
- [Adding a Tool to the Tool Gateway](adding-a-tool.md) — the tool test shape end to end
- [Architecture Overview](architecture-overview.md) — service topology and trust chain
- [Execution Cutover and Restore](execution-cutover-restore.md) — the durability guarantees tier 2/3 protect
- [Observability Dashboards](observability-dashboards.md) — what `validate-dashboards` checks
- [ADR-0008: Spec Delivery Traceability Gate](../adr/0008-spec-delivery-traceability-gate.md)
- [Spec Index](../specs/README.md) — per-spec acceptance criteria and delivery status
