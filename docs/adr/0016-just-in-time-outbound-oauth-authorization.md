# ADR-0016: Just-in-Time Outbound OAuth Authorization Without Credential Settings

## Status

`accepted`

- date: 2026-10-18
- accepted: 2026-10-18
- deciders: workspace operator; first-use redirect/no-settings direction and this ADR
  accepted. Acceptance ratifies the architecture; the detailed cross-product contract
  (SPEC-070 OQ-7) must be designed and ratified before runtime code, and the actual
  AAP/MCP deployment profile (OQ-3) remains a pre-live gate. Deployment, commit/push,
  version bump, and live-token tests are separate boundaries not granted here.
- related specs: [SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md),
  [plan](../specs/SPEC-070-outbound-user-delegated-identity/plan.md),
  [tasks](../specs/SPEC-070-outbound-user-delegated-identity/tasks.md)
- supersedes [ADR-0015](0015-outbound-user-delegated-identity-via-per-user-oauth.md),
  whose status is now `superseded by ADR-0016`; its accepted body is unchanged. This record
  retains ADR-0015's authorization-code/no-broker-mint core and per-user credential store,
  and replaces its provisioning-only enrollment, PAT alternative for this slice, and blanket
  no-kernel-change scope assumption.
- evidence: [compatibility report and redirect-based reassessment](../specs/SPEC-070-outbound-user-delegated-identity/compatibility-report.md#redirect-based-reassessment-2026-10-18)

## Context

ADR-0015 selected target-issued, user-bound authorization-code credentials with per-user
refresh-token custody in tool-gateway. A later strict zero-additional-browser requirement
could not be evidenced against the intended AAP target. The operator then agreed to allow
standard first-use/reauthorization redirects, while continuing to exclude credential-settings
screens, manual token copying, and enrollment commands.

AAP 2.6 and 2.7 document authorization-code authentication. This is a supported protocol
family, not proof of the organization's exact client, renewal, PKCE, or target RBAC profile.
SSO can reduce login prompts but does not guarantee silent target consent or equivalent roles.

First-use authorization is not only a connector token POST. It needs an authenticated browser
handoff, callback, cancellation/status feedback, and safe continuation across product
boundaries. The current tool-result error contract contains only `code` and `message`;
a typed first-use handoff is not an existing feature. The prior blanket no-kernel-change
assumption cannot safely be retained without that contract analysis.

## Decision

**Proposed:** acquire target-issued user credentials through just-in-time authorization-code
redirects and renew them server-to-server in tool-gateway. Persist required refresh tokens in
gateway-owned Postgres with authenticated encryption and separately mounted versioned keys;
provide workflow-local authorization feedback, not credential management UI.

1. **First use, not every login.** Only an authorized operation needing a configured target
   may initiate authorization. The provider may show login/consent; cancel/expiry is visible
   and stops repeated redirects. Missing configuration or a transient outage is not a reason
   to enroll the user into every target.
2. **Backend credential custody.** Tool-gateway owns acquisition, account validation, and
   encrypted records. Platform-gateway owns the authenticated portal edge and backend callback
   forwarding; the portal handles only safe status/navigation. No target token, client secret,
   or verifier reaches JS, model context, kernel state, or transcripts. Codes/state traverse
   only the necessary browser redirect and backend callback; they are not logged or persisted
   in conversation data. No upstream Keycloak-token retention or new outbound broker mint.
3. **Secure account binding.** Use confidential-client auth, exact HTTPS callback, short-lived
   single-use state/browser binding, and PKCE S256 in the proposed baseline. Verify the target
   immutable user against trusted linkage, not matching usernames/emails. Unsupported security
   behavior blocks the target; no implicit compatibility downgrade is permitted.
4. **Separate authorization from execution approval.** OAuth completion stores credentials
   and restores conversation context; it cannot dispatch tools. Continuing an operation must
   satisfy current platform policy and target RBAC. Existing HITL, signatures, durable claims,
   and uncertain-outcome handling remain authoritative; no automatic write replay.
5. **Cross-product contract in scope.** Agent-platform may need bounded stop/continue and
   typed signaling; shared API/stream contracts and audit query filters may need additive
   changes. Exact routes, fields, policy guards, persistence, and resume behavior must be
   specified and ratified under SPEC-070 OQ-7 before this ADR is accepted.
6. **Explicit lifecycle.** Access tokens are memory-only; durable refresh tokens are encrypted
   and bound to owner/target/config generation. Rotation/revocation coordinate across replicas.
   Provider rotation and a local database commit cannot be atomic: ambiguous refresh loss
   fails closed into reauthorization. SSO logout, local disconnect, target revocation, and
   group removal have separate documented/tested effects.

## Alternatives Considered

- **Zero-redirect token exchange** — not selected; no supported end-to-end path was evidenced
  for the intended target, and the user chose the more broadly documented redirect model.
- **Credential-settings UI or CLI enrollment** — rejected user experience; a minimal
  authorization-required/status surface is sufficient and distinct from settings.
- **Redirect during every Luban login for all targets** — unnecessary coupling, prompts,
  and grants for targets the user may not need; use first-use/reauthorization instead.
- **PAT/manual provisioning, password grants, admin impersonation, or shared-service fallback**
  — outside this slice; none substitutes for a failed user grant.
- **Preserve a connector-only impact claim** — rejected as unevidenced for the first-use
  workflow. Keep the existing OAuth core but expose the actual cross-product review scope.

## Consequences

- Uses a widely supported grant family while keeping user credential management out of the
  portal. It is not a universal or future-version compatibility guarantee.
- Requires operator client registration, callback configuration, explicit lifetimes, target
  SSO/RBAC mappings, and refresh/revocation verification. Provider prompts remain possible.
- Adds sensitive durable custody and browser transaction handling; negative tests, real
  Postgres races/recovery, and separately authorized two-user AAP proof are mandatory.
- SPEC-070 remains a reopened draft pending OQ-3/OQ-7 and revised approval. Acceptance will
  supersede ADR-0015 by status/link only; its historical body remains intact.
- No runtime changes, target registration, deployment, commit/push, version bump, or release
  are authorized merely by writing this proposal.
