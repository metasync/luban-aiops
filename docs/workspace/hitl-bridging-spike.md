# Spike: HITL Confirmation Bridging (kernel ASK → v2 SSE → portal)

Status: spike complete — findings below; promotion to a spec is pending review
Date: 2026-08-21
Roadmap home: Exploration Backlog "HITL confirmation bridging" (own spec; MUST precede any write/mutating tool — SPEC-018 Future Scope)
Verified against: agentscope 2.0.6 (locked), agent-platform runtime kernel at 0.5.0

## 1. Question

Can kernel confirmation events (agentscope `ASK` / `RequireUserConfirmEvent`)
be mapped onto v2 SSE frames with portal approve/deny and session
suspend/resume, without bypassing policy enforcement, audit, or identity
delegation — and what must be designed before any write/mutating tool ships?

## 2. Findings — kernel mechanics (verified)

The locked agentscope 2.0.6 kernel already carries the full suspend/resume
machinery; nothing needs to be invented kernel-side:

- A tool call whose permission decision is `PermissionBehavior.ASK` parks the
  reply: the tool call enters `ToolCallState.ASKING` and the agent yields a
  `RequireUserConfirmEvent` carrying `reply_id` and the pending `tool_calls`,
  then ends the reply stream (`agentscope/agent/_agent.py`,
  `agentscope/event/_event.py`).
- Resume is first-class: `agent.reply_stream()` accepts a
  `UserConfirmResultEvent` (per-call `ConfirmResult(confirmed, tool_call,
  rules?)`) or a `UserInterruptEvent` to abort a parked reply. On interrupt
  the agent closes every pending tool call with an interrupted result and ends
  the reply without re-entering the reasoning loop.
- Partial confirmation is explicit: if only some pending tool calls are
  confirmed, the agent does **not** re-emit requiring events for the rest.
- Authoritative pending state is the session's own `state.context` (the
  `ASKING` tool call); this is the same state surface the SPEC-017
  snapshot/restore persists (`_snapshot_state` after each completed turn).

Platform-side today (`runtime_kernel.stream_events`): only `Msg` inputs are
ever fed to `reply_stream`; a `RequireUserConfirmEvent` is emitted as a
generic normalized event, the stream ends, and the parked call silently never
runs. This is exactly the SPEC-018 headless posture (allow-list pre-answers
the gate; everything else keeps the ASK default).

Reference designs inside agentscope.app (reference-only per SPEC-018 R-7; no
runtime dependency without an adoption-gate pass):

- `SubagentHitlProjector` (`_service/_projectors/_subagent_hitl.py`): mirrors
  a parked member-session confirmation onto a leader session; authoritative
  state stays the parked session's `ASKING` tool call; the mirror carries no
  TTL and is healed by reconcile-on-read at replay time. Useful pattern
  reference for pending-request projection and stale-entry healing.
- AGUI protocol middleware: reference only if interaction richer than SSE
  evidence frames is ever needed.

## 3. Proposed shape of the bridging spec

### 3.1 Contract: new v2 SSE frame types (schema bump v3 → v4)

`agent-stream-event.schema.json` gains, per ADR-0006's allowance for
deliberately grown interaction semantics:

- `confirmation_request` — emitted when the kernel parks: `call_id`(s),
  `tool_name`(s), `parameters`, a confirmation `confirm_id`, and the kernel's
  permission message. Reuses the field conventions of `tool_call` frames.
- `confirmation_result` — emitted after the decision lands: `confirm_id`,
  `status` ∈ {approved, denied, expired, interrupted}. On approval, the
  existing `tool_call` / `tool_result` evidence frames follow unchanged — the
  evidence contract stays byte-stable; confirmation frames are additive.

`tool_result.status` already carries a `denied` enum value; the deny path
renders through existing portal evidence-panel code paths.

### 3.2 Answer-return endpoint (session suspend/resume)

- New small contract endpoint on agent-platform, e.g.
  `POST /api/v2/chat/confirm`, accepting `{session_id, confirm_id, decisions[]}`
  and returning the resumed turn as the same SSE stream shape
  (`GET /api/v2/chat/stream` contract). Proxied through platform-gateway like
  the existing chat routes (aud=platform-gateway, `enforce_policy`).
