# SPEC-009 Plan: Pre-Production Hardening — Tool Output Redaction and Workload-Identity Service Tokens

## Approach

Two independent hardening tracks that share no code path, delivered in
sequenced stages so each can be validated alone:

1. **Redaction track (R-1/R-2)** — a code-owned redaction module in
   `tool-gateway`, applied at the single choke point where every tool result
   becomes an HTTP response (`gateway_service.invoke_tool`), with a
   fail-closed overflow policy, a Prometheus counter, and an audit field.
2. **Workload-identity track (R-3)** — the broker exchange gains a second,
   bearer-based service-credential mode (Kubernetes projected service-account
   token, validated against the cluster OIDC issuer JWKS); the gateway's
   `DelegationClient` prefers a projected token file over the static secret.
3. **Overlay/doc track (R-4)** — config entries, README contracts, and
   example files.

Deliberately kept simple: no new services, no new trust roots, no
operator-editable redaction rules, and the dev path (static secret, no
workload issuer) keeps working unchanged.

## Design Per Requirement

### R-1: Deterministic redaction of tool output

- affected files: new `products/tool-gateway/src/api_gateway/tools/redaction.py`,
  `services/gateway_service.py` (choke-point call), `core/config.py`
- chosen approach:
  - `redact_result(result: ToolResult, settings) -> tuple[ToolResult, int]`
    walks the serialized result dict (`data`, `evidence`, `error`) and:
    - **value patterns** (shape-based, key-agnostic): JWTs
      (`eyJ…` three-segment tokens), `Bearer <…>`/`Basic <…>` credential
      values, PEM private-key blocks, AWS-style access key IDs — replaced by
      the fixed marker `[REDACTED]`
    - **explicit key list** (bounded): values of string fields named
      `password`, `passwd`, `secret`, `api_key`, `apikey`, `token`,
      `access_key`, `client_secret`, `private_key`, `authorization`
      (case-insensitive, exact key-name match, string values only) — the key
      name stays visible, only its value is replaced
  - pattern set is module-level constants (code-owned); the only config knob
    is `GATEWAY_REDACTION_ENABLED` (default `true`; the dev-mode opt-out)
  - redaction runs inside `invoke_tool` after dispatch and before both the
    HTTP response and the audit log, so no path can bypass it
- alternatives rejected:
  - per-tool redaction hooks — scatters the trust boundary across tools and
    makes the guarantee untestable
  - operator-editable regex config — violates the code-owned policy accepted
    at approval (Q-3)

### R-2: Redaction observability and failure policy

- affected files: `tools/redaction.py`, `core/metrics.py`,
  `services/gateway_service.py`
- chosen approach:
  - the redactor returns the redacted-span count; `invoke_tool` computes
    `redacted_chars / total_chars` and if it exceeds
    `GATEWAY_REDACTION_OVERFLOW_FRACTION` (default `0.2`) returns
    `make_error_result(tool, "REDACTION_OVERFLOW", …)` instead of the output
  - new counter `gateway_tool_redacted_spans_total` (label: `tool`), defined
    alongside the existing delegation counters in `core/metrics.py` per the
    SPEC-005 conventions
  - the existing structured audit log entry for tool invocation gains a
    `redacted_spans` field
- alternatives rejected: truncation-with-notice — rejected at approval
  (Q-2) in favor of fail-closed

### R-3: Workload-identity-bound service tokens at the exchange

- affected files:
  - broker: `services/exchange_service.py`, `core/config.py`,
    `api/routes/*` (exchange route accepts bearer credential)
  - gateway: `services/delegation_client.py`, `core/config.py`
