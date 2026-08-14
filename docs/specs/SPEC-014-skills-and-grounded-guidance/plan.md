# SPEC-014 Plan: Skills And Grounded Guidance (Release 2)

## Approach

skills-hub is built as a near-twin of `audit-service` — same frozen-dataclass
settings, structured logging, `/health` + `/metrics`, store-protocol with
in-memory and Postgres backends, Basic-client/workload-token auth, and the
same overlay/secrets-sync pattern — so the platform absorbs one more service
with zero new architectural vocabulary. On top of that chassis sit two
skills-specific subsystems: a federated source sync engine (local-directory
and git sources, per-source atomic swap) and a deterministic keyword scorer
shared by both store backends.

The agent side stays deliberately thin: tool-gateway gains one connector
registering two read-only tools, and agent-platform gains prompt wording and
two allow-list entries. Citations ride the existing SPEC-011 `tool_result`
evidence frames; the portal is unchanged.

Implementation stages: (1) contracts, (2) skills-hub chassis + ingestion +
stores, (3) retrieval API, (4) tool-gateway connector, (5) agent prompt and
allow-list, (6) overlay + sample skills + secrets sync, (7) living docs and
delivery artifacts.

## Design Per Requirement

### R-1: Skill document contract

- affected files: `shared/shared-contracts/schemas/skill.schema.json` (new),
  `shared/shared-contracts/skill-format.md` (new convention doc),
  `products/skills-hub/src/skills_hub/schemas/skill.py` (new Pydantic models),
  `products/tool-gateway` contract tests
- the envelope mirrors the schema fields in the spec: `skill_id`,
  `source_id`, `source_path`, `source_ref`, `title`, `description`, `tags`,
  `version`, `updated_at`; `body` travels in store records and the `get`
  response but is excerpted in search hits
- slug derivation: relative file path minus `.md` extension, path segments
  joined by `/`, each segment sanitized to `[a-z0-9-]` (lowercase, runs of
  other characters collapse to `-`); deterministic and path-stable
- frontmatter parsed with PyYAML `safe_load`; anything not a mapping is a
  validation failure
- contract tests follow `audit-service/tests/test_contracts.py`: Pydantic
  model instances validate against the JSON schema, and schema-required
  fields are asserted present

### R-2: skills-hub product with federated multi-source ingestion

- affected files: new `products/skills-hub` product (Dockerfile, Makefile,
  pyproject + uv lock, README scaffold, src tree, tests), layout mirroring
  audit-service:
  - `app.py`, `main.py`, `metadata.py`
  - `api/routes/health.py`, `api/routes/skills.py`, `api/routes/status.py`
  - `core/config.py`, `core/metrics.py`, `core/observability.py`,
    `core/request_context.py`, `core/runtime.py`, `core/telemetry.py`
  - `services/source_config.py` (SKILLS_SOURCES parsing),
    `services/ingestion.py` (walk/parse/validate),
    `services/sync.py` (per-source sync loop), `services/skill_store.py`
    (protocol + InMemory + Postgres), `services/scoring.py` (shared
    deterministic scorer), `services/query_auth.py`
- settings (frozen dataclass, env → field): `SKILLS_SOURCES` (JSON list),
  `SKILLS_GIT_TOKENS` (JSON map `source_id` → token, secrets),
  `SKILLS_SYNC_INTERVAL_SECONDS` (default 300), `SKILLS_DATA_PATH`
  (default `/var/lib/skills-hub`), `SKILLS_STORE_BACKEND` (`memory` |
  `postgres`), `SKILLS_DB_URL`, `SKILLS_QUERY_CLIENTS`,
  `SKILLS_WORKLOAD_ISSUER_URL`, `SKILLS_WORKLOAD_AUDIENCE` (default
  `skills-hub`), `SKILLS_WORKLOAD_CLIENTS`, `SKILLS_LOG_LEVEL`
