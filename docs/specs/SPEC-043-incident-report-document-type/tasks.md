# SPEC-043 Tasks

## R-1: The `incident_report` type on the existing substrate

- [x] Extend `operation-document.schema.json`: `incident_report` enum
      value + the digest object (incident / triage / dispatches /
      session sections) with SPEC-015 parity bounds
- [x] Accept the new type in the agent-platform document create path;
      confirm store conventions untouched (both backends, cap 20,
      30-day TTL)
- [x] Contract tests: fixture envelopes for both types validate;
      digest bounds parity with the incident-service models

## R-2: Incident-report assembly

- [x] New `incident_report.py` assembler: verbatim copies of the
      incident envelope, triage report (`not_triaged` marker),
      dispatches, and linked-session digest
- [x] Session tier logic: owner-full / foreign-metadata-only behind
      the trusted `X-Foreign-Coverage` header / `foreign_denied` /
      `missing`
- [x] Unknown incident id → structural 404; `triage_failed` and
      session-less incidents still assemble; no incident-state
      mutation anywhere in the path
- [x] Degradation: 502 upstream unreachable, `unavailable` session
      section on store failure, never a 500

## R-3: Internal incident client and dual-action gate

- [x] New `incident_client.py` in agent-platform (Basic query
      credential, bounded timeout, `x-request-id` forwarding,
      structured error mapping) + the three `AGENT_INCIDENT_*`
      settings knobs
- [x] Gateway create route: enforce `incident:read` in addition to
      `documents:create` for `incident_report`; `DocumentCreateRequest`
      accepts `incident_id` (pattern-validated) for the incident type
      and rejects cross-type field mixing
- [x] dev-k8s wiring: agent-platform credential in the incident-service
      query-auth registry Secret + URL knob via the existing
      Secret-sync conventions
- [x] Tests: not-configured 503, unauthorized 401, unknown-id 404,
      transport-failure 502, both gate denials

## R-4: Prose layer (inherited, digest-only)

- [x] Extend the prose prompt builder for the incident-report digest;
      prompt-purity regression test (digest fields only)
- [x] `prose_status` behavior and rendering identical to shift
      summaries

## R-5: Audit (no new event types)

- [x] `document_created` carries `incident_id` for the new type (agent
      layer + gateway log event); published/cross-owner-read events
      unchanged
- [x] Tests asserting event payloads and the no-new-event-type
      invariant

## R-6: Portal Documents support

- [x] Creation dialog: type radio, incident picker (existing incidents
      list surface), label + prose toggle retained
- [x] Drawer rendering: Incident / Triage / Dispatches / Session tabs
      + Raw JSON, narrative panel, marker alerts, foreign metadata
      banner; type badge on list rows; envelope-only listings intact
- [x] Vitest coverage for dialog + rendering; zero antd deprecation
      warnings (guard active)

## Delivery train

- [x] Living-state docs: portal-user-guide, incident-guide,
      authorization-matrix, documents-digest-reference,
      configuration-reference
- [x] Version lockstep to 0.25.0, CHANGELOG + release note + index
- [x] make build → make verify → make deploy → live checks (triaged
      incident report create/publish/cross-owner read on the durable
      trail; `triage_failed` and session-less marker paths)
- [x] Commit, security scan gate, tag v0.25.0, push, repowiki docs
      commit
