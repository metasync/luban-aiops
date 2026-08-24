# SPEC-027: Plan

## Approach

Extend the SPEC-026 catalog pipeline with a discovery layer that owns the
"which models does this provider offer" question at runtime, while every
downstream invariant (credential gating, model-name entry ids, alias map,
duplicate guard, discovery-safe public shape) is reused unchanged.

## Design

### Fallback ladder

Per configured provider, the model tuple resolves through:

```
override (<PROVIDER>_MODELS)          deterministic pin, discovery skipped
  -> live GET <base_url>/models       fresh, authoritative
  -> in-memory last-good              survives transient fetch failures
  -> Postgres last-good               survives pod restarts
  -> curated adapter series           SPEC-026 behavior, final fallback
```

The provider's resolved default model is force-included at every level.

### Components

- `services/model_discovery.py` (new): async httpx fetch with bearer auth
  and bounded timeout; OpenAI envelope parse; adapter filter predicates;
  in-memory last-good map; Postgres cache (sessions DB,
  `model_discovery_cache(provider PK, models JSONB, updated_at)`,
  `CREATE TABLE IF NOT EXISTS` bootstrap, psycopg in worker threads,
  all failures logged and swallowed); ladder resolver.
- `services/model_catalog.py`: `rebuild_catalog(entries)` + atomic swap of
  the module-level `MODEL_CATALOG` reference; startup order
  override -> live -> memory -> postgres -> curated.
- `providers/*`: refreshed `model_series` + `discover_filter` predicates
  (dated snapshots and non-chat modalities dropped).
- `runtime_settings.py`: `AGENT_MODEL_DISCOVERY_ENABLED` (true),
  `AGENT_MODEL_DISCOVERY_REFRESH_SECONDS` (1800),
  `AGENT_MODEL_DISCOVERY_TIMEOUT_SECONDS` (5); cache reuses `SESSION_DB_URL`.
- `app.py`: lifespan task — initial fetch, sleep loop, cancel on shutdown.

### Safety posture

- Discovery never raises into request paths; every failure mode ends in
  "serve the next ladder rung" with a warning log.
- Credentials never leave the runtime: `/models` payloads contribute ids
  only, and `to_public_dict()` is unchanged.
- Redis gains no new consumers (stays AgentScope kernel-bus-only, ADR-0003).

## Verification

- Unit tests: ladder levels (incl. restart-with-live-failure hitting the
  Postgres cache), atomic swap + alias rebuild, filter predicates,
  override precedence, disable knob, duplicate-id guard; mocked httpx,
  stubbed psycopg.
- Live: `/api/v2/models` reflects real provider lineups (DeepSeek V4
  family, DashScope qwen3.7/3.8 flagships), portal turn on a newly
  discovered model, audit attribution, restart-resilience check.

## Risks

- Provider `/models` payloads vary; filters tuned against the live
  endpoints during implementation, `<PROVIDER>_MODELS` remains the
  per-deploy escape hatch.
- A provider returning a duplicate model name across providers fails
  startup defensively (existing guard) — unlikely for curated providers.