- chosen approach:
  - **broker**: `authenticate_client` gains a bearer branch — when the
    exchange request carries `Authorization: Bearer <workload-token>` instead
    of HTTP Basic, the broker validates the token against the configured
    cluster OIDC issuer (issuer URL + JWKS fetched with the same caching
    pattern the gateway uses for broker JWKS), requires `aud` to contain the
    configured workload audience, and maps `sub`
    (`system:serviceaccount:<ns>:<sa>`) to a registered `ServiceClient` via
    a new registry entry. Same audience allow-list and same delegated-token
    claims as the static path (`sub`/`roles`/`aud`/`act` unchanged;
    `act.sub` = the mapped client_id). Any failure → `401`.
    - config: `IDENTITY_WORKLOAD_ISSUER_URL` (empty = feature off),
      `IDENTITY_WORKLOAD_AUDIENCE` (default `identity-broker`), and the
      workload-subject → client mapping in the existing
      `IDENTITY_SERVICE_CLIENTS`-style registry convention
  - **gateway**: `DelegationClient.exchange` prefers a projected token when
    `GATEWAY_WORKLOAD_TOKEN_PATH` is set (reads the file per exchange —
    kubelet rotates it in place); sends it as `Bearer` instead of Basic.
    When the path is set but the file is missing/unreadable, falls back to
    the static secret and logs a warning once per process. When the path is
    unset, behavior is byte-identical to today (dev overlays).
  - mechanism is generic: the broker knows only "validated workload subject
    → registered client"; adding a second service later is a registry entry,
    not code
- alternatives rejected:
  - SPIFFE/SPIRE SVIDs — rejected at approval (Q-1): new infrastructure and a
    second trust root; remains the documented future option for multi-cluster
    federation or mTLS
  - gateway-side JWT minting from the static secret — adds a round trip for
    no gain (same reasoning as SPEC-008 R-3)

### R-4: Overlay and documentation alignment

- affected files: `shared/platform-ops/gitops/dev-k8s/` (env fragments,
  READMEs, example files), product READMEs, root `README.md`, `CHANGELOG.md`,
  Release 1 release notes
- chosen approach:
  - redaction is on by default; no overlay change needed for the default —
    the dev-mode opt-out (`GATEWAY_REDACTION_ENABLED=false`) is documented
    in the dev-k8s README only
  - the workload-token contract (projected volume spec snippet, issuer/
    audience env names) is documented in the dev-k8s README and both product
    READMEs; dev overlays keep the static secret as fallback
  - `runtime-secrets.example.env` (gateway) marks the static secret as the
    dev fallback and links the workload-identity path

## Sequencing And Dependencies

1. Stage 1 — redaction engine + fail-closed overflow (R-1/R-2 core) —
   depends on nothing
2. Stage 2 — redaction metrics + audit field + choke-point wiring (R-2
   remainder) — depends on Stage 1
3. Stage 3 — broker bearer/workload branch at exchange (R-3 broker half) —
   depends on nothing; parallel-safe with Stages 1–2
4. Stage 4 — gateway projected-token preference + fallback warning (R-3
   gateway half) — depends on Stage 3's contract only
5. Stage 5 — overlays, READMEs, example files (R-4) + full `make verify` —
   depends on Stages 1–4
6. Delivery — advance living-state docs, CHANGELOG, release-notes Known
   Limitations, spec index/status — depends on Stage 5 green

## Test Strategy

- unit tests:
  - gateway `tests/test_redaction.py` (new): value patterns, key list,
    byte-identical passthrough on clean output, `REDACTION_OVERFLOW`
    fail-closed on a synthetic mostly-credential payload, opt-out switch
  - gateway `tests/test_gateway_service.py` (or new): redaction applied at
    the invoke choke point; audit entry carries `redacted_spans`
  - gateway delegation tests: projected-token file preferred, fallback +
    one-shot warning when the file is missing
  - broker `tests/test_exchange_service.py`: bearer workload token accepted
    (same delegated claims as static path), expired/wrong-audience/
    unregistered → 401, feature off when issuer URL empty
- contract tests: none new (evidence envelope schema unchanged;
  `REDACTION_OVERFLOW` is a new error-code value inside the existing shape)
- integration / overlay validation: `kustomize build` renders all overlays;
  workload-token path is exercised by unit tests only (dev clusters have no
  OIDC issuer — documented as the fallback case)

## Rollout And Migration

- deployment changes: none required for dev (redaction on by default;
  workload path unconfigured). Non-dev deployments set
  `GATEWAY_WORKLOAD_TOKEN_PATH` + a projected volume, and the broker sets
  `IDENTITY_WORKLOAD_ISSUER_URL`/`IDENTITY_WORKLOAD_AUDIENCE` + registry
  mapping
- backward compatibility: static client-secret path unchanged; redaction
  opt-out available for dev debugging only
- rollback: unset `GATEWAY_WORKLOAD_TOKEN_PATH` (gateway returns to static
  secret); set `GATEWAY_REDACTION_ENABLED=false` if a false-positive
  regression ever blocks diagnostics — both are pure env toggles