- source entry shapes: `{"source_id", "type": "local", "path"}` and
  `{"source_id", "type": "git", "url", "ref", ...}`; unknown type or
  duplicate `source_id` fails startup fast with a structured error
- git transport: `subprocess` git (`clone --depth 1 --branch <ref>` then
  `fetch` + `reset --hard origin/<ref>`), run via `asyncio.to_thread`;
  tokens injected as `https://x-access-token:<token>@host/...` only inside
  the pod; GitPython rejected to keep the dependency surface at audit-service
  parity (PyYAML, httpx-free, psycopg, prometheus-client, FastAPI)
- per-source sync loop: one asyncio task per source started at startup,
  interval ± small jitter; each cycle builds a fully validated snapshot,
  then `store.replace_source(source_id, records)` swaps it atomically;
  failures keep the previous snapshot served and are recorded in the
  per-source status plus a `skills_syncs_total{source,result}` counter
- checkouts live under `<SKILLS_DATA_PATH>/sources/<source_id>/`; the
  directory is disposable — a failed or missing checkout triggers a fresh
  clone on the next cycle
- validation failures collect per document `(source_id, path, reason)`;
  a source with zero valid documents still swaps (to an empty slice) and
  reports its rejections — partial acceptance within a source is allowed,
  mirroring "reject the document, keep the source healthy"
- the validation logic is importable standalone as
  `python -m skills_hub.validate <dir>` (same code path the service uses),
  so team repos can lint locally before pushing — the reference sample
  repos document this command as the contribution pre-flight
- `GET /api/v1/skills/status` is auth-exempt (operational surface like
  `/health`), reports per source: last sync time, ref/commit when
  applicable, accepted count, rejection list (bounded), and store backend

### R-3: Search and retrieval API

- affected files: `api/routes/skills.py`, `services/skill_store.py`,
  `services/scoring.py`, `services/query_auth.py`
- auth dependency mirrors `audit-service/services/ingest_auth.py` but is
  query-only: Basic registry from `SKILLS_QUERY_CLIENTS` first, projected
  workload tokens (`SKILLS_WORKLOAD_*`) when configured; 401 with a
  structured error otherwise
- endpoints:
  - `GET /api/v1/skills` — offset pagination (`offset`, `limit` capped at
    100), optional `source` and `tag` filters; returns envelope minus body
  - `GET /api/v1/skills/{skill_id:path}` — full record including body;
    the `:path` converter handles `<source_id>/<slug>` ids; 404 structured
  - `GET /api/v1/skills/search` — `q` required, optional `source`, `tag`,
    `limit` (capped at 20); hits carry excerpt (≤ 400 chars, first matched
    region) and full provenance
- ranking: a single pure function `score(query, record) -> float` in
  `scoring.py` used by both backends — tokenize lowercase query, score
  title matches ×3, tag matches ×2, body occurrences ×1 (saturating),
  zero-score records excluded, ties break by `skill_id` ascending; the
  Postgres store selects candidates with `to_tsvector('simple', ...)
  @@ plainto_tsquery('simple', :q)` and re-ranks candidates in Python, so
  both backends produce byte-identical ordering
- all SQL parameterized; `limit`/`offset` range errors return 400

### R-4: skills.search read-only tool in the tool execution framework

- affected files: `products/tool-gateway/src/tool_gateway/tools/
  skills_connector.py` (new), `core/config.py` (settings), `app.py`
  (registration)
- settings additions: `skills_service_url` (`GATEWAY_SKILLS_SERVICE_URL`,
  default empty → connector disabled), `skills_client_id`
  (`GATEWAY_SKILLS_CLIENT_ID`, default `tool-gateway`),
  `skills_client_secret` (`GATEWAY_SKILLS_CLIENT_SECRET`)
- `SkillsConnector` follows the `ElasticConnector` shape: constructor takes
  URL + credentials, `register_tools(registry)` registers `skills.search`
  (params: `query` required, `source`/`tag`/`limit` optional) and
  `skills.get` (params: `skill_id` required), both `risk_level="read"`,
  `category="skills"`
