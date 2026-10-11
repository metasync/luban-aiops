# SPEC-069: Ansible Read-Tier MCP-Ingestion Pilot

## Status

- status: `approved`
- owner: luban-platform-team
- created: 2026-10-11
- release slice: **R6 — External System Integration via MCP Ingestion** (second target
  slice, **re-sequenced ahead of SPEC-067 for implementation**; see the [delivery
  roadmap](../../agentic-aiops-platform/delivery-roadmap.md#r6-external-system-integration-via-mcp-ingestion))
- target version: **v0.48.0** — pinned at approval (2026-10-12). The platform is at
  v0.47.0 (SPEC-068 shipped the R6 outbound-credential substrate there); like SPEC-066/068,
  this pilot's read-only dev slice is self-contained enough to ship at its own minor bump.
  The `VERSION` file bump itself is a separate release gate, crossed neither by approval nor
  by implementation.
- related ADRs: **none at draft for this read-only slice.** Adopting the official `mcp`
  Python SDK as the ingestion transport is inherited from
  [SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md) OQ-3 (resolved
  2026-10-07); this pilot does not re-open it. The outbound-credential acquisition-locus
  ADR trigger was resolved in
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (Option A
  connector-local, no ADR needed). Two downstream decisions are deliberately **not** made
  here: (1) the **Layer-2 runbook-typed-tool** fast-follow will engage ADR-0007
  (one HITL gate per mutating flow) and ADR-0011 / SPEC-057 (no control flow in the
  kernel) — see Non-Goals; (2) the **outbound user-delegated identity** mechanism (OQ-4)
  is extracted to
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md), where the trust-model
  ADR it forces (**ADR-0015, expected**) lives — this read-only slice itself adds no
  signing authority and needs no ADR.
- lineage: promoted from the
  [MCP-ingestion re-sequencing memo](../../workspace/mcp-ingestion-resequencing-spike.md)
  §1/§3/§4/§6 (the self-provisioning ranking, the read-tier-neutralizes-blast-radius
  argument, and the pilot scope) and from the
  [MCP-ingestion memo](../../workspace/mcp-ingestion-spike.md) §5 (the connector
  invariants) and §6.2 (the "If a read/inventory/`--check` (dry-run) capability exists,
  stage it first as read-tier" escape hatch this pilot enacts, narrowed to pure reads per
  OQ-3). **Depends on**
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (delivered
  v0.47.0) for the outbound execution-credential substrate, and — for the **production**
  user-delegated path only — on
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) (the outbound
  user-delegated-identity substrate, extracted from this pilot's OQ-4; itself `draft`).
  **Re-sequences** — does
  *not* supersede — [SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md),
  which stays `draft` and PDI-gated. Builds on
  [SPEC-007](../SPEC-007-tool-execution-framework/spec.md) (the
  `BaseTool`/`ToolDefinition`/`ToolRegistry` seam the ingestion connector reuses) and is
  the **opposite direction** from the parked
  [MCP-exposure spike](../../workspace/mcp-exposure-spike.md) (gateway-as-MCP-*server*,
  never promoted to a spec).

> **Approval note (SDD discipline).** The full scaffold (`spec.md` + `plan.md` +
> `tasks.md`) was authored together per the SPEC-064/065/066/067 same-session precedent.
> The five Open Questions that blocked `approved` at drafting were **resolved by operator
> direction on 2026-10-11** (see Open Questions): OQ-1 develop against a **self-hosted
> open-source** Ansible MCP server behind a **server-agnostic** connector (AAP is the
> production target, validated as an operator Stage-0 step); OQ-2 a **two-layer** model —
> this spec is the **read-only discovery layer**, runbooks-as-typed-tools is a separate
> **write-tier fast-follow**; OQ-3 **`--check` dry-run is not a sound read-tier boundary**
> and is removed from the read tier; OQ-4 **user-delegated identity to the targets** is the
> governance model, with the mechanism extracted to
> **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)**;
> OQ-5 **self-contained in-cluster validation** confirmed. What remains is **Stage-0
> verification facts** (exact server artifact + license/provenance, the concrete read
> operation set + argument shapes, what AAP's MCP server auth accepts) recorded as tasks in
> `tasks.md`, plus the **production-path dependency** on
> [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md). Unlike SPEC-067, **no
> remaining item is gated on an external provider** — that self-provisionability is the
> entire reason this pilot is sequenced first. **Approved by the operator 2026-10-12;
> implementation authorized to begin** (the SPEC-066 precedent: the residual items are
> checkable Stage-0 verification tasks, not blocking Open Questions). The
> `plan.md`/`tasks.md` provisional banners are lifted. Commit/push, deployment, and any
> version bump remain separate authorization boundaries **not** granted by this approval.

## Summary

Give operators real **read-only** Ansible visibility — inventory host/group listing, fact
gathering, job-template listing, job log/status monitoring, and environment health — through
the platform's existing governed tool path, by building the **generic, server-agnostic
MCP-ingestion connector** beneath `tool-gateway` and pointing it at an Ansible MCP server
the pilot **self-provisions in the dev cluster**. This is R6's first *implementable* target
slice and the **discovery layer** of a deliberate **two-layer** model: Layer 1 (this spec)
admits only pure reads; Layer 2 — a separate **write-tier fast-follow** — models each
**runbook as a typed tool** behind the existing HITL machinery. The connector consumes the
delivered [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md)
outbound-credential substrate for development, proves the reusable ingestion adapter that
[SPEC-067](../SPEC-067-servicenow-mcp-ingestion-pilot/spec.md) will later configure rather
than build, and records the operator's governance target — **user-delegated identity carried
all the way to the managed targets** — against a target with **no external gate** and, at
read tier, **no infrastructure blast radius**.

## Motivation

- **The first-drafted pilot is externally blocked.** SPEC-067 (ServiceNow) cannot reach
  `approved`: its three remaining Open Questions (OQ-1 auth scheme, OQ-4 read-operation
  set, OQ-5 dev-cluster feasibility) are all **PDI-gated live-target facts** requiring a
  real ServiceNow tenant / Personal Developer Instance on a provider waitlist. R6's value
  ("prove governance survives the MCP boundary on one real target") stalls if it waits on
  ServiceNow.
- **The substrate is delivered and live-verified.** SPEC-068 shipped at v0.47.0 and was
  proven end to end on the dev cluster: an ephemeral in-cluster mock OAuth2 target, a real
  `client_credentials` token acquired and attached **through the deployed gateway over a
  network hop**, the fail-closed negative control (an upstream `401` surfaced as a fact),
  and redaction (no token / `client_secret` in any envelope or log) all green, with all
  ephemeral state torn down. That harness is the **pattern** this pilot's Stage-0 reuses —
  and it demonstrates the dev cluster can host a mock external target, which ServiceNow
  cannot.
- **Ansible is the self-provisionable target.** Ranked on *self-provisioning difficulty*
  rather than blast radius (re-sequencing memo §3): Ansible is open source, Linux-native,
  and runs in-cluster (🟢); Windows needs a non-cluster host + weak UI-verification
  determinism (🟠); ServiceNow needs a real tenant (🔴). The generic connector can be
  validated against Ansible **now**, with no external dependency.
- **The organization runs AAP; the connector must be server-agnostic.** The production
  target is the **Red Hat Ansible Automation Platform (AAP) MCP server** — technology
  preview in AAP 2.6.4 (Feb 2026), **generally available in AAP 2.7 (Jun 2026)**, deployed
  *within* AAP (operator on OpenShift, or containerized on RHEL 9/10) over HTTPS `:8448`.
  It ships a **native read-only mode** and a read-write mode, six official toolsets (job,
  inventory, monitoring, user, security/compliance, platform config), and **dual-layer auth
  that inherits the requesting user's permissions via RBAC** — which is exactly the OQ-2
  discovery layer and the OQ-4 user-delegated model. But AAP requires a **licensed
  instance** we do not have for development. So the deliverable is the **MCP
  client/connector inside tool-gateway**, and the server is the **integration counterpart**:
  the connector is written **server-agnostic** (config-driven tool admission + tier
  mapping) and developed against a **self-hosted open-source** server — AWX (AAP's
  open-source upstream) plus a community AWX MCP server, or a thin mock MCP server — then
  validated against real AAP read-only mode as an operator Stage-0 step. *(The
  `ansible-collections/ansible.mcp` project is the **opposite** direction — Ansible
  consuming MCP — and is not a candidate.)*
- **Read tier removes the objection that ranked Ansible 2nd.** The
  [MCP-ingestion memo](../../workspace/mcp-ingestion-spike.md) §6.2 called Ansible
  "highest value, highest blast radius" because a playbook is a **bundled N-step
  mutation** — but that is a *write-tier* property, and §6.2 already named the escape
  hatch: *"If a read/inventory/`--check` (dry-run) capability exists, stage it first as
  read-tier."* This pilot enacts that hatch but **narrows it to pure reads** (inventory,
  facts, job-template listing, job logs, health) — OQ-3 found the quoted `--check` clause
  unsound as a read-tier boundary (see the next bullet), so dry-run is **not** admitted. It
  mutates nothing. The write-tier blast-radius, idempotency, and uncertain-outcome problems
  stay out of scope (Non-Goals) for the Layer-2 fast-follow.
