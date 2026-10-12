# Spike: Re-sequencing the R6 MCP-Ingestion Pilots — Ansible Read-Tier First

Status: assessment — recommends re-ordering the staged R6 pilots from the
[mcp-ingestion memo](mcp-ingestion-spike.md) §6 so a **read-tier Ansible** pilot is
implemented **first**, ahead of the ServiceNow pilot
([SPEC-067](../specs/SPEC-067-servicenow-mcp-ingestion-pilot/spec.md)), because
ServiceNow is externally blocked and Ansible is not. **No implementation, pilot, ADR,
adapter, or spec approval is authorized by this memo.**
Date: 2026-10-11
Roadmap home: [R6 — External System Integration via MCP
Ingestion](../agentic-aiops-platform/delivery-roadmap.md#r6-external-system-integration-via-mcp-ingestion)
Re-sequences: [mcp-ingestion-spike.md](mcp-ingestion-spike.md) §6 (the
ServiceNow → Ansible → Windows risk order). This memo **inherits that memo's trust
boundary (§4) and connector invariants (§5) and does not restate them**; it changes
only the *order in which the pilots are built*, not the architecture.
Builds on: [SPEC-068 outbound execution-credential
schemes](../specs/SPEC-068-outbound-execution-credential-schemes/spec.md) (delivered
v0.47.0) — the substrate every ingestion pilot consumes.
Evidence baseline: repository at v0.47.0 (`a598ecb`); the SPEC-068 substrate was
**live-verified on the dev cluster** (see §3) — a real OAuth2 `client_credentials`
token was acquired and attached through the *deployed* gateway over a network hop to
an ephemeral in-cluster mock target, with the fail-closed negative control and
redaction assertions green. **No Ansible MCP server has been installed, tested, or
deployed.**
Promoted to: [SPEC-069 Ansible read-tier MCP-ingestion
pilot](../specs/SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) — `draft`
2026-10-11, **approved 2026-10-12** (implementation authorized to begin; commit/push,
deployment, and any version bump remain separate gates). Its five Open Questions were
**resolved by operator direction 2026-10-11** (see §8); what remains is Stage-0
verification facts about the Ansible target plus a production-path dependency on
[SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md) (the outbound
user-delegated-identity substrate, extracted from OQ-4 and numbered 2026-10-12; itself
`draft`) — not design preferences.

## 1. Question and recommendation

> SPEC-068 (the reusable outbound-credential substrate) is delivered and
> live-verified. SPEC-067 (ServiceNow, the first-drafted pilot) is blocked on
> PDI-gated facts we cannot obtain. What should R6 build next?

Recommendation: **build a read-tier Ansible pilot first** — as
[SPEC-069](../specs/SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) — and
treat it as the slice that **proves the generic MCP-ingestion connector on a target
we can self-provision**, so the ServiceNow pilot later reuses a connector already
validated end to end rather than building one blind against a waitlisted instance.

This is a **sequencing decision, not a supersession.** SPEC-067 stays `draft` with
its three PDI-gated Open Questions intact; it is *re-ordered behind* SPEC-069 for
implementation, not replaced. Both consume the same SPEC-068 substrate, and SPEC-069
builds the *generic* ingestion adapter that SPEC-067's R-2 had assumed it would build
first. The 2026-09-23/09-30 risk order (ServiceNow → Ansible → Windows) was correct
*on blast-radius grounds*; it did not anticipate that the lowest-blast-radius target
would be gated on an external waitlist we cannot walk around, while the
highest-blast-radius target (Ansible) has a **read-tier subset** that removes exactly
the risk that ranked it 2nd.

## 2. What changed — the sequencing constraint is external, not architectural

The [mcp-ingestion memo](mcp-ingestion-spike.md) §6 ranked the three named targets by
blast radius and put ServiceNow first as "the lowest-risk target to prove the
substrate." Two facts have since changed the *practical* order without changing that
ranking's logic:

1. **ServiceNow is externally blocked.** SPEC-067's three remaining Open Questions
   (OQ-1 auth scheme, OQ-4 read-operation set, OQ-5 dev-cluster feasibility) are all
   **PDI-gated live-target facts**: they need a real ServiceNow tenant / Personal
   Developer Instance, which is on a provider waitlist. No amount of local work
   resolves them. SPEC-067 cannot reach `approved`, let alone be implemented, on any
   timeline we control.
2. **The substrate it was waiting to prove is now delivered and live-verified.**
   SPEC-068 shipped at v0.47.0, and §3 below records a real end-to-end credential
   check against the deployed gateway. The reusable capability the *first* pilot was
   supposed to exercise no longer needs a pilot to exercise it — so the first pilot's
   job is now to prove the **ingestion connector**, and that can be done against a
   target we control.

The consequence: R6's value ("prove governance survives the MCP boundary on one real
target") is **blocked** if it waits on ServiceNow, and **unblocked** if the first
implemented pilot targets a system we can stand up in the dev cluster.

## 3. The re-sequencing axis — self-provisioning difficulty

The operator's steering question was: *which target is least dependent on live
systems we do not control — i.e. which can we set up ourselves without a
service-provider gate?* Ranked on that axis (not blast radius):

| Target | Can we self-provision the live target? | Blocker | Self-provision rank |
|---|---|---|---|
| **Ansible** | **Yes** — open source, Linux-native, runs in-cluster; a supply-chain-reviewed Ansible MCP server + a mock managed host both deploy to the dev-k8s namespace | none external; only a Stage-0 artifact/license review | 🟢 **1st** |
| **Windows UI** | **Partly** — the UI engine is open, but it needs a **Windows host/VM outside the Linux cluster** and its state is read via screenshots/UI-tree/OCR | non-cluster host + weak verification determinism (strains the anti-fabrication guardrail) | 🟠 2nd |
| **ServiceNow** | **No** — needs a real tenant / PDI | provider waitlist (SPEC-067 OQ-1/OQ-4/OQ-5) | 🔴 3rd |

**Corroborating evidence — the dev cluster can already host a mock external target.**
The SPEC-068 live-check (§ Evidence baseline) stood up an *ephemeral in-cluster mock
OAuth2 target*, provisioned `oauth2_client_credentials` credential sets for both
`client_secret_post` and `client_secret_basic`, drove a real token acquisition +
authenticated call **through the deployed tool-gateway over a network hop**, proved the
fail-closed negative control (an upstream `401` surfaced as a fact, not an error), and
proved redaction (no token / `client_secret` in any result envelope or gateway log).
All ephemeral state was torn down and the cluster verified reverted. That harness is
the *pattern* SPEC-069's Stage-0 will reuse: deploy the Ansible MCP server + a mock
managed host in-cluster, and validate the connector without any external dependency.
ServiceNow has no equivalent local path — which is precisely why it cannot be first.

## 4. Why read-tier neutralizes the Ansible blast-radius objection

The [mcp-ingestion memo](mcp-ingestion-spike.md) §6.2 ranked Ansible **2nd** and
called it "highest value, highest blast radius": a playbook is a **bundled N-step
mutation** with broad target credentials, a step-change beyond today's single
exact-name `k8s.delete_pod`. That objection is real — **for the write tier.** It does
not apply to the read tier, and §6.2 already named the escape hatch:

> *"If a read/inventory/`--check` (dry-run) capability exists, stage it first as
> read-tier."*

SPEC-069 enacts that hatch but **narrows it to pure reads** (the quoted `--check` clause
was subsequently found unsound — see the correction below) and admits **only**:

- **inventory reads** — list hosts/groups from the Ansible inventory (pure read, no
  target execution);
- **fact gathering** — `gather_facts` / setup-module reads against a managed host
  (read-only collection, the `elastic.*` / `incidents.*` read analog);
- **job-template listing + job log/status monitoring + environment health** — read-only
  visibility into what automation exists and how past runs fared (the AAP MCP server's
  read-only-mode analog).

None of these mutates infrastructure. The blast-radius, bundled-mutation,
uncertain-outcome, and idempotency problems §6.2 raised are **write-tier** problems and
are explicitly **out of scope** (Non-Goals).

> **Correction (OQ-3, resolved 2026-10-11).** This memo's original §4 listed Ansible
> `--check` (dry-run) as a third read-tier operation. The operator corrected that: a task
> with `check_mode: false` **bypasses** `--check`, many modules do not fully support check
> mode, and some results do not accurately reflect until a play is actually executed — so
> dry-run is **not** a sound read-tier safety boundary. `--check` is therefore **removed
> from the read tier**; it survives only as an optional **action-layer preview** on a
> Layer-2 runbook tool's HITL card (a fact about a *plan*, never an applied change and
> never a read-tier guarantee). The fail-closed / no-fabrication posture is unchanged and
> still mirrors SPEC-058's "an upstream 4xx/5xx is a fact, not a tool error."

