# Delivery Roadmap

## Objective

Define a delivery roadmap for the enterprise-grade agentic AIOps platform where each release:

- is self-contained
- adds one major capability on top of the previous release
- has explicit integration points
- is straightforward for operations teams to verify

This roadmap provides a release-by-release delivery view. Implementation details are tracked in feature specs under `docs/specs/`.

## Roadmap Principles

### 1. One release, one major value theme

Every release should have a clear purpose that operations teams can understand without reading the full platform design.

### 2. Releases should stack, not sprawl

Each release should extend the previous one rather than opening many parallel fronts of partially completed work.

### 3. Validation must happen inside each release

Each release must be verifiable by real user workflows, not only by engineering-level unit or integration tests.

### 4. Integration points should be visible

Each release should name the key service and API boundaries that must work together before the release is considered complete.

### 5. Trust should increase alongside capability

As the platform gains more power, it must also gain stronger identity, policy, approval, and audit behavior.

## Recommended Release Sequence

The roadmap is designed as six stacked releases:

| Release | Theme | Primary User Value | Risk Level |
|---|---|---|---|
| `R0` | Platform Foundation | Usable portal and runtime baseline | low |
| `R1` | Read-Only Operations Copilot | Grounded operational answers | low |
| `R2` | Skills and Grounded Guidance | Team-owned procedural guidance in answers | low |
| `R3` | Incident Triage and Collaboration | Faster and better triage | medium |
| `R4` | Approval-Gated Bounded Actions | Safe operational action through approval | medium-high |
| `R5` | Hardening and External Consumption | Broader adoption and stable reuse | medium |

## Release Details

## R0: Platform Foundation

### Theme

Make the platform real, runnable, and accessible.

### What It Delivers

- Kubernetes-deployed control-plane baseline
- enterprise portal login through `Keycloak`
- API gateway entry
- basic AgentScope runtime
- session handling
- event streaming to the UI

### Why It Comes First

All later releases depend on stable access, session, and serving foundations.

### Integration Points

- `web-ui` <-> `Keycloak`
- `web-ui` <-> `api-gateway`
- `api-gateway` <-> `agent-service`
- `agent-service` <-> session store
- `agent-service` <-> event streaming channel

### How Operations Teams Validate It

- log in through `SSO`
- open the portal successfully
- start a session
- receive a streamed response

### Release Completion Signal

Operations users can reliably access and use the portal in the target environment.

## R1: Read-Only Operations Copilot

### Theme

Give operators grounded answers before giving the platform write capabilities.

### What It Delivers

- service health query flow
- read-only Kubernetes access
- read-only observability access
- evidence-backed responses
- audit for read-only tool access

### Why It Comes Next

This is the first low-risk way to prove platform usefulness.

### Integration Points

- `agent-service` <-> `tool-gateway`
- `tool-gateway` <-> Kubernetes
- `tool-gateway` <-> observability source
- `agent-service` <-> UI evidence panels

### How Operations Teams Validate It

- ask about a service or deployment
- review returned status and supporting evidence
- confirm the system used the correct data sources

### Release Completion Signal

Operators say the platform is useful for real status and diagnostic questions.

## R2: Skills and Grounded Guidance

### Theme

Blend live evidence with team-owned operational knowledge.

### What It Delivers

- Git-based skill ingestion
- Markdown validation
- searchable knowledge retrieval
- runbook-aware answers
- cited skills and sources in the UI

### Why It Comes Next

After live evidence is working, team-owned guidance is the next layer of trust and utility.

### Integration Points

- skill repo <-> `skill-ingestion-service`
- `skill-ingestion-service` <-> `knowledge-service`
- `knowledge-service` <-> `agent-service`
- `agent-service` <-> UI source display

### How Operations Teams Validate It

- add or update a skill in Git
- verify the platform ingests it
- ask a relevant operational question
- confirm the platform cites and uses the expected skill

### Release Completion Signal

Operations teams trust that their own runbooks and skills are entering the answer flow correctly.

## R3: Incident Triage and Collaboration

### Theme

Help operators respond faster and with better context during incidents.

### What It Delivers

- incident or alert intake
- enrichment and correlation
- ranked next-step recommendations
- update flow to ticketing or collaboration systems
- richer incident context in the UI

### Why It Comes Next

This release turns the platform from a query assistant into an incident-support tool.

### Integration Points

- incident source <-> `agent-service`
- `agent-service` <-> `knowledge-service`
- `agent-service` <-> `tool-gateway`
- `agent-service` <-> collaboration or ticket connector
- `web-ui` <-> incident context view

### How Operations Teams Validate It

- feed a real or simulated alert into the platform
- verify the summary, evidence, and next steps
- confirm ticket or collaboration updates are usable

### Release Completion Signal

Operations users report that the platform improves triage quality and speed on sample incidents.

## R4: Approval-Gated Bounded Actions

### Theme

Allow the platform to act safely within explicit approval and policy boundaries.

### What It Delivers

- policy engine
- approval workflow
- approval queue and action cards
- isolated execution worker
- signed execution requests
- first bounded operational actions

### Why It Comes Next

Only after identity, evidence, grounding, and triage are stable should the platform be allowed to take actions.

### Integration Points

- `agent-service` <-> `policy-service`
- `policy-service` <-> `approval-service`
- `approval-service` <-> `web-ui`
- `approval-service` <-> `execution-worker`
- `execution-worker` <-> `tool-gateway`
- `execution-worker` <-> `audit-service`

### How Operations Teams Validate It

