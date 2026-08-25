# v0.12.0 — Require-Approval Policy Semantics

Date: 2026-08-25
Release type: minor (new enforced policy outcome, tighter default posture, portal restoration)

## Summary

v0.12.0 delivers SPEC-030 — `require_approval` as a first-class, enforced
policy outcome with approval tiers — and restores the portal Settings view
as a read-only Session & Identity panel (add-on R-6).

- **Approval tiers become policy data.** The shared policy schemas grow an
  additive v2 revision: rules may answer `require_approval` with an
  `approval` block — `tier_1` (session-operator self-confirmation,
  destructive-but-routine) or `tier_2` (designated approver distinct from
  the requester, critical destructive), `decided_by_roles`, and optional
  `allow_self_approval` with tier defaults. The reserved `approval_tier`
  decision field is activated.
- **Enforcement rides the existing confirm path.** Both gateway engines
  evaluate three outcomes (deny > require_approval > allow). Platform-
  gateway bridges the outcome onto `chat:confirm`: it fetches the parked
  batch's policy action (fail-closed), checks the confirmer's roles
  against `decided_by_roles`, and blocks self-approval where the tier
  forbids it — structured 403s naming the reason, the attempt audited as
  a blocked `confirmation_decided`, the parked call stays parked. Deny
  stays open to every `chat:confirm` holder.
- **Default posture tightens.** The shipped bundle puts `tools:mutate`
  under a `tier_2` rule decided by `approver` / `platform-admin`, so a
  mutating run now needs an approver distinct from the requester.
  `mutating-demo.sh` exercises the two-identity flow end-to-end
  (including the self-approval 403).
- **Transparency follows.** The live policy matrix exposes requirements
  as an additive third cell state (`approval_requirements`, with tier and
  decider roles) while boolean cells stay fail-safe; the portal
  permissions view renders it distinctly, and confirmation cards gain a
  tier badge ("operator confirmation" / "approver required") with
  read-only rendering for non-deciders.
- **Settings view restored (R-6).** The SPEC-023 placeholder is replaced
  by a read-only tabbed panel (Identity, Session, Platform) built as an
  extensible pane container; no mutable controls ship.

## Change Set

### Added — SPEC-030: require-approval semantics

- `policy-rule.schema.json` / `policy-decision.schema.json` v2 (additive;
  v1 bundles validate unchanged) and synced engine copies.
- Three-outcome evaluation in both policy engines; platform-gateway load
  validation rejects `require_approval` rules outside the bridged action
  set (`{tools:mutate}`) and `tier_2` + `allow_self_approval: true`;
  tool-gateway validates approval blocks loudly then skips the rules with
  a warning (the synced bundle stays loadable; SPEC-021 admission stays
  allow/deny).
- Agent-platform: parked batches expose their highest policy action;
  confirmer-must-own-session relaxed on `chat/confirm`; new
  `GET /api/v2/chat/pending-confirmation` endpoint for the bridge.
- Platform-gateway: tiered confirm bridge (`_enforce_approval_tier`),
  blocked-attempt audit emission, `confirmation_decided` enrichment with
  the matched rule id and tier; matrix third state
  (`approval_requirements`) with schema + response model.
- Default bundle: `require-approval-tools-mutate` (`tier_2`, decided by
  `approver` / `platform-admin`), `tier_1` authoring-pattern and
  synthetic-identity-exclusion comments; synced across packaged and
  overlay copies.
- Portal: tier badge + read-only confirmation cards, permissions-view
  third state, Settings view (Identity / Session / Platform panes),
  `client.ts` last-request-id accessor.
- Audit-event schema details description enrichment (enum unchanged).

### Changed

- Agent-platform `chat/confirm` no longer asserts session ownership —
  approval authorization lives at the platform edge (gateway bridge).
- `mutating-demo.sh` switched to a two-identity flow with a
  self-approval negative check.

## Validation

- agent-platform, platform-gateway, and tool-gateway suites green
  (engine semantics, confirm bridge, matrix, admission regression).
- Portal vitest green (decoder action parsing, card badge / read-only
  modes, Settings renders) plus `tsc --noEmit`.
- `make sync-policy` + `make validate-policy` across all bundle copies;
  `make verify` for the full gate.

## Rollback

Revert the bundle rule (redeploy the policy ConfigMap) to restore
operator-self-confirm behavior instantly; the code paths stay inert
without `require_approval` rules in the bundle.
