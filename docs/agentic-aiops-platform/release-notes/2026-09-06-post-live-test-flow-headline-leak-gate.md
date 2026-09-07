# Post-Live-Test Remediation: Flow-Headline Leak on Non-Browser Approval Cards (v0.34.1)

Date: 2026-09-06

Same-area follow-on to v0.33.1, from a live test of v0.34.0: a session that
first bound a browser flow and later parked an unrelated non-browser
mutation rendered that action card wearing the lingering flow's headline.
Kernel-only; no contract, policy, audit, or portal change.

## What the investigation proved

- The confirmation card's `flow_summary` (the SPEC-051 R-6 flow headline)
  was attached whenever a flow context was bound in the session
  (`FLOW_CONTEXTS.get(session_id) is not None`) — ambient session state —
  with no check that the *parked batch* actually carried a browser write.
- So a `k8s.delete_pod` parked while a `web.navigate`-bound "Reset User
  Password" flow lingered inherited that headline, mis-framing an infra
  action as a browser flow; a read-tier-only batch would leak it too.
- Flow-unlock authority (`_record_flow_approval`) already used the correct
  write-tier predicate (`_batch_has_browser_write` → `BROWSER_WRITE_TOOLS`),
  so framing and authority disagreed: the card *said* "flow" for a batch
  that would never arm flow-unlock.
- The leak was in the data (the gate), not the rendering: the live frame and
  the durable record are both built from the same `browser_flow` summary, so
  the stale headline reached the operator's live card, the approver inbox,
  and the re-loaded owner transcript alike.

## What changed

- Extracted the write-tier test into one shared static helper,
  `_tool_names_have_browser_write(tool_names, gateway_names)` (true iff a
  sanitized name maps into `BROWSER_WRITE_TOOLS`); `_batch_has_browser_write`
  now delegates to it, so flow-unlock authority is unchanged.
- The confirmation-frame builder gates `browser_flow` on that helper using
  the *same* `tool_calls` and `gateway_names` it registers the park with, so
  the headline is attached iff the parked batch is a browser-write batch —
  framing and authority now share one predicate and can never disagree.
- A non-browser (or read-tier-only) batch falls back to action-level
  rendering; a browser-write batch still carries the headline. Because the
  durable record is built from the same gated summary, the approver inbox and
  the re-loaded owner transcript are corrected too.
- Pinned by `TestConfirmationFrameFlowHeadline`: a non-browser batch carries
  no `flow_summary`, a read-tier-only browser batch carries no `flow_summary`,
  and a browser-write batch keeps the headline.

## Untouched

The portal (`ConfirmationCardView`, decoder, transcript), the stream and
session contracts, the flow-unlock one-gate behavior (SPEC-051 R-1..R-3), the
gateway deviation guard, and SPEC-037 signed execution are unchanged; no
policy action or audit event type changed. This is a correctness follow-on to
the v0.33.1 live-frame fix, not a change to it. Version lockstep 0.34.1
validated across all products and the portal; `make verify` green.

## Deployment state

Recorded 2026-09-07 for provenance completeness; the fix itself shipped
2026-09-06. The clean v0.34.1 image build and dev-k8s deploy were
**deliberately deferred** and fold into the next spec delivery. The cluster
already ran this code under the dirty tag
`0.34.0-dev-k8s-123c4b6-dirty-20260906161715`, so rebuilding for this
kernel-only patch would have produced no behavioral change in the environment
used for live verification. It is noted here because a `-dirty-` tag is not
reproducible from a git ref, and the platform's traceability posture (ADR-0008)
favors documenting the verification environment's provenance over leaving it
implied. The next delivery (SPEC-054) rebuilds every image this patch lives in —
agent-platform among them — which is when the v0.34.1 content lands as a
properly tagged image. If that delivery slips or is descoped, the clean build is
owed at the following slice rather than left indefinitely on the dirty tag.
