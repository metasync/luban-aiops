# SPEC-069 Plan: Ansible Read-Tier MCP-Ingestion Pilot

> **Approved — implementation authorized to begin.** This plan was authored alongside
> `spec.md` at drafting time per the SPEC-064/065/066/067 same-session precedent. SPEC-069
> is `approved` (operator, 2026-10-12). The **five Open Questions were resolved by operator
> direction on 2026-10-11** (OQ-1 self-hosted open-source server behind a server-agnostic
> connector; OQ-2 two-layer model — this spec is the read-only discovery layer; OQ-3
> `--check` removed from the read tier; OQ-4 user-delegated identity to the targets,
> mechanism extracted to
> [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); OQ-5 self-contained
> in-cluster validation). What remains is **Stage-0 verification facts** (exact server
> artifact + license/provenance, the concrete read-operation set + argument shapes, what
> AAP's MCP server auth accepts) and **one production-path dependency**
> ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md), itself `approved`) — so
> R-2–R-6 below stay provisional on the Stage-0 facts and firm up as Stage 0 closes. R-1 is
> not built here — it is a dependency on the delivered
> [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (v0.47.0) for dev
> and on [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) for the production
> user-delegated path. Approval authorizes implementation to begin; commit/push, deployment,
> and any version bump remain separate authorization boundaries **not** granted here.
> **Stage 0 (verification) is the first thing to execute now that the spec is approved** —
> the OQ-1 server-artifact choice determines whether R-2 builds an MCP adapter or the native
> fallback, so no target-specific implementation should start before Stage 0 closes.

## Approach

The pilot builds **one move**: the **generic, server-agnostic** MCP-ingestion connector
beneath `tool-gateway`, proven against a **self-provisioned** Ansible target at **read tier**
as the **discovery layer (Layer 1)** of a deliberate **two-layer** model. It consumes the
delivered SPEC-068 outbound-credential substrate for development (R-1 is a dependency gate,
not work), records **user-delegated identity to the targets** as the production governance
target (dependent on
[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)), and produces the reusable
adapter +
typed-tool model that [SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md) will
later configure for ServiceNow and that the **Layer-2 runbook-typed-tool fast-follow** will
extend — rather than either building blind. R-2–R-6 are provisional until Stage 0 pins the
server artifact (OQ-1), the read-operation set (OQ-2), and what AAP's MCP server auth
accepts (OQ-4 residual). The stages are ordered so the connector is validated against an
in-cluster mock target before any live infrastructure is touched.

0. **Verify** (Stage 0) — read-only. Pin the residual facts the OQ resolutions left as
   verification tasks because they are properties of the Ansible target/artifact, not
   decisions: the exact self-hosted MCP-server artifact + its license/provenance (OQ-1), the
   concrete admitted read-operation set + each tool's argument-validation shape (OQ-2), and
   what auth AAP's MCP server accepts for the delegated path (OQ-4 residual, feeding
   [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)). Confirm the
   self-contained validation topology (OQ-5). Each has a
   named fallback in *Sequencing* so a hard-to-obtain fact degrades the pilot's scope rather
   than blocking the reusable connector.
1. **Depend** (Stage 1, R-1 → SPEC-068) — the **dev** outbound credential substrate
   (additive `scheme` field + connector-local token client + resolver seam, with redaction
   and fail-closed tests) is **delivered** by SPEC-068 (v0.47.0), not built here; this pilot
   consumes its resolver, or uses no credential if Stage-0 picks a loopback sidecar. The
   **production user-delegated** identity is recorded as a dependency on
   **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (not built here).
2. **Connect** (Stage 2, R-2 + R-3) — the **server-agnostic** MCP-SDK ingestion adapter +
   the Ansible **read-only** binding (native read-only connector as the OQ-1 fallback),
   reusing the SPEC-007 registry seam and establishing the typed-tool model, plus
   deny-by-default policy-bundle coverage.
3. **Attribute** (Stage 3, R-4 + R-5) — audit fidelity (requester + acting service +
   target + tool + outcome + the dev-vs-production per-user-RBAC distinction) and the
   fail-closed/no-fabrication guardrail (with dry-run explicitly excluded from the read
   tier).
4. **Provision** (Stage 4, R-6) — the self-hosted Ansible MCP server + mock managed host
   deployment, sync-model credential delivery, and dev-k8s overlay wiring; AAP read-only-mode
   validation as a documented operator step outside CI.
5. **Deliver** (Stage 5) — living-state docs, CHANGELOG, version; separate authorization.

