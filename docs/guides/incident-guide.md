# Incident Triage and Collaboration Guide

Operating the Release 3 incident slice: connecting alert sources, running and
interpreting agent triage, and collaborating on incidents through the portal
(SPEC-015). For deployment-level configuration see the
[Configuration Reference](configuration-reference.md); for the read-only
`incidents.list` / `incidents.get` agent tools see the
[Tool and Connector Guide](tool-configuration.md).

## Concepts

The slice is carried by the standalone `incident-service` product (record
store backed by Postgres in the dev-k8s overlay) with relay routes in
platform-gateway, an `incidents` connector in tool-gateway, an Incidents
panel in operator-portal, and the `incident_triaged` event type on the
durable trail.

**Incident lifecycle.** Statuses move `new` → `triaging` → `triaged` (or
`triage_failed`), and alert-sourced incidents move to `resolved` when
Alertmanager reports the group resolved (`resolved_at` is stamped). Resolution
preserves any existing triage report; a group that resolves before anyone
triages it simply closes as `resolved`.

**Fingerprint dedupe.** Alert-sourced incidents dedupe on the Alertmanager
`groupKey` (a stable hash of `commonLabels` when the group key is absent). A
re-fired group reuses the existing open incident and refreshes its
severity/title/summary/labels rather than creating a new record. Manual
incidents (reported through the portal) are always distinct records.

**Triage sessions.** Each triage runs exactly one agent-platform chat turn in
a dedicated session named `incident-<incident_id>`. If that session is already
owned by a different operator (someone else triaged first), triage falls back
to `incident-<incident_id>--<operator>`, and the incident record tracks the
session actually used so **Continue in chat** reopens the right one.

## Wiring Alertmanager

Incident intake is a bearer-token webhook. Point an Alertmanager
`webhook_configs` receiver at:

```
POST http://<incident-service>:8000/api/v1/webhooks/alertmanager
Authorization: Bearer ${INCIDENT_WEBHOOK_TOKEN}
```

Minimal receiver configuration:

```yaml
receivers:
  - name: luban-aiops
    webhook_configs:
      - url: http://incident-service.dev-luban-aiops.svc:8000/api/v1/webhooks/alertmanager
        http_config:
          bearer_token: <INCIDENT_WEBHOOK_TOKEN>
```

Payload contract: Alertmanager v4 webhook format. `groupKey` drives identity,
`status` selects fire vs. resolve, `commonLabels` feed labels (including the
`severity` label) and `commonAnnotations` feed content: the `summary`
annotation (or the alert name) becomes the incident title and `description`
the summary. `status: resolved` resolves the incident group; a resolution for
an unknown fingerprint is an idempotent success (`action: ignored`).

Delivery semantics:

- **Fail-closed authentication.** Wrong or missing token → `401`; token not
  configured (`INCIDENT_WEBHOOK_TOKEN` unset) → `503` with a structured
  reason. Alertmanager retries on both, so nothing is silently dropped.
- **Duplicate alert deliveries are tolerated.** Re-posting the same payload is
  a no-op on the incident record (fingerprint dedupe).
- **Malformed payloads** (bad JSON, non-object, missing alert content) → `400`
  with a structured reason; these are not retried by Alertmanager's default
  policy, so fix the payload rather than relying on retry.

## Portal workflow

Log in through operator-portal as a role with the incident actions (see
[Roles](#roles-and-policy)). The Incidents panel:

1. **List and filter.** Newest first; filter by status (`new`, `triaging`,
   `triaged`, `triage_failed`, `resolved`), severity, or source. Rows show
   opened time, title, severity badge, status badge, source, and id.
2. **Detail view.** Shows fingerprint/timestamp metadata, label chips, the
   summary, and when present the triage report (severity assessment, summary,
   evidence, hypotheses, ranked next steps) plus connector dispatch outcomes.
   A failed triage keeps the raw agent output behind a disclosure for
   inspection.
3. **Run triage.** Executes one agent turn; the button (labeled **Re-run
   triage** once a report exists) shows progress while the agent works and is
   disabled while a triage is in flight. Success renders the report; failure
   surfaces a plain error banner and leaves the incident in `triage_failed` —
   run it again once the underlying problem is fixed.
4. **Continue in chat.** Opens the chat view on the incident's triage session
   so follow-up questions carry the gathered evidence.
5. **Report incident.** Manual intake form: title, summary, severity
   (`critical`/`warning`/`info`), optional `key=value` labels.

**Interpreting triage output.** Triage is advisory: the agent grounds its
answer in read-only tools (`k8s.*`, `elastic.*`, `skills.search`,
`incidents.*`) and the incident payload, then returns ranked next steps with
priorities (`high`, `medium`, `low`). It never performs remediation.
`generated_by` records the operator who ran the triage, not the agent.

**Re-triage.** Any authorized operator may run triage again; the latest
outcome wins and the previous report is replaced (the durable trail keeps both
`incident_triaged` events). This is the collaboration model: one incident,
sequential triage turns, per-operator sessions underneath.

## Roles and policy

Actions and default grants (`policy-default.yaml`):

| Action | Roles | Meaning |
|---|---|---|
| `incident:read` | platform-admin, approver, operator, developer, read-only-observer | List and inspect incidents and triage reports |
| `incident:create` | platform-admin, approver, operator, developer | Report a manual incident |
| `incident:triage` | platform-admin, approver, operator, developer | Run agent triage |

Read-only observers can follow incident work but not trigger agent turns.
Adjust grants through the normal policy workflow documented in the
[Configuration Reference](configuration-reference.md).

## Verification

The end-to-end smoke test covers webhook auth controls, intake → dedupe →
resolve, gateway query visibility, operator triage through platform-gateway,
and the audit dispatch:

```bash
shared/platform-ops/e2e/incident-demo.sh
# cluster-side assertions only (no port-forwards needed):
SKIP_TRIAGE_LEG=true shared/platform-ops/e2e/incident-demo.sh
```

Health checks:

```bash
kubectl -n dev-luban-aiops exec deployment/incident-service -- \
  curl -fsS http://localhost:8000/health/ready
# liveness at /health/live; gateways include incident connectivity in their
# readiness payloads
```

The [Getting Started](getting-started.md) Incident Triage Tour walks the same
workflow interactively through the portal.

## Troubleshooting pointers

- Webhook `401`/`503`, triage failures, and the agent not seeing incidents are
  covered in the [Troubleshooting Guide](troubleshooting.md) under the
  incident symptoms.
- Triage turns fail closed: a failed turn marks the incident `triage_failed`
  with a reason; no partial state is published.