- **`--check` is not a read-tier boundary (OQ-3 correction).** The original draft admitted
  Ansible `--check` (dry-run) as a read-tier operation. The operator corrected this: a task
  with `check_mode: false` **bypasses** `--check`, many modules do not fully support check
  mode, and some results do not accurately reflect until a play is actually executed — so
  dry-run is **not** a sound safety boundary. `--check` is therefore **removed from the read
  tier**; it survives only as an optional **action-layer preview** on a Layer-2 runbook
  tool's HITL card (a fact about a *plan*, never a read-tier guarantee and never an applied
  change).
- **User-delegated identity is the governance default (OQ-4).** The operator directs that
  tasks/tools run under the **requesting user's delegated identity all the way to the
  managed targets**, so the agent never acts on its own authority and every action is
  attributable to a human principal under that principal's own target RBAC. SPEC-068's
  shipped schemes (`basic` / `bearer` / `oauth2_client_credentials`) are **service/machine**
  grants with **no user subject**, so this needs an **outbound user-delegated credential**
  (OAuth2 Token Exchange RFC 8693 / on-behalf-of, per-user OAuth authorization, or
  shared-IdP SSO) that exists nowhere today. It is extracted as
  **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** — a reusable substrate
  mirroring how SPEC-068 was itself extracted from SPEC-067 — and is a dependency of the
  **production** path; SPEC-069 dev-validates against the self-hosted
  server's own auth meanwhile.