- request a bounded action such as `restart-service`
- verify the system returns `require_approval`
- approve the action as an authorized approver
- verify the worker executes and returns results
- confirm the full audit chain is present

### Release Completion Signal

Operations and governance teams agree that bounded actions are sufficiently trustworthy for controlled use.

### Status

Closed 2026-08-27 with the v0.20.0 delivery. All six deliverables are
shipped — policy engine (SPEC-030), approval workflow (SPEC-031–036),
approval queue and action cards (SPEC-031/033/034), first bounded
operational actions (SPEC-021), signed execution requests (SPEC-037),
and the isolated execution worker (SPEC-038). The completion signal
was exercised end to end across the v0.13.1–v0.20.0 live approval-test
campaign: every run drove the full request → `require_approval` →
approver decision → isolated-worker execution → signed receipt →
audit-chain path on the `mutating-dev` profile, and the final delivery
gate verified the worker pod's handoff → invoke → audit chain directly.
R4-adjacent candidates that remain deliberately parked are recorded on
the exploration backlog with explicit promotion triggers.

## R5: Hardening and External Consumption

### Theme

Make the platform easier to operate, govern, and consume beyond the initial user group.

### What It Delivers

- better policy testing and rollout controls
- stronger reliability and observability
- stable API productization
- richer audit reporting
- better internal platform operations visibility

### Why It Comes Last

This release builds on proven operator value and focuses on broader rollout readiness.

### Integration Points

- policy repo <-> CI/CD
- `api-gateway` <-> external consumers
- `audit-service` <-> reporting interface
- all core services <-> dashboards and metrics

### How Operations Teams Validate It

- use stable platform APIs from another internal application
- inspect audit trails for real workflows
- verify policy changes move through promotion safely
- confirm platform stability under realistic usage

### Release Completion Signal

The platform is ready for wider enterprise adoption beyond the initial user group.

## Release Stacking Logic

### Why This Sequence Works

- `R0` creates access and runtime
- `R1` proves read-only value
- `R2` adds team-owned knowledge
- `R3` adds incident workflow value
- `R4` adds safe action capability
- `R5` makes the platform ready for broader production use

This avoids introducing powerful execution features before the platform has earned user trust.

## Exploration Backlog

Candidates identified during the AgentScope utilization audit (post-R3) that
are not yet decision-complete enough for a spec. Each needs a spike before
promotion; until then they stay here.

