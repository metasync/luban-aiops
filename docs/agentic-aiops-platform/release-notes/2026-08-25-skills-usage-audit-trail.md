# v0.11.0 — Skills Usage Audit Trail and Pre-Milestone Review Remediation

Date: 2026-08-25
Release type: minor (new audit vocabulary and emission surface; additive knobs)

## Summary

v0.11.0 delivers SPEC-029 — a skills usage audit trail — and closes the
pre-milestone code & documentation review.

- **SPEC-029** makes skill usage observable: skills-hub emits
  `skill_searched` / `skill_retrieved` events per authenticated query and
  one `skills_synced` event per source per sync cycle, correlated with the
  caller's `tool_invoked` events via forwarded `x-request-id` — so one
  portal question can be traced end-to-end without forwarding user
  identity to skills-hub.
- The **review remediation** closes all findings from the holistic
  pre-milestone review: three new operator guides (portal day-2 usage,
  adding-a-tool walkthrough, user/role administration), a drift-guard
  parity suite for every intentionally duplicated module, and a
  test-coverage deep dive that raised audit-service to 95% and
  incident-service to 92%.
- Two items are deliberately deferred to the exploration backlog:
  in-portal help & onboarding (D6) and shared-package extraction of the
  parity-guarded duplicate modules (M1, revisited only if the parity
  suite's churn grows).

## Change Set

### Added — SPEC-029: Skills usage audit trail

- Three new event types in the shared audit-event contract and the
  audit-service vocabulary: `skill_searched`, `skill_retrieved`,
  `skills_synced`.
- skills-hub emits via the canonical fire-and-forget emitter — now the
  fourth member of the drift-guard parity family — behind new knobs
  `SKILLS_AUDIT_SERVICE_URL` / `SKILLS_AUDIT_CLIENT_ID` /
  `SKILLS_AUDIT_CLIENT_SECRET` (an empty URL disables emission; delivery
  failures are metric + log only and never touch the request path).
- Emission points: every authenticated `search` (`query`, `limit`,
  `result_count`, matched `skill_ids`, optional source/tag filters),
  every `get` (hit → `success` with provenance; miss → `error` with
  `reason: not_found` — the demand signal for skills that do not exist),
  and one `skills_synced` per source per cycle (accepted/rejected counts
  on success; token-scrubbed error on failure). List/status/401s remain
  unaudited by design.
- Correlation: tool-gateway passes `request_id` into the tool identity
  dict and the skills connector forwards it as `x-request-id`, joining
  skill events to the caller's `tool_invoked` events on one key.
- Deployment: skills-hub joins `AUDIT_INGEST_CLIENTS` in
  `sync-audit-secrets.sh` (registry line, secret upsert, sync, restart);
  dev-k8s wires the `SKILLS_AUDIT_*` knobs.

### Added — review remediation (docs)

- `docs/guides/portal-user-guide.md` — portal day-2 usage (D1).
- `docs/guides/adding-a-tool.md` — worked-example contributor
  walkthrough for adding a read-only tool (D2).
- `docs/guides/user-and-role-administration.md` — Keycloak + policy
  administration for users, groups, and role changes (D3).
- CONTRIBUTING testing section refreshed; stale study README fixed;
  pydantic pins aligned (D4/D5/L2).

### Added — review remediation (tests)

- `test_module_parity.py`: drift-guard parity suite binding the
  intentionally duplicated modules byte-for-byte across services —
  telemetry ×7, observability ×7, token verifier, audit emitter (now
  four services), and audit-service ingest-auth ↔ incident-service
  query-auth (M1).
- Coverage deep dive (L1): audit-service 80% → 95% (Postgres store
  adapter, ingest auth, session/request filtering) and incident-service
  87% → 92% (telemetry gating, runtime settings); incident-service
  `query_auth` stays parity-bound to the fully tested audit copy.

### Fixed

- **Audit-secret rollout race**: `sync-audit-secrets.sh` restarted all
  six deployments at once, so an emitter's boot-time emission could hit
  the still-serving old audit-service pod (registry without the new
  client) and 401 — observed live for skills-hub's startup sync, dropped
  by fire-and-forget design until the next cycle. The script now blocks
  on the audit-service rollout before restarting any emitter; a rollout
  timeout fails the script before emitters move, and re-running
  converges.
- The audit-credential wipe caused by skills secret sync was fixed in
  the v0.11.1 follow-up patch — see
  `2026-08-25-skills-secret-sync-patch.md`.

## Validation

- skills-hub 133 tests, tool-gateway 205 tests (including the parity
  guard with skills-hub in the emitter family), audit-service 90 tests —
  all green; `make verify` gate green (all products, overlay renders,
  policy validation, version lockstep at 0.11.0).
- Live-verified in dev-k8s (`0.10.0-dev-k8s-98b949e` images):
  - a portal skills search produced two `tool_invoked(skills.search)`
    events joined to two `skill_searched` events on one request-id;
  - a deliberate 404 produced `skill_retrieved` with
    `outcome=error, reason=not_found`;
  - the periodic sync cycle emitted one `skills_synced` per source with
    accepted/rejected counts.
- The restart-order fix shipped after the live 401 observation; the
  corrected script is idempotent and converges on re-run.
- L3 deep security review at the push gate returned zero findings.

## Upgrade Notes

- No breaking changes; the audit vocabulary extension is additive.
- New knobs (all optional): `SKILLS_AUDIT_SERVICE_URL`,
  `SKILLS_AUDIT_CLIENT_ID`, `SKILLS_AUDIT_CLIENT_SECRET` — an empty URL
  keeps skills-hub emission-free. `sync-audit-secrets.sh` provisions the
  credential; deployments that restart emitters alongside audit-service
  should use the new script ordering.
