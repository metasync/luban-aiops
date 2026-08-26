# Release Notes

This folder captures milestone-oriented release notes for the workspace.

During the current pre-release phase, release notes describe implementation
waves and validation outcomes rather than published product releases.

## Available Notes

- `2026-08-26-server-inbox-pagination-and-seeded-reveal.md`
  - delivers SPEC-036 (v0.18.0): the approvals History tab moves to
    server-side pagination (split store queries with a windowed total,
    paginated inbox API, gateway pass-through, server-driven portal
    tab) so decisions past the old 100-row payload cap stay reachable,
    and the typewriter reveal cascades across every reply of a
    cold-seeded transcript instead of only the most recent one
- `2026-08-26-decision-sync-arrival-polish.md`
  - delivers SPEC-035 (v0.17.0): the four v0.16.0 live-test findings —
    transcript segment boundaries (agent-service block join +
    live-stream paragraph break) so resumed headings render, a
    time-based settle window with a visibility kick so slow resumed
    turns land without refresh, progressive arrival reveal with a
    stronger flash and scroll-into-view, session-tag park timing with a
    stale-response guard, plus the approvals banner line and
    History-tab pagination
- `2026-08-26-approval-owner-ux-polish.md`
  - delivers SPEC-034 (v0.16.0): five portal usability enhancements from
    the v0.15.0 live approval test — arrival highlight for post-decision
    content in the owner window, instant session-panel refresh on applied
    decisions, Pending/History tabs in the Approvals view, separated
    inbox entries with structured provenance headers, and a banner note
    on unanswered-request expiry
- `2026-08-26-confirmation-card-turn-anchoring.md`
  - delivers SPEC-033 (v0.15.0): the v0.14.1 live validation found a
    multi-park session stacking every confirmation card under the
    newest turn — parked records now persist their parking turn
    ordinal (additive column with in-place migration), the session
    detail carries it additively, and transcript seeding anchors each
    card under the exchange that parked it, with the legacy
    newest-turn anchoring kept as the fallback for pre-delivery
    records
- `2026-08-25-owner-decision-sync-reseed-patch.md`
  - closes v0.14.1: the SPEC-032 poll applied through `setSession`,
    whose stash-then-restore hands back the stale cached turns for the
    session already on screen — the owner window stayed deaf after an
    external decision; the new `reseedTurns` path replaces live turns
    and the cache entry authoritatively, with regression tests
- `2026-08-25-owner-side-live-decision-sync.md`
  - delivers SPEC-032 (v0.14.0): the owner's open chat window syncs
    externally made decisions live — a bounded, change-gated
    poll-while-pending on the session-detail surface (5s, torn down
    when no card is pending or any stream is active, settle window for
    the trailing resumed-turn content) flips the card with decider
    attribution and surfaces the resumed turn without a refresh;
    portal-only, no backend/contract/policy changes
- `2026-08-25-confirmation-race-and-restart-sweep-patch.md`
  - closes v0.13.1: SPEC-031 review remediations — the confirm route
    persists the durable outcome at claim time (racing approvers get
    `409 already_resolved` even mid-stream of the winner's resume,
    never a bare 404), and the Postgres startup sweep only expires
    pending rows older than the HITL confirmation TTL so a sibling
    replica's restart never kills a live park
- `2026-08-25-approval-inbox-persistent-confirmation.md`
  - delivers SPEC-031 (v0.13.0): durable confirmation lifecycle records
    on the shared Postgres posture (cap 50 per session, cascade delete,
    TTL-scoped startup expiry, registry rehydration), an additive owner-transcript
    `confirmations` session-detail surface so cards survive re-login and
    pod restarts, a decider-scoped approvals inbox
    (`GET /api/v1/approvals/inbox` behind the new `approvals:list`
    action — metadata-only, pending + 30-day history incl. expired),
    structured `409 already_resolved` race semantics, and the portal
    Approvals view with pending-count badge and persistent owner-side
    cards
- `2026-08-25-require-approval-policy-semantics.md`
  - delivers SPEC-030 (v0.12.0): `require_approval` as a first-class,
    enforced policy outcome with approval tiers (`tier_1` operator
    self-confirmation, `tier_2` designated approver with self-approval
    blocked), evaluated in both gateway engines and bridged onto
    `chat:confirm` with structured 403s and blocked-attempt audit;
    default `tier_2` rule on `tools:mutate`, matrix third state
    (`approval_requirements`), portal tier badges + read-only cards,
    and the Settings view restored as a read-only Session & Identity
    panel (add-on R-6)