| Candidate | Question to answer in a spike | Likely home |
|---|---|---|
| MCP exposure of tool-gateway connectors | Can connectors be served as MCP endpoints without bypassing policy enforcement and audit? | own spec after R4 policy surfaces settle |
| Semantic (vector) skill retrieval | Does an Elasticsearch vector store measurably beat skills-hub's scoring search on our corpus? We already run Elastic (SPEC-011). | skills-hub enhancement spec |
| Long-term operator memory | Do agentscope long-term-memory middlewares (mem0/reme) add real triage continuity across sessions, and where would that state live? ReME was evaluated 2026-08-20 and does not fit as-is (file-based vault vs Postgres durability, unaudited LLM write-back, no per-user isolation); a spike needs a governed storage backend, per-tenant scoping, and audit hooks first (see `docs/workspace/agentscope-utilization-audit.md`). | follow-up to SPEC-017 durability |
| Kernel-side SQL storage | When would adopting `AsyncSQLAlchemyStorage` for the kernel app beat platform-owned state snapshots (SPEC-017 R-3)? | revisit if the native entrypoint is ever deployed |
| HITL confirmation bridging | Delivered 2026-08-21 as `SPEC-020-hitl-confirmation-bridging` (kernel ASK → portal approve/deny, `chat:confirm` action, `confirmation_decided` audit). MUST still precede any write/mutating tool. | `docs/specs/SPEC-020-hitl-confirmation-bridging/` |
| Bounded mutating actions | Delivered 2026-08-21 (0.7.0) as `SPEC-021-bounded-mutating-actions`: first write tool `k8s.delete_pod`, triple-gated (gateway `GATEWAY_MUTATING_TOOLS_ENABLED` risk-tier admission → read-only-by-construction auto-allow invariant → SPEC-020 HITL confirmation) behind the deny-by-default `tools:mutate` action (platform-admin + operator). Disabled by default in dev-k8s; opt-in RBAC and `mutating-demo.sh` ship out-of-band. Policy-center `require_approval` semantics delivered 2026-08-25 (0.12.0) as `SPEC-030-require-approval-policy-semantics` (spike memo: `docs/workspace/policy-require-approval-spike.md`). | `docs/specs/SPEC-021-bounded-mutating-actions/` |
| ASK → DENY tightening | Resolved 2026-08-21 during SPEC-020 live-check hardening: `GatewayPermissionMiddleware` now answers every non-allow-listed tool with an explicit ASK (parked as a confirmation card) instead of delegating to the built-in engine, whose read-only fast path silently auto-allowed read-only tools; "silently never runs" no longer describes any path. | superseded by SPEC-020 hardening |
| Multi-session operator workspace | Delivered 2026-08-22 (0.8.0) as `SPEC-022-multi-session-operator-workspace`, backend-first: session lifecycle API (list/transcript/delete, `pending_confirmation` flags, `session:list`/`session:delete` actions), voice-readiness contract (`input_modality` + HITL-stays-click-gated invariants), and the SPEC-021 dev opt-in promoted to a committed `mutating-dev` kustomize profile. The portal session-panel UI is deferred to the portal rebuild spec (Appendix A handoff). | `docs/specs/SPEC-022-multi-session-operator-workspace/` |
| Portal framework rebuild | Delivered 2026-08-22 (0.9.0) as `SPEC-023-portal-framework-rebuild`: operator portal rebuilt on Vite + React 18 + TypeScript with antd / Ant Design X — platform-owned SSE contract adapter (schema v6), SPEC-022 Appendix A session workspace UI (panel, switch/resume, anchored confirmations, incident deep links), browser voice composition with a language selector (`input_modality=voice` metadata only), full view-migration parity, and the vanilla trio removed at delivery. | `docs/specs/SPEC-023-portal-framework-rebuild/` |
| Runtime LLM model switching | Delivered 2026-08-24 as `SPEC-024-runtime-llm-model-switching`: credential-gated model catalog (one entry per configured provider), per-session selection with affinity and switch-on-demand agent rebuild, audited choice via `chat_started`/`chat_completed` enrichment, portal composer selection bar. | `docs/specs/SPEC-024-runtime-llm-model-switching/` |
| Evidence persistence in session transcripts | Delivered 2026-08-24 as `SPEC-025-evidence-persistence`: `tool_call`/`tool_result` frames persisted per assistant turn into a `session_evidence` store behind the existing `AGENT_STATE_STORE_BACKEND`/`AGENT_STATE_DB_URL` knobs, per-entry truncation cap and per-session byte budget with eviction markers, additive `evidence_turns` on session detail, and prop-identical replayed evidence cards in the portal. | `docs/specs/SPEC-025-evidence-persistence-in-transcripts/` |
| Multi-model runtime catalog | Delivered 2026-08-24 as `SPEC-026-multi-model-runtime-catalog`: extends SPEC-024 — each configured provider exposes its curated model series (model name as entry id), `<PROVIDER>_MODELS` override, legacy provider-name ids aliased to the provider default, and gitops runtime-profiles consolidated from per-provider dirs into one generic `default` profile. | `docs/specs/SPEC-026-multi-model-runtime-catalog/` |
| Live model discovery | Delivered 2026-08-24 as `SPEC-027-live-model-discovery`: extends SPEC-026 — agent-service queries each configured provider's OpenAI-compatible `/models` endpoint and serves the live list with snapshot/modality filtering, a fail-soft fallback ladder (live fetch -> in-memory last-good -> Postgres-persisted last-good -> curated series), periodic refresh with atomic catalog swap, and Redis kept exclusively as the AgentScope kernel message bus. | `docs/specs/SPEC-027-live-model-discovery/` |
| Luban-hosted small model provider | Delivered 2026-08-24 as `SPEC-028-luban-llm-provider`: `luban` adapter for team-hosted OpenAI-compatible servers (Ollama/vLLM/llama.cpp) with token-based auth and a mandatory base URL, an operator hosting guide (`docs/guides/luban-llm-guide.md`), and free-standing reference Ollama K8s manifests (`shared/platform-ops/gitops/llm-hosting/`) — the foundation for the big-small LLM collaboration pattern (small edge model for pre-triage/redaction, cloud flagship for tool-heavy agent turns). | `docs/specs/SPEC-028-luban-llm-provider/` |
| Skills usage audit trail | Delivered 2026-08-25 (0.11.0) as `SPEC-029-skills-usage-audit-trail`: skills-hub emits `skill_searched`/`skill_retrieved` per authenticated query and one `skills_synced` per source per sync cycle via the canonical fire-and-forget emitter (fourth parity-guard member), correlated with caller `tool_invoked` events through forwarded `x-request-id` (no user identity forwarded); shipped alongside the pre-milestone review remediation (operator guides, drift-guard parity suite, audit-service 95% / incident-service 92% coverage). | `docs/specs/SPEC-029-skills-usage-audit-trail/` |
| Require-approval policy semantics | Delivered 2026-08-25 (0.12.0) as `SPEC-030-require-approval-policy-semantics`: `require_approval` becomes a first-class, enforced policy outcome with approval tiers — `tier_1` session-operator self-confirmation and `tier_2` designated-approver with self-approval blocked — evaluated in both gateway engines (deny > require_approval > allow) and bridged onto `chat:confirm` with structured 403s, blocked-attempt audit, and fail-closed parked-info fetch. The default bundle ships a `tier_2` rule on `tools:mutate` (decided by `approver` / `platform-admin`), the live matrix gains an additive `approval_requirements` third cell state, confirmation cards gain tier badges with read-only rendering for non-deciders, and the portal Settings view is restored as an extensible read-only Session & Identity panel (add-on R-6). | `docs/specs/SPEC-030-require-approval-policy-semantics/` |
| In-portal help & onboarding | Spiked 2026-08-25 from the 2026-08-25 code/doc review (finding D6): tiered scope and a measurement plan are recorded in `docs/workspace/portal-help-onboarding-spike.md` — guide links (option A) are the cheap floor and prerequisite, the antd first-run tour (option B) follows on real onboarding friction, contextual hints and an in-app guide renderer stay deferred/rejected. The Settings view restoration (read-only Session & identity panel) was moved forward into SPEC-030 as add-on R-6 (memo addendum). Promote on the first onboarding friction signal, not before. | portal enhancement spec |
| Shared-package extraction of duplicated service modules | Spiked 2026-08-25 from the 2026-08-25 code/doc review (finding M1): copy-with-parity retained — the memo (`docs/workspace/shared-sdk-extraction-spike.md`) measures the five parity families (~400 unique lines) against packaging, seven-lockfile ripple, and image-build coupling, rejects a `make sync` generator, and records three revisit triggers (sixth family / five copies of one family, 3+ behavioral changes to one family per quarter, shared-sdk needed for another reason). | own spec; revisit on the recorded triggers |
| Cross-owner session review | Raised in the v0.16.0 live approval test (SPEC-035 open question) and re-stated by SPEC-036: incident review and 7x24 roster handover need a read-only view of another operator's sessions. Agreed direction: role-gated, read-only, audit-logged; session inheritance is discouraged (never-expiring sessions, ambiguous HITL ownership). Spiked 2026-08-27 in the paired memo (`docs/workspace/session-handover-spike.md`): parked behind a recorded trigger — promote on the first concrete need to read raw sessions the shift-summary artifact cannot satisfy; the artifact's provenance index doubles as its natural entry point. | portal + session-API spec |
| Shift-summary artifacts | Delivered 2026-08-27 (0.21.0) as `SPEC-039-operations-document-repository`, the first R5 slice: spiked 2026-08-27 in the paired memo (`docs/workspace/session-handover-spike.md`) as the paired candidate with cross-owner session review (SPEC-035 open question), promoted on same-day operator sign-off, then retargeted by the same-day operator review to the **operations document repository** — a typed-document substrate with a role-based access matrix (draft→publish replaces per-document grants), provenance anchoring, and document audit, shipping the shift-summary digest (deterministic two-tier own/foreign coverage plus an optional digest-only prose layer) as the first type and the session-rename and session-id-copy add-ons; incident reports were
promoted as the next type on 2026-08-28 (`SPEC-043-incident-report-document-type`,
delivered 2026-08-29 as v0.25.0), and skill authoring is tracked separately below. | `docs/specs/SPEC-039-operations-document-repository/` |
| Shift-summary handover narrative and export | Delivered 2026-08-28 (0.22.0) as `SPEC-040-shift-summary-handover-narrative` (second R5 slice) from same-day operator feedback on the v0.21.0/0.21.1 document repository: the shipped digest is a pile of receipts without the story, so the spec adds a deterministic `handover` digest section (decisions, execution outcomes, open items — facts only), repositions prose as the default digest-anchored narrative, moves the portal Documents entry from Control to Workspace, and adds a client-side Markdown export for offline use; no new policy actions or audit event types. | `docs/specs/SPEC-040-shift-summary-handover-narrative/` |
| Documents readability and digest reference | Delivered 2026-08-28 (0.23.0) as `SPEC-041-documents-readability-and-digest-reference` (third R5 slice) from operator live-test feedback on v0.22.0: the digest's vocabulary (digest, frame, coverage tiers, handover) is nowhere documented for operators, the drawer renders the digest as hard-to-scan nested lists, Digest/Prose blocks grow unbounded, and the document lists give no glimpse of each document's substance. The slice adds an operator-facing digest reference guide, tabbed structured digest rendering (handover default, raw JSON preserved), bounded scrollable digest and prose panes, and a deterministic counts-only creation-time summary shown in the Mine/Published lists (kept counts-only so the envelope-only listing posture holds); no new policy actions or audit event types. | `docs/specs/SPEC-041-documents-readability-and-digest-reference/` |
| Incident report document type | Delivered 2026-08-29 (0.25.0) as `SPEC-043-incident-report-document-type` (fifth R5 slice) from the SPEC-039 recorded next-type commitment, promoted by the v0.24.0 post-release review: a durable `incident_report` assembled verbatim from incident-service facts (incident envelope, validated triage report, connector dispatches) plus the linked triage session's digest under the existing two-tier own/foreign posture, with the inherited digest-only prose layer and draft→publish lifecycle; gated by the combination of the existing `documents:create` and `incident:read` actions — no new policy actions, no new audit event types, read-only with respect to incident state; retention adjudicated to inherit the substrate defaults with the bump parked behind an operator-ask trigger. | `docs/specs/SPEC-043-incident-report-document-type/` |
| Skill authoring export from sessions | Delivered 2026-08-30 (0.26.0) as `SPEC-044-skill-authoring-export` (sixth R5 slice), raised in the 2026-08-27 operator review beside the document repository and spiked 2026-08-29 in `docs/workspace/skill-authoring-spike.md` (Option A promoted by operator sign-off the same day): the platform drafts a Skill Format v1 Markdown from the caller's own session digest bundle (plus the validated triage report when incident-linked), validates it on skills-hub's own ingestion code path before it reaches the operator, and hands it over as a client-side `.md` download — ephemeral by construction, the artifact of record stays in the team's Git skills repo (the platform drafts, humans merge); gated by one new `session:skill_draft` action (platform-admin/approver/operator) with one new `skill_draft_generated` audit event, and generation never 500s (facts-only skeleton degradation). | `docs/specs/SPEC-044-skill-authoring-export/` |
| Incident-anchored skill drafts and draft preview | Delivered 2026-08-30 (0.27.0) as `SPEC-045-incident-skill-draft-and-preview` (seventh R5 slice), raised in the 2026-08-30 post-v0.26.0 design exchange (memo-free, drafted directly from the discussion per the SPEC-042 precedent): the operator's mental model for skill authoring starts at the incident — re-read the triage report, then convert it — so the incident detail gained **Draft as skill** anchored to the incident envelope plus the validated triage report (never anyone's session: the two-use-case split keeps session drafting owner-only and incident drafting incident-visible, dual-gated on one new `incident:skill_draft` action plus `incident:read`, deterministic 409 without a validated triage report, one new `incident_skill_draft_generated` audit event); both entry points open a read-only preview (rendered + raw toggle, mode badge, Download .md / Discard) before the client-side download; editing in the preview and dispatch-outcome bundle input parked as promotion triggers. The exchange's Q-1…Q-7 resolved in the draft's Design Decisions; live check 5/5 on the canonical deployment. | `docs/specs/SPEC-045-incident-skill-draft-and-preview/` |
| Audit reporting and export | Delivered 2026-08-31 (0.28.0) as `SPEC-046-audit-reporting-and-export` (eighth R5 slice), drafted 2026-08-31 and promoting the R5 "richer audit reporting" deliverable (`audit-service` <-> reporting interface) memo-free per the SPEC-042/045 precedent from the 2026-08-31 roadmap review: deterministic envelope-column summary aggregates (total, by event type/outcome/service, top actors, and a decision-chain projection over the SPEC-037 `confirmation_decided` / `execution_*` events) plus a bounded server-side CSV export (`AUDIT_EXPORT_MAX_ROWS` default 10 000, streaming 200-row pages, always-present truncation headers), proxied by platform-gateway under the existing `audit:read` action — no new policy actions, no new audit event types, `auditor` stays read-only — and a portal Audit view upgrade (Events/Summary tabs, export button, full filter vocabulary pinned to the shared audit-event schema by a vitest drift guard, remediating the stale 7-of-20 event-type / 4-of-7 service selects). Reports are ephemeral facts-only surfaces, not a SPEC-039 document type (the auditor holds no document actions); JSON export, scheduled reports, and per-detail breakdowns parked as promotion triggers. Approved 2026-08-31 with no requirement changes; the browser live check on the canonical deployment found and fixed one Postgres array-adaptation defect in the summary path (`event_type IN $1` rejects a list parameter; `= ANY(...)` with a pinned-shape test) before release, then all scenarios ran green — filtered summary with the decision-chain zeros, bounded export with the truncation notice, operator/observer denial (nav gate + audited policy 403 on both routes), and the stale-vocabulary regression (all 20 event types / 7 emitter services filterable). | `docs/specs/SPEC-046-audit-reporting-and-export/` |
| Audit summary drill-down and readability | Delivered 2026-08-31 (0.29.0) as `SPEC-047-audit-summary-drilldown` (ninth R5 slice), drafted memo-free from the operator UX review of the v0.28.0 Summary tab live check and approved the same day with no requirement changes: one additive `outcome` filter dimension on the existing audit events/summary/export routes (four contract enum values, 422 otherwise, applied in the shared WHERE-builder so both store backends inherit it) forwarded by platform-gateway under the unchanged `audit:read` gate, `OUTCOMES` joining the portal's pinned vocabulary behind the existing drift guard plus the toolbar select, and the Summary tab rebuilt into a single page — headline statistic row (total + decision chain, zeros as 0), drill-down from every aggregate value into the Events tab under merged filters (merge never reset, time range survives, zero-count buckets still navigate), a one-decimal percentage + neutral bar share column per bucket row via one shared formatter (the bar was retired in the 0.29.1 patch hardening after live-review feedback — the share cell is now a single right-aligned percentage), and default-expanded collapsible sections; no new routes, no new policy actions, no new event types, both contract schemas unchanged. The browser live check passed all twelve scenarios on the canonical deployment. | `docs/specs/SPEC-047-audit-summary-drilldown/` |
| Policy testing and rollout controls | Spiked 2026-09-01 from the next-step review after the v0.29.3 train (`docs/workspace/policy-rollout-controls-spike.md`), promoting the R5 "better policy testing and rollout controls" deliverable (`policy repo <-> CI/CD` integration point): the memo verifies the current bare-change workflow (one canonical bundle copied by `make sync-policy` into four locations, `validate-policy` schema + duplicate-id guard in `make verify`, path-keyed bundle caching with no hot reload, `version: 1` parsed and surfaced by `bundle_metadata` but unbumped and hashless, 17 bundle edits since inception, no bundle-lifecycle audit) and recommends Option B — a bundle content-hash provenance field on the transparency/readiness surfaces, a scenario-expectation harness pinned into `make verify` (the policy analog of the portal drift guard), a `make policy-diff` per-(role, action) impact report, and the documented rollout runbook — parking staged promotion, hot reload, policy-center, change windows, and new audit event types as the policy-center-shaped remainder; promotion to SPEC-048 (tenth R5 slice, 0.30.0 train) pending operator sign-off. | `docs/workspace/policy-rollout-controls-spike.md` |
| Approval-workflow extensions | SPEC-031 non-goals parked as future candidates: multi-approver quorum / N-of-M semantics (extending the SPEC-030 approval tiers), push notifications (webhook, email, browser push), cross-session bulk approve, and richer approver review context (owner-transcript exposure has its own decision). Promote on the first concrete governance or operational ask, not before. | approval-flow spec |
| Numbered-list continuation across separated blocks | v0.18.1 live-check observation: when the model emits numbered steps as separate blocks (blank line or paragraph between items), the escape-first renderer produces separate `<ol>` elements and each restarts at 1. Cosmetic; decide renderer merge strategy vs prompt guidance if operators complain. | operator-portal markdown renderer / prompt guidance |
| Dependency hygiene (portal and backend) | Raised in the v0.23.2 delivery train: the vitest suite prints 53 antd deprecation warnings (48× Drawer `width`, 5× Alert `message`) and the same-day upgrade check found the portal majors several majors behind upstream (vite 6 vs 8, vitest 3 vs 4, TypeScript 5.6 vs 5.9, React 18 vs 19, jsdom 25 vs 30). A matching backend check found the lockfiles close to current: agentscope 2.0.6 → 2.0.7.post1 and fastapi/uvicorn in-range floats, plus three adjudicated range decisions (cryptography caps `<45` vs upstream 50.x; redis `<7` and elasticsearch `<9` parked with reasons). Revised 2026-08-28 per operator feedback: latest-stable-only adoption policy (no beta/RC/dev; single recorded exception — the OTel instrumentation packages' permanent 0.xb upstream channel, kept at its locked pairing). Drafted as `SPEC-042-dependency-hygiene` (renamed from `SPEC-042-portal-dependency-hygiene`) directly from the checks (memo-free, SPEC-031/032 departure): deprecation migration plus a zero-tolerance vitest guard, the recorded adopt set, the React 19 migration with a behavioral gate, and the backend re-lock with a kernel-verification leg for agentscope; TypeScript 7.x parked as too new. Approved 2026-08-28; delivered 2026-08-28 (0.24.0) as the fourth R5 slice — antd deprecation migration with a zero-tolerance vitest guard, the recorded adopt set (TypeScript 5.9.3, vite 8.2.2 + plugin-react 6.1.1, vitest 4.1.11, jsdom 30.0.1, `engines.node >=22.22.2`), React 19.2.8 behind the behavioral gate, and the backend stable-channel re-lock (agentscope 2.0.7.post1, fastapi 0.141.1, uvicorn 0.52.4; cryptography caps raised to `<51.0` after the signing call-site review; redis/elasticsearch caps parked). | `docs/specs/SPEC-042-dependency-hygiene/` |
| Isolated execution worker and signed execution requests | Spiked 2026-08-26 after the v0.18.1 consolidated live check declared the approval cluster stable: the memo (`docs/workspace/execution-runtime-spike.md`) verifies the approved mutating path still executes in-process under the confirmer's delegated token, weighs sign-and-record vs isolated-worker vs full-async-queue, and recommends a phased shape. Phase 1 (HMAC-signed execution requests/receipts bound to the parked args digest) was promoted to `SPEC-037-signed-execution-requests` on 2026-08-27 after operator sign-off and delivered the same day (0.19.0). The memo's promotion gate was then satisfied — Phase 1 live-verified on the `mutating-dev` profile — and Phase 2 (the isolated `execution-runtime` worker) was promoted to `SPEC-038-isolated-execution-worker` on 2026-08-27 with the memo's Q-1 (handoff service identity) and Q-2 (resume await timeout) resolved in the draft; the spec was approved the same day with one recorded condition — an R5 re-evaluation trigger: when more team members work simultaneously, concurrent approved actions contending on the single worker pod promote the queue/pool spec at that signal. Together they close the two remaining R4 deliverables. | SPEC-037 delivered; SPEC-038 delivered (0.20.0) |
| Approval inbox and persistent confirmation cards | Delivered 2026-08-25 (0.13.0) as `SPEC-031-approval-inbox-persistent-confirmation`, drafted directly from the SPEC-030 live-cluster validation (no spike memo — the validation itself was the evidence base): durable confirmation lifecycle records on the shared Postgres posture (cap 50 per session, TTL-scoped startup expiry), an additive owner-transcript `confirmations` surface so cards survive re-login and pod restarts, a decider-scoped `GET /api/v1/approvals/inbox` behind a new `approvals:list` policy action (metadata-only, pending + 30-day history incl. expired), structured `409 already_resolved` race responses, and a portal Approvals view with pending-count badge plus persistent owner-side cards. | `docs/specs/SPEC-031-approval-inbox-persistent-confirmation/` |
| Owner-side live decision sync | Delivered 2026-08-25 (0.14.0) as `SPEC-032-owner-side-live-decision-sync`, drafted directly from the v0.13.1 live validation finding that the owner's open chat window never learned about a decision made from the approver inbox: a bounded, change-gated poll-while-pending on the existing session-detail surface (5s, torn down when no card is pending or any stream is active, settle window for the trailing resumed-turn content) re-seeds the turn timeline so the decided card with attribution and the resumed turn appear without a refresh. Portal-only — no backend, contract, or policy changes. | `docs/specs/SPEC-032-owner-side-live-decision-sync/` |
| Confirmation card turn anchoring | Delivered 2026-08-26 (0.15.0) as `SPEC-033-confirmation-card-turn-anchoring` from the v0.14.1 live validation finding that a multi-park session stacks every confirmation card under the newest turn: parked records persist their parking turn ordinal (the same `_count_user_turns` convention SPEC-025 evidence uses, additive column with in-place migration), the session-detail surface carries it additively, and transcript seeding anchors each card under the exchange that parked it. Legacy rows fall back to today's anchoring. | `docs/specs/SPEC-033-confirmation-card-turn-anchoring/` |
| Approval & owner chat UX polish | Delivered 2026-08-26 (0.16.0) as `SPEC-034-approval-owner-ux-polish` from the v0.15.0 live approval-test feedback: portal-only — owner-window arrival highlight for post-decision content, instant session-list refresh on applied decisions, Pending/History tabs in the Approvals view, separated inbox entries with structured provenance headers, and a banner note on pending-request expiry. | `docs/specs/SPEC-034-approval-owner-ux-polish/` |
| Decision sync robustness and arrival polish | Delivered 2026-08-26 (0.17.0) as `SPEC-035-decision-sync-arrival-polish` from the v0.16.0 live approval-test feedback: transcript segment boundaries (agent-service block join + live-stream paragraph break), a time-based settle window with a visibility kick, progressive arrival reveal, session-tag park timing with a stale-response guard, approvals banner line, and History-tab pagination. | `docs/specs/SPEC-035-decision-sync-arrival-polish/` |
| Server inbox pagination and seeded transcript reveal | Delivered 2026-08-26 (0.18.0) as `SPEC-036-inbox-pagination-and-seeded-reveal` from the v0.17.0 post-release review: the approvals History tab moved to server-side pagination (split store queries with a windowed total, paginated inbox API, gateway pass-through, server-driven portal tab) because the combined payload's 100-row cap silently dropped older decisions as volume grew. R-1 (the cold-seeded transcript typewriter cascade) shipped with 0.18.0 but was reverted in the 0.18.1 patch after the live check — the typewriter now applies to live arrivals only — alongside two more live-check fixes: a markdown list-rendering fix (nested/indented bullets and ordered-list wrapping) and pod-log excerpts in agent replies moving to fenced code blocks rendered in a fixed-height scrollable box. | `docs/specs/SPEC-036-inbox-pagination-and-seeded-reveal/` |
| Signed execution requests and receipts | Delivered 2026-08-27 (0.19.0) as `SPEC-037-signed-execution-requests`, Phase 1 of the execution-runtime spike (`docs/workspace/execution-runtime-spike.md`): approved mutating calls gain a tamper-evident execution chain — HMAC-signed execution requests bound to the parked arguments' digest at approval resume (missing signing key fails closed with an audited `signing_unavailable` rejection), argument-digest verification at the invocation boundary (`args_digest_mismatch` blocks and audits), durable execution records and signed receipts beside the SPEC-031 confirmation records with an additive owner-scoped `executions` session-detail surface, `execution_requested` / `execution_completed` / `execution_rejected` audit events correlating the full decision-to-execution chain, a read-only receipt badge on decided confirmation cards, and the `execution-signing-secret` deploy wiring. Execution stays in-process; the isolated worker remains Phase 2. | `docs/specs/SPEC-037-signed-execution-requests/` |
| Isolated execution worker | Delivered 2026-08-27 (0.20.0) as `SPEC-038-isolated-execution-worker`, Phase 2 of the execution-runtime spike (`docs/workspace/execution-runtime-spike.md`) and the close of R4: approved mutating calls leave agent-service via an authenticated internal handoff to the new `execution-runtime` worker, which independently re-verifies the SPEC-037 envelope signature and parked-arguments digest, executes through the tool-gateway under the forwarded confirmer delegated token, authors the signed receipt on the shared `execution_records` table (first-write-wins), and emits the correlated `execution_completed` / `execution_rejected` events. The resumed stream blocks on the worker under a bounded timeout (default 60s); single-flight idempotency keyed by `execution_id` plus a pinned single replica make re-execution structurally impossible; every missing credential fails closed (`worker_unavailable`, no in-process fallback); isolation is infrastructure-enforced (own Deployment/ClusterIP Service, `execution-handoff-secret`, no HTTPRoute). The approval-condition R5 re-evaluation trigger (concurrent-operator queueing) stays recorded on the backlog. | `docs/specs/SPEC-038-isolated-execution-worker/` |

Promotion rule: a spike lands its findings as a short memo (workspace docs);
only then does the item get a SPEC number. SPEC-018 (kernel middleware
alignment) was delivered after SPEC-017 and re-confirmed this backlog in its
utilization memo (`docs/workspace/agentscope-utilization-audit.md`).
SPEC-020 (HITL confirmation bridging) was promoted from this backlog on
2026-08-21 after its spike memo landed. SPEC-030 (require-approval policy
semantics) was drafted on 2026-08-25 from its spike memo, promoted from the
"next R4 slice" marker on the bounded-mutating-actions row, and delivered
the same day in the 0.12.0 train. SPEC-031 (approval inbox and persistent
confirmation cards) was drafted on 2026-08-25 directly from the SPEC-030
live-cluster validation findings — a deliberate departure from the
memo-first rule, since the validation itself supplied the evidence base —
and delivered the same day in the 0.13.0 train. SPEC-032 (owner-side live
decision sync) was drafted the same day from the v0.13.1 live validation
finding (owner window deaf to external decisions) — the same memo-free
evidence-base departure — and delivered the same day in the 0.14.0 train.
SPEC-033 (confirmation card turn anchoring) was drafted on 2026-08-26 from
the v0.14.1 live validation finding (multi-park sessions stack every card
under the newest turn) — the same memo-free evidence-base departure — and
delivered the same day in the 0.15.0 train. SPEC-034 (approval & owner
chat UX polish) was drafted the same day from the v0.15.0 live
approval-test feedback (five portal usability enhancements) — the same
memo-free evidence-base departure — and delivered the same day in the
0.16.0 train. SPEC-035 (decision sync robustness and arrival polish) was
drafted the same day from the v0.16.0 live approval-test feedback (a
refresh-needed sync gap, broken resumed-heading markdown, an unnoticed
arrival highlight, session-tag timing, and two approvals-view layout
asks) — the same memo-free evidence-base departure — and delivered
the same day in the 0.17.0 train. SPEC-036 (server inbox pagination and
seeded transcript reveal) was drafted the same day from the v0.17.0
post-release review (a growing-history truncation concern and a
presentation-consistency ask) — the same memo-free evidence-base
departure — and delivered the same day in the 0.18.0 train, with R-1
refined mid-flight at operator sign-off so the cold-seed reveal
cascades every seeded reply instead of only the most recent one. The
v0.18.0 live check then produced the 0.18.1 patch the same day: R-1
was reverted at operator decision (the seeded typewriter read as delay
rather than polish — the reveal stays reserved for live arrivals), and
the chat markdown renderer gained nesting-aware list handling after
indented sub-bullets were observed rendering as literal "- text"; the
same patch moved pod-log excerpts in agent replies into fenced code
blocks (prompt guidance plus a fixed-height scrollable box in the
portal) after the live check surfaced a JSON-serialized log string.
SPEC-037 (signed execution requests and receipts) then returned the
promotion flow to the memo-first rule: spiked 2026-08-26 from the
verified current execution path after the consolidated v0.18.1 live
check declared the approval cluster stable
(`docs/workspace/execution-runtime-spike.md`), operator sign-off on
the phased shape given 2026-08-27, and the Phase-1 scope promoted to
a spec draft the same day. Its Phase 2 (the isolated
`execution-runtime` worker) will take its own spec number after Phase
1 is live-verified. Phase 1 was delivered the same day in the 0.19.0
train with no requirement changes: the live check ran the
`mutating-demo.sh` HITL leg on the `mutating-dev` profile and observed
the signed receipt on the approved card plus the correlated
`execution_requested` / `execution_completed` audit chain. That live
verification satisfied the memo's promotion gate, and the Phase-2 scope
(the isolated `execution-runtime` worker) was promoted on 2026-08-27 to
`SPEC-038-isolated-execution-worker` under the same memo-first lineage —
the memo's Q-1 (worker service identity for the internal handoff) and
Q-2 (resume-stream await timeout) resolved during drafting; Q-3 was
already resolved by SPEC-037 R-6. SPEC-038 was approved the same day
with one recorded condition — the R5 re-evaluation trigger for
concurrent-operator queueing on the single worker pod — and delivered
the same day in the 0.20.0 train, closing the last two R4
deliverables. R4 was formally closed the same day: all six R4
deliverables shipped and the Release Completion Signal exercised
across the v0.13.1–v0.20.0 live approval-test campaign. Opening R5,
the paired cross-owner session review / shift-summary candidates
(raised in the SPEC-035 open question, re-stated by SPEC-036) were
spiked together on 2026-08-27 under the memo-first rule
(`docs/workspace/session-handover-spike.md`), verified against the
0.20.0 session workspace and approval surfaces; the memo recommends
promoting the shift-summary artifact first — a deterministic digest
with an optional clearly-labeled prose layer and provenance anchoring
— and parks raw cross-owner session review behind a recorded trigger,
awaiting operator sign-off before spec promotion. Sign-off was granted
the same day, and the shift-summary artifact was promoted to SPEC-039
(draft) under the memo-first lineage with the memo's Q-1 (artifact
ownership/audience), Q-2 (audit posture), Q-3 (prose guardrails —
digest-only prompt contract, labeled rendering, fail-soft), and Q-4
(retention — immutable snapshot, cap 20, 30-day TTL aligned with the
inbox history window) resolved in the draft. The same-day operator
review then generalized the scope — operators also need incident
reports and reusable guidance, and per-document permission grants are
the wrong operating model — so SPEC-039 was retargeted to
`SPEC-039-operations-document-repository`: a typed-document substrate
with a role-based access matrix (draft→publish lifecycle replaces
per-document ACLs; creation/publishing behind `documents:create`,
role-scoped reads behind `documents:read`, cross-owner reads
audited), the shift summary as the first document type, and session
rename plus session-id copy as add-ons supporting the sharing
workflow. Incident reports become the next type candidate (their
assembly reaches incident-service data), skill authoring export is
recorded as a separate backlog candidate — explicitly not a document
type, keeping Git-managed team knowledge (SPEC-014) the artifact of
record — and cross-owner raw session review stays parked behind its
recorded trigger. SPEC-039 remains the first R5 slice.