So the re-sequencing is **not** "do the risky target first." It is "do the *read tier*
of the self-provisionable target first, and defer every write-tier risk to its own
gated spec" — the same read-tier-first posture R6 already committed to.

## 5. Non-negotiable architecture (inherited, unchanged)

SPEC-069 inherits the trust boundary and connector invariants from
[mcp-ingestion-spike.md](mcp-ingestion-spike.md) §4–§5 **verbatim** and adds nothing
to them. The load-bearing points, for convenience:

- The MCP adapter sits **beneath** `tool-gateway`; the gateway is the only execution
  surface and the **kernel never becomes an MCP client**.
- The connector **reuses the SPEC-007 seam** (`BaseTool` / `ToolDefinition` /
  `ToolRegistry`); an MCP-backed tool is another `BaseTool`, registered beside
  `k8s.*` / `elastic.*` / `web.*` / `http.*`, with the same local static risk tiers,
  the same redaction choke point, and the same `tool_invoked` audit.
- **Server-advertised metadata is untrusted.** The adapter admits only tools
  explicitly named in the policy bundle; a server's `readOnlyHint` / annotations never
  set a tier or grant auto-approval.
- **Endpoint URLs, executable paths, inventory, and credential sources are operator
  configuration, never model-selected arguments.**
- Topology prefers **in-cluster / sidecar reachability on a bound endpoint**, mirroring
  the browser engine — which for Ansible means the MCP server can be a loopback-bound
  sidecar (no egress, possibly no outbound credential at all) or a NetworkPolicy-
  isolated in-cluster Service (a SPEC-068 `bearer` credential). Stage-0 picks between
  them (SPEC-069 OQ-1/OQ-5).