- `2026-08-25-skills-secret-sync-patch.md`
  - closes v0.11.1: `sync-skills-secrets.sh` preserves
    `SKILLS_AUDIT_CLIENT_SECRET` across its rewrite of the shared
    skills-hub `runtime-secrets.env` (same pattern as the OTLP-header
    preservation), fixing the wipe that 401'd every skills-hub audit
    emission after a plain `make deploy`; version lockstep and
    lockfiles refreshed for the patch
- `2026-08-25-skills-usage-audit-trail.md`
  - delivers SPEC-029 (v0.11.0): skills-hub emits `skill_searched` /
    `skill_retrieved` per authenticated query and one `skills_synced`
    per source per sync cycle via the canonical fire-and-forget emitter
    (fourth parity-guard member), correlated with caller `tool_invoked`
    events through forwarded `x-request-id`; plus the pre-milestone
    review remediation (three operator guides, drift-guard parity
    suite, audit-service 95% / incident-service 92% coverage) and the
    audit-secret rollout-race fix in `sync-audit-secrets.sh`
- `2026-08-24-multimodel-runtime-and-live-discovery.md`
  - closes v0.10.0, the multi-model runtime train: SPEC-024 per-turn
    model selection with session pinning and audit attribution, SPEC-025
    evidence persistence with replayed prop-identical evidence cards,
    SPEC-026 per-provider curated model series with `<PROVIDER>_MODELS`
    override and consolidated `default` runtime profile, SPEC-027
    live `/models` discovery behind a fail-soft ladder (live → memory →
    Postgres → curated), and SPEC-028 the `luban` provider for
    team-hosted OpenAI-compatible servers (Ollama/vLLM/llama.cpp) with
    token auth, an operator hosting guide, and reference Ollama K8s
    manifests; plus four review remediations (confirm-route
    stale-pin degradation, fallback-response provider attribution,
    discovery-cache bootstrap connection leak, Ollama readiness probe
    under token auth)
- `2026-08-22-portal-framework-rebuild.md`
  - delivers SPEC-023 (v0.9.0): the operator portal rebuilt as a
    Vite + React 18 + TypeScript SPA on antd / Ant Design X — a
    platform-owned SSE contract adapter (schema v6, unit-tested), the
    SPEC-022 multi-session workspace UI (session panel, switch/resume
    with transcripts, anchored confirmation cards, parked-delete 409
    posture, incident deep links), browser voice composition with a
    recognition-language selector (`input_modality=voice` metadata only,
    HITL stays click-gated), full view-migration parity (audit,
    permissions, tools, skills, incidents) with role-scoped navigation,
    immutable-cache hashed assets with a no-store SPA shell, and the
    vanilla trio removed at delivery
- `2026-08-22-post-release-hardening.md`
  - closes v0.8.1: post-v0.8.0 code-review hardening — atomic set-once
    Redis session titles (dedicated NX title key), gateway session-list
    proxy 4xx passthrough parity, twelve new store/proxy tests,
    `is_parked`/`has_pending` dedupe, `select-runtime-profile.sh`
    guard against `mutating-dev`, and the documented
    delete-vs-in-flight-turn limitation; no API or contract changes
- `2026-08-22-multi-session-operator-workspace.md`
  - delivers SPEC-022 (v0.8.0), backend-first: session workspace
    lifecycle API (list cap-50 / title + transcript detail /
    owner-only delete with 404 anti-enumeration and 409 parked) under
    the new deny-by-default `session:list` / `session:delete` actions
    with a durable `session_deleted` audit event; voice-readiness
    `input_modality` contract (metadata only, HITL stays click-gated);
    the SPEC-021 dev opt-in promoted to the committed `mutating-dev`
    kustomize profile; plus two walkthrough fixes closed in-release
    (session-detail proxy 4xx passthrough, audit `EventType` enum
    sync)
