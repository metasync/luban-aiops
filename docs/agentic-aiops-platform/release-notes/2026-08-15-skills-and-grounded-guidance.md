# Release Notes: 2026-08-15 — Skills and Grounded Guidance (SPEC-014)

## Summary

SPEC-014 opens Release 2: operator answers now blend live cluster evidence
with cited, team-owned guidance. The release delivers a canonical skill
contract, a new `skills-hub` product with federated multi-source ingestion
and deterministic ranked retrieval, read-only `skills.search`, `skills.get`,
and `skills.list` tools in the tool execution framework, a skills discipline
in the agent system prompt, two adapted open-source sample skill sources,
and a deterministic end-to-end demo smoke test.

Skills reach the agent exclusively through the existing tool execution
framework, so policy, audit, redaction, and evidence-panel behavior are
inherited with no new trust surface. skills-hub also adopts a dedicated
query-credential registry from day one, deliberately avoiding the shared
ingest/query credential limitation recorded against SPEC-013.

`make verify` is green: all product tests (agent-platform 125,
audit-service 68, identity-broker 58, platform-gateway 92, skills-hub
101, tool-gateway 138 — 582 total), all four Kustomize overlays render
cleanly, and the policy validation target confirms the five-rule
deny-by-default bundle.

## Change Set 1: Skill document contract (R-1)

### Highlights

- `shared/shared-contracts/schemas/skill.schema.json`: canonical envelope
  (`skill_id`, `title`, `description`, `tags`, `version`, `source_id`,
  `source_path`, optional `source_ref` and `source_url` attribution,
  `updated_at`, `body`)
- `shared/shared-contracts/skill-format.md`: frontmatter convention with
  size caps, the slug rule, and a "where to find open-source skills"
  discovery appendix
- Contract tests bind the skills-hub Pydantic models to the schema,
  following the audit-event contract pattern

### Why It Matters

- every producer (team repos) and consumer (skills-hub, tool-gateway,
  agent) binds to one schema, so guidance payloads cannot drift across
  the retrieval path
- the `source_url` field keeps upstream attribution machine-readable, which
  is what makes adapted open-source content license-compliant

## Change Set 2: skills-hub product (R-2)

### Highlights

- New `products/skills-hub` product: FastAPI on the shared `base-uv`
  image, mirroring the audit-service chassis — frozen-dataclass `SKILLS_*`
  settings, structured JSON logging, `/health` + `/health/ready`,
  always-on `/metrics`, wired into the root Makefile
- Federated ingestion: `SKILLS_SOURCES` admits `local` directories and
  `git` repositories under namespaced `<source_id>/<slug>` ids; per-source
  sync loops with jitter perform atomic slice swaps, a failed sync keeps
  the prior slice, and outcomes count in `skills_syncs_total{source,result}`
- `SkillStore` protocol with two backends selected by `SKILLS_STORE_BACKEND`:
  `InMemorySkillStore` for tests/dev and `PostgresSkillStore` (psycopg v3,
  `to_tsvector` candidate selection re-ranked by the shared scorer) with a
  byte-identical ordering parity test
- Standalone validator CLI (`python -m skills_hub.validate <dir>`) reuses
  the service validation path so teams pre-flight their repos without the
  service

### Why It Matters

- teams own their skill repositories and opt into the federation entry by
  entry; a bad document rejects at sync time without poisoning other sources
- deterministic ingestion and ranking make guidance behavior regression-testable

## Change Set 3: Retrieval API and query auth (R-3)

### Highlights

- `GET /api/v1/skills` (source/tag filters, capped offset pagination),
  `GET /api/v1/skills/{skill_id:path}` (full record, structured 404),
  `GET /api/v1/skills/search` (excerpt ≤ 400 chars, provenance, 400 on
  malformed params), and auth-exempt `GET /api/v1/skills/status`
- Deterministic scorer: title ×3, tags ×2, body ×1, saturating, with
  `skill_id` tie-break — identical ordering across both store backends
- Multi-word queries match OR-wise (tokenized lexemes OR-joined into
  `to_tsquery`), so partial matches survive the Postgres prefilter and
  reach the shared scorer; a tokenless query short-circuits to an empty
  success without a database round-trip
- Query auth: a dedicated static Basic registry `SKILLS_QUERY_CLIENTS`
  plus projected workload tokens (`SKILLS_WORKLOAD_*`) — separate from any
  ingest credential vocabulary from day one