## 6. Scope of the read-tier Ansible pilot

One generic ingestion connector, pointed at one self-provisioned target, admitting a
minimal read-tier operation set:

- **Build the generic MCP-ingestion adapter** (the reusable piece SPEC-067 will later
  consume) over the official `mcp` Python SDK, behind a gateway-owned governance
  adapter, added as a **tool-gateway-only** direct dependency (kernel lockfile
  untouched).
- **Point it at a self-hosted Ansible MCP server** the pilot deploys in-cluster (Stage-0
  pins the exact open-source artifact — AWX + community AWX MCP server, or a thin mock —
  plus license/provenance review, with a gateway-owned native read-only Ansible connector
  — `ansible-inventory` shell-out, **no `--check`** — as the documented fallback if no
  suitable MCP server passes review). The connector is **server-agnostic**, so the same
  adapter later binds AAP's read-only-mode server (the production target).
- **Admit only** the read-only discovery operations — inventory / facts / job-template
  listing / job log-status / health (per the §4 correction, **not** `--check`) — each named
  at read tier in the canonical policy bundle; deny-by-default for everything else, and
  **no** playbook-run / runbook-execution / mutation tool exposed.
- **Attribute + fail closed:** requester + acting-service identity + target + tool +
  outcome per call, with **user-delegated identity to the targets** as the production
  governance model (OQ-4; mechanism in
  [SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md)); unreachable /
  timeout / error → a failed outcome, never a fabricated result.
- **Validate against the dev cluster** using the §3 mock-target harness pattern (a mock
  managed host in-cluster), so CI makes no live external call.

## 7. Go/no-go gates and next decision

This memo authorizes **no** implementation. Recommended next decisions, in order:

1. **Accept the re-sequencing** — implement SPEC-069 (read-tier Ansible) ahead of
   SPEC-067 (ServiceNow), leaving SPEC-067 `draft` and PDI-gated, not superseded.
2. **Resolve SPEC-069's Stage-0 Open Questions** (transport/server artifact + license,
   read-operation set, `--check` safety, control-node credential/audience model, and
   dev-cluster feasibility) before `approved`. — **Done 2026-10-11:** all five were
   resolved by operator direction (see §8 and the SPEC-069 Open Questions); `--check`
   safety resolved **against** read-tier admission, and the credential/audience question
   resolved to **user-delegated identity to the targets** with the mechanism extracted to
   [SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md). What remains is
   Stage-0 verification facts, not decisions.
3. **Build the generic connector under SPEC-069** so SPEC-067's R-2 becomes a
   ServiceNow-specific configuration of an already-proven adapter, not a first
   implementation against a waitlisted target.
4. **Keep writes deferred.** Any real playbook execution is a later, separately-approved
   write-tier spec under the existing HITL / signed-execution path — it must first solve
   §6.2's bundled-mutation blast-radius and idempotency problems.

**Stop and retain native** if Stage-0 finds no Ansible MCP server that passes the
supply-chain/license review *and* the native read-only fallback cannot preserve the
governance invariants — failure to adopt Ansible is not approval to build a
replacement, and ServiceNow returns to first place whenever its PDI unblocks.

## 8. Open questions handed to SPEC-069

> **Resolved 2026-10-11.** All five questions below were answered by operator direction and
> are recorded as RESOLVED in
> [SPEC-069](../specs/SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) §Open
> Questions; the list is retained as the historical hand-off. In brief: OQ-1 → self-hosted
> open-source server behind a **server-agnostic** connector (AAP = production target);
> OQ-2 → **two-layer** model (this spec = read-only discovery; runbooks-as-typed-tools =
> write-tier fast-follow); OQ-3 → `--check` is **not** a read-tier boundary (removed);
> OQ-4 → **user-delegated identity to the targets** (mechanism →
> [SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md)); OQ-5 →
> **self-contained in-cluster validation**.

