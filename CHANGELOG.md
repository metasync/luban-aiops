# Changelog

All notable changes to this repository are documented in this file.

The format is intentionally lightweight during the current pre-release phase.
Entries are grouped by workspace-level implementation milestones rather than
published product versions.

## Unreleased

### Added — OpenObserve Telemetry Enablement (SPEC-005 completion)

- The opt-in OTel push pipeline is now live for all six services against the
  in-cluster OpenObserve backend: `OTEL_ENABLED=true` and the org-scoped OTLP
  HTTP endpoint move into the shared ConfigMap, and the six `telemetry.py`
  pipelines switch from OTLP gRPC to OTLP **HTTP/protobuf** (the protocol
  OpenObserve ingests; dependency swapped to
  `opentelemetry-exporter-otlp-proto-http`).
- New **OTLP log bridge**: when enabled, each service attaches an OTel
  `LoggingHandler` to the root logger, mirroring every structured JSON record
  as an OTLP log with automatic trace/span association (via the non-deprecated
  `opentelemetry-instrumentation-logging` handler). JSON stdout remains the
  audit source of truth; OTel's own loggers are detached from the root to
  prevent export-failure recursion. Gating and fail-open semantics unchanged.
- skills-hub sync-loop depth: `skills.sync` spans (source id/type, result,
  accepted count) and `skills.git.checkout` spans (source id, requested ref)
  with checkout errors recorded **after** scrubbing the git token — the
  token-injected clone URL never reaches span attributes or events.
- New `sync-otel-secrets.sh` (wired into `make deploy`): computes the Basic
  auth header from `OO_ROOT_USER_EMAIL`/`OO_ROOT_USER_PASSWORD` and upserts
  `OTEL_EXPORTER_OTLP_HEADERS` into all six runtime-secrets Secrets, then
  restarts the workloads. Unset credentials skip with a clear message — push
  then 401s and fails open. `SKIP_OTEL_SECRETS=true` escape hatch for CI.
- Docs: observability conventions now define the OpenObserve backend, OTLP
  HTTP protocol, and log-bridge semantics; configuration reference documents
  the three `OTEL_*` variables and the header contract per Secret;
  troubleshooting gains a "no data in OpenObserve" section.

### Added — Git-Federated Skill Sources, End to End (R2 gap-closure)

- The skills-hub image now ships `git`: the sync engine shells out to it for
  `type=git` sources, but the base-uv-derived image lacked the binary, so git
  federation could never have worked in-cluster. Git stays out of the shared
  base image.
- `SKILLS_SOURCES` git entries accept an optional `path` — the subdirectory
  within the checkout to ingest (real team repos keep skills next to other
  code). Path-escaping values are rejected at config parse; a missing subpath
  fails the sync with a clear error while the previous snapshot keeps serving.