## Design Per Requirement

### R-1: Outbound identity, credential, and target topology (dependency on SPEC-068 + SPEC-070)

- affected files / modules: **none in this spec.** The dev credential-scheme extension — the
  optional per-set `scheme`, the connector-local `oauth2_client_credentials`/`bearer`
  token client, and the reusable async auth-resolution seam — is delivered by
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (v0.47.0). See
  SPEC-068's plan for the design, alternatives (Option A connector-local chosen over B/C
  centralized), and test strategy. The **production** outbound **user-delegated** credential
  (token exchange / OBO / per-user OAuth / SSO) is
  **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** — its own spec — and
  is **not** designed here.
- chosen approach here: **consume** SPEC-068's resolver seam for dev. The Ansible MCP
  session resolves any dev credential through SPEC-068 (never a pilot-local
  re-implementation); this pilot adds no credential code of its own. The production
  user-delegated path is recorded as a dependency; SPEC-069's read-only discovery slice runs
  against the self-hosted server's own auth and is **not blocked** on
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md).
- **OQ-1/OQ-5 topology gate:** Stage-0 picks between (a) a **loopback-bound in-pod
  sidecar** — the browser-engine model (`chromedp/headless-shell` at `127.0.0.1:9222`,
  NetworkPolicy-isolated, so nothing off-pod can bypass the gateway and **no outbound
  credential is needed**) — and (b) a **NetworkPolicy-isolated in-cluster Service**, which
  needs a SPEC-068 `bearer` credential. The sidecar is preferred where feasible (safest,
  no egress); the Service topology exercises SPEC-068's `bearer` path. Either way the
  endpoint is operator configuration, never a model-selected argument.
- **OQ-4 delegation note:** the operator's governance target is that the requesting user's
  delegated identity reaches the managed target (per-user RBAC + attribution). Because
  SPEC-068's `client_credentials` is a machine grant with no user subject, realizing this in
  production requires
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); the mechanism decision
  lives there, not here.

### R-2: Server-agnostic MCP-ingestion connector + Ansible read-only binding

- affected files / modules: a new `products/tool-gateway/src/tool_gateway/` ingestion
  subpackage (a **generic, server-agnostic** MCP client adapter over the official `mcp` SDK +
  an Ansible **read-only** target binding); registration into the existing `ToolRegistry` as
  **typed tools**; a new **direct `mcp` dependency** in tool-gateway's
  `pyproject.toml`/`uv.lock`.
- chosen approach (**transport inherited from SPEC-067 OQ-3**): build the **generic**
  adapter over the **official `mcp` Python SDK** behind a gateway-owned governance layer
  that maps each discovered server tool into a typed `BaseTool`/`ToolDefinition` (SPEC-007
  seam), authenticating the MCP session via the R-1 dev credential set (or loopback, per the
  topology gate). **The adapter is server-agnostic**: tool admission and tier mapping are
  **configuration** (endpoint, admitted tool names, tier mapping), not adapter code — which
  is exactly what lets the same adapter bind to a self-hosted AWX/mock server in dev, to
  **AAP's read-only-mode** server in production, and later to a ServiceNow binding (SPEC-067)
  and the **Layer-2 runbook-tool** binding, all without re-building the adapter. Governance
  stays tool-gateway-side: the adapter admits only tools explicitly named in the policy
  bundle and treats server-advertised metadata as untrusted. The kernel calls them through
  the existing signed-tool path (SPEC-037); no new kernel seam, and the kernel never becomes
  an MCP client. `mcp` is added to tool-gateway only — its lockfile is separate from the
  kernel's transitive AgentScope pin.
- alternatives: (a) a gateway-owned **native read-only Ansible connector** — retained as
  the documented **fallback** if Stage-0 (OQ-1) finds no suitable open-source Ansible MCP
  server passes the supply-chain/license review; it shells to `ansible-inventory` in
  read-only mode and registers the same `BaseTool` seam, but it does **not** prove the
  MCP-ingestion substrate (so it is a last resort, not the goal); (b) a third-party/community
  Ansible MCP *server* deployed as-is without review — rejected (supply-chain/license risk,
  and it would re-expose our target credential to a component we have not vetted); (c)
  hand-rolling the MCP protocol — rejected (an official maintained SDK exists); (d)
  `ansible-collections/ansible.mcp` — rejected, it is the **opposite** direction (Ansible
  *consuming* MCP), not an Ansible-as-server target.
