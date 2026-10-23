# Spike: Ansible Write-Tier Fast-Follow — Runbooks as Typed Tools (Layer-2 Boundary Study)

Status: assessment / boundary study — records the scope, the machinery it **reuses**,
and the **net-new** design problems for a **separate write-tier spec** (its number is
assigned at its own drafting — **not** reserved here). **No implementation, spec, spec
number, ADR, approval, deployment, commit/push, or version bump is authorized by this
memo.**
Date: 2026-10-19
Roadmap home: [R6 — External System Integration via MCP
Ingestion](../agentic-aiops-platform/delivery-roadmap.md#r6-external-system-integration-via-mcp-ingestion)
Builds on: [SPEC-069 Ansible read-tier MCP-ingestion
pilot](../specs/SPEC-069-ansible-read-tier-mcp-ingestion-pilot/spec.md) — **delivered
v0.48.0**. This memo extends the generic server-agnostic MCP-ingestion adapter, the
Ansible binding, and the `ansible-dev` in-cluster mock that SPEC-069 shipped and
live-validated; it builds no connector from scratch.
Lineage: SPEC-069 **OQ-2** (the deliberate two-layer model) and its **Non-Goals**
"Layer-2 runbook execution (runbooks as typed tools)"; and
[mcp-ingestion-spike.md](mcp-ingestion-spike.md) **§6.2** (the bundled-N-step-mutation
blast-radius / uncertain-outcome / idempotency problems) + **§5** (the connector
invariants, including "post-timeout blind retries need reconciliation or idempotency").
Depends on (production path only): [SPEC-070 outbound user-delegated
identity](../specs/SPEC-070-outbound-user-delegated-identity/spec.md) plus actual AAP
integration evidence. **Update 2026-10-23:** the operator separated SPEC-070 development
delivery/version eligibility from AAP readiness. OQ-3/R-6e remain open under
[DI-070](../specs/SPEC-070-outbound-user-delegated-identity/tasks.md#post-delivery-deployment-integration-di-070)
before production target enablement, not as development-delivery gates. The dated study
below retains its original sequencing language; references to SPEC-070 itself being blocked
by OQ-3 are superseded by this update. No write-tier approval is added.

## 1. Question and recommendation

> SPEC-069 shipped the **read** tier: six pure-read Ansible tools projected from AAP's
> `controller.*` operationIds through a generic adapter, deny-by-default, live-validated
> against an in-cluster mock. Its Non-Goals name a **Layer-2 write-tier fast-follow** that
> models "each runbook as a typed tool" behind the existing HITL machinery. What is that
> fast-follow's real scope, what does it reuse, what is net-new, and is it actually
> unblocked?

Recommendation: **draft it as a separate write-tier spec** that **promotes one runbook-launch
operation from denied to admitted at `risk_level="write"`**, reusing the delivered adapter,
the `ansible-dev` mock, and — because the park/mutate gate is **risk-tier-driven and
connector-agnostic** (§3) — the *already-shipped* HITL, signed-execution, isolated-worker,
and durable-claim machinery. The net-new work is **not** "build HITL"; it is the four
write-tier problems §6.2 flagged: the **launch→outcome contract** (a launch returns a job
id, never a verified success), the **confirmation-card payload** (what the operator
approves, with `--check` as a *plan fact* only), the **idempotency / double-launch guard**
across park/resume, and **blast-radius scoping** of the admitted op + its arguments.

**Honest caveat (§5):** a **dev/CI machinery increment** is self-provisionable (no PDI, no
Windows host, no AAP license) exactly as SPEC-069's read tier was — but the
**production user-delegated** write path **depends on SPEC-070**, because OQ-4 requires a
*mutating* action to run under the requesting user's delegated identity, never the agent's
own `acting_service` authority. The fast-follow ships the **machinery**, not the
production-governance-correct write path; it is **not** a route around the SPEC-070/OQ-3
gate.

## 2. What already exists to extend (verified in code at v0.48.0)

- **The typed-tool config seam already carries tier.** `AdmittedTool`
  (`products/tool-gateway/src/tool_gateway/ingestion/mcp_adapter.py`, L90–L107) has a
  `risk_level: str` field (L103). The read binding sets every entry to `"read"`; admitting
  a write tool is **binding configuration**, not adapter code.
- **The mutating operations are already named — as denied.** `DENIED_SERVER_TOOLS`
  (`ingestion/ansible_binding.py`, L59–L63) lists `controller.job_templates_launch_create`,
  `controller.workflow_job_templates_launch_create`, `controller.projects_update`. The core
  move is promoting one of these (job-template launch is the natural first) from *denied* →
  *admitted at write tier* with a gateway-owned `parameters_schema`.
- **The admitted-read pattern to mirror.** `ANSIBLE_ADMITTED_TOOLS` (L91–L176) shows the
  exact shape: `server_name`, canonical `name`, `description`, `risk_level`, `category`,
  `parameters_schema`, optional `argument_map`. `map_arguments` (mcp_adapter.py L156–L168)
  forwards **only** schema-declared keys, so an LLM-invented argument can never reach the
  server — the injection surface for `extra_vars` is already bounded by the schema.
- **The dev target + harness already exist.** `build_ansible_mcp_connector` (L179–L206) binds
  the adapter to operator config (endpoint, transport, timeout, credential set) and the
  `ansible-dev` overlay + in-cluster thin mock SPEC-069 live-validated against — reusable
  with **no new infrastructure**.
- **Outcome-verification reads already exist.** `ansible.get_job` (L125–L141) and
  `ansible.get_job_stdout` (L142–L164) are shipped read tools — exactly what a write-tier
  launch polls to confirm the *real* terminal outcome (§4.1).
- **The registry has a mutating-mode backstop.** mcp_adapter.py L277–L281: a non-read tier is
  refused unless mutating tools are enabled — so a write tool plugs into the existing
  `mutating-dev` runtime-profile gate rather than needing a new enablement path.

## 3. What is inherited for free by registering at `risk_level="write"`

This is the key finding that shrinks the fast-follow. The HITL park/resume and the mutate
gate are **keyed on risk tier upstream of the connector**, so a write-tier MCP tool inherits
them with **no connector HITL code**:

- **Policy action mapping.** `RISK_LEVEL_ACTIONS = {"read": "tools:invoke", "write":
  "tools:mutate", "admin": "tools:mutate"}`
  (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`, L42–L46). A
  tool whose `risk_level` is `"write"` automatically maps to `tools:mutate`.
- **Gateway mutate gate.** `gateway_service.invoke_tool` (L294–L330) additionally evaluates
  `tools:mutate` for any tool whose `definition.risk_level != "read"` (SPEC-021 R-1) and
  denies on policy — connector-agnostic.
- **Park / resume machinery.** The agent-service `GatewayPermissionMiddleware` parks a
  write-tier call as `PermissionBehavior.ASK` → `RequireUserConfirmEvent`; resume via
  `UserConfirmResultEvent` is first-class (see
  [hitl-bridging-spike.md](hitl-bridging-spike.md) §2, and the delivered SPEC-051 flow-unlock
  + SPEC-054 action-card). The MCP connector's `_invoke` just calls the server and returns a
  `ToolResult`; **the park happens above it**, so the connector needs no park logic.
- **One gate per mutating flow** (ADR-0007), **signed execution** (SPEC-037), **isolated
  worker** (SPEC-038), **durable claim** (SPEC-063), **kernel-side secret masking** — all
  ride the existing write-tier path the browser tools already use.
- **No kernel control-flow collision.** A runbook's N-step flow executes **inside**
  Ansible/AAP, so modeling it as one typed tool does not collide with ADR-0011 / SPEC-057
  ("no control flow; composition carries no authority") — SPEC-069's Non-Goal already records
  this.

**Consequence:** the fast-follow is *mostly binding config + four write-tier design contracts*,
not a new approval subsystem.

## 4. What is net-new (the actual spec content)

The inherited machinery handles *whether* a write call parks and *who* may approve it. It does
**not** handle the four things that make a **runbook launch** different from a read — these are
the spec's real requirements, and they are the §6.2 problems made concrete.

### 4.1 Launch→outcome contract (the "uncertain outcome" problem)
A read returns its answer synchronously. A runbook **launch** returns a **job id** while the
work is still running — so the tool result at call time is *"launched, job N, status=pending"*,
**never** *"succeeded"*. The spec must decide and enforce:
- the write tool returns a **launch fact** (job id + initial status), and **terminal outcome is
  verified separately** by polling the existing `ansible.get_job` / `ansible.get_job_stdout`
  reads — or an explicit launch-and-poll-until-terminal contract with a bounded timeout.
- **No-false-success / anti-fabrication** (SPEC-069 R-5, inherited): a launch that cannot be
  confirmed terminal is reported as *pending/unknown*, never as success; a job that ends in
  failure is surfaced as a failed outcome with its stdout, not masked.

### 4.2 Confirmation-card payload (what the operator approves)
The HITL card must show enough to approve meaningfully: the **runbook/job-template**, the
**target inventory**, and the **bounded `extra_vars`** — plus, optionally, a **`--check`
dry-run preview**. Per SPEC-069 **OQ-3**, dry-run is **not** a safety boundary
(`check_mode: false` bypasses it; some modules do not reflect real results until executed): the
preview is a **fact about a *plan***, never a read-tier guarantee and never an applied change,
and a module that cannot check is reported "not checkable", never silently "no change".

### 4.3 Idempotency / double-launch guard
Approval resumes a parked call; a re-park, retry, or post-timeout blind retry **must not launch
twice**. This is the §5 invariant ("post-timeout blind retries need reconciliation or
idempotency") applied to a mutation whose side effect is irreversible. The spec must bind the
launch to the **durable claim** (SPEC-063) / a single-flight key so exactly one job is created
per approved card, and reconcile a timed-out launch by **querying job state**, never by
re-firing.

### 4.4 Blast-radius scoping
§6.2: map "run playbook X" to a **scoped, pre-declared blast radius**. Concretely: which
mutating op(s) are admitted (start with `job_templates_launch`; leave workflow-launch and
project-update denied), which inventories a runbook may target, and a **bounded `extra_vars`
schema** (declared keys only, per §2). The gateway-owned schema — not the server, not the model
— is the scoping surface.

## 5. The identity split: dev `acting_service` vs production `user_delegated` (the SPEC-070 gate)

SPEC-069's binding deliberately runs at `target_identity_mode = "acting_service"`
(`ansible_binding.py` L194–L199): the dev/self-hosted server is addressed with the **acting
service's** own credential or a loopback session; Luban still records attribution to the
requesting principal, but the **target does not enforce that user's own RBAC**. The reserved
`"user_delegated"` mode is **SPEC-070's seam** and is not wired in SPEC-069.

For **reads** this is benign. For **writes** it is the crux:

- **OQ-4 governance principle** (SPEC-069): a mutating action must run under the **requesting
  user's delegated identity all the way to the target**, so the agent **never acts on its own
  authority** and every action is attributable to a human principal under that principal's own
  target RBAC. A write under `acting_service` is precisely what production governance forbids.
- SPEC-069's **Non-Goal** therefore states Layer-2 "**depends on the OQ-4 delegation substrate
  (SPEC-070)**."
- **SPEC-070 is gated on OQ-3** (real AAP/MCP deployment facts), which is **open**. So the
  production user-delegated write path carries the **same external gate** as SPEC-070 itself.

**What this means for sequencing:**
- A **dev/CI machinery increment** — typed runbook tool + inherited HITL + launch→outcome
  verification, against the in-cluster mock under `acting_service` — is **self-provisionable**
  (no PDI, no Windows host, no AAP license), exactly as SPEC-069 shipped its dev-proven read
  connector. It proves the write-tier *machinery*.
- Its **production user-delegated** form is **SPEC-070/OQ-3-gated**. The increment ships the
  machinery, **not** the production-governance-correct write path.
- **Open governance question (§6):** is a dev `acting_service` *write* acceptable even against a
  mock, given OQ-4's optics, or should the dev write-tier be explicitly flagged "machinery proof
  only — never a production posture"?

## 6. Open questions for the spec (surfaced here, decided there)

1. **Which mutating op first?** `controller.job_templates_launch_create` is the natural single
   slice; workflow-launch and project-update stay denied until a named need.
2. **Launch-and-return vs launch-and-poll?** Recommend: return the launch fact, verify terminal
   outcome via the existing reads (§4.1) — keeps the connector thin and the kernel free of
   control flow.
3. **`extra_vars` schema + bounds** — declared keys only; what is the injection/scoping surface
   and who authors the per-runbook schema?
4. **Idempotency key source** — derived from the durable claim / approval id; reconcile a
   timed-out launch by job-state query, never re-fire (§4.3).
5. **Dev-write optics** — is an `acting_service` dev write against the mock acceptable as a
   machinery proof, and how is it flagged so it never implies a production posture? (§5)
6. **Does the connector need any write-awareness at all?** Evidence says the park/mutate gate is
   inherited (§3); the only connector/binding-side write concern is the launch→outcome contract
   (§4.1). Confirm at drafting whether that lives in the binding, the connector, or is left to
   the agent polling the read tools.

## 7. Recommendation and next decision

This memo authorizes **no** implementation. Recommended next decision:

1. **Draft a separate write-tier spec** (number at its own drafting) scoped to **§4's four
   contracts** + the **§2 binding promotion** of one runbook-launch op, explicitly **reusing**
   §3's inherited machinery and the SPEC-069 `ansible-dev` mock.
2. **Split the delivery** the way SPEC-069 did: a **dev/CI-proven machinery increment**
   (self-provisionable now) and a **production user-delegated** form **gated on SPEC-070/OQ-3**
   — recorded as a dependency, not built around.
3. **Settle §6's open questions** (esp. #2 launch→outcome and #5 dev-write optics) at drafting;
   they are design decisions, not external facts, so they do not block writing the spec.

Compared with the other R6 directions: this is the **smallest new-code surface** (it extends a
connector shipped one release ago) and needs **no new infrastructure** — clearly lighter than
Windows (a non-cluster host + an unsolved UI-verification boundary study,
[mcp-ingestion-spike.md](mcp-ingestion-spike.md) §6.3) or SPEC-067 (PDI-gated). Its one real
external dependency is the **production** identity path it shares with SPEC-070.