- dev-k8s wires a production-parity git source (`platform-skills`, tracking
  this repository's `shared/platform-ops/skills`): non-secret `url`/`ref`/
  `path` in the ConfigMap, the PAT only in `skills-hub-runtime-secrets`.
  `sync-skills-secrets.sh` provisions `SKILLS_GIT_TOKENS` when
  `SKILLS_GIT_TOKEN` is exported (never echoed, never committed).
- Operator portal: successful `skills.*` tool calls now render the matched
  skills as **Cited guidance** chips (title + namespaced id) under the
  tool-evidence card, making the guidance behind an answer glanceable.

### Refined — Skills and Grounded Guidance (post-delivery)

- Search prefilter semantics now match the deterministic scorer: query words
  are tokenized and OR-joined into `to_tsquery`, so multi-word queries keep
  partial matches (`plainto_tsquery` previously AND-ed the words and silently
  dropped them); a tokenless query short-circuits to an empty success without
  a database round-trip.
- New read-only `skills.list` tool in tool-gateway (catalog discovery:
  summaries without bodies, source/tag filters, capped offset pagination),
  mapped to the existing `GET /api/v1/skills` endpoint; auto-allowed for the
  agent alongside `skills.search` / `skills.get`, and the system prompt now
  teaches catalog discovery via `skills.list`.
- skills-hub prunes store records whose source is no longer configured at
  startup, so removing a `SKILLS_SOURCES` entry immediately retires its
  skills from search, list, and get.
- New [Skills and Guidance Operations Guide](docs/guides/skills-guide.md):
  day-2 content operations for operators — adding, revising, and removing
  skills and sources (local ConfigMap-backed and git), pre-flight
  validation, verification, metrics, and troubleshooting.

### Added — SPEC-014: Skills and Grounded Guidance

- New `shared/shared-contracts/schemas/skill.schema.json` (R-1): canonical
  skill envelope (`skill_id`, `title`, `description`, `tags`, `version`,
  `source_id`, `source_path`, optional `source_ref` / `source_url`
  attribution, `updated_at`, `body`) plus the `skill-format.md` frontmatter
  convention (size caps, slug rule, and an open-source skill discovery
  appendix). Contract tests bind skills-hub Pydantic models to the schema.
- New `products/skills-hub` product (R-2): FastAPI service mirroring the
  audit-service chassis — frozen-dataclass `SKILLS_*` settings, structured
  logging, `/health`, `/metrics` (incl. `skills_syncs_total{source,result}`),
  federated multi-source ingestion (`local` directories and `git`
  repositories, namespaced `<source_id>/<slug>` ids), per-source atomic sync
  with jitter (a failed sync keeps the prior slice), and a `SkillStore`
  protocol with in-memory and PostgreSQL backends selected via
  `SKILLS_STORE_BACKEND`. Includes a standalone validator CLI
  (`python -m skills_hub.validate <dir>`) for team pre-flight checks.
- Retrieval API (R-3): `GET /api/v1/skills` (source/tag filters, capped
  offset pagination), `GET /api/v1/skills/{skill_id:path}` (full record,
  structured 404), `GET /api/v1/skills/search` (deterministic ranking —
  title ×3 / tags ×2 / body ×1 with `skill_id` tie-break, excerpt ≤ 400
  chars, provenance), and an auth-exempt `/api/v1/skills/status`. Query auth
  uses a dedicated Basic registry `SKILLS_QUERY_CLIENTS` plus projected
  workload tokens — deliberately distinct from the SPEC-013 shared
  ingest/query credential.
- Skills connector in tool-gateway (R-4): read-only `skills.search` /
  `skills.get` tools with Basic-auth httpx transport (10s timeout) and
  structured error mapping (404 → `SKILL_NOT_FOUND`, unreachable →
  `TOOL_EXECUTION_ERROR`); registered only when `GATEWAY_SKILLS_SERVICE_URL`
  is set (unset preserves today's tool surface byte-for-byte). Settings:
  `GATEWAY_SKILLS_SERVICE_URL`, `GATEWAY_SKILLS_CLIENT_ID`,
  `GATEWAY_SKILLS_CLIENT_SECRET`.
- Runbook-aware answers (R-5): `DEFAULT_SYSTEM_PROMPT` gains the skills
  discipline (consult skills for procedure/remediation, cite by title, keep
  guidance separate from live cluster evidence, report no-match honestly);
  `skills.search` / `skills.get` join the default auto-allow list. Portal
  evidence panels render skills frames without changes.
- Deployment and sample content (R-6): dev-k8s deploys `skills-hub` with two
  sample sources — `sre-alerting` (six adapted Prometheus Operator alert
  runbooks, Apache-2.0) and `platform-runbooks` (five adapted Kubernetes
  troubleshooting guides, CC-BY-4.0), each with NOTICE attribution and a
  team contribution README. Postgres gains a `skills` database (initdb
  ConfigMap for fresh clusters; `sync-skills-secrets.sh` idempotently creates
  it and provisions the shared query secret on existing clusters,
  `SKIP_SKILLS_SECRETS=true` opt-out). Deterministic e2e smoke test
  `shared/platform-ops/e2e/skills-demo.sh` asserts source sync, alert-name
  search ranking, and the `skills.search` tool_call/tool_result frame pair in
  a scripted chat; getting-started gains a Skills demo tour (UAT checklist +
  operator training).

### Added — SPEC-013: Durable Audit Trail

- New `shared/shared-contracts/schemas/audit-event.schema.json` (R-1):
  canonical audit-event envelope (`event_id`, `occurred_at`, `event_type`,
  `service`, `request_id`, `subject`, `username`, optional `actor`
  delegation chain, `roles`, optional `session_id`, `outcome`, typed
  `details`); covers `tool_invoked`, `policy_decision`, `token_exchange`,
  `session_created`, `chat_started`, `chat_completed`. Contract tests bind
  emitter and audit-service Pydantic models to the schema.
- Canonical policy bundle: new `audit:read` action granted to `auditor`
  and `platform-admin` only (deny-by-default for all other roles);
  synced to all consumer copies via `make sync-policy`.
- New `products/audit-service` product (R-2): FastAPI service with
  frozen-dataclass `AUDIT_*` settings, structured logging, `/health`,
  `/metrics`, and an `AuditStore` protocol with two backends —
  `InMemoryAuditStore` (dev/tests) and `PostgresAuditStore` (psycopg v3
  async pool, keyset pagination), selected via `AUDIT_STORE_BACKEND`.
- Authenticated non-blocking ingest (R-3): `POST /api/v1/audit/events`
  accepts batches (capped by `AUDIT_MAX_BATCH`), rejects malformed events
  with 400 + counter. Auth via static Basic client registry
  (`AUDIT_INGEST_CLIENTS`) or projected workload tokens
  (`AUDIT_WORKLOAD_*`), mirroring SPEC-008/009 credential vocabulary.
- Fire-and-forget audit emitters (R-3) in tool-gateway, platform-gateway,
  and identity-broker: 2s bounded timeout, failure counted in
  `audit_emits_total`, never blocks or fails the originating request;
  feature-gated by `GATEWAY_AUDIT_SERVICE_URL`,
  `PLATFORM_GATEWAY_AUDIT_SERVICE_URL`, and `IDENTITY_AUDIT_SERVICE_URL`
  (unset preserves log-only behavior exactly). Structured-log emission
  retained alongside.
- Permission-scoped query API (R-4): `GET /api/v1/audit/events` with
  filters (`username`, `session_id`, `request_id`, `event_type`,
  `service`, `since`/`until`), newest-first cursor pagination, verbatim
  envelope round-trip. platform-gateway proxies the route under
  `/api/v1/audit/*` with portal-token verification and
  `enforce_policy("audit:read")` (structured 403 on deny).
- Operator portal audit view (R-5): read-only audit trail function view
  with filter bar, newest-first table, cursor pagination, and expandable
  event envelopes; navigation entry rendered only for `auditor` /
  `platform-admin` roles.
- Operator portal shell: two-column layout replacing the stacked panels —
  left sidebar carries the logo and the function list (Chat, Settings &
  Debug, Audit trail); the main column shows one function at a time with
  state preserved across switches. Narrow screens (≤800px) collapse the
  sidebar into a hamburger-triggered off-canvas drawer (the topbar stays
  above the open drawer so the hamburger always toggles).
- Operator portal sidebar footer: a user card (initials avatar, username,
  icon-only Sign in / Sign out with tooltips; clicking the user opens a
  popup menu showing granted roles, extensible with future user-related
  info) and a platform version card — separated from the function list.
- Operator portal polish: sticky audit-table column headers inside the
  scroll area, `:focus-visible` keyboard focus rings, and
  `prefers-reduced-motion` guards on blinking/spinning animations.
- Retention and bounded growth (R-6): `AUDIT_RETENTION_DAYS` (default 30)
  window eviction + `AUDIT_MAX_EVENTS` hard cap, batched deletes,
  eviction counted in metrics, never blocks ingest; window and store size
  exposed in `/health` / `/metrics`.
- dev-k8s overlay: PostgreSQL StatefulSet + PVC + Service, audit-service
  deployment/service/runtime-config (`AUDIT_STORE_BACKEND=postgres`),
  `sync-audit-secrets.sh` for shared ingest credentials (wired into
  `make deploy` with skip switch), emitter `*_AUDIT_SERVICE_URL` env in
  the three emitting services, policy ConfigMap updated.
- Root Makefile: `audit-service` added to `PYTHON_PRODUCTS`,
  `IMAGE_PRODUCTS`, `.images.env`, and the kind-load list.
- Operator guides updated: audit-service in the architecture topology and
  service inventory, `AUDIT_*` variables in the configuration reference,
  audit-service activation checklist, and troubleshooting entries for
  missing events, ingest 401, and query denial.

### Fixed — SPEC-013: Durable Audit Trail

- `PostgresAuditStore.add` now wraps `details` in `psycopg.types.json.Jsonb`
  before insert; a raw dict is not adaptable for the `JSONB` column and
  every ingest failed with `psycopg.ProgrammingError: cannot adapt type
  'dict'`. Caught during the dev-k8s live test (unit tests exercised the
  in-memory backend); regression test added against the fake psycopg
  driver (audit-service tests 67 → 68).

### Added — SPEC-012: Operator Guide and Deployment Documentation

- New operator-facing documentation suite under `docs/guides/`:
  - `getting-started.md` (R-1): prerequisites, build→deploy→verify walkthrough,
    secrets provisioning, end-to-end verification checklist.
  - `configuration-reference.md` (R-2): feature activation matrix, cross-service
    dependency chains (token delegation, identity, tool relay), per-service
    environment variable tables, secret contracts, runtime profiles, policy
    management workflow.
  - `troubleshooting.md` (R-3): symptom-based diagnostics for nine common
    failure modes (access not granted, no tools, login fails, stream stalls,
    policy denied, Elastic not configured, ErrImagePull, policy load failure,
    token expiry).
  - `tool-configuration.md` (R-4): tool inventory (K8s + Elastic), connector
    activation checklists, RBAC configuration, redaction engine reference,
    new-connector extension guide.
  - `architecture-overview.md` (R-5): service topology, request flow, trust
    chain, token delegation, workload identity, RBAC model, with Mermaid
    diagrams.
  - `README.md`: guide index and navigation.
- Root Makefile: added `sync-policy` target (copy canonical `policy-default.yaml`
  to all consumer locations) and `validate-policy` target (validate bundle
  against `policy-rule.schema.json`); `validate-policy` wired into `make verify`.
- New `shared/shared-contracts/scripts/validate_policy.py` validation script.

### Changed — Evidence and audit groups follow their reply inline

- operator-portal: replaced the bottom evidence drawer with per-turn
  collapsible groups rendered inline directly after the agent reply they
  ground. Each question's evidence cards and audit card follow that
  answer; groups stay collapsed by default (the summary line shows the
  counts) and are created lazily on the first tool frame, so purely
  conversational turns leave no empty group.

### Changed — Evidence and audit cards are kept per turn

- operator-portal: evidence and audit cards are no longer wiped when the
  next question is sent. Each chat turn gets its own collapsible group in
  the evidence drawer ("Turn N · HH:MM · counts"), created lazily on the
  first tool frame and bounded to the last 20 turns; the drawer summary
  shows session totals. Logout resets the drawer.

### Changed — Evidence moved to a collapsed drawer; audit card; sticky scroll

- operator-portal: tool evidence no longer renders inline in the chat
  column (it crowded out the streamed answer and fought the auto-scroll).
  It now lives in a dedicated collapsed drawer above the input bar with a
  live summary line ("N calls · X ok · Y denied"), matching the existing
  Settings & Debug drawer idiom.
- Added an "Audit trail · this turn" card assembled from streamed evidence
  (tool, status, executed_at, duration, risk, source) plus request/session
  IDs — self-service inspection of the caller's own turn. The authoritative
  backend audit trail (cross-user, persistent) remains a future spec.
- Sticky smart-scroll: the chat view only follows the stream while the
  reader is near the bottom, so growing evidence no longer yanks the
  viewport away from text being read.

### Fixed — Rotated delegated tokens no longer strand sessions without tools

- agent-platform: delegated tokens rotate mid-session (portal token refresh,
  300s TTL), but tool discovery only ran at agent creation — keyed by
  session — so a rotated token never got tool definitions and every
  subsequent turn injected the no-tools notice until browser refresh.
  `_build_request_toolkit` now discovers with the current token on cache
  miss, and empty discovery results are never cached (both per-request and
  `_ensure_toolkit` paths) so a transient failure can no longer poison the
  cache. `_ensure_toolkit` additionally reuses the discovery result instead
  of discovering twice.

### Fixed — Evidence panel frames, audit log visibility, cluster-wide read access

- agent-platform: the stream event adapter (`AgentStreamEvent` /
  `_normalize_stream_event`) now passes v3 `tool_call`/`tool_result` frames
  through untouched. Previously the pre-v3 Pydantic model coerced every tool
  frame to `message_delta` and stripped all evidence fields, so the portal
  evidence panel never rendered despite kernel and portal support.
- All four Python services: `configure_logging()` now raises the root logger
  to INFO (overridable via `LOG_LEVEL`) at app startup. Uvicorn's WARNING
  default silently discarded every `log_event` record — including the
  `tool_invoked` audit trail and `http_request` middleware events.
  Convention codified in `shared-contracts/observability-conventions.md`.
- dev-k8s: tool-gateway RBAC upgraded from a namespaced Role to a
  cluster-wide read-only ClusterRole (get/list/watch on core, apps, batch,
  networking, and autoscaling resources) so the agent can health-check any
  namespace (e.g. `argocd`). No mutating verbs are granted; tool surface and
  deny-by-default policy remain the enforcement layers.

### Changed — Permission auto-approval narrowed to an explicit allow-list

- agent-platform: the `RequireUserConfirmEvent` bypass now applies only to
  read-only tools on a vetted allow-list (`DEFAULT_AUTO_ALLOWED_TOOLS`,
  overridable via `AGENT_GATEWAY_TOOL_AUTO_ALLOW`), instead of every
  read-only tool. Anything outside the allow-list keeps the interactive ASK
  default. Admission, policy enforcement, and per-invocation audit logging
  by the tool-gateway are unchanged. (L3 security review remediation,
  CWE-862.)

### Added — SPEC-011: Observability Connector and Evidence Panels

- Extended the agent stream event contract (`agent-stream-event.schema.json`,
  v3) with `tool_call` and `tool_result` event types carrying tool name,
  call ID, parameters, status, evidence metadata, and data summary.
- agent-platform: toolkit closures now post `tool_call`/`tool_result` events
  to a per-request `asyncio.Queue`; trace events are drained into the SSE
  stream alongside text deltas. `data_summary` is truncated to
  `AGENT_TOOL_DATA_SUMMARY_MAX_CHARS` (default 2000) with a structured
  marker; full payloads stay in audit logs only.
- tool-gateway: new Elastic observability connector
  (`elastic.search_logs`, `elastic.get_service_health`,
  `elastic.get_active_alerts`) following the Kubernetes connector pattern
  (lazy init, executor-based sync, feature-gated by `GATEWAY_ELASTIC_ENABLED`).
  Auth supports API key (preferred) and basic auth with TLS verification
  toggle. Added `elasticsearch>=8.0,<9.0` dependency.
- operator-portal: evidence panel renders tool call/result cards with status
  badges, collapsible parameters and data summaries, and evidence metadata.
  Panel appears on first `tool_call` event and clears on each new request.
- dev-k8s overlay: `GATEWAY_ELASTIC_ENABLED=false` with commented Elastic env
  var examples in tool-gateway `runtime-config.env`; gated off by default.

### Fixed — Token delegation secrets auto-provisioning

- New `sync-delegation-secrets.sh` script generates a shared client secret,
  creates both `platform-gateway-runtime-secrets` and
  `identity-service-runtime-secrets` K8s secrets, and restarts the affected
  deployments. Previously these optional secrets were not provisioned by
  `make deploy`, causing silent delegation failures — the agent ran without
  tools ("access not granted").
- `make deploy` now calls `sync-delegation-secrets.sh` automatically after
  the overlay apply; set `SKIP_DELEGATION_SECRETS=true` when secrets are
  injected externally (e.g. CI pipelines).
- dev-k8s README: new "Token Delegation Secrets" section with usage,
  verification commands, and skip switch.

### Changed — Observer read-only tool access + anti-fabrication guardrail

- Policy bundle now grants `read-only-observer` the `tools:list` and
  `tools:invoke` actions, aligning the implementation with the authorization
  matrix (observers may perform tier-0 reads, and every registered tool is
  read-only). Previously observers were denied tool discovery (403), which
  left the agent with an empty toolkit and caused it to emit fabricated
  "health check" reports. All four byte-identical copies updated
  (shared-contracts, tool-gateway, platform-gateway, dev-k8s overlay).
- agent-platform system prompt hardened against fabrication: the agent must
  ground every factual claim in real tool output and state explicitly when no
  tools are available or a call fails, instead of inventing metrics/statuses.

### Fixed — Agent toolkit registration (AgentScope 2.x) + deterministic no-tools guard

- agent-platform: gateway tools are now built with the AgentScope 2.x API —
  `FunctionTool` objects passed to `Toolkit(tools=[...])` instead of the
  removed `Toolkit.add()`, which raised `AttributeError` per tool and left
  every session with an empty toolkit (zero tool invocations, fabricated
  health reports). The gateway's `parameters_schema` is bound explicitly
  (closures expose only `**kwargs`) and normalized to the object-with-
  properties shape AgentScope validates.
- agent-platform: deterministic anti-hallucination guard — when a tool
  gateway is configured but zero tools are registered for the turn, the
  kernel injects an explicit "no operational tools" notice into that turn
  instead of relying solely on the standing system prompt.
- agent-platform: gateway tools now auto-approve read-only execution.
  AgentScope 2.x defaults custom function tools to an interactive
  user-confirmation prompt (`RequireUserConfirmEvent`), which a headless SSE
  stream can never answer — the agent stalled and the portal showed "No
  response received". `GatewayFunctionTool` returns ALLOW for read-only
  tools (admission and policy are enforced by the tool-gateway), mirroring
  AgentScope's MCP adapter; non-read-only tools still require confirmation.

### Fixed — Deployment env collisions and portal stream rendering

- All five dev-k8s app deployments set `enableServiceLinks: false`:
  Kubernetes' legacy service-link env vars (e.g.
  `AGENT_SERVICE_PORT=tcp://…`, injected for the same-named Service)
  collided with the services' own port settings and crash-looped
  `agent-service` on startup. Service discovery uses DNS names only.
- operator-portal chat stream rendering fixed: the UI read `payload.event`
  while the gateway/agent stream contract emits `payload.type`, so every
  `message_delta` was dropped and the response area showed
  "[stream completed with no visible text]". The portal now reads `type`
  (with `event` as a legacy alias) and treats stream EOF as completion
  when no `message_end` event arrives.

### Changed — SPEC-010 code-review follow-ups

- platform-gateway `/health/ready` now verifies the policy bundle loads
  (reports a `policy_rules` count when ok; `status: degraded` with
  `policy_error` on `PolicyLoadError` instead of silently reporting ok).
- tool-gateway protected-action vocabulary corrected to the actual routes
  (`tools:list` / `tools:invoke`); regression tests added for the readiness
  degradation path.

### Changed — Shared `base-uv` container base image and non-root enforcement

- New shared Python base image `luban-aiops/base-uv:al2023`
  (`shared/base-images/base-uv/Dockerfile`): Amazon Linux 2023 minimal with
  a pinned uv (`UV_VERSION` ARG, default 0.12.1 — never `latest`), no system
  Python (uv resolves the interpreter from each product's `.python-version`
  during `uv sync`; `UV_PYTHON`/`PYTHON_VERSION` ARG default 3.12 is the
  deterministic fallback), and a non-root `app` user (uid 1000). Built by
  the new `make base-images` target, wired as a prerequisite of `make build`
  (overridable: `make base-images BASE_UV_UV_VERSION=...`).
- All four Python product Dockerfiles (`agent-platform`, `identity-broker`,
  `platform-gateway`, `tool-gateway`) now build `FROM luban-aiops/base-uv:al2023`;
  the env contract, `WORKDIR`, and `USER` move into the base, replacing the
  divergent bookworm-slim and ad-hoc amazonlinux bootstrap.
- operator-portal switches to `nginxinc/nginx-unprivileged:1.27-alpine` and
  listens on 8080 (nginx.conf, deployment containerPort, web-ui Service
  port/targetPort, dev-k8s README port-forward).
- All five app deployments gain a non-root `securityContext`
  (`runAsNonRoot`, `runAsUser` 1000 — 101 for web-ui,
  `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`).
- Docs: `python-container-strategy.md` records the Option B migration as
  executed; backend layout convention updated.

### Changed — Explicit target platform for image builds

- New `IMAGE_PLATFORM` build parameter (default `linux/amd64`, the deployment
  target) in the root `Makefile` and `mk/image.mk`: applied to
  `make base-images` and forwarded to every product build, so base and product
  images always share one platform. Override per build, e.g.
  `make build IMAGE_PLATFORM=linux/arm64` for native local/kind builds on
  arm64 hosts.

### Changed — Build configuration extracted to `mk/defaults.mk`

- New `mk/defaults.mk` is the single source of truth for overridable build
  settings (`IMAGE_PLATFORM`, `IMAGE_TAG_PREFIX`/`IMAGE_TAG_PROFILE`,
  `REGISTRY`, `AUTO_LOAD_KIND`/`KIND_CLUSTER_NAME`, `BASE_UV_*`), included by
  the root `Makefile` and by `mk/image.mk`, so root-driven and standalone
  product builds resolve identical defaults. All values use `?=`, so
  command-line overrides still win; `mk/` fragments keep processing logic
  only. `IMAGE_TAG` and `IMAGE_CONTEXT` intentionally stay in `mk/image.mk`
  (computed fallback / per-product hook).

### Changed — SPEC-010: Platform Gateway Extraction (ADR-0005)

- Split the former combined gateway into two products with the boundaries
  ADR-0005 assigns: new `products/platform-gateway` owns the portal-facing
  edge (token verification for portal sessions, action policy, chat/session
  proxying, broker delegation client, `/api/v1` portal routes); the existing
  product renames its package `api_gateway` → `tool_gateway` and keeps only
  the tool/connector home (`ToolRegistry`, connectors, `tools:list` /
  `tools:invoke`, redaction choke point, tool audit). HTTP contract shapes,
  deny-by-default policy, and audit fields are unchanged.
- env contract (Q-1): edge settings rename `GATEWAY_*` → `PLATFORM_GATEWAY_*`;
  `GATEWAY_*` stays tool-scoped only (k8s, policy path, redaction, token
  audience, auth knobs, host/port).
- k8s (Q-2): `api-gateway` deployment/service/image rename to
  `platform-gateway`; new `tool-gateway` deployment/service/SA/RBAC with
  image `luban-aiops/tool-gateway`; policy ConfigMap `gateway-policy` →
  `platform-policy` mounted on both services from one shared bundle;
  `deploy-overlay.sh` and root `Makefile` updated (`.images.env` gains
  `PLATFORM_GATEWAY_IMAGE` + `TOOL_GATEWAY_IMAGE`). Portal `nginx.conf`
  proxies to `platform-gateway:8000`.
- identity (Q-3/Q-4): portal platform JWTs change audience `tool-gateway` →
  `platform-gateway` (broker `IDENTITY_TOKEN_AUDIENCE` default, overlay,
  schema note, edge verifier); delegated tokens keep `aud = tool-gateway`.
  The edge registers as a new `platform-gateway` broker client
  (`act.sub = platform-gateway`); the old `tool-gateway` client entry is
  removed.
- guards: both gateways gain route-inventory tests pinning their surfaces
  (edge: `/api/v1/*` portal routes only; tool: health/metrics +
  `/api/v2/tools*` only). Metric names unchanged (`gateway_*` /
  `delegation_*` remain the scrape contract).
- docs: platform-gateway/tool-gateway READMEs, dev-k8s README (incl. the
  one-time `kubectl delete deployment/api-gateway service/api-gateway`
  cleanup), workspace model, product boundaries, layout convention, and
  governance label scheme updated; spec status `delivered`.

### Added — SPEC-009: Pre-Production Hardening (Tool Output Redaction and Workload-Identity Service Tokens)

- Closes the two deadline-bound Release 1 deferrals before the first non-dev
  deployment: SPEC-007 Q-3 (tool-output redaction) and the SPEC-008 R-3
  workload-identity upgrade path.
- tool-gateway: code-owned redaction engine applied at the single
  `invoke_tool` choke point before both the response and the audit log —
  value patterns (JWTs, `Bearer`/`Basic` values, PEM private keys, AWS-style
  key IDs) plus a bounded explicit key list; clean output passes through
  byte-identical. Fail-closed: results whose redacted fraction exceeds
  `GATEWAY_REDACTION_OVERFLOW_FRACTION` (default 0.2) are withheld with a
  `REDACTION_OVERFLOW` error. New `gateway_tool_redacted_spans_total{tool}`
  metric and `redacted_spans` audit field; `GATEWAY_REDACTION_ENABLED`
  (default `true`) is the dev-debugging opt-out.
- identity-broker: the exchange endpoint now also accepts Kubernetes
  projected service-account tokens as the service credential
  (`Authorization: Bearer`), validated against the cluster OIDC issuer JWKS
  (`IDENTITY_WORKLOAD_ISSUER_URL`, empty = feature off) with an audience
  check (`IDENTITY_WORKLOAD_AUDIENCE`) and a workload-subject registry
  (`IDENTITY_WORKLOAD_CLIENTS`); delegated-token claims are identical to the
  static path. Invalid/expired/wrong-audience/unregistered tokens yield 401.
- tool-gateway delegation: `GATEWAY_WORKLOAD_TOKEN_PATH` prefers the
  projected token file (re-read per exchange; kubelet rotates it in place)
  over the static secret; a missing file falls back to the static secret
  with a once-per-process warning. Unsetting the path is the rollback
  switch; the dev path is unchanged.
- docs: dev-k8s README documents the redaction opt-out and the workload-token
  contract (projected volume snippet, issuer/audience env names); the
  gateway `runtime-secrets.example.env` marks the static secret as the dev
  fallback.

### Added — Release 1 (SPEC-008: Service-to-Service Identity)

- Implemented ADR-0004 broker-mediated token delegation, closing SPEC-007 R-4/R-6
  and open questions Q-1/Q-2 and completing Release 1.
- identity-broker: platform JWTs are now audience-bound (`aud`, default
  `["tool-gateway"]`); added `POST /api/v1/auth/exchange` which authenticates a
  registered service credential, verifies the subject token, and mints a
  short-lived delegated token (`sub`/`username`/`roles` copied never elevated,
  `act` naming the caller, `aud` = requested audience, TTL
  `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS` default 300s). New service-client
  registry `IDENTITY_SERVICE_CLIENTS` and `token_exchange_total` metric.
- tool-gateway: verifies token `aud` (`GATEWAY_TOKEN_AUDIENCE`); exchanges the
  verified user token for a delegated token via a per-user TTL cache
  (`delegation_exchange_total`, `delegation_cache_total` metrics) and forwards
  it downstream as `Authorization: Bearer`; exchange failure is non-fatal
  (chat proceeds tool-less). Tool routes derive identity solely from the
  verified token (`identity_context` removed from the invoke contract);
  `GET /api/v2/tools` is authenticated and gated by a new `tools:list` policy
  action; audit logs record both `sub` and `act`.
- agent-platform: relays the delegated token as a bearer token on tool
  discovery and invocation, bound per-user into the toolkit closures (no
  cross-user sharing); removed `identity_context` from the invoke payload;
  no-token path degrades to an empty Toolkit / structured error.
- contracts: `identity-token.schema.json` documents `aud` (required) and `act`
  (optional) with a delegated-token note; `policy-default.yaml` adds
  `tools:list`. Contract tests bind both gateway and identity-broker models to
  the updated schema.
- dev-k8s overlay: sets `GATEWAY_TOKEN_AUDIENCE`, `GATEWAY_SERVICE_CLIENT_ID`,
  `IDENTITY_TOKEN_AUDIENCE`, `IDENTITY_DELEGATED_TOKEN_TTL_SECONDS`; the gateway
  and broker service secrets are provisioned as optional K8s Secrets
  (`api-gateway-runtime-secrets`, `identity-service-runtime-secrets`) and are
  not committed.

### Changed — Single Image Build Path

- Folded `build-images.sh` into `make build`: the root target now builds all
  four product images (delegating to each product's Makefile) with a
  coordinated `IMAGE_TAG`, writes `.images.env` for `make deploy`, and keeps
  the `AUTO_LOAD_KIND` / `KIND_CLUSTER_NAME` kind-load support.
- Removed `shared/platform-ops/gitops/dev-k8s/build-images.sh` and the separate
  `build-images` Make target; `make build` is now the single build path.
- Per-product `build` always tags the local image and adds a registry tag when
  `REGISTRY` is set; `push` re-tags then pushes, so build and push stay
  consistent.
- Updated the dev-k8s README to use `make build` / `make deploy` and corrected
  stale `dev-k8s-transitional` paths to `dev-k8s`.

### Changed — Build & Verification Tooling

- Added a forge-agnostic root `Makefile` (with per-product Makefiles and shared
  `mk/` fragments) consolidating project routines: `verify` (the
  pre-commit/pre-push gate), `test`, `sync`, `lint`, `build`, `push`,
  `overlays`, `deploy`, and `clean`.
- Removed the GitHub Actions workflows (`.github/workflows/ci.yml`,
  `overlays.yml`). The verification gate now lives in `make verify`,
  decoupling the project from GitHub-specific CI; the same checks run
  locally and under any CI provider.
- Updated the SDD enforcement guidance (`docs/specs/README.md`) to name
  `make verify` as the mechanical gate in place of the CI workflows.

### Added — Release 1 (SPEC-007: Tool Execution Framework)

- Added tool execution framework to tool-gateway: `ToolRegistry`, `BaseTool`
  abstraction, and structured `ToolResult` evidence envelope.
- Added Kubernetes read-only connector with four tools: `k8s.list_pods`,
  `k8s.get_pod`, `k8s.get_events`, `k8s.get_pod_logs` (kubernetes-client/python).
- Added `GET /api/v2/tools` (discovery) and `POST /api/v2/tools/invoke`
  (execution) endpoints with policy enforcement and audit logging.
- Added `tools:invoke` policy action granted to platform-admin, operator, and
  developer roles; read-only-observer is excluded.
- Added agent-platform Toolkit integration: when `TOOL_GATEWAY_URL` is
  configured, the AgentScope kernel discovers and registers gateway tools so
  the LLM can autonomously invoke them.
- Added shared contract schemas: `tool-invocation.schema.json` and
  `tool-result.schema.json`.
- Added RBAC (ServiceAccount + Role + RoleBinding) to dev-k8s overlay granting
  tool-gateway read-only access to pods, events, and pods/log.

### Changed — Release 1 Close

- Changed `GATEWAY_REQUIRE_AUTH` default from `false` to `true` in code and
  the dev overlay, completing the outstanding SPEC-001 release-close step.
  Unauthenticated requests to business routes now return `401` by default.
- Added `POST /api/v1/auth/refresh` to identity-broker: exchanges a Keycloak
  refresh_token for a fresh platform JWT, re-fetching userinfo so role changes
  are picked up on refresh.
- Added gateway proxy route `POST /api/v1/auth/refresh` forwarding to
  identity-broker.
- Added silent token refresh in operator-portal: schedules a background refresh
  60 seconds before JWT expiry; on failure, clears the session and prompts
  re-authentication.
- Collapsed the dual GitOps overlay (`dev-k8s-transitional` + `dev-k8s-native`)
  into a single `shared/platform-ops/gitops/dev-k8s` overlay. The
  transitional/native distinction no longer exists at the code level after
  SPEC-002 retired the transitional surface; a single overlay removes
  configuration drift and maintenance overhead.

### Added — Release 1 (SPEC-001 .. SPEC-006)

- Added `SPEC-001` release-1 platform hardening (delivered): gateway authentication
  enforcement behind `GATEWAY_REQUIRE_AUTH`, role propagation in structured logs,
  transitional session integrity (ownership scoping, 404 on unknown session IDs,
  TTL/size-bounded store, per-session agent isolation), typed contract
  enforcement bound to shared-contracts schemas, cached backend resolution with
  bounded outbound timeouts, and the GitHub Actions CI baseline.
- Added `SPEC-002` agent-service contract (delivered): platform-owned
  agent-service contract (ADR-0003) with v2 envelope (`content` replacing
  `response`, simplified stream events, header-based identity), `/api/v2/`
  adapter in agent-platform over the AgentScope kernel, tool-gateway migrated to
  a single agent-service client, retired the transitional `/api/v1/` surface,
  and bidirectional contract tests.
- Added `SPEC-003` identity-trust hardening (delivered): identity-broker now
  issues RSA-signed platform JWTs (`POST /api/v1/auth/token`) and publishes a
  JWKS endpoint (`GET /.well-known/jwks.json`, RFC 7517); the gateway verifies
  tokens locally via PyJWKClient, validates the `iss` claim, and derives
  `X-User-ID` exclusively from verified claims; removed `DEFAULT_USER_ID`
  fallback in favour of explicit `GATEWAY_DEV_USER` with synthetic identity
  logging.
- Added `SPEC-004` deny-by-default policy enforcement (delivered): defined the
  policy contract in shared-contracts (`policy-rule.schema.json`,
  `policy-decision.schema.json`, `policies/policy-default.yaml`) as a strict
  `action_authz` subset of the Tier-1 policy specification; the gateway
  evaluates every business request (`chat`, `session:create`, `session:read`)
  against a versioned role→action bundle, denying by default with a structured
  403 and audit-logging every decision.
- Added `SPEC-005` observability baseline (delivered): metrics naming
  conventions, OTel switch semantics, and `x-request-id` ↔ `trace_id` bridging
  rule in `shared/shared-contracts/observability-conventions.md`; all three
  Python services expose an always-on `/metrics` Prometheus surface plus an
  opt-in OTLP push pipeline gated by `OTEL_ENABLED`; standard HTTP RED metrics,
  domain counters (`agent_sessions_created_total`, `identity_tokens_issued_total`,
  `gateway_policy_decisions_total`, `gateway_token_verification_total`), and
  Prometheus scrape annotations on every deployment manifest.
- Added `SPEC-006` session durability (delivered): Redis-backed session store
  with strategy-pattern interface (`InMemorySessionStore` for dev/CI,
  `RedisSessionStore` for deployed environments); backend selection via
  `SESSION_STORE_BACKEND` env; graceful fallback to in-memory when Redis is
  unreachable; session store backend and readiness reported in `/health`;
  `session_store_backend`, `session_store_errors_total`, and
  `session_store_fallbacks_total` Prometheus metrics.
- Added ADR-0001 (SDD adoption), ADR-0002 (AgentScope 2.0 kernel), and
  ADR-0003 (platform-owned agent-service contract) under `docs/adr/`.
- Added spec-driven development workflow under `docs/specs/` with plan/spec/tasks
  templates and delivered specs for SPEC-001 through SPEC-006.
- Added `docs/agentic-aiops-platform/part-1b-framework-revalidation.md`.

### Added — Release 0

- Added typed provider-specific runtime options for `products/agent-platform`,
  including provider-owned defaults for `dashscope`, `deepseek`, and `openai`.
- Added provider adapters and a provider registry that resolve runtime settings
  into concrete AgentScope chat model implementations.
- Added gateway backend adapters so `products/tool-gateway` can resolve
  `transitional` versus `native` agent-service backends through a shared
  interface.
- Added deterministic local image build and deploy scripts for the GitOps-based
  Kubernetes development overlays under `shared/platform-ops/gitops/`,
  including both `dev-k8s-transitional` and `dev-k8s-native`.
- Added shared runtime profile overlays and selector helpers so provider
  selection stays explicit, reviewable, and Git-diffable in the deployment
  layer.
- Added Dockerfiles for the Release 0 development overlay services and an
  `nginx` proxy baseline for `products/operator-portal`.
- Added a minimal `OIDC` authorization-code callback path across
  `products/operator-portal`, `products/identity-broker`, and
  `products/tool-gateway`.
- Added configurable `OIDC_SCOPES` support so the shared identity flow can work
  against realms that do not expose the default `profile` and `email` scopes.
- Added focused tests for runtime settings, runtime metadata, provider registry
  behavior, and gateway backend resolution.
- Added release notes under `docs/agentic-aiops-platform/release-notes/`.
- Added a Git-tracked Keycloak browser-client reconciliation script for
  `dev-k8s-transitional` so the portal client redirect URIs, PKCE/public-client
  settings, and `preferred_username` / `email` mappers stay durable across
  overlay deploys.

### Changed

- Changed runtime metadata to expose resolved provider, model, base URL, and
  provider option details instead of only raw environment overrides.
- Changed `api-gateway` development overlay configuration to prefer `auto`
  backend resolution rather than pinning `AGENT_BACKEND_MODE` to
  `transitional`.
- Changed the platform-ops layout to use the durable
  `shared/platform-ops/gitops/` root for active operational assets while
  keeping `Release 0` wording in milestone-planning documents.
- Changed the development overlay rollout workflow to use explicit,
  overlay-specific image tags and per-overlay `.images.env` state instead of
  reusing a single static placeholder tag.
- Changed the operator portal browser baseline to default API requests to the
  current origin and route them through the local `nginx` proxy.
- Changed backend package layout across `agent-platform`, `tool-gateway`, and
  `identity-broker` to follow a clearer FastAPI-by-responsibility structure.
- Changed the gateway and portal request path so authenticated bearer identity
  now overrides manually entered user IDs for session and chat operations.
- Changed the GitOps overlay roots to set the deployment namespace explicitly so
  shared runtime-profile config maps are created in the same namespace as the
  services that consume them.
- Changed the committed `dev-k8s-transitional` OIDC baseline to match the live
  shared sandbox `Keycloak` validation path used for `Release 0` closure.

### Fixed

- Fixed a runtime settings mismatch where direct `RuntimeSettings(...)`
  construction could pair a provider with the wrong provider-options type.
- Fixed development cluster rollout ambiguity caused by stale same-tag image reuse.
- Fixed native AgentScope streaming compatibility so incremental reply updates
  preserve all accumulated content blocks instead of dropping earlier blocks.
- Fixed the native overlay image-build wrapper so it is directly executable as
  documented and writes to the correct overlay-specific image-state file.
- Fixed local runtime artifact hygiene by ignoring generated `**/.workspaces/`
  directories.
- Fixed the remaining `Release 0` auth gap by adding identity-broker token
  exchange, portal callback handling, optional identity-service secret
  injection, and structured request/session logs across the core services.
- Fixed fresh-namespace startup for `api-gateway` and `identity-service` by
  ignoring Kubernetes service-link `*_PORT=tcp://...` values when parsing their
  listen ports.
- Fixed the live `Release 0` overlay wiring so `agent-platform-runtime-profile`
  is created in the target namespace instead of `default`.
- Fixed the portal SSO identity contract in the shared sandbox realm by making
  the browser client emit durable `preferred_username` and `email` claims, so
  authenticated identity no longer falls back to the UUID subject value.
- Fixed the remaining `Release 0` documentation drift so the checklist,
  release notes, and closure status now consistently describe `Release 0` as
  completed with only post-closure follow-up items remaining.