- **OQ-2/OQ-3 gate (resolved):** the admitted set is **read-only discovery operations only**
  — inventory host/group listing, `gather_facts`/setup reads, job-template listing, job
  log/status monitoring, environment health. **`--check`/dry-run is not admitted** (OQ-3: not
  a sound read-tier boundary). The exact operation list + each tool's argument-validation
  shape are pinned in Stage 0.

### R-3: Deny-by-default policy coverage for Ansible tools

- affected files / modules: `shared/shared-contracts/policies/` (canonical bundle), synced
  to consumers via `make sync-policy`; the policy scenario suite.
- chosen approach: name each admitted Ansible read tool in the bundle at **read tier**;
  unlisted tools (and any playbook-run/runbook-execution/mutation name) stay denied. Add
  scenario coverage so `make validate-policy-scenarios` asserts the new names resolve as read
  tier and that no write/admin Ansible name exists.

### R-4: Audit fidelity and user-delegated attribution

- affected files / modules: the tool-gateway audit emission path, keeping the requester and
  acting-service identities separate per ADR-0004's `sub`/`act` delegation and the identity
  model's separate-identity logging.
- chosen approach: emit requester identity + acting service identity + target system + tool
  name + outcome per call; assert no secret/token/`client_secret` reaches audit. **Plus the
  delegation distinction (OQ-4):** the production path attributes each call to the requesting
  user end to end (per-user target RBAC, realized through the R-1 dependency
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); AAP's
  MCP server natively inherits the user's RBAC). In dev (self-hosted server) Luban-side
  attribution to the principal is still recorded, but the record makes the **dev-vs-production
  per-user-RBAC distinction explicit** rather than implying target-side per-user RBAC the dev
  topology does not provide.

### R-5: Fail-closed and no-fabrication guardrail (dry-run is never read-tier)

- affected files / modules: the Ansible connector's error handling and result normalization.
- chosen approach: map transport/timeout/HTTP-error to a failed tool outcome with a reason
  and a target-unavailable audit attribution; never return an empty "success." Mirrors
  SPEC-058's `http.get` "an upstream 4xx/5xx is a fact, not a tool error" rule. **Dry-run
  exclusion (OQ-3):** no read-tier tool invokes `--check`; the admitted read set contains no
  operation whose safety depends on check mode. Where the Layer-2 fast-follow later offers a
  dry-run preview, it is surfaced as a fact about a *plan* (a "not checkable" module reported
  honestly), never as an executed mutation and never as a read-tier guarantee.

### R-6: Target provisioning and overlay wiring

- affected files / modules: `shared/platform-ops/gitops/dev-k8s/` (the self-hosted Ansible
  MCP server Deployment/Service or sidecar, the mock managed-host target, overlay, and any
  credential-set secret); the `sync-*.sh` secret-delivery scripts if the topology needs a
  credential.