- **It de-risks SPEC-067 rather than competing with it.** Building the *generic*
  ingestion adapter here — against a target we control — means SPEC-067's R-2 becomes a
  ServiceNow-specific **configuration** of an already-proven adapter, not a first
  implementation against a waitlisted instance.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable acceptance
criteria. R-1 is a dependency pointer (SPEC-068 for dev;
[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) for production); R-2–R-6
remain provisional on the Stage-0 verification facts and are finalized as Stage 0 closes.

### R-1: Outbound identity, credential, and target topology

The connector authenticates to the Ansible MCP server through the outbound
execution-credential substrate delivered by
[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (v0.47.0) for
**development** — never a pilot-local re-implementation — **or** through no credential at
all if Stage-0 selects a loopback-bound sidecar topology isolated by NetworkPolicy (the
browser-engine model). The **production** governance target is a **user-delegated** outbound
identity (OQ-4), which depends on
[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) (the outbound
user-delegated-identity substrate) that this pilot records as a dependency but does not build.

Acceptance criteria:

- SPEC-068 is delivered (it is — v0.47.0) before this pilot's connector authenticates a
  target: the Ansible MCP session resolves any **dev** credential through SPEC-068's
  resolver seam (`bearer` or `oauth2_client_credentials`), with no pilot-local token code.
- Stage-0 (OQ-1/OQ-5) pins the **topology**: a loopback-bound in-pod sidecar (no egress,
  possibly no outbound credential) or a NetworkPolicy-isolated in-cluster Service (a
  SPEC-068 `bearer` credential). Whichever is chosen, the endpoint is **operator
  configuration, never a model-selected argument**.
- The **production user-delegated identity** is recorded as a **dependency on
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (itself `draft`);
  SPEC-069 does **not**
  implement token exchange / OBO itself. The dev path runs against the self-hosted server's
  own auth, so SPEC-069's read-only discovery slice is **not blocked** on that substrate.
- SPEC-068's secret-handling invariants (redaction, fail-closed, no secret in audit/logs)
  apply to this pilot's calls by inheritance; R-4 asserts them for the Ansible path.

### R-2: Server-agnostic MCP-ingestion connector + Ansible read-only binding

Add the **generic MCP-ingestion adapter** owned by `tool-gateway` — the reusable piece
SPEC-067 later consumes and the Layer-2 fast-follow extends — over the official `mcp`
Python SDK, plus an Ansible target binding. Discovered server tools are mapped into the
SPEC-007 `BaseTool`/`ToolDefinition`/`ToolRegistry` seam as **typed tools** and registered
beside the native `k8s.*`/`elastic.*`/`web.*`/`http.*` connectors. The adapter is
**server-agnostic**: tool admission and tier mapping are **configuration**, so the same
adapter binds to a self-hosted AWX/mock server in dev and to AAP's read-only-mode server in
production without adapter-code changes. The `mcp` dependency is added to **tool-gateway
only**; the agent-platform kernel never becomes an MCP client. *(Transport direction
inherited from SPEC-067 OQ-3; server artifact and exact read-operation set provisional on
Stage-0.)*

Acceptance criteria:

- The generic adapter maps an MCP-server tool into a typed `ToolDefinition` and registers it
  in the gateway registry; the mapping is target-agnostic (the Ansible binding is
  configuration, not adapter code), so a future ServiceNow binding — and the Layer-2
  runbook-tool binding — reuse the same adapter and the same typed-tool model.
- Admitted Ansible read tools are **read-only discovery operations only** — inventory
  host/group listing, `gather_facts`/setup reads, job-template listing, job log/status
  monitoring, environment health — each callable by the kernel through the existing
  signed-tool path (SPEC-037) with **no new kernel seam**. **No `--check`/dry-run and no
  mutating operation is admitted** (OQ-3; see R-5).
- **Tool metadata advertised by the MCP server is untrusted input.** The adapter admits
  only tools explicitly named in the policy bundle and never auto-registers whatever the
  server advertises; a server-declared annotation, `readOnlyHint`, or description never
  sets a tool's tier or grants approval (the MCP-exposure spike's "remote annotations
  never auto-approve" invariant, applied to ingestion).
- The MCP protocol is never hand-rolled. A gateway-owned **native** read-only Ansible
  connector (`ansible-inventory` shell-out, not MCP) is the documented **fallback** if
  Stage-0 (OQ-1) finds no suitable MCP server passes the supply-chain / license review.
- Endpoint URL, executable path, inventory source, admitted-tool list, tier mapping, and
  credential source are operator configuration; no credential or token crosses the adapter
  into a tool result or log.

### R-3: Deny-by-default policy coverage for Ansible tools

Ansible tools are deny-by-default until the policy bundle names them, and each named read
tool resolves to read tier.

Acceptance criteria:

- An unlisted Ansible tool is denied (deny-by-default preserved).
- Each named read tool resolves to **read tier**; no admitted tool resolves to write or
  admin tier. A playbook-run / runbook-execution / mutation tool name is **absent** from the
  bundle (it belongs to the Layer-2 fast-follow at write tier).
- The policy-bundle scenario suite (`make validate-policy-scenarios`) gains coverage for
  the new tool names; `make validate-policy` and `make policy-diff` stay green after the
  bundle change is synced (authored canonically in `shared/shared-contracts/policies/`,
  never edited in place).

### R-4: Audit fidelity and user-delegated attribution

Every Ansible tool call records the requester identity, the acting service identity, the
target system, the tool name, and the result outcome; secrets never appear in audit. The
governance target (OQ-4) is that the **requesting user's delegated identity is carried to
the managed target**, so the target enforces that user's own RBAC and every action is
attributable to a human principal.

Acceptance criteria:

- An audit event for an Ansible read carries requester + acting-service identity + target
  + tool + outcome, keeping the requester and acting-service identities separate per
  ADR-0004's `sub`-user / `act`-service delegation and the identity model's
  separate-identity logging.
- The **production** path attributes each call to the requesting user end to end (per-user
  target RBAC), realized through the R-1 dependency
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); AAP's MCP server
  natively supports this by inheriting the user's RBAC. In **dev** (self-hosted server)
  Luban-side attribution to the principal is still recorded even though the target-side
  identity is the dev server's own — the audit record makes this distinction explicit
  rather than implying per-user target RBAC that the dev topology does not provide.
