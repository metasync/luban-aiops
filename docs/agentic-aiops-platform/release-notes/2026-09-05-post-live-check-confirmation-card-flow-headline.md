# Post-Live-Check Remediation: Live Confirmation Card Flow Headline (v0.33.1)

Date: 2026-09-05

Next-day patch from a live test of v0.33.0: the operator's HITL
confirmation card rendered without its browser-flow *description* while
the approver inbox card showed it, and the operator's card only gained
the description after the decision. Backend serialization plus two
shared contracts touched; the portal was already correct and is
unchanged.

## What the investigation proved

- Both views render the same portal `ConfirmationCardView` off
  `flowSummary.description`, so the divergence was in the data each
  received, not in the rendering.
- The approver inbox and the operator's post-decision/reload card read
  the **durable** `ConfirmationRecordModel`, whose `flow_summary` JSONB
  column (SPEC-051 R-6) carries the headline — so they always showed it.
- The operator's **live** card reads the `confirmation_request` SSE
  frame. That frame is serialized through `AgentStreamEvent` in
  `_normalize_stream_event`, and the model had no `flow_summary` field,
  so the kernel's headline (`frame["flow_summary"]`, set from
  `FlowContext.summary()`) was dropped at the serialization boundary and
  never reached the wire.
- No test guarded that boundary: the portal decoder tests mock the frame
  *with* `flow_summary`, and the SPEC-051 delivery smoke-tested only the
  durable JSONB persistence — so the live-frame half of R-6 shipped
  unverified.

## What changed

- `AgentStreamEvent` (`schemas/v2.py`) gains the optional `flow_summary`;
  the stream contract bumps v8 → v9 to declare it.
- `_normalize_stream_event` (`api/v2/routes.py`) passes `flow_summary`
  through a defensive `_coerce_flow_summary` that keeps only the
  contract's five string fields (`skill_id`, `origin`, `title`,
  `description`, `risk_class`) and degrades a non-dict summary to absent,
  so a malformed headline can never fail the frame's
  `additionalProperties:false` validation.
- `agent-session.schema.json` declares the same `flow_summary` on the
  durable confirmation-card items — a latent gap, since
  `ConfirmationRecordModel` already served it.
- Three contract tests pin it: the live frame preserves `description`
  (and every field), malformed/unknown fields are dropped while the frame
  stays valid, and a durable card carrying a headline conforms to the
  session contract.

## Untouched

The portal (`ConfirmationCardView`, decoder, models) was already correct
and is unchanged; the kernel already set `frame["flow_summary"]`; no API
route, policy action, or audit event type changed. Version lockstep
0.33.1 validated across all products and the portal; `make verify` green
before `make build`.
