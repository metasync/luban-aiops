# SPEC-067: ServiceNow ITSM MCP-Ingestion Pilot (Read Tier)

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-10-06
- release slice: **R6 — External System Integration via MCP Ingestion** (first slice;
  see the [delivery roadmap](../../agentic-aiops-platform/delivery-roadmap.md#r6-external-system-integration-via-mcp-ingestion))
- target version: **v0.49.0 — delivered 2026-10-20** (the next minor slot after
  SPEC-069's v0.48.0). SPEC-070's planning target re-slots to v0.50.0 accordingly.
  The `VERSION` file now reads `0.49.0`; the release/version bump crossed as its own
  delivery gate after the full aggregate `make verify` passed green (exit 0).
  (R5 closed at v0.45.0 and SPEC-066 shipped standalone at v0.46.0.)
- related ADRs: **none.** The transport decision (OQ-3, resolved 2026-10-07:
  official MCP SDK as conditional primary, REST/Table-API as fallback) is recorded
  here; **Stage-0 (2026-10-19) selected the REST fallback** because the target PDI
  does not expose ServiceNow's own MCP server. The transport merits **no** ADR — it is
  a connector-local REST binding reusing SPEC-068 (mirroring SPEC-068's no-ADR Option
  A). The outbound-credential acquisition-locus ADR
  trigger (Option A connector-local vs B/C centralized) now lives in
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md), where this
  spec's original R-1 was extracted; this pilot consumes that substrate and introduces
  no signing authority of its own.
- lineage: promoted from the
  [MCP ingestion spike](../../workspace/mcp-ingestion-spike.md) §2 (the
  gateway-as-client seam, ServiceNow-first staging), §5 (the credential/audience
  boundary), and §6 (the sequencing that makes the credential model the first
  slice), and from the
  [machine-consumer credential memo](../../workspace/machine-consumer-credential-model-spike.md)
  §3–§4 (the `credential_set` Basic-only gap and the outbound plane) and §6 (the
  recommendation this spec enacts). **The outbound execution-credential extension
  originally drafted as this spec's R-1 was extracted to
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) on 2026-10-08
  (OQ-2 resolved); SPEC-068 extends SPEC-049 R-5** (the `credential_set` mechanism)
  additively, and this pilot now **depends on** that substrate rather than defining it.
  Builds on
  [SPEC-007](../SPEC-007-tool-execution-framework/spec.md) (the
  `BaseTool`/`ToolRegistry` seam the ingestion connector reuses) and is the
  **opposite direction** from the parked
  [MCP-exposure spike](../../workspace/mcp-exposure-spike.md) (gateway-as-MCP-*server*,
  never promoted to a spec): ingestion reuses the platform's tool contract, never an
  exposure path.

> **Approval note (SDD discipline).** The full scaffold (`spec.md` + `plan.md` +
> `tasks.md`) was authored together per the SPEC-064/SPEC-065/SPEC-066
> same-session precedent. At drafting the spec was deliberately **not**
> decision-complete: the source memos authorized **no implementation** and handed the
> scope questions to "the first pilot spec" — i.e. to this document. **All six Open
> Questions are now resolved and the spec is `approved` (operator, 2026-10-20):**
> OQ-1 (auth scheme), OQ-4 (read-operation set), and OQ-5 (validation model) were
> resolved by operator direction on 2026-10-20; OQ-2 (substrate-vs-pilot coupling)
> was resolved 2026-10-08 by extracting the credential extension to SPEC-068; OQ-3
> (transport) was resolved 2026-10-07 and validated read-only against the operator's
> PDI 2026-10-19 (the REST/Table-API fallback is taken); OQ-6 (provisioning) moved to
> and was resolved in SPEC-068. The `plan.md`/`tasks.md` banners are lifted to
> **binding**: approval authorizes implementation to *begin*. Commit/push,
> deployment, and any `VERSION` bump remain separate authorization gates not granted
> here. None of the resolved questions reopened SPEC-068 — OQ-1 only *selects* among
> schemes SPEC-068 already ships, and OQ-4/OQ-5 scope and validate this pilot's
> live target.

## Summary

Give operators real read-only ServiceNow ITSM actions through the platform's
existing governed tool path. **Transport (Stage-0 settled 2026-10-19):** the pilot
builds a ServiceNow **REST/Table-API native connector** — OQ-3's documented
fallback, taken because read-only verification on the operator's PDI (`dev417985`)
found ServiceNow's **own** MCP server unavailable there (the AI Platform stack is
not provisioned; no MCP plugin can be activated). The connector mirrors the shipped
`ansible_native.py` fallback, registering `servicenow.*` read tools on the same
SPEC-007 `BaseTool` seam and adding **no new dependency** (`httpx` is already
present). The MCP-SDK path (via SPEC-069's generic adapter) stays the conditional
alternative for a differently-entitled instance that does expose ServiceNow's own
MCP server. This pilot **depends on**
[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) — the
target-agnostic outbound execution-credential substrate (bearer / OAuth2
`client_credentials`) extracted from this spec's original R-1 — which lands first and
is reused by every future ingestion pilot. This is R6's first *target* slice; SPEC-068
is the enabling substrate it consumes.

## Motivation

- **The trigger is met.** The MCP-ingestion backlog row's promotion trigger
  ("operations names a concrete external target system to expose as MCP tools")
  fired on 2026-09-30 when operations named three targets — ServiceNow ITSM,
  Ansible runbooks, and Windows UI automation. ServiceNow is the first
  risk-ordered pilot (structured REST/OAuth API, read tier first, real operations
  value, no arbitrary host-code-execution risk).
- **The outbound credential gap is the real prerequisite — and is delivered by
  SPEC-068.** Today `products/tool-gateway/src/tool_gateway/tools/credential_sets.py`
  enforces `REQUIRED_FIELDS = ("username", "password")` and `http_connector._resolve_auth`
  returns only `httpx.BasicAuth`; there is no bearer or OAuth2 token acquisition
  anywhere in `products/`. A real ServiceNow (or any modern SaaS) surface will not
  authenticate with Basic, so the pilot cannot proceed without extending the credential
  vocabulary. That extension was extracted to
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (the *External
  Execution Identity* plane of the
  [identity model](../../agentic-aiops-platform/identity-and-authorization-design.md)
  §Service Identity Model — **not** the parked inbound machine-consumer grant), so this
  pilot consumes it as a dependency.
- **Why this release slice is the right time.** R5 closed at v0.45.0; SPEC-066
  shipped standalone at v0.46.0. R6 is the next theme the trigger-gated backlog
  promotes. The credential substrate (SPEC-068) was split out precisely because it is
  unblocked, well-understood, and prerequisite to all three named pilots — it can be
  approved and shipped while this ServiceNow pilot waits on its PDI-gated Stage-0.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria. R-1 is a dependency pointer to SPEC-068 (decision-ready there);
R-2–R-6 are provisional on the Open Questions and are written to be finalized at
approval.

### R-1: Outbound execution credential (delivered by SPEC-068)

The credential-scheme extension this pilot needs — an optional per-set `scheme`
(`basic` | `bearer` | `oauth2_client_credentials`) plus a connector-local OAuth2 token
client behind a reusable auth-resolution seam — was **extracted to
[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md)** on 2026-10-08
(OQ-2 resolved) so the target-agnostic substrate can be approved and shipped
independent of this pilot's PDI-gated Stage-0. SPEC-067 no longer defines that
capability; it **consumes** it.

Acceptance criteria:

- SPEC-068 is delivered (or at least approved and built) before this pilot's connector
  authenticates a live target: the ServiceNow MCP/REST session resolves its credential
  through SPEC-068's resolver seam, never a pilot-local re-implementation.
- OQ-1 (ServiceNow's actual scheme) selects **among** the schemes SPEC-068 already
  ships (`bearer` or `oauth2_client_credentials`). If Stage-0 finds ServiceNow requires
  a scheme SPEC-068 does not yet build (e.g. mTLS-only), that reopens SPEC-068's scope
  in a follow-up rather than being special-cased here.
- SPEC-068's secret-handling invariants (redaction, fail-closed, no secret in
  audit/logs) apply to this pilot's calls by inheritance; R-4 asserts them for the
  ServiceNow path specifically.

### R-2: ServiceNow read-tier ingestion connector beneath the gateway

Add a ServiceNow ingestion connector owned by tool-gateway that registers read-tier
tools into the same registry as native tools, reusing the SPEC-007
`BaseTool`/`ToolDefinition`/`ToolRegistry` seam. **Transport (Stage-0 settled
2026-10-19 — OQ-3 fallback taken):** a hand-rolled **REST/Table-API native
connector** (`servicenow_native.py`), mirroring the shipped `ansible_native.py`
fallback — read-only verification on the operator's PDI (`dev417985`) found
ServiceNow's **own** MCP server unavailable there, so the MCP-SDK path is not
exercisable on this target. Every governance decision (classification, policy,
redaction, audit) stays tool-gateway-side. The REST connector uses `httpx` (already
a tool-gateway dependency) and adds **no new dependency**; the agent-platform kernel
never becomes an MCP client. *(OQ-3 resolved 2026-10-07 with the MCP SDK as the
conditional primary and REST as the fallback; Stage-0 selected the fallback on
2026-10-19. Scope still provisional on OQ-4.)*

Acceptance criteria:

- ServiceNow read tools register in the gateway registry and are callable by the
  kernel through the existing signed-tool path (SPEC-037) with no new kernel seam.
- Each call carries the requester identity and the acting service identity to the
  target, per the identity model's three-plane logging.
- No write/mutating ServiceNow operation is exposed in this slice (read tier only).
- The connector talks to ServiceNow's REST **Table API** (`/api/now/table/...`) via
  `httpx`, following the `ansible_native.py` / skills-incidents connector pattern;
  the tool set is **statically declared** by the operator (as `ansible_binding.py`
  declares its admitted tools), never auto-discovered from the target. The MCP-SDK
  path (SPEC-069's generic adapter) remains the documented alternative for a
  differently-entitled instance that exposes ServiceNow's own MCP server; if it is
  ever taken, server-advertised metadata stays untrusted (R-3).
- The REST session authenticates using the R-1/SPEC-068 credential scheme (the
  scheme OQ-1 pins — bearer / OAuth2 `client_credentials` / basic); no credential or
  token crosses the connector into a tool result or log.

### R-3: Deny-by-default policy coverage for ServiceNow tools

ServiceNow tools are deny-by-default at the **gateway admission allowlist**, and each
admitted tool resolves to read tier. The policy bundle is **action-based** (role ×
action), not a per-tool-name allowlist, so R-3 requires **no bundle change**: read-tier
tools ride the existing `tools:invoke` grant exactly as the `k8s.*`/`http.*`/`ansible.*`
read tools already do (the SPEC-069 R-3 faithful reinterpretation).

Acceptance criteria:

- An unlisted ServiceNow tool is denied: it is never registered (the allowlist is
  connector config — `SERVICENOW_ADMITTED_TOOLS` — not a bundle entry), so invoking it
  returns `TOOL_NOT_FOUND` — deny-by-default preserved without naming any tool in the
  bundle. The deferred `problem`/`attachment` capabilities and any write/mutation name
  are structurally absent from the allowlist.
- **The admitted tool set is operator-declared, never target-derived.** Under the
  REST path the connector registers only the six statically declared `servicenow.*`
  tools (as `servicenow_binding.py` declares them); there is no auto-discovery from the
  target. If the MCP-SDK alternative is ever taken, **server-advertised metadata is
  untrusted input** — a server-declared annotation, `readOnlyHint`, or description never
  sets a tool's tier or grants approval (the MCP-exposure spike's "remote annotations
  never auto-approve" invariant, applied to ingestion).
- Each admitted tool resolves to **read tier** (`risk_level="read"`), which the gateway
  maps to `tools:invoke` alone, never `tools:mutate`; no admitted tool resolves to write
  or admin tier. With no bundle edit, `make sync-policy` is not invoked and
  `make validate-policy-scenarios`, `make validate-policy`, and `make policy-diff` stay
  green **unchanged** (no drift, bundle byte-identical); the read-tier-only and
  deny-by-default invariants are asserted by the gateway tool tests
  (`test_servicenow_native.py`) instead of a per-tool-name scenario.

### R-4: Audit fidelity for external ingestion

Every ServiceNow tool call records the requester identity, the acting service
identity, the target system, the tool name, and the result outcome; secrets never
appear in audit.

Acceptance criteria:

- An audit event for a ServiceNow read carries requester + acting-service identity
  + target + tool + outcome, keeping the requester and acting-service identities
  separate per ADR-0004's `sub`-user / `act`-service delegation and the identity
  model's separate-identity logging.
- No credential secret, token, or `client_secret` appears in any audit record or
  log line (asserted alongside R-1's redaction tests).

### R-5: Fail-closed and no-fabrication guardrail

A target that is unreachable, times out, or returns an error is surfaced as a
failed outcome and never presented as a successful result.

Acceptance criteria:

- A simulated ServiceNow outage/timeout yields a failed tool outcome with a
  reason, not a fabricated or empty "success" (mirrors SPEC-058's `http.get` rule
  that "an upstream 4xx/5xx is a fact, not a tool error", and the MCP-exposure
  spike §5's fail-closed-no-fabrication posture).
- The failure is attributed in audit as a target-unavailable outcome, distinct from
  a policy denial.

### R-6: Secret provisioning and overlay wiring

The new credential fields are provisioned through the established `sync-*.sh`
model and wired into the dev-k8s overlay; nothing is edited in place.

Acceptance criteria:

- New fields (`token_url`, `client_id`, `client_secret`, `scheme`) are delivered by
  a sync script and never hand-edited in a consumer copy.
- The dev-k8s overlay wires the ServiceNow credential set; `make overlays` renders
  green.
- `make validate-secret-vocabulary` stays green (a new canonical field set is added
  if OQ-6 requires it).

## Non-Goals

- **Write-tier ServiceNow operations** (mutations). These stay behind the existing
  HITL one-gate-per-flow (ADR-0007) and signed-execution (SPEC-037) path and belong
  to a later slice, not this read-tier pilot.
- **Ansible and Windows pilots.** Each is a separate spec (the backlog row names "one
  connector spec per pilot"). The read-tier **Ansible** pilot is now drafted as
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) and — because
  this ServiceNow pilot is PDI-blocked — is **re-sequenced ahead of it for
  implementation** (2026-10-11): SPEC-069 builds the **generic** ingestion adapter this
  spec's R-2 assumed it would build first, so R-2 later reduces to a ServiceNow-specific
  binding of an already-proven adapter. This is a sequencing change, not a supersession.
  Windows remains a later spec needing its own boundary study.
- **The inbound machine-consumer `client_credentials` grant / stable-API
  productization.** That is the parked, trust-model-blocked row (no human
  owner/approver); it needs a machine-*subject* token identity-broker cannot mint.
  This spec is the outbound plane and does not touch it. See the credential memo §5.
- **Gateway-as-MCP-server exposure.** That is the parked
  [MCP-exposure spike](../../workspace/mcp-exposure-spike.md) (never promoted to a
  spec), the opposite direction; this spec reuses the platform's tool contract,
  never an exposure path.
- **Outbound credential acquisition locus.** Centralizing token acquisition
  (identity-broker or K8s workload identity) is out of scope for the substrate this
  pilot consumes — see
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md)'s Non-Goals
  (Option A connector-local is the default; B/C would require their own ADR).
- **Hand-rolling the MCP protocol, or adopting a third-party ServiceNow MCP
  *server*.** If the MCP-SDK path is ever taken (OQ-3's conditional primary), it uses
  the official `mcp` Python SDK — the protocol is never re-implemented here — against
  ServiceNow's **own** MCP server, not a community/marketplace one (supply-chain +
  license risk, an extra stateful deployment, and it would re-expose our credential to
  a component we do not control). Stage-0 (2026-10-19) took the REST/Table-API
  fallback instead, so this pilot exercises no MCP protocol at all.

## Impact

- products touched: `products/tool-gateway` (a new ServiceNow **REST/Table-API native
  connector** registering `servicenow.*` read tools on the SPEC-007 seam, mirroring
  `ansible_native.py`). **No new dependency** — the connector uses `httpx` (already
  present), and `mcp>=2.3` is already a direct tool-gateway dependency from SPEC-069
  (unused by the REST path; the kernel's separate lockfile is untouched either way);
  `shared/platform-ops/gitops` (the `servicenow-dev` runtime-profile overlay + the
  dev-k8s ServiceNow credential-set entry). **No `shared/shared-contracts/policies`
  change** — the bundle is action-based (role × action), so read-tier `servicenow.*`
  tools ride the existing `tools:invoke` grant and deny-by-default lives at the
  connector admission allowlist (`SERVICENOW_ADMITTED_TOOLS`), not the bundle (R-3).
  The outbound-credential code (`credential_sets.py`, `http_connector.py`,
  `oauth_client.py`) is delivered by **SPEC-068**, on which this pilot depends.
- contracts touched: **none in the policy bundle** (it is action-based; it names no
  per-tool entry — R-3). The credential-file shape and any secret-vocabulary work
  belong to SPEC-068.
- identity / policy / audit / execution safety impact: **consumes** SPEC-068's outbound
  execution credential (the External Execution Identity's first concrete form); audit
  gains external-target attribution; read-tier only, so no new HITL surface;
  fail-closed and no-fabrication preserved.
- living state docs to update on delivery: `products/tool-gateway/README.md` (tool
  surface + the credential scheme), `docs/agentic-aiops-platform/architecture.md`
  (tool-gateway section), the delivery-roadmap R6 status, and
  `identity-and-authorization-design.md` §Service Identity Model (record the
  outbound credential landing as the External Execution Identity's first concrete
  credential form).

## Open Questions

**All Open Questions are resolved; the spec is `approved` (2026-10-20).** OQ-2 and
OQ-3 were resolved earlier and OQ-6 moved to SPEC-068; OQ-1, OQ-4, and OQ-5 — the
three PDI-gated live-target facts — were resolved by operator direction 2026-10-20
(each below). None of them ever blocked SPEC-068.

- **OQ-1 (fact, PDI-gated) — RESOLVED 2026-10-20 (operator direction):** ServiceNow's
  auth scheme for the **REST Table API** (Stage-0 2026-10-19 confirmed the target PDI
  exposes REST only — no MCP server) is **OAuth2 `client_credentials`**, against a
  **dedicated least-privilege read-only integration service account** (never `admin`).
  **Basic** is an acceptable dev bootstrap but not the production posture; **mTLS is
  out** (it would reopen SPEC-068's scope). All are schemes SPEC-068 already ships, so
  this *selects among* them with **no substrate change**; `client_credentials`
  exercises SPEC-068's token client (in-memory cache + near-expiry refresh + redaction).
- **OQ-2 (architectural fork) — RESOLVED 2026-10-08 (operator decision).** Extract
  the credential-scheme extension into a standalone target-agnostic substrate spec —
  **[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md)** — so the
  reusable capability is not bound to this pilot's PDI-gated fate (the SPEC-007
  tool-framework precedent: land the reusable seam first). R-1 above is now a
  dependency pointer, and SPEC-068 can be approved and shipped during the ServiceNow
  waitlist.
- **OQ-3 (dependency) — RESOLVED 2026-10-07 (operator decision).** Adopt the
  official `mcp` Python SDK as the ingestion transport against **ServiceNow's own**
  MCP server, behind a gateway-owned governance adapter; add `mcp` as a direct
  dependency of tool-gateway only; keep a hand-rolled REST/Table-API connector as
  the fallback. Never hand-roll the protocol and never adopt a third-party
  ServiceNow MCP server. Governance stays tool-gateway-side regardless of transport.
  Stage-0 (OQ-1/OQ-4/OQ-5) still gates feasibility: if the target instance's MCP
  server is not GA/enabled or lacks the needed read coverage, the REST fallback is
  taken. This reverses the drafting-time lean in the exposure spike's "don't take
  the dependency until it earns its keep" posture — overridden because ServiceNow now
  ships an official MCP server and an official maintained SDK exists.
  - **Stage-0 update 2026-10-19 (fallback taken).** Read-only verification on the
    operator's PDI (`dev417985`, an **Australia**-build instance) found ServiceNow's
    **own MCP server UNAVAILABLE** — a provisioning/entitlement gap, not a release
    gap: AI Agent Studio / AI Platform / AI Control Tower are absent (page-not-found
    routes, 0 modules), **no `sys_plugins` entry named MCP/AI-Platform/GenAI is even
    available to activate**, there is no MCP Server Console route or registration
    table, and the Now Assist Admin console shows "Requires plugin install" on every
    capability (`Now Assist Core` is active but `sys_gen_ai_skill` is empty). The
    fallback condition this OQ specified is therefore **TRIPPED**: the
    **REST/Table-API native connector** is the taken transport for this pilot, and
    R-2 is re-scoped accordingly. The MCP-SDK path remains the conditional primary
    for a differently-entitled instance that does expose ServiceNow's own MCP server.
    Building **our own** MCP server around the REST API was considered and
    **rejected** — for a single internal consumer it adds a stateful hop + a
    credential boundary and re-wraps the same `BaseTool` seam a direct REST connector
    already registers (the `mcp-exposure-spike.md` "retain native connectors; own a
    server only on a documented adoption gap" posture; none of its triggers apply).
- **OQ-4 (scope) — RESOLVED 2026-10-20 (operator direction):** six read-tier tools,
  all at read tier (`risk_level="read"` → `tools:invoke`), deny-by-default, each name
  explicitly allowlisted at the gateway admission connector (`SERVICENOW_ADMITTED_TOOLS`;
  the action-based bundle names no tool — see R-3), each with a bounded argument schema
  (fixed
  table, allowlisted field projection, capped `sysparm_limit`, `sys_id` format
  validation): `servicenow.incident.list`, `servicenow.incident.get`,
  `servicenow.change_request.list`, `servicenow.change_request.get`,
  `servicenow.user.get` (`sys_user`), and `servicenow.cmdb_ci.get` (`cmdb_ci`).
  `change_request` is **in scope** (operator amendment 2026-10-20 — not deferred).
  **Deferred** to a fast-follow: **attachments** (`/attachment/{sys_id}/file` returns
  arbitrary binary — an exfil/payload/redaction surface) and **`problem`** (broader
  ITSM); neither is needed for the incident/change-triage use case.
- **OQ-5 (fact, go/no-go) — RESOLVED 2026-10-20 (operator direction):** validate
  against a **local mock Table-API responder in dev-k8s** (the SPEC-069 `ansible-dev`
  pattern, so CI makes no live external call), with **live-PDI validation as a gated,
  separately-authorized operator check script** (a `servicenow-check.sh`-style leg),
  never a CI dependency. This promotes the plan's Test-Strategy fallback to the
  decision; the mock also lets the fail-closed / no-fabrication guardrail be tested
  deterministically (simulated 4xx/5xx/timeout → a failed outcome, never a fabricated
  success), which a live PDI cannot produce on demand. The MCP-ingestion spike §2
  go/no-go is thereby satisfied without hard-wiring the entitlement-fragile PDI into
  the test path.
- **OQ-6 (provisioning) — MOVED to SPEC-068 (resolved there 2026-10-08).** The
  credential-field provisioning question travels with the extracted substrate: SPEC-068
  R-5 confirms the new fields ride the existing file-mounted `credential-sets.json` +
  `sync-browser-credentials.sh` model, and R-4 confirms `make validate-secret-vocabulary`
  needs **no** new canonical field set (the validator pins redaction vocabularies, not
  credential field names).

## Changelog

- 2026-10-20: **delivered as v0.49.0.** R-2–R-6 implemented on the OQ-3
  REST/Table-API fallback (Stage-0 2026-10-19 found the PDI exposes no ServiceNow
  MCP server). R-2: the `servicenow_native` connector + `servicenow_binding` (six
  read-tier tools, gateway-owned field projection that strips secret columns,
  `sys_id`/`limit` validation before transport, OAuth2 `client_credentials` via
  SPEC-068's resolver seam). R-3: deny-by-default at the connector admission
  allowlist `SERVICENOW_ADMITTED_TOOLS` — a documented faithful reinterpretation
  (the action-based bundle names zero tools), **no bundle edit**. R-4/R-5: the
  opt-in `audit_attribution` hook (`source_system="servicenow"`,
  `target_identity_mode="acting_service"`) + fail-closed mapping
  (`SERVICENOW_TIMEOUT`/`_UNREACHABLE` → `failure_class="target_unavailable"`; an
  upstream 4xx/5xx stays a plain fact, distinct from a policy denial). R-6: the
  `servicenow-dev` resource-bearing overlay + mock Table-API/`oauth_token.do`
  responder + two-sink `sync-servicenow-credentials.sh` + gated
  `e2e/servicenow-check.sh`. **No new dependency** (`httpx` present; `mcp>=2.3`
  unused by the REST path). `tests/test_servicenow_native.py` (40 tests) and the
  full tool-gateway suite (592) green; the full aggregate `make verify` passed
  (exit 0). Status `approved` → `delivered`; `VERSION` bumped 0.48.0 → 0.49.0 in
  lockstep; spec index + delivery-roadmap R6 flipped to delivered.
- 2026-10-20: **approved** (operator). OQ-1, OQ-4, and OQ-5 resolved by operator
  direction — OQ-1 = OAuth2 `client_credentials` against a dedicated least-privilege
  read-only service account (Basic a dev bootstrap; mTLS out, it would reopen SPEC-068);
  OQ-4 = six read-tier tools (`servicenow.incident.list/.get`,
  `servicenow.change_request.list/.get`, `servicenow.user.get`,
  `servicenow.cmdb_ci.get`) — `change_request` kept **in scope** by operator amendment,
  attachments + `problem` deferred; OQ-5 = a local mock Table-API responder in dev-k8s +
  a gated live-PDI operator check, never a CI dependency. Target version pinned
  **v0.49.0** (SPEC-070's planning target re-slots to v0.50.0). The transport merits
  **no** ADR (a connector-local REST binding reusing SPEC-068, mirroring its no-ADR
  Option A). `plan.md`/`tasks.md` provisional banners lifted; status `draft` →
  `approved`. Per the SPEC-066/069 precedent, approval **authorizes implementation to
  begin**; commit/push, deployment, and any version bump remain separate boundaries
  **not** granted here.
- 2026-10-19: **Stage-0 transport verification — OQ-3 REST fallback taken; R-2
  re-scoped to a `servicenow_native` REST connector.** Read-only verification on the
  operator's PDI (`dev417985`, Australia build) found ServiceNow's **own MCP server
  unavailable** (AI Platform / AI Agent Studio / AI Control Tower not provisioned; no
  MCP-named plugin even available to activate; Now Assist Admin shows "Requires
  plugin install"). This trips the fallback condition OQ-3 (resolved 2026-10-07)
  specified, so the **REST/Table-API native connector** — mirroring the shipped
  `ansible_native.py` — is the taken transport. Amended the Summary, R-2, R-3, the
  Impact dependency note (`mcp` is already a direct dep from SPEC-069; the REST path
  adds **no** new dependency), the target-version note (R6's first slice, SPEC-069,
  shipped at v0.48.0), and OQ-1 (now REST-only) accordingly, and recorded "build our
  own MCP server around the REST API" as **considered and rejected** (a stateful hop
  + credential boundary that re-wraps the same `BaseTool` seam, for one internal
  consumer). **OQ-1, OQ-4, OQ-5 remain open** (PDI-gated facts), so the spec stays
  `draft`; no implementation, approval, commit/push, or version bump is authorized.
- 2026-10-11: **Cross-reference — re-sequenced behind
  [SPEC-069](../SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) for
  implementation.** Because this pilot's three remaining Open Questions (OQ-1, OQ-4,
  OQ-5) are all PDI-gated on a real ServiceNow tenant, the
  [MCP-ingestion re-sequencing memo](../../workspace/mcp-ingestion-resequencing-spike.md)
  (2026-10-11) re-orders the R6 pilots so a read-tier **Ansible** pilot (SPEC-069) is
  implemented **first**. SPEC-069 builds the **generic** MCP-ingestion adapter this
  spec's R-2 consumes, so on delivery R-2 reduces to a ServiceNow-specific binding of an
  already-proven adapter. This is a **sequencing** change, **not** a supersession:
  SPEC-067 stays `draft` with its OQs intact and returns to active sequencing when its
  PDI unblocks. Non-Goals updated to point at SPEC-069. No implementation authorized.
- 2026-10-08: **OQ-2 resolved by operator decision — extract the credential
  substrate.** The outbound execution-credential extension originally drafted as R-1
  was extracted to a standalone target-agnostic spec,
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md), so it can be
  approved and shipped independent of this pilot's PDI-gated Stage-0. R-1 became a
  dependency pointer; OQ-6 (provisioning) moved to and was resolved in SPEC-068; the
  title, Status (ADRs + lineage), approval note, Summary, Motivation, Non-Goals,
  Impact, and the Open Questions were updated accordingly. Three Open Questions remain
  (OQ-1, OQ-4, OQ-5), all PDI-gated. Spec remains `draft`. No implementation.
- 2026-10-07: **OQ-3 resolved by operator decision** — adopt the official `mcp`
  Python SDK as the ingestion transport against ServiceNow's own MCP server, behind
  a gateway-owned governance adapter (dependency added to tool-gateway only), with a
  hand-rolled REST/Table-API fallback; never hand-roll the protocol, never adopt a
  third-party ServiceNow MCP server. Amended R-2 (transport + fallback + credential
  wiring), R-3 (untrusted server metadata never auto-registers or sets tier), the
  Non-Goals, Impact, Summary, the approval note, and the Open Questions preamble
  accordingly. Spec remains `draft` — five Open Questions still block `approved`. No
  implementation.
- 2026-10-06: created as `draft`; full scaffold (`spec.md` + `plan.md` +
  `tasks.md`) authored together per the SPEC-064/065/066 precedent, with
  `plan.md`/`tasks.md` banner-marked provisional because six Open Questions block
  `approved` and the source memos authorize no implementation.
