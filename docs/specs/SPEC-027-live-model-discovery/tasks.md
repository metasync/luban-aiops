# SPEC-027: Tasks

## Backend (agent-platform)

- [x] T-1 (R-5): `runtime_settings.py` — `AGENT_MODEL_DISCOVERY_ENABLED`,
      `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS`,
      `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS`
- [x] T-2 (R-4, R-6): provider adapters — refreshed `model_series` +
      `discover_filter` predicates
- [x] T-3 (R-1, R-2): `services/model_discovery.py` — httpx fetch,
      envelope parse, in-memory + Postgres cache, ladder resolver
- [x] T-4 (R-3): `model_catalog.py` rebuild + atomic swap; `app.py`
      lifespan refresh task; metrics
- [x] T-5 (R-1…R-5): unit tests — ladder, swap, filters, override,
      disable knob, duplicate guard

## Docs

- [x] T-6: configuration-reference knobs, agent-platform README,
      runtime-profiles secrets example note, CHANGELOG entry

## Delivery

- [x] T-7: `make verify`; commit; `make build`; `make deploy`
- [x] T-8: live verification — real lineups in `/api/v2/models`, portal
      turn on a newly-discovered model, audit attribution,
      restart-resilience; L3 gate; push
