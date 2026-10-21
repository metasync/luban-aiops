# SPEC-070 Gate 0: SSO-Only Delegation Compatibility Report

> **Historical zero-redirect assessment.** The original report below is preserved. Later on
> 2026-10-18 the operator agreed to first-use authorization redirects without credential
> settings. See the [redirect-based reassessment](#redirect-based-reassessment-2026-10-18)
> for the current decision and remaining gate; the old zero-redirect requirement is no
> longer the implementation direction.

- Assessed: 2026-10-18.
- Outcome: **NO-GO for R-1–R-6 implementation on the available evidence.**
- Scope: repository inspection, read-only dev-cluster configuration checks, and official documentation research. No target token acquisition, registration, deployment, or live authorization test was performed.
- Related: [SPEC-070](spec.md), [existing implementation plan](plan.md), [tasks](tasks.md), and [ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md).

## Decision and Operator Requirement

The operator requires user-bound target credentials to be acquired **server-to-server after normal Luban SSO**, with no additional browser redirects, consent clicks, enrollment helper, manual token entry, or portal settings UI. Users and groups originate in enterprise SSO; each system retains its own authorization mapping.

Postgres with application-level authenticated encryption and separately mounted keys is selected for any durable credential custody the eventual mechanism requires. This selection does not establish a grant mechanism or require storing refresh tokens when the target supplies none.

The approved kickoff plan explicitly stops at a compatibility report when the target path cannot be established. That stop condition applies: **no supported end-to-end path satisfying the new requirement has been evidenced for the intended AAP target**. This is an evidence/compatibility blocker, not proof that every possible AAP deployment can never support such a path.

The repository's existing SPEC-070 approval and ADR-0015 describe a different mechanism: one-time target authorization-code enrollment followed by refresh-token use. They are not authority to implement that workflow against the operator's newer requirement. No replacement scheme, target substitution, product upgrade, or outbound signing authority is selected by this report.

## Environment Evidence

Read-only checks used the `orbstack` context and the `dev-luban-aiops` namespace. Only deployment image names and selected non-secret ConfigMap fields were queried; no Kubernetes Secret values or user tokens were read.

| Item | Observed evidence | Limit |
| --- | --- | --- |
| Active Ansible endpoint | `http://ansible-mock-mcp:8000/mcp` in the live `platform-runtime-config` ConfigMap | A dev mock, not an AAP production endpoint |
| Deployed counterpart | `ansible-mock-mcp` deployment uses a tool-gateway image | Does not identify an AAP release or prove native AAP authentication |
| Committed profile | [ansible.env](../../../shared/platform-ops/gitops/runtime-profiles/ansible-dev/ansible.env) selects `ansible-mock`, streamable HTTP | The mock uses a shared bearer; it does not enforce per-user AAP RBAC |
| Keycloak configuration | Live ConfigMap agrees with [identity-broker runtime configuration](../../../shared/platform-ops/gitops/dev-k8s/base/identity-broker/runtime-config.env): shared external IdP, realm `luban-aiops` | No installed Keycloak version is pinned in the inspected configuration |
| Local Keycloak lookup | No Deployment/StatefulSet matched `app.kubernetes.io/name=keycloak` | A label-scoped negative result does not prove absence elsewhere or identify the external server version |
| Intended production target | SPEC-069 names Red Hat AAP; documentation discusses both 2.6 and 2.7 | Actual organization target version, MCP build, endpoint, and enabled federation features remain unknown |

The [mock source](../../../shared/platform-ops/gitops/runtime-profiles/ansible-dev/mock_ansible_mcp_server.py) explicitly returns canned data and checks a shared bearer. Its transport/tool-surface fidelity cannot validate the new credential acquisition or target authorization boundary.

## Current Credential Custody

The inspected source establishes this flow:

1. [Identity-broker login](../../../products/identity-broker/src/identity_service/services/identity_service.py) exchanges the ordinary Keycloak authorization code, uses the Keycloak access token for user information, and maps directory groups to Luban roles.
2. It returns a **Luban-issued access token** plus the Keycloak refresh token and ID token when present. The Keycloak access token is not returned as the platform access token or persisted by that login function.
3. [Platform-gateway auth routes](../../../products/platform-gateway/src/platform_gateway/api/routes/auth.py) return the login/refresh response to the portal. [Portal storage](../../../products/operator-portal/web-ui/app/src/auth/storage.ts) stores the auth session in browser `sessionStorage`; [OIDC handling](../../../products/operator-portal/web-ui/app/src/auth/oidc.ts) sends the refresh token back for normal login renewal.
4. [Internal token exchange](../../../products/identity-broker/src/identity_service/services/exchange_service.py) preserves the human subject/roles and adds the service actor to a Luban-issued audience-bound token. [Tool-gateway verification](../../../products/tool-gateway/src/tool_gateway/services/token_verifier.py) validates that internal issuer/audience locally.
5. [Outbound resolution](../../../products/tool-gateway/src/tool_gateway/tools/auth_resolution.py) supports Basic, bearer, and machine client-credentials today, without upstream SSO token custody. The [MCP adapter](../../../products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py) does not thread the tool's identity argument into credential acquisition.

**Consequence:** retaining or accessing an upstream user token for noninteractive exchange requires an explicit credential-custody design across the auth boundary. It cannot be implemented solely by looking up a username in tool-gateway, forwarding the internal Luban JWT, or assuming the browser-held login refresh token is a target credential. Changing custody is distinct from granting the identity-broker new outbound signing authority; neither is authorized by this report.

## Protocol Compatibility Findings

| Candidate | Verified documentation behavior | Gate result |
| --- | --- | --- |
| AAP 2.6 MCP OAuth | Explicit AAP `/o/authorize/` and `/o/token/` endpoints; authorization-code client registration and callback | Conflicts with the no-additional-browser requirement unless an independently supported noninteractive path is evidenced |
| AAP 2.7 MCP OAuth 2.1 | Adds discovery/PKCE-related configuration; still registers an authorization-code application with redirect URI | Does not establish user token exchange or direct Keycloak-token acceptance; no upgrade assumed |
| Existing AAP refresh token | Refresh renews a previously established grant | Does not solve first-time acquisition without the now-disallowed enrollment |
| Keycloak Standard Token Exchange V2 | Exchanges a Keycloak token for another Keycloak-issued token in the same realm, under configured client/audience permissions | Only usable downstream if that target explicitly accepts the issued token; no such AAP configuration/evidence is available |
| Keycloak cross-domain chaining | Requires a separate accepting authorization server and supported destination grant; destination issues its own token | The destination's support and user linkage are prerequisites, not features created by enabling source-side exchange |
| Keycloak brokered external-token retrieval | Retrieves an existing external IdP credential captured through broker authentication/account linkage; current Broker API V2 has explicit enablement/client permissions | Does not derive an AAP credential from Keycloak group membership; unattended renewal and an existing relationship have not been established here |
| PAT/password/admin-assisted creation | Requires manual credential provisioning, user passwords, or privileged target authority | Outside the approved kickoff's allowed mechanisms; not used as a workaround |

The AAP 2.7 troubleshooting documentation also uses the phrase “token exchange” for an ordinary **authorization-code exchange** after browser sign-in. That phrase is not evidence of RFC 8693 support.

### Evidence sources

Sources were read as documentation, not exercised against the organization's deployment:

- [AAP 2.6: Authenticate with OAuth](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/extend-oauth_authentication_for_the_mcp_server).
- [AAP 2.7: Enable OAuth 2.1 on the MCP server](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/extend-configure_oauth_2_1_authentication_for_the_mcp_server).
- [AAP 2.7: Portal authentication troubleshooting](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/troubleshoot-ref_troubleshoot_portal_authentication).
- [AAP 2.6: Authenticate through the API](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/develop-assembly_controller_api_auth_methods). Documents SSO separately from OAuth token use; external-user token creation is disabled by default and requires administrator configuration. Enabling it is not itself an automatic grant.
- [AAP MCP server source repository](https://github.com/ansible/aap-mcp-server). Its README requires an AAP bearer token; this corroborates the credential boundary but is not a pinned production-build proof.
- [Keycloak: Standard Token Exchange](https://www.keycloak.org/securing-apps/token-exchange#_standard-token-exchange) and [scope, audience, session, and revocation details](https://www.keycloak.org/securing-apps/token-exchange#_standard-token-exchange-details).
- [Keycloak: Cross-domain authorization chaining](https://www.keycloak.org/securing-apps/oauth-identity-authorization-chaining-across-domains) and [JWT Authorization Grant](https://www.keycloak.org/securing-apps/jwt-authorization-grant).
- [Keycloak: Identity Brokering API V2](https://www.keycloak.org/docs/latest/server_development/#identity-brokering-api-v2) and [external-token renewal](https://www.keycloak.org/docs/latest/server_development/#refreshing-external-tokens).

Current Keycloak documentation describes newer features than the original ADR research. It is **not** evidence that the configured shared Keycloak runs a version providing those features or has them enabled. No claim of universal AAP incompatibility is inferred from an absent documentation entry.

## Group Mapping and Revocation

- Luban role mapping is explicit in `resolve_roles`. Login/refresh obtains current user information; already-issued internal JWTs carry a snapshot of groups/roles and tool-gateway verifies them locally. Group changes are not automatically re-read from Keycloak for every tool call.
- [AAP authenticator mapping](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/secure-assembly_gw_mapping) runs during authentication. Its documented examples retain existing permissions for nonmatching users unless the relevant “Block non-matching users” option is selected. Shared group names alone therefore do not prove either equivalent permissions or automatic removal.
- Current Keycloak exchange documentation states that revoking an original access token does not revoke exchanged access tokens. Refresh-token chains have different revocation behavior. Token/session lifetimes and target enforcement must be pinned and tested rather than described as instantaneous revocation.
- No organization-specific AAP mappings, account-disable behavior, group-removal propagation delay, or token-cache lifetime was tested. These remain acceptance blockers for the proposed SSO-only path.

## Required Facts to Reopen Gate 0

The operator or target administrator must supply non-secret configuration facts and supporting documentation; credentials must not be pasted into the report or chat.

| Contract dimension | Missing evidence |
| --- | --- |
| Target/version | Actual AAP release/patch, MCP server build, and an authorized validation environment |
| IdP/version | Actual shared Keycloak version and enabled exchange/brokering features |
| Accepted grant | Target-supported noninteractive user grant, or explicit acceptance of appropriately audience-bound IdP tokens |
| Trust | Accepted issuer, token/validation endpoints, audience/resource, registered client authentication, and trust configuration |
| User binding | Verified namespace/subject linkage and target RBAC mapping; not inferred from email/name equality |
| Authority/lifecycle | Permitted scopes, token/refresh lifetimes, renewal prerequisites, group synchronization, account-disable and revocation behavior |
| Validation authority | Separate permission for any registration, deployment, or live authorization tests required to prove the path |

The enabling proof must use two users with distinct target permissions after ordinary Luban SSO, with **zero additional browser activity**, then demonstrate target refusal and revocation/group-removal behavior. A mock that accepts a token because the test configured it to do so is not production compatibility proof.

## Conditional Spec and ADR Reconciliation

No mechanism-specific amendment is ready for approval. If compatibility is established:

1. Propose a successor ADR rather than rewriting ADR-0015's accepted decision body. [ADR rules](../../adr/README.md) make accepted records immutable except for status/supersession links; update those only when a successor is accepted.
2. Amend SPEC-070 requirements and tasks by agreement: replace one-time enrollment, name the actual grant, specify upstream credential custody and subject/session binding, and update product impact. Do not call token exchange `oauth2_authorization_code`.
3. Explicitly resolve whether identity-broker/platform-gateway login and refresh handling need changes. Preserve the no-new-outbound-signing-authority default unless separately approved. No new settings UI is required merely because auth plumbing changes.
4. Keep R-6's encrypted Postgres selection, but store only the durable secret class the verified mechanism needs. Specify credential/key rotation, revocation, and cross-process concurrency before implementation.
5. Reconcile the spec index, roadmap, and affected dependency pointers with the revised approval state; preserve dated history. The attached kickoff plan is not edited.
6. Map the revised acceptance criteria to R-1–R-6 failure-first tests, then obtain approval before runtime work. Release/version, commit, push, deployment, and live tests remain separate boundaries.

## Execution Disposition

- Completed: code/configuration assessment, read-only deployed-profile checks, current AAP/Keycloak documentation assessment, and this compatibility report.
- Pending/blocking: exact target/IdP facts, a supported no-browser user grant, target identity/RBAC/lifecycle proof, and revised architectural approval.
- Not started: R-1 parser changes; R-6 store; R-2 grant/client/custody; R-3 trust wiring; R-4 audit changes; R-5 runtime tests; deployment or release work.
- Verification for this change is documentation-only. No `make verify` or runtime acceptance pass is claimed. The implementation plan's runtime test gates remain pending.

**Next move:** obtain the versioned target capability evidence above. If the target cannot provide the required grant, return to the operator with that incompatibility; do not weaken the SSO-only requirement, introduce impersonation, or substitute another target without a new decision.

## Redirect-Based Reassessment (2026-10-18)

This addendum follows the operator's later agreement to the recommended direction:
**allow standard first-use/reauthorization redirects, without credential settings, manual
token entry, or an enrollment helper**. It supersedes the zero-redirect requirement for
future work, not the factual evidence or original no-go result above.

### Current Disposition

- **Protocol direction: supported by documentation.** Target authorization-code OAuth
  matches AAP's documented MCP path. Specialized noninteractive token exchange is no
  longer required. This is a more interoperable baseline, not universal future-proofing.
- **Deployment compatibility: still unverified.** No organization AAP release/MCP build,
  configured security/renewal profile, or actual per-user RBAC proof was supplied. The
  existing dev mock is unchanged. No token acquisition, registration, or live test was run.
- **Architecture: ratified 2026-10-18.** SPEC-070 now includes first-use workflow handling,
  encrypted Postgres custody, and callback/account-binding gates, and is `approved`.
  [ADR-0016](../../adr/0016-just-in-time-outbound-oauth-authorization.md) is **accepted** and
  retains ADR-0015's grant while expanding the cross-product scope; ADR-0015 is
  `superseded by ADR-0016` with its accepted body unchanged. Approval authorized the OQ-7
  detailed-contract design, which was **ratified 2026-10-19** — the pre-runtime gate is closed
  and R-1..R-6 implementation may begin against it. Runtime code that depends on the OQ-3
  deployment facts and any live target work remain gated (OQ-3 pre-live).

### Rechecked Target Evidence

| Source | Documented behavior | Implication / remaining check |
| --- | --- | --- |
| [AAP 2.6 MCP OAuth](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/extend-oauth_authentication_for_the_mcp_server) | Authorization-code application; confidential client when the client can protect a secret; explicit `/o/authorize/`, `/o/token/`, callback URI | Suitable grant family for a backend client. No discovery requirement should be invented. PKCE is **not enforced**; that is not a statement that it is unsupported. Verify S256 behavior on the actual build. |
| [AAP 2.7 MCP OAuth 2.1](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.7/extend-configure_oauth_2_1_authentication_for_the_mcp_server) | Authorization-code app; PKCE required by default for new apps, disabled for migrated apps; MCP OAuth must be enabled through deployment settings | Version alone is insufficient: inspect app and MCP settings. No upgrade or settings change was performed. |
| [AAP 2.6 API authentication](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/develop-assembly_controller_api_auth_methods) | OAuth application tokens, configurable expiration/revocation; external SSO users cannot generate OAuth tokens by default | Administrator must confirm external-user eligibility and client registration. SSO login does not itself supply Luban with a target token. |
| [AAP 2.6 external-application token configuration](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/secure-assembly_gw_token_based_authentication) | Documents application-scoped tokens and revocation, read-only tokens, and a **one-year default access-token lifetime**, with older long-lived tokens retained | Explicit lifetime/revocation policy is required; do not call tokens short-lived by default. Controller/gateway token migration distinctions also require the actual endpoint/build. |

The reviewed MCP setup pages do not pin this installation's refresh-token issuance,
rotation, expiry, or revocation contract. Those are required follow-up facts, not inferred
from the existence of `/o/token/`. A target not supporting the required renewal must be
reported explicitly; do not invent a refresh token or silently substitute a PAT.

### User Experience and Security Boundary

Normal Luban SSO stays unchanged. First use of a needed target may redirect through its
own login/consent flow and reuse an existing SSO session where supported. Later calls renew
server-to-server; revoked/expired grants may need another redirect. Cancellation is a
normal visible outcome, not an automatic redirect loop.

Target access/refresh tokens stay backend-only. Authorization codes/state necessarily
traverse the authorization browser redirect, but the backend callback consumes them before
rendering portal content; JS, browser storage, logs, traces, referrers, and transcripts must
not receive them. The code is not the long-lived credential. OAuth consent does not approve
an operation or permit replay of a write.

### Remaining Approval and Evidence Checklist

1. Supply exact AAP release/patch, MCP build and non-secret endpoint/security settings;
   Keycloak version and target SSO mappings are needed for login/lifecycle behavior, not
   token-exchange features. Keep all credentials out of chat and documentation.
2. Confirm confidential-client authentication, exact callback, PKCE S256, read-tier scopes,
   trusted immutable target-account linkage, refresh issuance/rotation, and explicit
   access/refresh lifetimes. Identify supported revocation and identity lookup endpoints.
3. Pin Luban/target group mappings, external-user OAuth eligibility, offboarding/revocation,
   and measured cache/synchronization limits; matching group names are not proof.
4. **Done — OQ-7 ratified 2026-10-19.** The detailed first-use API/stream/browser-binding/
   continue contract (SPEC-070 OQ-7) is complete and ratified, closing the pre-runtime design
   gate that stood before runtime implementation. The revised spec/ADR were ratified
   2026-10-18 (ADR-0016 accepted, ADR-0015 superseded, SPEC-070 approved); the contract's two
   **[OQ-3]** value/fact pins (numeric TTLs, PKCE enforcement) await the OQ-3 deployment facts.
5. Obtain separate authorization for registration/deployment/live tests. Delivery needs
   two actual target users proving first-use redirects, later no-prompt renewal, wrong-account
   rejection, RBAC denial, disablement/group removal, revocation, and restart/removal behavior.

**No zero-redirect grant evidence is requested under this revised direction.** The next
external input is the actual AAP client/renewal/security profile. Documentation-only checks
do not satisfy any runtime or live acceptance gate.