- transport: `httpx.AsyncClient` with a 10s timeout, Basic auth from the
  gateway-held credential; upstream 404 → structured `SKILL_NOT_FOUND`
  error result, other 4xx pass through with code/message, connection
  failure → `TOOL_EXECUTION_ERROR`; every outcome builds the standard
  evidence envelope via `build_evidence("read", "skills", duration_ms)`
- `skills.search` result `data`: `{"matches": [{skill_id, title, excerpt,
  source_id, source_path, source_ref, updated_at}], "total": n}` — this
  same object becomes the `data_summary` in the SPEC-011 `tool_result`
  frame, which is what the portal evidence panel renders
- redaction, `tool_invoked` audit emission, and policy (`tools:invoke`)
  are inherited from the existing invoke choke point — no new wiring
- registration in `_build_tool_registry()` gated on
  `settings.skills_service_url` being non-empty

### R-5: Runbook-aware answers with visible citations

- affected files: `products/agent-platform/src/agent_service/
  runtime_settings.py` (prompt), `tools/gateway_tools.py` (allow-list),
  tests in both
- `DEFAULT_SYSTEM_PROMPT` gains a skills discipline paragraph: for
  procedure/interpretation/remediation questions, consult `skills.search`;
  cite used skills by title (their `skill_id` is acceptable too); never
  present skill guidance as live cluster data, and never present tool
  evidence as procedure; when no skills match, say no team guidance
  matched instead of inventing steps
- `DEFAULT_AUTO_ALLOWED_TOOLS` gains `skills.search` and `skills.get`
  (the dev overlay does not set `AGENT_GATEWAY_TOOL_AUTO_ALLOW`, so the
  code default governs)
- empty-match contract: `skills.search` with no hits returns
  `status="success"` with `matches: []` — verified by a tool-gateway test
  against a fake skills-hub double and an agent-platform contract test
- portal: no changes planned — the evidence panel renders `data_summary`
  generically; verified visually during delivery, and any mismatch is
  treated as a portal bug to fix in-spec

### R-6: Deployment, configuration, and living-state docs

- affected files: `shared/platform-ops/gitops/dev-k8s/base/skills-hub/`
  (new: deployment, service, runtime-config.env, runtime-secrets.env,
  runtime-secrets.example.env), `base/infra/postgres-statefulset.yaml`
  (initdb script mount), `shared/platform-ops/gitops/sync-skills-secrets.sh`
  (new), `dev-k8s/deploy.sh` + `deploy-overlay.sh` (skills-hub image +
  secrets-sync call), `shared/platform-ops/skills/` (new sample sources),
  tool-gateway and agent-platform `runtime-config.env` fragments
- sample skills: two local sources adapted from community-trusted open
  source content, checked into the workspace under
  `shared/platform-ops/skills/`:
  - `sre-alerting/` — adapted prometheus-operator runbooks
    (Apache-2.0): `KubePodNotReady`, `KubeNodeNotReady`,
    `KubeContainerWaiting`, and 2–3 more; every skill tagged with its
    alert name to drive the alert→runbook demo loop; NOTICE file records
    upstream URL and license
  - `platform-runbooks/` — adapted Kubernetes troubleshooting guides
    (CC-BY-4.0): CrashLoopBackOff, ImagePullBackOff, node debugging, and
    1–2 more; deliberately overlapping the pod-troubleshooting topic with
    `sre-alerting` to demonstrate namespaced cross-source retrieval;
    NOTICE file as above
  - adaptation is a one-time manual pass (frontmatter + `source_url`
    added, content condensed to fit size caps) rather than a mechanical
    importer; a short README in each source doubles as the contribution
    template teams fork; shipped via ConfigMap volumes mounted at
    `/skills` in the pod (well under the 1 MiB cap), wired as two `local`
    entries in `SKILLS_SOURCES`
- e2e demo: `shared/platform-ops/e2e/skills-demo.sh` (curl/kubectl based,
  no new dependencies) implementing the R-6 deterministic assertions; the
  chat-leg uses the existing dev-user auth path and parses the SSE frames
  for the `skills.search` pair