- chosen approach: deploy the **self-hosted** Ansible MCP server (AWX + community AWX MCP
  server, or a thin mock MCP server, per Stage-0 OQ-1) + mock managed host through the
  overlay (reusing the SPEC-068 live-check's ephemeral-mock-target pattern); deliver any
  credential fields through the existing sync model (never hand-edited in a consumer copy);
  keep `make validate-secret-vocabulary` and `make overlays` green. Inventory source,
  endpoint, admitted-tool list, and executable path are operator configuration in the
  overlay; **CI makes no live external call** (OQ-5). The chosen server artifact + its
  license/provenance pass a recorded supply-chain review before pinning; **AAP read-only-mode
  validation is a documented operator step outside CI**, not a CI gate.

## Sequencing And Dependencies

1. **Stage 0 — Verify** — depends on nothing; read-only; first to execute at approval.
   Fallbacks: if OQ-1 finds no self-hosted MCP server passes review, take the native
   read-only connector fallback (R-2 alternative a) and record that the MCP substrate was
   *not* proven on this target; if a required read needs real infrastructure, defer that
   operation rather than fake it (OQ-5 go/no-go).
2. **Stage 1 — R-1 credential substrate (SPEC-068)** — **delivered** (v0.47.0) for dev, a
   dependency not built here; does **not** depend on Stage 0. Gate: the connector resolves
   any dev credential through SPEC-068's resolver seam (or uses loopback with no credential).
   The **production** user-delegated path depends on
   **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (separate spec) and
   does **not** block the read-only discovery slice.
3. **Stage 2 — R-2 connector + R-3 policy** — depends on Stage 0 (server artifact/scope) and
   Stage 1 (resolver). Builds the **generic, server-agnostic** adapter + typed-tool model
   first, then the Ansible read-only binding.
4. **Stage 3 — R-4 audit + R-5 fail-closed/no-fabrication** — depends on Stage 2.
5. **Stage 4 — R-6 provisioning + overlay** — depends on Stage 0 (topology) and Stage 2.
6. **Stage 5 — delivery boundary** — separate authorization (docs, CHANGELOG, version).

**Relationship to SPEC-067:** this pilot is sequenced **ahead of** SPEC-067 for
implementation because SPEC-067 is PDI-blocked; it does **not** supersede SPEC-067. The
generic adapter built in Stage 2 is the piece SPEC-067's R-2 assumed it would build first,
so once SPEC-069 lands, SPEC-067's R-2 reduces to a ServiceNow-specific binding + its own
Stage-0 facts. If SPEC-067's PDI unblocks first, the order can flip back — the connector is
server-agnostic either way.

**Relationship to the Layer-2 fast-follow:** SPEC-069 delivers **Layer 1 (read-only
discovery)** and establishes the server-agnostic connector + typed-tool model. **Layer 2 —
runbooks as typed tools** — is a **separate write-tier fast-follow spec** (number assigned at
its own drafting, not reserved here). It reuses this adapter and the typed-tool model, adds
write-tier tools behind the existing HITL machinery (ADR-0007, SPEC-054, SPEC-037, SPEC-038,
SPEC-063), and depends on the OQ-4 delegation substrate
([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)) + solving the §6.2
bundled-mutation / idempotency / uncertain-outcome problems. A runbook's N-step control flow
executes inside
Ansible/AAP, not the kernel, so it does not collide with ADR-0011 / SPEC-057.

## Test Strategy

- unit tests: the generic MCP-tool→typed-`ToolDefinition` mapping (server metadata treated
  as untrusted, never setting tier); **server-agnostic** binding (the same adapter maps a
  self-hosted AWX/mock server's tools and an AAP read-only-mode config without adapter-code
  change); connector registration and **read-tier-only** exposure (assert no
  playbook-run/runbook-execution/mutation tool registers, and **no `--check`/dry-run tool is
  admitted**); the no-fabrication mapping; and that the connector resolves any dev credential
  through SPEC-068's resolver (not a local re-implementation). The `credential_sets` parsing,
  bearer branch, and token-client cache/redaction tests live in SPEC-068. Redaction tests
  mirror SPEC-009 R-1's deterministic tool-output redaction.
- contract tests: policy-bundle scenarios (`make validate-policy-scenarios`),
  `make validate-policy` + `make policy-diff`, and `make validate-secret-vocabulary`.
- integration / overlay validation: `make overlays` renders the dev-k8s wiring; the adapter
  is exercised against a **local self-hosted Ansible MCP server + mock managed host** deployed
  in-cluster (the SPEC-068 live-check pattern) so CI makes **no live external call**; the
  native read-only fallback path is covered by the same mock-target tests. A gated
  live-check script (mirroring `shared/platform-ops/e2e/http-check-demo.sh`) proves the
  end-to-end inventory/facts read against the deployed gateway, with the fail-closed negative
  control and redaction assertions. **AAP read-only-mode validation is a documented operator
  step run outside CI** (no licensed instance in CI).

## Rollout And Migration

- deployment or configuration changes required: the self-hosted Ansible MCP server + mock
  managed-host deployment in the dev-k8s overlay; any credential-set entry (delivered through
  SPEC-068's provisioning model); a synced policy-bundle update naming the Ansible read tools;
  a new direct `mcp` dependency in tool-gateway's lockfile.
- backward compatibility: the SPEC-068 substrate is already shipped and inert until a
  non-`basic` set exists; this pilot adds only the ingestion adapter + Ansible read-only
  binding + policy entries, so no current behavior moves. The adapter is inert without a
  named, policy-admitted Ansible tool.
- rollback approach: remove the Ansible credential set / MCP-server deployment and its
  policy entries; the adapter is inert without them, so rollback needs no code revert (the
  `mcp` dependency can stay pinned-but-unused or be dropped). SPEC-068's additive scheme
  code is unaffected by this pilot's rollback. Because the adapter is generic and
  server-agnostic, rolling back the Ansible binding does not affect any future ServiceNow
  binding or the Layer-2 runbook-tool binding.
- forward path: the **Layer-2 runbook-typed-tool fast-follow** and the **outbound
  user-delegated-identity substrate**
  ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)) are separate specs that
  build on this adapter and on SPEC-068 respectively; neither is authorized by this plan.