## Validation Model Per Release

Every release should have four validation layers:

- `service validation`
- `workflow validation`
- `control validation`
- `user acceptance validation`

### Service Validation

Checks:

- service health
- API contract behavior
- event streaming
- connector integration

### Workflow Validation

Checks:

- end-to-end operator scenarios
- evidence visibility
- UI usability for the intended release goal

### Control Validation

Checks:

- `SSO`
- identity propagation
- policy decision behavior
- approval and audit integrity

### User Acceptance Validation

Checks:

- operations team can use the release without engineering guidance
- release saves time or improves confidence
- operators trust the outputs enough to adopt the workflow

## Suggested Iteration Rhythm

Use short internal iterations within each release, but treat the release itself as the validation boundary.

Recommended rhythm:

- `design and integration preparation`
- `core implementation`
- `end-to-end workflow completion`
- `operations validation`
- `hardening and release decision`

This keeps releases self-contained while still allowing normal engineering iteration inside them.

## Recommended Release Readiness Checklist

Every release should answer `yes` to these questions before moving on:

- does the release deliver one clear operator-visible capability?
- are the integration points working end to end?
- can operations teams validate the release with a small set of concrete scenarios?
- are logs, traces, and audit records sufficient to investigate problems?
- does the release keep faith with the platform design principles?

## Design Principles Carried Through Delivery

These principles should remain visible in every release:

- `bounded autonomy`
- `diagnose before act`
- `identity before privilege`
- `read before write`
- `explicit approvals for risk`
- `Git-managed team knowledge`
- `API-first and gateway-friendly integration`

## Final Recommendation

Deliver the platform as a sequence of self-contained, vertically integrated releases where each release gives operations teams something specific to try, verify, and trust.

The recommended release progression is:

- `R0` foundation
- `R1` read-only operational value
- `R2` grounded guidance
- `R3` incident triage
- `R4` approval-gated bounded action
- `R5` hardening and external consumption

This roadmap provides the clearest path to building enterprise trust while steadily increasing platform capability.
