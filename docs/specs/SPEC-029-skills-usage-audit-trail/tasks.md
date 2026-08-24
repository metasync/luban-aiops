# SPEC-029: Tasks

## Contract & audit-service (R-1)

- [x] T-1 (R-1): `audit-event.schema.json` — `skill_searched`,
      `skill_retrieved`, `skills_synced` enum values + `details`
      per-type payload docs
- [x] T-2 (R-1): audit-service `schemas/audit.py` `EventType` Literal
      +3 values; confirm `test_contracts.py` enum parity stays green;
      ingest/query round-trip test for a `skill_searched` event in
      `tests/test_routes.py`

## skills-hub emission (R-2, R-4)

- [x] T-3 (R-2): `skills_hub/services/audit_emitter.py` (canonical copy)
      + `record_audit_emit` in `core/metrics.py` +
      `SKILLS_AUDIT_SERVICE_URL` / `SKILLS_AUDIT_CLIENT_ID` /
      `SKILLS_AUDIT_CLIENT_SECRET` in `core/config.py`
- [x] T-4 (R-2): `api/routes/skills.py` — capture `authenticate_caller`
      client_id; emit `skill_searched` (search) and `skill_retrieved`
      (get, hit + not-found miss); list stays silent
- [x] T-5 (R-4): `services/sync.py` — `skills_synced` emission on both
      arms of `sync_once`
- [x] T-6 (R-2, R-4): skills-hub tests — `test_audit_emitter.py`
      (envelope contract validation, gating no-op, delivery
      ok/4xx/transport), route emission payloads, sync-cycle emission,
      config field parsing

## tool-gateway correlation (R-3)

- [x] T-7 (R-3): `gateway_service.py` identity dict gains `request_id`;
      `skills_connector.py` `_get` forwards `x-request-id`; tests for
      both; skills-hub joins `AuditEmitterParityTest` in
      `test_module_parity.py`

## Deployment & docs (R-5)

- [x] T-8 (R-5): `sync-audit-secrets.sh` skills-hub registration
      (registry line, secret upsert, sync, restart);
      `dev-k8s/base/skills-hub/runtime-config.env` audit knobs
- [x] T-9 (R-5): `configuration-reference.md` `SKILLS_AUDIT_*` rows;
      skills-hub README audit bullet; CHANGELOG entry

## Delivery

- [ ] T-10: `make verify`; commit; `make build`; `make deploy`; run
      `sync-audit-secrets.sh`
- [ ] T-11: live verification — trigger a portal skills search, query
      `GET /api/v1/audit/events?event_type=skill_searched`, confirm
      request-id join with the matching `tool_invoked` event and a
      `skills_synced` event per source; L3 gate; push