- **Transport/server (architectural fork):** which Ansible MCP server does the connector
  consume — a self-hosted open-source server deployed in-cluster (supply-chain +
  license reviewed), Ansible Automation Platform's MCP server if the operator licenses
  AAP, or a gateway-owned **native** read-only Ansible connector (not MCP — which would
  not prove the R6 ingestion substrate)? This selects the whole shape.
- **Read-operation set + tiers:** exactly which inventory / facts / `--check` operations
  are admitted, and each one's argument-validation shape and policy tier.
- **`--check` safety:** is dry-run mode a sound read-tier boundary given that some
  modules do not support check mode and report "changed", and some read remote state?
  Pin whether the pilot admits `--check` at all or only inventory + facts.
- **Control-node credential/audience model:** the Ansible control node holds broad
  SSH/WinRM credentials to managed hosts. How does that reconcile with per-requester
  attribution, and how is the memo §5 "one dedicated target identity is **not**
  per-user target RBAC" caveat surfaced?
- **Dev-cluster feasibility (go/no-go):** can the whole pilot be validated in-cluster
  against a mock managed host (expected yes — the re-sequencing rationale), or does any
  part need real infrastructure?

## Changelog

- 2026-10-11, initial draft: records the re-sequencing of the R6 MCP-ingestion pilots
  so a **read-tier Ansible** pilot (promoted to
  [SPEC-069](../specs/SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md)) is
  implemented ahead of the PDI-blocked ServiceNow pilot (SPEC-067). Ranks the three
  named targets on **self-provisioning difficulty** (Ansible 🟢 / Windows 🟠 /
  ServiceNow 🔴) rather than blast radius, cites the SPEC-068 v0.47.0 live-check as
  evidence the dev cluster can host a mock external target, and shows that a read-tier
  subset (inventory / facts / `--check`) neutralizes the blast-radius objection that
  ranked Ansible 2nd in the [mcp-ingestion memo](mcp-ingestion-spike.md) §6. Inherits
  that memo's §4–§5 architecture unchanged. **Assessment only — no implementation,
  pilot, ADR, adapter, or spec approval is authorized by this memo.**
- 2026-10-11, OQ resolutions folded in: the operator resolved all five SPEC-069 Open
  Questions. §4/§6 corrected to **drop `--check` from the read tier** (OQ-3: dry-run is
  not a sound read-tier boundary — `check_mode: false` bypasses it, and some modules do
  not reflect results until executed) and to name the read-only discovery set (inventory /
  facts / job-template listing / job log-status / health); §6/§8 note the **server-agnostic**
  connector developed against a **self-hosted** open-source server with **AAP** as the
  production target (OQ-1), the **two-layer** model with runbooks-as-typed-tools as a
  write-tier fast-follow (OQ-2), **user-delegated identity to the targets** as the
  governance model with the mechanism in a SPEC-068 follow-up substrate (OQ-4), and
  **self-contained in-cluster validation** (OQ-5). Still **assessment only** — no
  implementation authorized.
- 2026-10-12, SPEC-069 approved + SPEC-070 numbered: SPEC-069 was **approved** (status
  `draft` → `approved`; implementation authorized to begin per the SPEC-066 precedent — the
  residual items are checkable Stage-0 verification tasks, not blocking Open Questions), its
  target version pinned to v0.48.0 (the `VERSION` bump itself a separate release gate). The
  outbound user-delegated-identity substrate this memo referenced as "a SPEC-068 follow-up"
  (OQ-4) is now numbered
  **[SPEC-070](../specs/SPEC-070-outbound-user-delegated-identity/spec.md)** (`draft`); its
  OQ-1 mechanism + OQ-2 ADR-scope block its own approval and it forces **ADR-0015**
  (expected, not yet drafted). The header/§6/§7/§8 forward pointers now name it. This memo
  remains **assessment only** — commit/push, deployment, and any version bump are separate
  gates.
- 2026-10-12, SPEC-070 approved + ADR-0015 accepted: the outbound user-delegated-identity
  substrate numbered above was **approved** (status `draft` → `approved`; target **v0.49.0**).
  Its OQ-1 resolved to **(c) per-user OAuth 2.x authorization-code, connector-local**, OQ-2
  to **no identity-broker mint**, and OQ-3 was answered by research (Red Hat AAP's MCP server
  takes per-user OAuth auth-code / PATs and inherits user RBAC; no OIDC discovery /
  token-exchange / OBO in 2.6);
  **[ADR-0015](../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md)** is
  **accepted**. This does not change SPEC-069's read-only **dev** slice (it validates against
  the self-hosted server's own auth). Still **assessment only** — no implementation,
  commit/push, deployment, or version bump authorized by this memo.