- The runtime keeps a per-session pending-confirmation registry keyed by
  `confirm_id`; the resume path feeds `UserConfirmResultEvent` (or
  `UserInterruptEvent` for cancel) into `agent.reply_stream` and streams the
  continuation.
- Pending requests get a bounded TTL (proposed default 10 min,
  `AGENT_HITL_CONFIRM_TIMEOUT`); expiry emits `confirmation_result` with
  `expired` and closes the parked calls — no indefinite headless parking.

### 3.3 Identity, policy, and audit (the trust layer)

- **Identity before privilege**: the resume request is authenticated through
  the same gateway path; only the session's owning operator (or a role the
  later R4 approval workflow explicitly grants) may answer a confirmation.
  The delegated token set into `DELEGATED_TOKEN` on the resumed turn is the
  **confirmer's** token, so the tool-gateway sees the approving identity on
  the actual invocation.
- **Policy stays authoritative**: kernel ASK confirmation is *not* platform
  policy. The tool-gateway still enforces admission and policy on every
  invocation; a confirmed call can still be denied by policy, and that
  surfaces as today's gateway `denied` result.
- **Audit**: emit audit events for confirmation-requested,
  confirmation-decided (who, when, approve/deny), and the linkage to the
  resulting tool invocation `call_id`, through the SPEC-013 durable trail.
- **Transparency consistency (agreed addition)**: if R4 introduces
  policy-level `require_approval` outcomes, both the live permission matrix
  (`GET /api/v1/policy/matrix`, SPEC-019) and the audit trail must render
  approval requirements and decisions consistently. Decision point for this
  spec: reserve a `confirmation` dimension in audit events now so the R4
  approval queue can reuse it rather than retrofitting.

### 3.4 Two confirmation layers — must not be conflated

| Layer | Gate | Decided by | Delivered by |
|---|---|---|---|
| Kernel HITL confirmation (this spec) | agentscope permission `ASK` on tool execution | session operator, inline in the chat stream | bridging spec (SPEC-020 candidate) |
| Platform approval workflow (R4) | policy engine `require_approval` on bounded actions | designated approver, via approval queue | policy-center / execution-runtime specs |

They share portal rendering conventions and the audit `confirmation`
dimension, but are different decisions at different layers; the bridging spec
must not grow the approval queue.

## 4. Open questions for the spec phase

1. **Parked-state durability**: does the SPEC-017 snapshot carry an `ASKING`
   tool call across pod restarts (state.context persistence), and does
   `ensure_agent` restore resume a parked reply correctly? If not, the
   fail-safe is expiry-on-rebuild — verify with a prototype before freezing
   requirements.
2. **Multi-tool-call batching**: a single `RequireUserConfirmEvent` can carry
   multiple tool calls; decide whether the portal answers all-or-nothing
   (simpler v1) or per-call (kernel supports partial confirmation).
3. **Deny semantics**: on deny, feed `confirmed=False` and let the agent
   reason about the refusal (kernel closes the call with a denied result) vs.
   ending the turn. Prefer the former — it keeps the agent grounded about why
   no action happened (anti-fabrication posture).
4. **Concurrent turns**: a parked session must reject new chat turns with a
   clear "confirmation pending" contract error rather than forking state.
5. **ASK → DENY tightening**: stays a follow-up per SPEC-018; once the
   confirmation model is implemented, non-allow-listed tools in the headless
   fallback (e.g. blocking/incident paths that never stream) should become an
   explicit observable DENY.

## 5. Recommendation

Promote to **SPEC-020: HITL Confirmation Bridging** as the first R4 release
slice (0.6.0 train). Scope it to the read-to-write bridge only: kernel ASK
mapping, contract frames, confirm endpoint, identity/audit wiring, and
portal rendering (the SPEC-019 sectioned sidebar already anticipates the
surface). Explicitly out of scope: any write/mutating gateway tool, the
policy-center approval queue, and execution-runtime — those are subsequent
R4 slices that depend on this spec.

Update on promotion: the delivery-roadmap Exploration Backlog row
"HITL confirmation bridging" moves from spike-needed to spec-numbered;
"ASK → DENY tightening" stays parked as its declared follow-up.