- `2026-08-22-bounded-mutating-actions.md`
  - delivers SPEC-021 (v0.7.0): the platform's first write capability
    (`k8s.delete_pod`), triple-gated — tool-gateway risk-tier admission
    behind `GATEWAY_MUTATING_TOOLS_ENABLED`, read-only-by-construction
    agent auto-allow, and SPEC-020 HITL confirmation with `mutating`
    badges on stream schema v6 — under the deny-by-default
    `tools:mutate` action; disabled by default in dev-k8s with opt-in
    RBAC, the Approval & HITL Governance Guide, and a deterministic
    `mutating-demo.sh`
- `2026-08-21-durable-otlp-secret-provisioning.md`
  - closes 0.6.1: fixes the OTLP ingest 401 regression where sibling
    secret-sync scripts wiped `OTEL_EXPORTER_OTLP_HEADERS` from five
    service Secrets; provisioning now merges the header cluster-side
    and file rewrites preserve it, restoring authenticated telemetry
    push to OpenObserve for all seven services
- `2026-08-21-hitl-confirmation-bridging.md`
  - delivers SPEC-020: kernel ASK decisions surface as inline approval
    cards (park/resume bridging via `confirmation_request` /
    `confirmation_result` frames and `POST /api/v1/chat/confirm` under
    the new deny-by-default `chat:confirm` action), platform-owned
    permission gating (the allow-list is the only auto-approval
    surface), TTL-safe expiry, `confirmation_decided` audit events, and
    stream schema v5 full-output evidence transparency
- `2026-08-20-portal-transparency-and-navigation.md`
  - delivers SPEC-019: sectioned portal navigation (Chat / Control /
    Workspace) with auto-hiding sections and a logo-row version chip,
    live permission matrix endpoint (`GET /api/v1/policy/matrix`)
    evaluated from the enforced bundle with server-side role scoping and
    a Permissions view, read-only Tools and Skills inventory views behind
    new platform-gateway proxies, new `policy:read` / `skills:read`
    policy actions for all operational roles, and dev-k8s skills-query
    wiring for the platform-gateway client
- `2026-08-17-r3-incident-triage-and-collaboration.md`
  - delivers Release 3 with SPEC-015: new `incident-service` product
    (Alertmanager webhook + manual intake, fingerprint dedupe, dual-backend
    store), operator-initiated agent triage with validated triage reports,
    pluggable connector framework with the built-in audit sink, read-only
    `incidents.list` / `incidents.get` tools, the portal Incidents panel,
    dev-k8s wiring, and a deterministic e2e demo smoke test
- `2026-08-15-skills-and-grounded-guidance.md`
  - opens Release 2 with SPEC-014: canonical skill contract, new
    `skills-hub` product (federated multi-source ingestion, deterministic
    ranked retrieval, dedicated query-credential registry), read-only
    `skills.search` / `skills.get` / `skills.list` tools in tool-gateway,
    skills discipline in the agent prompt, two adapted open-source sample
    sources, dev-k8s wiring, and a deterministic e2e demo smoke test
- `2026-08-12-durable-audit-trail.md`
  - delivers SPEC-013: canonical audit-event contract, new `audit-service`
    product (in-memory + PostgreSQL stores, retention), authenticated
    fire-and-forget ingestion from three services, `audit:read`-gated query
    API proxied via platform-gateway, and the operator portal audit view
  - ships the operator portal shell redesign alongside: two-column
    sidebar/drawer layout, sidebar-footer user and version cards, and
    accessibility polish
- `2026-08-11-r1-close-operator-guide.md`
  - closes Release 1 with SPEC-012: operator guide suite (getting started,
    configuration reference, troubleshooting, tool configuration, architecture
    overview), policy management tooling (`sync-policy`, `validate-policy`),
    and the completion of all 12 Release 1 specs
- `2026-08-10-r1-hardening-grounded-responses-and-evidence-ux.md`
  - summarizes the Release 1 hardening wave: SPEC-011 completion (grounded
    responses with v3 evidence frames), audit log visibility, cluster-wide
    read-only access, permission allow-list and token-rotation fixes, and
    the portal's inline per-turn evidence/audit UX
- `2026-07-30-release-1-tool-execution-and-service-identity.md`
  - summarizes Release 1 (read-only operations copilot): the SPEC-007 tool
    execution framework and the SPEC-008 broker-mediated token delegation
    that completes the authenticated end-to-end tool path
- `2026-07-26-release-0-runtime-and-dev-k8s-overlays.md`
  - summarizes the current Release 0 runtime/provider refactor and the
    GitOps-oriented development Kubernetes overlay and rollout improvements
