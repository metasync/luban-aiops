# SPEC-063 S6 / T-38 — Isolated Acceptance Authorization Record (F-35)

Status: **authorized, not yet executed**. This record is the explicit
environment/action authorization the plan requires before any `make
execution-acceptance` run (plan.md §F-35; tasks.md T-38). It refuses implicit
defaults to the shared development cluster: every field below is named
explicitly, and the driver fails closed if any is missing or if the target
namespace resolves to `dev-luban-aiops`.

## 1. Authorization

- Granted by the user on **2026-09-25**, choosing **Path A-safe**: build a
  purpose-built *isolated* fork overlay and run the live acceptance in a
  **dedicated namespace on the shared OrbStack cluster**.
- Explicitly authorized actions for this acceptance:
  1. Build product images from the current working tree and **deploy** the full
     platform into the isolated namespace.
  2. **Enable durable admission** (real mutations) via the deliberate T-34
     cutover (migration first, then flip `*_ADMISSION_ENABLED=true`).
  3. **Inject real faults** against the live target: interrupt the
     execution-runtime worker mid-dispatch, deny/expire a flow authority, and
     withhold agent acceptance.
  4. Perform **real secret delivery** (password generation + one-time handoff)
     for the held-secret path.
- Explicitly **not** authorized / out of scope: any commit, push, image registry
  push, or modification of the `dev-luban-aiops` deployment, the shared envoy
  Gateway routes, or the shared external Keycloak realm/client. No restart of
  OrbStack. No disruption of the other namespaces on the shared cluster.
- User reminder (2026-09-25): **on teardown, also clean up any Keycloak
  config/settings this acceptance created.** Default plan creates none (see §6);
  if a distinct OIDC client is provisioned, it is deleted on teardown.

## Machine-readable scope (consumed by the fail-closed driver)

The user reconfirmed both implementation and deployment, selecting a dedicated
throwaway user. This block binds CLI arguments to that authorization; it is not
an authorization source independent of the user's approval.

```json
{
  "authorized": true,
  "scenario": "F-35",
  "context": "orbstack",
  "namespace": "spec063-acceptance",
  "origin": "http://acme-admin:8080",
  "target_user": "spec063-accept",
  "operator": "luban-operator",
  "approver": "luban-approver",
  "epoch": "01960c63-0001-4000-8000-000000000001",
  "paths": ["normal", "denied-expired", "interrupted", "owner-reload", "held-secret"],
  "actions": ["lock", "unlock", "password-reset", "interrupt-worker", "withhold-acceptance"],
  "target_restart_allowed": false,
  "keycloak_reconciliation_allowed": false
}
```

## 2. Environment / target identity

| Field | Value |
|---|---|
| Cluster | `orbstack` (single shared node — physical resource sharing is unavoidable; see §7) |
| Namespace (isolated) | `spec063-acceptance` (dedicated; **never** `dev-luban-aiops`) |
| Overlay | `.workspaces/spec063-acceptance/gitops/` (disposable fork; untracked) |
| Target app | `acme-admin` deployed in `spec063-acceptance` via `samples/acme-admin/deploy.sh spec063-acceptance` |
| Target origin | `http://acme-admin:8080` (browser + HTTP allowlists) |
| Ledger DB | the namespace's **own** Postgres (`postgresql://audit:@postgres:5432/sessions`), separate from dev |
| Identity provider | external Keycloak `https://idp.apps.metasync.cc`, realm `luban-aiops` — **read-only reuse**, no reconciliation |
| Admission epoch | `01960c63-0001-4000-8000-000000000001` (fixed UUID; must match migration + both products; replaces the invalid human-readable label `spec063-acceptance-e1` before any migration) |

## 3. Account / actor identity

| Role | Account | Notes |
|---|---|---|
| Operator (initiator) | `luban-operator` (`TEST_USER`) | mints a platform token via the acceptance `identity-service` port-forward |
| Approver / decider | `luban-approver` (`APPROVER_USER`) | tier-2 HITL decider; distinct from operator (no self-approval) |
| Target user mutated | `spec063-accept` (`ACME_ACCEPTANCE_USER`) | dedicated startup-only throwaway record in the isolated acme-admin; not a Keycloak user |