- No credential secret, token, or `client_secret` appears in any audit record or log line
  (asserted alongside R-1's inherited redaction).

### R-5: Fail-closed and no-fabrication guardrail (dry-run is never read-tier)

A target that is unreachable, times out, or errors is surfaced as a failed outcome and
never presented as a successful result. **`--check`/dry-run is not admitted at read tier**
(OQ-3) and is never presented as a safety boundary; where a Layer-2 runbook tool later
offers a dry-run preview, it is reported as a **plan**, never as an applied change.

Acceptance criteria:

- A simulated Ansible / MCP-server outage or timeout yields a **failed** tool outcome with
  a reason, not a fabricated or empty "success" (mirrors SPEC-058's `http.get` rule that
  "an upstream 4xx/5xx is a fact, not a tool error", and the MCP-exposure spike §5
  fail-closed-no-fabrication posture).
- The failure is attributed in audit as a target-unavailable outcome, distinct from a
  policy denial.
- **No read-tier tool invokes `--check`/dry-run**; the admitted read set (R-2) contains no
  operation whose safety depends on check mode. A dry-run preview, if any, exists only at
  the Layer-2 action tier and is surfaced as a fact about a *plan* — a module that does not
  support check mode is reported as "not checkable", never silently as "no change".

### R-6: Target provisioning and overlay wiring

The self-hosted Ansible MCP server (or native fallback), its mock managed target, and any
credential set are provisioned through the established GitOps / `sync-*.sh` model and wired
into the dev-k8s overlay; nothing is edited in place. Validation against real **AAP**
read-only mode is an **operator Stage-0 step** performed outside CI.

Acceptance criteria:

- The self-hosted Ansible MCP server (AWX + community AWX MCP server, or a thin mock MCP
  server, per Stage-0 OQ-1) + mock managed host deploy to the dev-k8s namespace through the
  overlay; `make overlays` renders green.
- Any credential fields the topology needs (per R-1) are delivered by a sync script and
  never hand-edited in a consumer copy; `make validate-secret-vocabulary` stays green.
- Inventory source, endpoint, admitted-tool list, and executable path are operator
  configuration in the overlay, never model-selected; **CI makes no live external call**
  (OQ-5 self-contained validation is against the in-cluster mock target only). The chosen
  server artifact + its license/provenance pass a recorded supply-chain review before
  pinning; AAP read-only-mode validation is a documented operator step, not a CI gate.

## Non-Goals

- **Layer-2 runbook execution (runbooks as typed tools).** Modeling each runbook as a typed
  tool the agent can invoke is a **write-tier** capability and a **separate fast-follow
  spec** (number assigned at its own drafting — **not** reserved here). It must first solve
  the [MCP-ingestion memo](../../workspace/mcp-ingestion-spike.md) §6.2 **bundled N-step
  mutation** blast-radius, uncertain-outcome, and idempotency problems, and it depends on
  the OQ-4 delegation substrate
  ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)). It stays behind the
  existing HITL one-gate-per-flow
  (ADR-0007), action-card (SPEC-054), signed-execution (SPEC-037), isolated-worker
  (SPEC-038), and durable-claim (SPEC-063) machinery. **SPEC-069 establishes the
  server-agnostic connector and the typed-tool model this fast-follow extends, but builds no
  write tool.** *(A runbook's N-step control flow executes inside Ansible/AAP, not the
  kernel, so modeling it as one typed tool does not collide with ADR-0011 / SPEC-057 "no
  control flow; composition carries no authority".)*
- **`--check`/dry-run as a read-tier boundary.** Dry-run is **not** a sound safety boundary
  (OQ-3: `check_mode: false` bypasses it; some modules do not reflect real results until
  executed). It is never admitted at read tier; it survives only as an optional Layer-2
  action-layer preview.
- **Building the outbound user-delegated identity mechanism.** OQ-4's user-delegated
  identity to the targets is the recorded governance **target**, but the **mechanism**
  (token exchange / OBO / per-user OAuth / SSO) is extracted to
  **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** and is **not**
  implemented here. SPEC-069 dev-validates against the
  self-hosted server's own auth.
- **Superseding SPEC-067 (ServiceNow).** This pilot **re-sequences** implementation order
  only. SPEC-067 stays `draft` and PDI-gated; it is not replaced, and it returns to
  active sequencing whenever its PDI unblocks — reusing the generic connector this pilot
  builds.
- **Windows UI automation.** The third named target needs a Windows host/VM outside the
  Linux cluster and its own boundary study (verification/evidence quality for UI-derived
  state); it is a separate later spec.
- **Wiring production AAP auth/topology.** AAP is the **production target server** (its
  MCP server is validated in read-only mode as an operator Stage-0 step), but wiring
  AAP-specific production auth, licensing, and topology is an operator/deployment activity
  outside this self-provisioned dev-cluster pilot's code scope.
- **The inbound machine-consumer `client_credentials` grant / stable-API
  productization.** That is the parked, trust-model-blocked row (no human owner/approver);
  this spec is the outbound plane and does not touch it.
- **Gateway-as-MCP-server exposure.** That is the parked
  [MCP-exposure spike](../../workspace/mcp-exposure-spike.md) (never promoted to a spec),
  the opposite direction; this spec reuses the platform's tool contract, never an exposure
  path.
- **Hand-rolling the MCP protocol.** The official `mcp` Python SDK is the transport
  (inherited from SPEC-067 OQ-3); the protocol is never re-implemented here.

## Impact

- products touched: `products/tool-gateway` (the generic **server-agnostic** MCP-ingestion
  adapter + Ansible target binding, typed-tool registration, and a new **direct `mcp`
  dependency** in tool-gateway's `pyproject.toml`/`uv.lock` — the kernel's separate lockfile
  is untouched); `shared/shared-contracts/policies` (Ansible read-tool names/tiers);
  `shared/platform-ops/gitops/dev-k8s` (the self-hosted Ansible MCP server + mock
  managed-host deployment, overlay, and any credential-set entry). The outbound-credential
  code (`credential_sets.py`, `http_connector.py`, `oauth_client.py`) is delivered by
  **SPEC-068**, on which this pilot depends; the **production** user-delegated path
  additionally depends on
  **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (out of scope here).
- contracts touched: the policy bundle (new read-tier Ansible tool names). The
  credential-file shape and secret-vocabulary work belong to SPEC-068 and are inherited
  unchanged; [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) will add an
  outbound user-delegated credential shape of its own.
- identity / policy / audit / execution safety impact: **consumes** SPEC-068's outbound
  execution credential for dev (the External Execution Identity's second concrete form) and
  records **user-delegated identity to the targets** as the production governance target;
  audit gains external-target attribution plus the dev-vs-production per-user-RBAC
  distinction (R-4); read-tier only, so no new HITL surface; fail-closed and no-fabrication
  preserved, with dry-run explicitly excluded from the read tier.
- living state docs to update on delivery: `products/tool-gateway/README.md` (tool surface
  + the ingestion adapter), `docs/agentic-aiops-platform/architecture.md` (tool-gateway
  section), the delivery-roadmap R6 status, and
  `identity-and-authorization-design.md` §Service Identity Model (record the outbound
  user-delegated-identity target and the Ansible control-node attribution case).

## Open Questions

All five Open Questions that blocked `approved` at drafting were **resolved by operator
direction on 2026-10-11**. What remains is **Stage-0 verification facts** (checkable, not
decisions — recorded as tasks in `tasks.md`) and **one production-path dependency**
([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)). Following the
SPEC-066/067 precedent, checkable facts are
Stage-0 tasks rather than blocking Open Questions.

- **OQ-1 — RESOLVED (operator direction 2026-10-11): develop against a self-hosted
  open-source server behind a server-agnostic connector.** The organization runs the **AAP
  MCP server** in production (GA in AAP 2.7, native read-only mode, RBAC-inheriting auth),
  but it is not available for development. The connector is therefore written
  **server-agnostic** and developed against a **self-hosted open-source** server — AWX +
  community AWX MCP server, or a thin mock MCP server — with real AAP read-only-mode
  validation as an operator Stage-0 step. *Residual Stage-0 facts:* pin the exact server
  artifact and pass a supply-chain/license/provenance review before pinning (R-2/R-6);
  confirm what auth AAP's MCP server accepts for the delegated path (feeds
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)).
- **OQ-2 — RESOLVED (operator direction 2026-10-11): two-layer model.** The read-only tier
  is a **must** for troubleshooting and agent↔Ansible interaction (Layer 1, this spec);
  runbooks are additionally exposed as **typed tools** the agent can call (Layer 2), under
  the **same HITL rules as today**. SPEC-069 delivers **Layer 1 only** and establishes the
  typed-tool model + server-agnostic connector Layer 2 extends; **Layer 2 is a separate
  write-tier fast-follow spec** (number assigned at its own drafting). *Residual Stage-0
  facts:* pin the exact read-operation set (inventory host/group, facts, job-template list,
  job log/status, health) and each tool's argument-validation shape (R-2/R-3).
