# Release Notes

This folder captures milestone-oriented release notes for the workspace.

During the current pre-release phase, release notes describe implementation
waves and validation outcomes rather than published product releases.

## Available Notes

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
