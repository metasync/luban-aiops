# SPEC-009: Pre-Production Hardening — Tool Output Redaction and Workload-Identity Service Tokens

## Status

- status: `delivered`
- owner: chi
- created: 2026-07-30
- release slice: Release 1 closure gate — must be `delivered` before the first
  non-dev deployment (independent of the R2 roadmap theme)
- related ADRs: `docs/adr/0004-broker-mediated-token-delegation.md`

## Summary

Close the two deadline-bound deferrals from Release 1: (1) redact sensitive
content from read-only tool outputs before they reach the model provider
(closes SPEC-007 Q-3), and (2) replace the gateway's static client secret with
Kubernetes workload-identity-bound short-lived service tokens at the broker
exchange (closes the SPEC-008 R-3 upgrade path). Both were explicitly flagged
as "must not pass the first non-dev deployment".

## Motivation

- `k8s.get_pod_logs` returns raw container logs into the LLM context and thus
  to a third-party model API; line count is bounded but content is
  uninspected (SPEC-007 Q-3). Service-account JWTs, bearer tokens, and basic
  credentials appear routinely in Kubernetes workloads' logs and env echoes.
- The gateway's service identity currently rests on a static,
  audience-scoped client secret (SPEC-008 R-3). It is the one extractable
  long-lived secret in the platform; ADR-0004 named workload-identity-bound
  short-lived tokens as the upgrade path, to be done once for all services at
  the first non-dev deployment or at Release 4.
- Release 1 is delivered and `make verify` is green; this is the cheapest
  moment to harden both paths before any non-dev environment exposes them.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance criteria.

### R-1: Deterministic redaction of tool output

The tool gateway applies a built-in pattern set to every tool result payload
before it leaves the service, covering `Authorization` header values,
`Bearer`/`Basic` tokens, Kubernetes service-account JWTs, and
password/secret/api-key field values in structured output. Redaction replaces
matched spans with a fixed marker (no length-preserving echoing).

Acceptance criteria:

- a tool result containing a service-account JWT, a `Bearer` token in log
  text, and a `password` field value has each span replaced by the marker
- unchanged tool output passes through byte-identical when no pattern matches
- the pattern set is code-owned (not operator-editable regex) in Release 1,
  with an opt-out only via a documented dev-mode switch
- redaction applies uniformly to `tools/invoke` results regardless of which
  tool produced them

### R-2: Redaction observability and failure policy

Redaction is observable and fail-closed for pathological outputs.

Acceptance criteria:

- a Prometheus counter records redacted spans per tool result
  (labels: tool name), following the SPEC-005 metric conventions
- if the redacted fraction of a result exceeds a configured bound
  (default 20%), the invocation returns the structured evidence envelope with
  an explicit `REDACTION_OVERFLOW` error instead of releasing the output
- the audit log entry for a tool invocation records the redacted-span count
- `REDACTION_OVERFLOW` is unit-tested with a synthetic mostly-credential
  payload

### R-3: Workload-identity-bound service tokens at the exchange

The broker exchange accepts Kubernetes workload-identity-bound short-lived
tokens as the service credential, and the gateway prefers them over the
static client secret. This realizes the ADR-0004 upgrade path for the first
service pair; the mechanism must be generic so later services adopt it
without bespoke plumbing.

Acceptance criteria:

- the broker validates workload tokens against the configured cluster token
  issuer JWKS/audience and maps a validated workload subject to a registered
  service client (same audience allow-list as today)
- a valid workload token on the exchange endpoint issues the same delegated
  token as the static-secret path (identical claims semantics: `sub`,
  `roles`, `aud`, `act`)
- an invalid, expired, wrong-audience, or unregistered workload token yields
  `401` on the exchange endpoint
- the static client-secret path remains functional and is documented as the
  dev-cluster fallback (dev overlays have no workload issuer)
- the gateway obtains its service token via the cluster token projection when
  configured and falls back to the static secret otherwise; the fallback is
  logged at warning level once per process

### R-4: Overlay and documentation alignment

The dev-k8s overlay and living-state docs reflect the hardened defaults.

Acceptance criteria:

- redaction is enabled by default in every overlay; the dev-mode opt-out is
  documented in the dev-k8s README
- the workload-token configuration contract (issuer, audience, projected
  volume) is documented in the dev-k8s README and in the
  identity-broker/tool-gateway READMEs
- `kustomize build` renders all overlays with the new configuration entries
- the gateway's `runtime-secrets.example.env` marks the static secret as the
  dev fallback and links the workload-identity path

## Non-Goals

- semantic or LLM-assisted redaction; general PII detection beyond the
  credential pattern set
- mutating tools, approval flows, and execution workers (Release 4)
- mTLS/SPIFFE dataplane sender-constraining — future hardening on top of
  ADR-0004, not this spec
- token revocation lists or refresh flows (short TTL remains sufficient)
- Redis HA/durability tuning and other deferred operational hardening items
- redaction of chat history or model inputs originating from the user

## Impact

- products touched: `products/tool-gateway` (redaction engine, metrics,
  service-token client), `products/identity-broker` (workload-token
  validation at exchange), `shared/platform-ops/gitops/dev-k8s` (config)
- contracts touched: none (redaction is gateway-internal; the evidence
  envelope gains a new error code value only)
- identity / policy / audit / execution safety impact: strengthens the trust
  model — shrinks the extractable-secret surface and prevents credential
  leakage to model providers; audit gains redaction counts; no policy
  semantics change
- living state docs to update on delivery: root `README.md`,
  `products/tool-gateway/README.md`, `products/identity-broker/README.md`,
  `shared/platform-ops/gitops/dev-k8s/README.md`, `CHANGELOG.md`, Release 1
  release notes (Known Limitations), SPEC-007/SPEC-008 delivery notes via
  changelog entries in this spec's delivery commit

## Open Questions

None — all resolved (see Changelog).

## Changelog

- 2026-07-30: created as `draft`, closing SPEC-007 Q-3 and the SPEC-008 R-3
  workload-identity upgrade path before the first non-dev deployment
- 2026-07-30: open questions resolved — Q-1: Kubernetes projected
  service-account token exchange (OIDC-federated at the broker) chosen over
  SPIFFE SVIDs: zero new infrastructure, reuses the broker's existing JWKS
  validation, no new trust root; SPIFFE remains the documented future option
  for multi-cluster federation or mTLS sender-constraining. Q-2: fail-closed
  `REDACTION_OVERFLOW` at the 20% bound confirmed. Q-3: bounded explicit key
  list (password, passwd, secret, api_key, apikey, token, access_key,
  client_secret, private_key, authorization) layered on strict value
  patterns; a generic key-substring matcher rejected as untestable and
  over-redaction-prone. Approved by workspace maintainers; implementation may
  begin per `plan.md`
- 2026-07-30: delivered per `plan.md` — redaction engine at the `invoke_tool`
  choke point with fail-closed `REDACTION_OVERFLOW` at the 20% bound,
  `gateway_tool_redacted_spans_total` metric and `redacted_spans` audit field;
  broker exchange accepts projected service-account tokens (cluster OIDC
  issuer JWKS, audience check, workload-subject registry) and the gateway
  prefers `GATEWAY_WORKLOAD_TOKEN_PATH` with a logged static-secret fallback;
  overlays/docs aligned; `make verify` green (88 + 47 + 123 tests)