Tokens are minted deterministically through `identity-service` (no browser OIDC
login), so no portal redirect URI or Keycloak client change is required.

## 4. Code / image versions

- `VERSION` = **0.42.0**; git `HEAD` = **bd756e9** with a **dirty** working tree
  (the SPEC-063 implementation, ~104 changed/untracked files).
- Images built from this tree via `make build`; the coordinated `IMAGE_TAG` is
  `0.42.0-dev-k8s-bd756e9-dirty-<timestamp>` — a **distinct tag** from dev's
  running `0.42.0-dev-k8s-00186fb`, so building does not overwrite dev's images.
- Postgres image `postgres:16` (16.14); browser sidecar `chromedp/headless-shell:stable`.

## 5. Permitted faults (and the invariant each proves)

| Path | Permitted fault | Invariant proven |
|---|---|---|
| normal | none | one claim / one gateway attempt / one target effect; durable signed receipt |
| denied-expired | deny or expire the flow authority before dispatch | zero target effect; structured refusal; no forged claim |
| interrupted | kill the execution-runtime pod mid-dispatch (after claim, before/after send) | outcome recorded **unknown**, claim retained, **no** automatic re-dispatch/takeover |
| owner-reload | withhold agent acceptance, then reload the owner session via a fresh process | durable result recovered metadata-only; no re-execution; stop reasons persist |
| held-secret | real password generation + delivery | secret released **only** on original durable success; never on unknown/replay/late |

Constraint (plan §F-35): **do not reseed or restart the acme-admin target between
observations.** Live conversational checks may supplement but never replace the
deterministic assertions.

## 6. Isolation guarantees and Keycloak posture

- The fork overlay renders **only** into `spec063-acceptance` (verified:
  `kubectl kustomize` exit 0; 0 HTTPRoute, 0 web-ui, base `luban-tool-gateway-readonly`
  binding absent, only the renamed `…-spec063` cluster-scoped pair).
- The operator-portal web-ui + its envoy HTTPRoute are **omitted**, so the live
  portal's hostnames/routes are untouched.
- `deploy.sh` is invoked with `RECONCILE_OIDC_PORTAL_CLIENT=false`, so
  `reconcile-luban-realm.sh` and `reconcile-portal-oidc-client.sh` are **skipped**:
  the shared Keycloak realm and `luban-aiops-portal` client are neither created
  nor modified. **Expected Keycloak cleanup: none.**

## 7. Residual risk (disclosed)

Only one thing cannot be isolated: the single OrbStack VM's CPU/RAM/disk are
shared with `dev-luban-aiops` and ~20 other namespaces. A heavy image build plus
a second full platform stack could strain the VM (documented wedge-under-load
history). Mitigations: reuse identical image layers where possible, set explicit
resource requests/limits, check node pressure with bounded `kubectl
--request-timeout` before/after each cluster step, and **stop + tear down
immediately** on MemoryPressure/DiskPressure or API unreachability.

## 8. Independent revision baseline (T-40 reconciliation)

Before and after each mutating observation, read the target state **directly from
acme-admin** — `GET /api/users/spec063-accept` `revision` and `password_changed_at` —
independent of the platform's own claims. Reconcile those against the ledger's
claim/attempt/receipt rows and the HITL card history; record unknowns honestly
and prove no automatic repeat mutation and no late secret release.

## 9. Teardown inventory (executed on removal; keeps nothing orphaned)

1. `kubectl delete namespace spec063-acceptance` — removes all namespaced
   resources (deployments, services, ConfigMaps, Secrets, ServiceAccounts, own
   Postgres StatefulSet + PVC, Redis, acme-admin app + its Secret).
2. `kubectl delete clusterrole,clusterrolebinding luban-tool-gateway-readonly-spec063`
   — the only cluster-scoped objects created (renamed; dev's are untouched).
3. **Keycloak:** none expected (§6). Contingency — if a distinct OIDC client was
   provisioned, delete that client from realm `luban-aiops`; never modify
   `luban-aiops-portal`.
4. Built images: distinct dirty tag; harmless to leave, optionally `docker rmi`.
5. Remove `.workspaces/spec063-acceptance/` (disposable overlay + logs).

Retention option: the namespace is self-contained and may be **kept** for other
test cases; keeping or removing it does not modify any `dev-luban-aiops` object.
