# Release Notes: 2026-07-30 — Release 1 (Read-Only Operations Copilot)

## Summary

`Release 1` delivers the read-only operations copilot: an operator can sign in
through the portal, ask the agent diagnostic questions, and the agent can now
discover and invoke read-only platform tools (Kubernetes status and diagnostics)
through an authenticated, policy-enforced, fully audited path.

The release closes with two specs delivered together:

- `SPEC-007` — read-only tool execution framework (tool registry, K8s
  read-only connector, policy-gated discovery and invocation, structured
  evidence results)
- `SPEC-008` — service-to-service identity via broker-mediated token
  delegation (implementing `ADR-0004`), which unblocked SPEC-007 R-4/R-6 and
  closed its open questions Q-1/Q-2

`make verify` is green: `agent-platform` 88 tests, `identity-broker` 38 tests,
`tool-gateway` 105 tests, and all GitOps overlays render cleanly.

## Change Set 1: Read-Only Tool Execution (SPEC-007)

### Highlights

- added a tool execution framework to `tool-gateway`: `ToolRegistry`, a
  `BaseTool` abstraction, and a structured evidence envelope for results
- shipped a Kubernetes read-only connector: `k8s.list_pods`, `k8s.get_pod`,
  `k8s.get_events`, `k8s.get_pod_logs`
- exposed `GET /api/v2/tools` (discovery) and `POST /api/v2/tools/invoke`
  (execution with deny-by-default policy enforcement and audit logging)
- wired the agent-platform runtime kernel to discover gateway tools and
  register them into the AgentScope Toolkit (empty Toolkit when unconfigured)

### Why It Matters

- the agent can ground answers in live cluster state instead of generic advice
- every tool call passes the same deny-by-default policy model as chat, with
  audit trails per invocation
- read-only scope keeps the release safe: no mutating operations exist yet;
  action tools and approval gating are deferred to Release 4

## Change Set 2: Broker-Mediated Token Delegation (SPEC-008)

### Highlights

- platform JWTs are now audience-bound (`aud`), closing the cross-service
  replay weakness
- `identity-broker` gained `POST /api/v1/auth/exchange`: authenticates a
  registered service credential and mints short-lived delegated tokens
  (`sub`/`username`/`roles` copied — never elevated — plus an RFC 8693 `act`
  actor claim and the requested audience, TTL 300s)
- `tool-gateway` exchanges the verified user token for a delegated token
  (cached per user subject with near-expiry re-exchange) and forwards it to
  `agent-platform` as `Authorization: Bearer`; exchange failure is non-fatal
  (chat proceeds tool-less)
- `agent-platform` relays the delegated token on tool discovery and
  invocation, bound per-user into the toolkit closures; `identity_context` was
  removed from the invoke payload — identity is carried exclusively by the
  token
- tool routes derive identity solely from the verified token; discovery is
  gated by a new `tools:list` policy action; audit logs record both the human
  subject (`sub`) and the acting service (`act`)
- dev-k8s overlay wires audience/client-id/TTL config; the gateway and broker
  service secrets are provisioned as optional K8s Secrets (not committed)

### Why It Matters

- the agent holds only a short-lived, least-privilege, audience-bound
  credential — never the user's broad token
- `identity-broker` remains the sole signing authority; no new trust root
- audit can now answer both "who requested" (`sub`) and "which service acted"
  (`act`)
- the delegation pattern is reusable for future service-to-service calls

### Validation

- contract tests bind gateway and identity-broker models to the updated
  `identity-token.schema.json` (portal and delegated token shapes)
- exchange security paths covered: missing/invalid credential → 401,
  invalid/expired subject → 401, disallowed audience → 400, roles never
  elevated
- audience enforcement: wrong/missing `aud` → 401 before policy evaluation
- delegation cache hit/miss/expiry, exchange-failure degradation, and the
  synthetic dev identity path (same exchange route, no bypass)
- per-user toolkit isolation: one user's credential is never reused for
  another user's session
- metrics: `token_exchange_total` (broker), `delegation_exchange_total` and
  `delegation_cache_total` (gateway)

## Known Limitations

- tool output (e.g. raw pod logs) reaches the model provider unredacted; a
  redaction decision is tracked as SPEC-007 Q-3 and must not be deferred past
  the first non-dev deployment
- the gateway's service credential is a static audience-scoped client secret
  for Release 1; Kubernetes workload-identity-bound short-lived tokens are the
  documented upgrade path (at the first non-dev deployment or Release 4)
- delegated tokens are cached in-memory per gateway replica; a replica restart
  simply re-exchanges on the next request
- end-to-end dev-cluster wiring of the dev signing key for the synthetic
  identity path is an overlay provisioning step, covered in isolation by unit
  tests
- mutating tools and approval flows are out of scope by design (Release 4)

## Related Documents

- `../../specs/SPEC-007-tool-execution-framework/spec.md`
- `../../specs/SPEC-008-service-to-service-identity/spec.md`
- `../../adr/` (ADR-0003, ADR-0004)
- `../identity-and-authorization-design.md`
- `../../../CHANGELOG.md`