- Postgres: fresh clusters gain the `skills` database through an initdb
  script (`/docker-entrypoint-initdb.d/create-skills-db.sql` mounted via
  ConfigMap); existing dev clusters are covered by `sync-skills-secrets.sh`
  running an idempotent `CREATE DATABASE skills` through `kubectl exec` on
  the postgres pod before writing secrets — same pattern as the audit
  secrets sync, with a `SKIP_SKILLS_SECRETS=true` opt-out
- secrets contract: `skills-hub-runtime-secrets` holds
  `SKILLS_QUERY_CLIENTS` (client `tool-gateway`); tool-gateway
  `runtime-secrets` gains `GATEWAY_SKILLS_CLIENT_SECRET`; one shared
  random secret generated by the sync script, mirroring the audit chain
- docs: root README (product table + topology), skills-hub README
  (placeholder → product doc), tool-gateway README (new connector),
  configuration-reference (feature matrix row, skills dependency-chain
  diagram, per-service env tables, secrets section), tool-configuration
  (tool inventory +2, activation checklist, new-connector example),
  architecture-overview (topology diagram + request-flow note), dev-k8s
  README (skills-hub section), getting-started (Skills demo tour / UAT
  checklist), skill-format.md appendix ("where to find open-source
  skills" discovery pointers — prometheus-operator runbooks, Kubernetes
  docs, curated awesome-lists — with attribution guidance)

### R-7: Tests and verification gate

- see Test Strategy below

## Sequencing And Dependencies

1. Contracts: `skill.schema.json` + `skill-format.md` — depends on nothing
2. skills-hub chassis + source config + ingestion + stores — depends on (1)
3. Retrieval API + query auth + status endpoint — depends on (2)
4. tool-gateway connector + settings — depends on (3)'s API shape only
   (testable against a fake); can run parallel with (3)
5. agent-platform prompt + allow-list — depends on (4) tool names only
6. Overlay, sample skills, secrets sync — depends on (2) image + (4)
   env contract
7. Living docs, CHANGELOG, release note, delivery gate — depends on all

## Test Strategy

- unit tests (skills-hub): frontmatter validation matrix (missing title,
  missing description, oversize body/description/tags, non-mapping
  frontmatter, duplicate slug in-source, cross-source duplicates legal),
  slug derivation vectors, atomic per-source swap (failed sync keeps old
  slice), rejection reporting, scorer determinism and tie-breaking,
  pagination bounds, auth 401/200 paths, Postgres store against a fake
  driver double (audit-service pattern)
- unit tests (tool-gateway): connector registration gating, credential
  wiring, upstream error mapping (404 → SKILL_NOT_FOUND, unreachable →
  TOOL_EXECUTION_ERROR), empty-match success result, evidence envelope
  shape
- unit tests (agent-platform): extended default prompt content, allow-list
  contains both skills tools (sanitized names)
- contract tests: skills-hub models ↔ `skill.schema.json`; tool-gateway
  connector payloads ↔ schema; bound the same way as the audit-event tests
- integration / overlay validation: `kustomize build` for dev-k8s renders
  with the new base wired in (part of `make verify`); live-cluster check
  is a delivery-time `make deploy` + two-source search smoke, not part of
  the gate

## Rollout And Migration

- deployment: `make deploy` gains skills-hub automatically (deploy script
  applies the overlay and calls `sync-skills-secrets.sh`); existing
  clusters upgrade in place — the new `skills` database is created
  idempotently, no data migration
- backward compatibility: `GATEWAY_SKILLS_SERVICE_URL` unset leaves
  tool-gateway byte-for-byte as before (connector not registered);
  skills-hub absent from the cluster changes nothing for other services;
  the prompt extension is additive
- rollback: remove skills-hub from the overlay and unset the gateway URL;
  the `skills` database can be dropped without affecting any other
  service; no schema changes to existing databases
