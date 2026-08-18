# Release Notes

This folder captures milestone-oriented release notes for the workspace.

During the current pre-release phase, release notes describe implementation
waves and validation outcomes rather than published product releases.

## Available Notes

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