### Why It Matters

- search results are reproducible, so "which runbook ranks first for alert
  X" is an assertable contract, not a vibe
- the query surface never doubles as a write surface; the SPEC-013 shared
  credential limitation was designed out rather than inherited

## Change Set 4: skills.search in the tool execution framework (R-4)

### Highlights

- `SkillsConnector` registers read-only `skills.search`, `skills.get`,
  and `skills.list` (catalog discovery, summaries without bodies, capped
  offset pagination) with parameter schemas; Basic-auth httpx transport,
  10s timeout, structured error mapping (404 → `SKILL_NOT_FOUND`,
  unreachable → `TOOL_EXECUTION_ERROR`)
- Registration in `_build_tool_registry()` is gated on
  `GATEWAY_SKILLS_SERVICE_URL`; unset preserves the prior tool surface
  byte-for-byte (gating test)
- Empty-match searches are a success contract (`{"matches": [], "total": 0}`),
  covered by a dedicated contract test

### Why It Matters

- the tools inherit policy, audit, redaction, and evidence-panel behavior
  from the SPEC-007 choke point — no new trust surface
- deployments without skills-hub are untouched; the feature switches on
  with one URL plus the shared query secret

## Change Set 5: Runbook-aware answers (R-5)

### Highlights

- `DEFAULT_SYSTEM_PROMPT` gains the skills discipline: consult
  `skills.search` for procedure/interpretation/remediation questions, read
  full skills with `skills.get`, discover the catalog with `skills.list`,
  cite relied-upon skills by title, keep guidance separate from live
  cluster evidence, and report an honest no-match instead of inventing
  steps
- `skills.search` / `skills.get` / `skills.list` join
  `DEFAULT_AUTO_ALLOWED_TOOLS` (sanitized-name test), so no overlay change
  is needed for the agent to use them

### Why It Matters

- citations make grounded answers checkable in the portal evidence panel
- the guidance-vs-data separation prevents the agent from presenting stale
  runbook steps as current cluster state

## Change Set 6: Deployment, sample sources, and e2e demo (R-6)

### Highlights

- Two sample sources committed under `shared/platform-ops/skills/` and
  shipped to the pod as ConfigMap volumes: `sre-alerting` (six adapted
  Prometheus Operator alert runbooks, Apache-2.0) and `platform-runbooks`
  (five adapted Kubernetes troubleshooting guides, CC-BY-4.0), each with a
  NOTICE attribution file and a README serving as the team contribution
  template; deliberate pod-troubleshooting overlap exercises cross-source
  search
- dev-k8s overlay: skills-hub deployment/service, postgres `skills`
  database (initdb ConfigMap for fresh clusters), tool-gateway
  `GATEWAY_SKILLS_*` fragments, and `sync-skills-secrets.sh` (idempotent
  `CREATE DATABASE skills` + one shared query secret across both K8s
  secrets), wired into `make deploy` with a `SKIP_SKILLS_SECRETS` opt-out
- `shared/platform-ops/e2e/skills-demo.sh`: deterministic smoke test —
  both sources synced with no errors, `KubePodNotReady` ranks the matching
  runbook first, and (optionally) a scripted chat shows the
  `skills.search` tool_call/tool_result SSE frame pair
- Getting-started gains the Skills demo tour: alert→runbook loop,
  cross-source citation, and the honest no-match path, as UAT checklist
  and operator training

### Why It Matters

- `make deploy` brings up the full guidance slice with no manual steps
- the demo script gives teams a repeatable acceptance path before pointing
  the federation at their own repositories

## Known Limitations

- sample skill content is adapted by hand from upstream sources; there is
  no automated upstream tracking — teams treat the sample sources as
  forkable starting points
- the git source path is unit-tested with a `file://` fixture; live
  remote-repo soak (token rotation, large checkouts) is part of
  operational validation rather than `make verify`
- search ranking is keyword-based by design (deterministic and testable);
  semantic ranking is a future candidate and would need a new spec
- no portal-native skill browsing UI — skills are experienced through the
  agent conversation and evidence panel

## Related Documents

- `../../specs/SPEC-014-skills-and-grounded-guidance/spec.md`
- `../../specs/SPEC-014-skills-and-grounded-guidance/plan.md`
- `../../specs/README.md` (spec index, SPEC-014 delivered)
- `../../../CHANGELOG.md`
