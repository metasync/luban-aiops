# v0.23.1 — Mutating Tool Name Regression Fix

Date: 2026-08-28
Release type: patch (correctness fix on the SPEC-037/038 signed-execution
path; no new actions, event types, or approval-path change)

## Summary

A live test of the bounded restart primitive surfaced that an approved
`k8s.delete_pod` invocation never executed: the execution-runtime worker
called the tool-gateway with `k8s_delete_pod` (the sanitized,
model-visible name) and the registry — keyed on the dotted canonical name
`k8s.delete_pod` — answered `TOOL_NOT_FOUND` every time. The park,
approval, signature, and digest verification all worked; only the name
handed to the last hop was wrong. v0.23.1 restores the canonical name
end-to-end.

## Root Cause

Toolkit functions are registered under sanitized names (dots become
underscores) because function-calling identifiers cannot contain dots.
Read-only tools were unaffected: each closure captures the canonical
dotted name and POSTs it to the gateway. Mutating calls, however, route
through the SPEC-037 signed envelope, whose `tool_name` was copied from
the parked tool call's model-visible name; the SPEC-038 worker then
invokes the gateway with the envelope field verbatim. The regression
entered with the worker handoff — before it, the in-process closure always
sent the canonical name. The opt-in `mutating-demo.sh` HITL leg would
have caught it, but it had not run since SPEC-038 shipped.

## What Changed

### Canonical name on parked calls (agent-service)

- `PendingConfirmation` now carries a sanitized→canonical name map
  captured from the toolkit at park time (`gateway_tool_name`), and
  `pending_calls_payload()` emits the canonical dotted name. Confirmation
  cards, durable confirmation records, approval inbox entries,
  `confirmation_decided` audit details, and the signed execution envelope
  all now agree on the name the gateway registry resolves. Risk-tier
  snapshots stay keyed by the sanitized model name.

### Tests

- New regression tests: payload canonical-name emission (mapped and
  unmapped), confirmation-frame canonical-name emission through the
  kernel park path, and the signed envelope carrying the canonical name.
- `mutating-demo.sh` HITL leg updated to expect the canonical name on the
  execution row (it previously pinned the buggy sanitized form).

## Posture

Fails-closed behavior is unchanged: an unmapped or unknown name still
answers `TOOL_NOT_FOUND` at the gateway, and every gate (risk-tier
admission, auto-allow invariant, HITL confirmation, signed-request
verification) remains independently enforced. This patch only makes an
approved, verified invocation reach the tool it was approved for.
