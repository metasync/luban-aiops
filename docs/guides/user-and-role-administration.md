# User and Role Administration Guide

How identities get into the platform and how their permissions are decided:
adding users, assigning roles through Keycloak groups, adjusting what a role
may do, and verifying the result. Written for platform administrators.

## How Identity Becomes Permission

The chain has four links, each owned by a different surface:

```
Keycloak user ──member of──► Keycloak group ──`groups` claim──► identity-broker
                                                                    │ ROLE_MAPPINGS
                                                                    ▼
                             policy bundle ◄──actions checked── platform roles
```

1. **Keycloak** authenticates the user (OIDC) and emits their group
   memberships as a `groups` token claim (realm `luban-aiops`, client scope
   `groups`).
2. **identity-broker** maps groups to platform roles via a fixed vocabulary
   (`ROLE_MAPPINGS` in
   `products/identity-broker/src/identity_service/services/identity_service.py`):

   | Keycloak group | Platform role |
   |---|---|
   | `ops-admins` | `platform-admin` |
   | `ops-approvers` | `approver` |
   | `ops-operators` | `operator` |
   | `ops-observers` | `read-only-observer` |
   | `ops-auditors` | `auditor` |
   | `ops-developers` | `developer` |

3. **The policy bundle** (`shared/shared-contracts/policies/policy-default.yaml`)
   grants actions to roles, deny-by-default.
4. **The gateways** enforce the bundle on every request.

So the two administrative levers are: *group membership* decides **who has
which role**, and the *policy bundle* decides **what each role may do**.
Neither requires touching the other.

**Default role:** a signed-in user whose groups match nothing resolves to
`read-only-observer`. New users are therefore never locked out of the
portal, but they also cannot act on the system until placed in a group.

## Adding a User

### Dev cluster (test users)

`make deploy` runs `shared/platform-ops/gitops/reconcile-luban-realm.sh`,
which idempotently reconciles the `luban-aiops` realm: the `groups` client
scope, the six role groups, and one test user per group
(`luban-admin`, `luban-approver`, `luban-operator`, `luban-observer`,
`luban-auditor`, `luban-developer`), all with the shared dev password
(`LUBAN_TEST_USER_PASSWORD`, default `luban-dev-2026`). Re-running is safe;
it only re-syncs the test users' passwords.

> **DEV ONLY.** The shared, non-secret password and the script's admin-cli
> flow are for the local dev realm. Never reuse this setup for a real
> environment.

### Real users (Keycloak admin console)

1. Open the Keycloak admin console and select the platform realm
   (`KEYCLOAK_REALM`, `luban-aiops` on dev).
2. **Users → Add user**: set username and email, enable the account.
3. **Credentials**: set a password (or rely on your IdP federation — see
   [Production identity](#production-identity)).
4. **Groups → Join group**: add the user to exactly the `ops-*` groups for
   the roles they should hold. Multiple groups mean multiple roles.

No platform restart is needed — roles are resolved from the token at sign-in.

### Changing or revoking a user's roles

Move the user between `ops-*` groups (or remove them from all). The change
takes effect on the user's **next token**: at their next sign-in, or within
the token lifetime at the silent refresh. To force it immediately, revoke
the user's sessions in Keycloak (**Users → Sessions → Sign out**).

## Changing What a Role May Do

Role capabilities live in the policy bundle, not in Keycloak. The workflow
(edit → `make sync-policy` → `make validate-policy` → commit → deploy) and
worked examples (granting `tools:mutate` to `developer`, revoking a rule)
are in
[Approval and HITL Governance](approval-and-hitl.md#policy-bundle-workflow).

Verify the deployed result in the portal **Permissions** view — it renders
the matrix evaluated from the bundle the gateway actually enforces,
including the bundle version and source.

## Adding a New Role

The role vocabulary is deliberately fixed today. A new role requires:

1. a code change to `ROLE_MAPPINGS` in identity-broker (map a new group),
2. bundle rules granting the role its actions, and
3. a spec, since this changes the trust model (see `docs/specs/README.md`).

If you only need a different *permission mix*, prefer granting or revoking
actions on an existing role via the bundle.

## Production Identity

The dev realm with local users is a stand-in. For real environments the
platform is designed for IdP federation — Keycloak brokering your corporate
directory (AD/LDAP) so group membership flows from existing directory
groups. The design, including attribution requirements, is in
[Identity and Authorization Design](../agentic-aiops-platform/identity-and-authorization-design.md);
the role-to-action rationale is in the
[Authorization Matrix](../agentic-aiops-platform/authorization-matrix.md).

When federating, map directory groups onto the `ops-*` group names (or
adjust the group mapper) so the `groups` claim keeps the vocabulary
identity-broker expects.

## Verifying

1. Sign in to the portal as the user.
2. Click the user card in the sidebar footer — it lists the resolved roles.
3. Open **Permissions** — the user sees their own rows of the live
   role × action matrix.
4. For the full trail, sign in as `luban-auditor` (or any `audit:read`
   identity) and check the audit view: login and action events carry the
   acting identity.

## Troubleshooting

- **User signs in but has only observer access** — their token's `groups`
  claim matched no `ROLE_MAPPINGS` entry: check group membership and that
  the realm's `groups` client scope is attached (the reconcile script
  creates it on dev).
- **Role change not taking effect** — the old token is still live; revoke
  sessions or wait for refresh.
- **Login fails outright** — see
  [Troubleshooting](troubleshooting.md) for the OIDC flow symptoms.

## Related Documentation

- [Portal User Guide](portal-user-guide.md) — what each role sees in the portal
- [Approval and HITL Governance](approval-and-hitl.md) — policy bundle workflow
- [Architecture Overview](architecture-overview.md) — the trust chain end to end
- [Configuration Reference](configuration-reference.md) — identity-broker variables