- **OQ-3 — RESOLVED (operator direction 2026-10-11): `--check` is not a read-tier
  boundary.** Dry-run is useful but **unsound** as a read-tier safety boundary — a task with
  `check_mode: false` bypasses `--check`, and some runbook results do not properly reflect
  in check mode until actually executed. `--check` is **removed from the read tier** (R-2/R-5)
  and survives only as an optional **Layer-2 action-layer preview** (a fact about a plan,
  never an applied change and never a read-tier guarantee).
- **OQ-4 — RESOLVED in direction (operator direction 2026-10-11): user-delegated identity to
  the targets.** The safest AI-governance default is to run tasks/tools under the
  **requesting user's delegated identity all the way to the targets**, so the agent never
  acts on its own authority. **Consequence:** SPEC-068's `client_credentials` is a
  service/machine grant with **no user subject**, so this needs an **outbound user-delegated
  credential** that exists nowhere today. It is **extracted as
  [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (R-1 dependency for the
  production path); SPEC-069 dev-validates against the self-hosted server's own auth and is
  **not blocked**. *The mechanism decision (OAuth2 Token Exchange RFC 8693 / OBO, per-user
  OAuth authorization, or shared-IdP SSO) lives in SPEC-070, not here.*
- **OQ-5 — RESOLVED (operator direction 2026-10-11): self-contained validation.** The
  operator wants self-hosted/self-contained validation: the whole pilot is validated against
  the local dev-k8s cluster by deploying the self-hosted Ansible MCP server + a **mock
  managed host** in-cluster (the SPEC-068 live-check pattern), so **CI makes no live external
  call** (R-6). Real AAP read-only-mode validation is a documented operator step outside CI.

## Changelog

- 2026-10-12: **approved by the operator** (status `draft` → `approved`); implementation
  authorized to begin (the SPEC-066 precedent — the residual items are checkable Stage-0
  verification tasks, not blocking Open Questions). Target version pinned to **v0.48.0**
  (the `VERSION` bump itself remains a separate release gate). The outbound user-delegated-
  identity follow-up substrate referenced throughout is now numbered
  **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (`draft`; its OQ-1
  mechanism + OQ-2 ADR scope block its own approval, and it forces **ADR-0015**); R-1's
  production-path dependency now names it. The `plan.md`/`tasks.md` provisional banners are
  lifted. Commit/push, deployment, and any version bump remain separate authorization
  boundaries not granted by this approval. No implementation has started.
- 2026-10-11: created as `draft`; full scaffold (`spec.md` + `plan.md` + `tasks.md`)
  authored together per the SPEC-064/065/066/067 precedent, with `plan.md`/`tasks.md`
  banner-marked provisional because five Open Questions blocked `approved` and the source
  memos authorize no implementation. Promoted from the
  [MCP-ingestion re-sequencing memo](../../workspace/mcp-ingestion-resequencing-spike.md)
  (2026-10-11), which re-orders the R6 pilots so this read-tier Ansible pilot is
  implemented ahead of the PDI-blocked SPEC-067. Depends on SPEC-068 (delivered v0.47.0);
  re-sequences, does not supersede, SPEC-067. No implementation, pilot, ADR, adapter,
  deployment, or version bump is authorized.
- 2026-10-11: **all five Open Questions resolved by operator direction.** OQ-1 → develop
  against a **self-hosted open-source** server (AWX/mock) behind a **server-agnostic**
  connector; AAP is the production target, validated as an operator Stage-0 step. OQ-2 →
  **two-layer** model: this spec is the **read-only discovery layer**; runbooks-as-typed-tools
  is a separate **write-tier fast-follow**. OQ-3 → **`--check` dry-run removed from the read
  tier** (not a sound safety boundary); it survives only as a Layer-2 action-layer preview.
  OQ-4 → **user-delegated identity to the targets** is the governance target; the mechanism
  is extracted to a **SPEC-068 follow-up substrate** (production-path dependency, not built
  here). OQ-5 → **self-contained in-cluster validation** confirmed. Summary, Motivation,
  R-1/R-2/R-4/R-5/R-6, Non-Goals, and Impact revised accordingly; residual checkable facts
  moved to Stage-0 tasks. Still `draft`; approval, implementation, commit, deployment, and
  version bump remain separate authorization gates.
