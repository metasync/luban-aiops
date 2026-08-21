# Release Notes: 2026-08-21 — HITL Confirmation Bridging (SPEC-020)

## Summary

SPEC-020 closes the last autonomy gap in the read-only operations copilot:
tool batches the kernel gates with an ASK permission decision no longer
park silently. Agent-platform translates the kernel's
`RequireUserConfirmEvent` into a `confirmation_request` SSE frame, holds
the parked batch in an in-memory confirmation registry, and resumes the
parked reply when an authorized operator decides — approve executes the
exact parked tool calls, deny reports the refusal back into the agent
context. Platform-gateway fronts the decision with
`POST /api/v1/chat/confirm` under a new deny-by-default `chat:confirm`
action, and the portal renders an inline approval card whose decision
drives the resumed stream.

The delivery went through four live-check hardening rounds after the
first cluster deployment: the permission middleware now owns the gate
explicitly (agentscope's read-only fast path would otherwise auto-allow
every read-only tool and silently bypass the platform allow-list),
confirmed calls are delegated on resume instead of re-asked (agentscope
re-traverses the middleware chain for ALLOWED-state calls), the portal
card always reaches a final status, and stream schema v5 carries the
full tool payload on evidence frames so operators can expand the
complete output (e.g. all requested log lines) even when the model
summarizes. A post-delivery code review additionally made the TTL
cleanup path claim-aware so a racing expiry can never interrupt an
in-flight approved resume.

`make verify` is green: all product suites pass (agent-platform at 272
tests including the confirmation registry, kernel park/resume, and
middleware regression suites), all four Kustomize overlays render
cleanly, the eleven-rule deny-by-default bundle validates, and
`validate-version` confirms lockstep. This slice closes release
**0.6.0** (MINOR bump per the release-train convention).

## Change Set 1: Kernel park → portal card → resume (R-1, R-2, R-3)

### Highlights

- Permission-middleware ASKs park the active reply on
  `RequireUserConfirmEvent`; agent-platform emits a
  `confirmation_request` frame (`confirm_id`, message, pending calls
  with names and parameters) and registers the batch per session
- `POST /api/v2/chat/confirm` (agent-platform) resumes the parked reply
  with the operator's decision: approve feeds the exact parked
  `ToolCallBlock`s back into the kernel; deny feeds a refusal the agent
  sees in context
- Platform-gateway `POST /api/v1/chat/confirm` under the new
  deny-by-default `chat:confirm` action (granted to `platform-admin`,
  `approver`, `operator`, `developer`; `read-only-observer` excluded),
  with upstream status mapped eagerly before any frame goes out
  (404/409/410 passthrough, outages → 502)
- Registry safety: atomic claim makes decisions single-flight
  (duplicate confirms fail closed with 404), TTL expiry never silently
  evicts — an expired park is closed through `UserInterruptEvent` on
  the confirm attempt (410) or the next chat turn, and the cleanup path
  claims via `take_for_expiry` so it can never interrupt an in-flight
  approved resume
- Parked sessions reject new turns with 409 instead of forking state;
  foreign or unknown sessions answer 404 (house anti-enumeration
  convention)

### Why It Matters

- write-adjacent or unvetted tools can join the catalog later without
  granting the agent unilateral execution — the ASK surface is already
  bridged end to end
- every decision is attributable: `confirmation_decided` audit events
  are tee'd off the kernel-applied `confirmation_result` frame, so only
  decisions the kernel actually applied reach the durable trail

## Change Set 2: Permission gate ownership (live-check rounds 1–2)

### Highlights

- `GatewayPermissionMiddleware` answers every non-allow-listed tool
  with an explicit ASK instead of delegating to agentscope's
  `PermissionEngine`, whose read-only fast path auto-allows read-only
  invocations in every mode and would silently bypass the platform
  allow-list — the allow-list (`AGENT_GATEWAY_TOOL_AUTO_ALLOW`) is the
  only auto-approval surface
- Confirmed calls re-traverse the middleware chain with
  `tool_call.state == ALLOWED`; the middleware delegates them to the
  built-in resolution so an approved batch executes on resume instead
  of re-parking the reply in an endless approve loop

### Why It Matters

- deny-by-default holds even against framework-level conveniences — the
  platform's policy is what decides, not a kernel default
- approval is one round-trip: card → approve → execution → finished
  reply in one continuous stream

## Change Set 3: Evidence transparency (live-check rounds 3–4)

### Highlights

- Stream schema bumps v4 → v5: `tool_result` frames carry an optional
  `data` field — the full tool payload when its serialized size stays
  within `AGENT_TOOL_DATA_MAX_CHARS` (default 32000); oversized
  payloads remain audit-trail-only so SSE frames stay bounded
- Portal evidence cards offer a "Show full output" expander with the
  complete tool result; multi-line text fields (such as the `logs`
  blob from `k8s.get_pod_logs`) render as raw log-style blocks with
  wrapping lines instead of one escaped JSON string
- The confirmation card's status line always reaches its final state —
  including mid-stream error frames and streams that end without a
  `confirmation_result`

### Why It Matters

- operators can verify the exact tool output behind a summarized reply
  without leaving the chat surface or digging in the audit trail
- the card never misleads about a decision's outcome

## Validation

- `make verify` green: agent-platform 272 tests (new
  `test_hitl_confirmations.py` and `test_chat_confirm.py` suites plus
  middleware regression tests), all other product suites pass, four
  overlays render, eleven-rule bundle validates, version lockstep holds
- Deployed to the dev cluster and live-checked end to end: tightening
  `AGENT_GATEWAY_TOOL_AUTO_ALLOW` to exclude `k8s.get_pod_logs` forced
  the ASK; the portal walkthrough confirmed card → approve → tool
  execution → full log output in the evidence expander, with
  `confirmation_decided` in the audit trail; the override was reverted
  after the check

## Known Limitations

- The confirmation registry is per-process memory by design: a parked
  confirmation does not survive an agent-service restart (confirm
  attempts fail closed with 404/410 rather than auto-running a parked
  batch)
- A resumed turn that parks again emits a fresh card — chained parks
  are supported, but each needs its own decision

## Related Documents

- `../../specs/SPEC-020-hitl-confirmation-bridging/spec.md`
- `../../specs/SPEC-020-hitl-confirmation-bridging/plan.md`
- `../../workspace/hitl-bridging-spike.md`
- `../../specs/README.md` (spec index, SPEC-020 delivered)
- `../../../CHANGELOG.md`
