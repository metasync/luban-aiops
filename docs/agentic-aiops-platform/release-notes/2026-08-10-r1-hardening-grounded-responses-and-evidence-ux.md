# Release Notes: 2026-08-10 — R1 Hardening (Grounded Responses, Audit Visibility, Evidence UX)

## Summary

This wave completes and hardens the Release 1 read-only operations copilot
end-to-end. An operator can ask diagnostic questions and receive answers that
are provably grounded: every tool call surfaces as structured evidence,
structured audit events are actually visible in service logs, the agent can
read across the whole cluster, and the portal presents evidence and audit
detail as supportive, collapsible context that follows each answer.

The wave covers `SPEC-011` (observability and evidence panels) delivery
follow-ups plus four reliability/security fixes discovered during live
dev-cluster validation.

`make verify` is green: `agent-platform` 122 tests, `tool-gateway` 109 tests,
`platform-gateway` 77 tests, `identity-broker` 49 tests, and all GitOps
overlays render cleanly. The wave was validated live on the dev cluster with
real health checks (including an ArgoCD diagnosis whose every claim mapped to
a Kubernetes Audit-ID).

## Change Set 1: Grounded Responses End-to-End (SPEC-011 completion)

### Highlights

- fixed agent toolkit registration for AgentScope 2.x (toolkit construction
  now passes tools at build time) and auto-approves a vetted read-only
  allow-list so headless streams no longer stall awaiting confirmation
- extended the agent-platform stream adapter to the v3 stream contract:
  `tool_call`/`tool_result` frames now pass through to the portal instead of
  being coerced into `message_delta`, restoring evidence fields
  (`parameters`, `status`, `evidence`, `data_summary`, `error`)
- per-request trace queues bind evidence frames to the exact chat request
  (SPEC-011 R-2)

### Why It Matters

- answers are grounded in live cluster state and the portal can prove it:
  each tool call renders with parameters, outcome, timing, and risk level

## Change Set 2: Audit Log Visibility and Cluster-Wide Read Access

### Highlights

- added `configure_logging()` to all four services so INFO-level structured
  events (`tool_invoked`, `http_request`) survive uvicorn's WARNING
  root-logger default; the requirement is codified in
  `shared/shared-contracts/observability-conventions.md`
- replaced tool-gateway's namespaced Role with a cluster-wide read-only
  ClusterRole (`luban-tool-gateway-readonly`: get/list/watch across core,
  apps, batch, networking, autoscaling) so the copilot can diagnose any
  namespace while remaining strictly read-only

### Why It Matters

- the audit trail that Release 1 promised is now actually emitted and
  inspectable in service logs
- operators are no longer limited to one or two namespaces when asking for
  cluster diagnostics

## Change Set 3: Security Hardening

### Highlights

- L3 deep-review finding (CWE-862) remediated: tool permission auto-approval
  narrowed from "any read-only tool" to an explicit vetted allow-list
  (`AGENT_GATEWAY_TOOL_AUTO_ALLOW`, env-overridable; empty approves nothing)
- fixed a token-rotation cache bug: delegated tokens rotate mid-session
  (portal refresh, 300s TTL) but tool discovery only ran at agent creation;
  `_build_request_toolkit` now discovers with the current token on cache
  miss, and empty discovery results are never cached — sessions can no
  longer be stranded without tools until browser refresh

### Why It Matters

- permission decisions stay explicit and reviewable
- long-lived chat sessions remain tool-enabled across credential rotation

## Change Set 4: Operator Portal Evidence and Audit UX

### Highlights

- each agent reply is followed by its own collapsed "Tool evidence" group
  (summary line shows live counts: `8 calls · 7 ok · 1 denied`); expanding it
  reveals that turn's evidence cards and an "Audit trail · this turn" card
  (tool, status, executed at, duration, risk, source, plus request/session
  IDs)
- evidence groups are created lazily (purely conversational turns add
  nothing) and provenance follows the answer it grounds through the chat
  history
- sticky smart-scroll: the view follows the stream only while the reader is
  near the bottom, so evidence never fights the streamed answer

### Why It Matters

- supportive detail no longer crowds the primary reading flow, while trust
  signals (what ran, what succeeded, what was denied) remain one click away

## Known Limitations

- the authoritative audit trail still lives only in pod logs: ephemeral and
  unqueryable. The portal audit card is a rendition of streamed evidence for
  the caller's own turn. A durable, queryable, permission-scoped audit API
  (cross-user troubleshooting, retention, redaction reuse) needs its own
  spec — next free number is SPEC-013 (SPEC-012 is the operator guide)
- portal evidence/audit history lives for the browser page lifetime only;
  a refresh starts clean (session conversation memory persists server-side)
- delegated tokens are cached in-memory per gateway replica (unchanged from
  Release 1); rotation is now handled transparently by the agent runtime

## Related Documents

- `../../specs/SPEC-011-observability-and-evidence-panels/spec.md`
- `../../shared/shared-contracts/observability-conventions.md`
- `../../shared/platform-ops/gitops/dev-k8s/base/tool-gateway/rbac.yaml`
- `../../../CHANGELOG.md`
