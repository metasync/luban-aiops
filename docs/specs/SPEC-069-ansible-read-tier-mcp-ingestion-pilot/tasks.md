# SPEC-069 Tasks: Ansible Read-Tier MCP-Ingestion Pilot

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Approved — implementation authorized to begin.** SPEC-069 is `approved` (operator,
> 2026-10-12). The **five Open Questions were resolved by operator direction on 2026-10-11**
> (OQ-1 self-hosted open-source server behind a server-agnostic connector; OQ-2 two-layer
> model — this spec is the read-only discovery layer; OQ-3 `--check` removed from the read
> tier; OQ-4 user-delegated identity to the targets, mechanism extracted to
> [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); OQ-5 self-contained
> in-cluster validation). What remains is **Stage-0 verification facts** (exact server
> artifact + license/provenance, the concrete read-operation set + argument shapes, what
> AAP's MCP server auth accepts) and **one production-path dependency**
> ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md), itself `draft`), so
> R-2–R-6 below stay provisional on the Stage-0 facts and firm up as Stage 0 closes. R-1 is
> not built here — it is a dependency on the delivered
> [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (v0.47.0) for dev and
> on [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) for the production
> user-delegated path. Approval authorizes implementation to begin; commit/push, deployment,
> and any version bump remain separate authorization boundaries **not** granted here. **Stage
> 0 is read-only and is the first thing to execute now that the spec is approved** — the OQ-1
> server-artifact choice determines whether R-2 builds the MCP adapter or the native
> fallback, so no target-specific implementation should start before Stage 0 closes.

## Stage 0 — Verify (read-only; pins the residual OQ facts; confirms the SPEC-068 dependency and the topology)

- [ ] Pin the exact **self-hosted** Ansible MCP-server artifact (AWX + community AWX MCP
      server, or a thin mock MCP server) and run the supply-chain/license/provenance review
      (OQ-1 residual) — record the chosen dev transport against R-2/R-6. If no self-hosted MCP
      server passes review, record the native-fallback decision and that the MCP substrate was
      **not** proven on this target.
- [ ] Fix the **read-only discovery** operation set + each tool's argument-validation shape
      (OQ-2 residual) — record against R-2/R-3: inventory host/group listing, `gather_facts`/
      setup reads, job-template listing, job log/status monitoring, environment health.
      **Confirm no `--check`/dry-run operation is admitted** (OQ-3 resolved).
- [ ] Confirm what auth **AAP's MCP server** accepts for the delegated path (OQ-1/OQ-4
      residual) — record against R-1/R-4 as the input
      **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** will consume; note
      that the production user-delegated path depends on that substrate (not built here) and
      that AAP's MCP server natively inherits user RBAC.
- [ ] Confirm the **self-contained** validation topology (OQ-5 resolved) — the self-hosted
      Ansible MCP server + a **mock managed host** deploy in-cluster (the SPEC-068 live-check
      pattern) so CI makes no live external call; record the topology (loopback sidecar vs
      in-cluster Service) against R-1/R-6. AAP read-only-mode validation is a documented
      operator step **outside CI**.
- [ ] Confirm SPEC-068 (the delivered dev credential substrate, v0.47.0) is present and that
      OQ-5's topology either needs no credential (loopback) or a scheme SPEC-068 ships
      (`bearer`).
- [ ] Pin the official `mcp` Python SDK version and run the supply-chain/license review
      before adding it as a direct tool-gateway dependency (inherited from SPEC-067 OQ-3).

## R-1: Outbound identity, credential, and topology (dependency on SPEC-068 + SPEC-070 — not built here)

The dev credential-scheme extension is delivered by
[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (v0.47.0); its
parsing, token client, resolver seam, redaction, fail-closed, and provisioning tasks live
in SPEC-068's `tasks.md`. The **production** outbound user-delegated credential is
**[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** (separate spec) and is
**not** built here.

- [ ] Gate: SPEC-068 is delivered (it is — v0.47.0); the Ansible connector resolves any
      **dev** credential through SPEC-068's resolver seam (no pilot-local re-implementation),
      or uses a loopback sidecar with no outbound credential per the Stage-0 topology.
- [ ] Record the **production user-delegated identity** as a dependency on
      [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) (OQ-4); confirm the
      read-only discovery slice is **not blocked** on it (dev runs against the self-hosted
      server's own auth).

## R-2: Server-agnostic MCP-ingestion connector + Ansible read-only binding (the generic adapter)

- [ ] Add the official `mcp` SDK as a direct tool-gateway dependency
      (`products/tool-gateway/pyproject.toml` + `uv.lock`; kernel lockfile untouched).
- [ ] Add the **generic, server-agnostic** MCP ingestion adapter that consumes an MCP server
      and maps discovered tools into the SPEC-007 `BaseTool`/`ToolDefinition`/`ToolRegistry`
      seam as **typed tools**, admitting only policy-named tools and treating server metadata
      as untrusted (`products/tool-gateway/src/tool_gateway/`). Tool admission + tier mapping
      are **configuration**, not adapter code — so the same adapter binds a self-hosted
      AWX/mock server (dev), AAP read-only mode (production), a future ServiceNow binding
      (SPEC-067), and the Layer-2 runbook-tool binding.
- [ ] Add the Ansible **read-only** target binding (endpoint, admitted read tool names, tier
      mapping); authenticate the MCP session via the R-1 dev credential scheme or loopback;
      implement the native read-only fallback connector (`ansible-inventory` shell-out, **no
      `--check`**) for the OQ-1 fallback path.
- [ ] Wire calls through the existing signed-tool path (SPEC-037); confirm no new kernel
      seam and the kernel is never an MCP client.
- [ ] Tests: tools register as typed tools and are callable; **read-tier-only** (no
      playbook-run/runbook-execution/mutating operation exposed, **no `--check`/dry-run tool
      admitted**); **server-agnostic** (the same adapter maps a self-hosted server's tools and
      an AAP read-only config without adapter-code change); server-advertised metadata never
      sets tier/auto-approves; requester + acting-service identity carried; the adapter
      resolves any dev credential through SPEC-068's resolver
      (`products/tool-gateway/tests/`).

## R-3: Deny-by-default policy coverage for Ansible tools

- [ ] Name each admitted Ansible read tool at **read tier** in the canonical bundle
      (`shared/shared-contracts/policies/`); sync via `make sync-policy`. Assert no
      write/admin, playbook-run, or runbook-execution Ansible name exists.
- [ ] Add policy scenario coverage; keep `make validate-policy-scenarios`,
      `make validate-policy`, and `make policy-diff` green.

## R-4: Audit fidelity and user-delegated attribution

- [ ] Emit requester + acting-service identity + target system + tool name + outcome per
      Ansible call (`products/tool-gateway/`), keeping requester and acting-service separate
      per ADR-0004 `sub`/`act`.
- [ ] Record the **dev-vs-production per-user-RBAC distinction** (OQ-4): production
      attributes each call to the requesting user end to end (via the R-1 dependency
      [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); AAP inherits user
      RBAC); dev records Luban-side attribution to the principal
      while the target-side identity is the self-hosted server's own — the audit record makes
      this explicit rather than implying target-side per-user RBAC the dev topology lacks.
- [ ] Tests: audit record carries all five fields + the delegation distinction; no
      secret/token/`client_secret` appears in audit or logs
      (`products/tool-gateway/tests/`).

## R-5: Fail-closed and no-fabrication guardrail (dry-run is never read-tier)

- [ ] Map transport/timeout/HTTP-error to a failed outcome with a reason + a
      target-unavailable audit attribution; never an empty "success"
      (`products/tool-gateway/`).
- [ ] Assert **no read-tier tool invokes `--check`/dry-run** and the admitted read set
      contains no operation whose safety depends on check mode (OQ-3); document that any
      dry-run preview is a **Layer-2 action-tier** concern (a fact about a plan), never a
      read-tier guarantee.
- [ ] Tests: simulated outage/timeout yields a failed outcome, not a fabricated result; the
      admitted read-tool set contains no dry-run/`--check` operation
      (`products/tool-gateway/tests/`).

## R-6: Target provisioning and overlay wiring

- [ ] Deploy the **self-hosted** Ansible MCP server (or native fallback) + a mock managed
      host to the dev-k8s namespace through the overlay (reusing the SPEC-068 live-check
      ephemeral-mock pattern); keep `make overlays` green
      (`shared/platform-ops/gitops/dev-k8s/`).
- [ ] Deliver any credential fields the topology needs through the `sync-*.sh` model — never
      hand-edited in a consumer copy; keep `make validate-secret-vocabulary` green
      (`shared/platform-ops/`).
- [ ] Ensure inventory source, endpoint, admitted-tool list, and executable path are operator
      configuration in the overlay (never model-selected); CI makes no live external call.
- [ ] Add a gated live-check script (mirroring `shared/platform-ops/e2e/http-check-demo.sh`)
      proving the end-to-end inventory/facts read against the deployed gateway, with the
      fail-closed negative control and redaction assertions. Document **AAP read-only-mode
      validation** as an operator step run outside CI (no licensed instance in CI).

## Delivery Gate

- [ ] Stage 0 residual facts recorded; all five Open Questions show their 2026-10-11 operator
      resolutions in `spec.md`.
- [ ] SPEC-068 (the dev outbound credential substrate, delivered v0.47.0) confirmed present;
      the connector resolves any dev credential through its resolver seam. The production
      user-delegated path's dependency on
      [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) is recorded (and does
      not block this read-only slice).
- [ ] All acceptance criteria in `spec.md` verified; `make verify` green (incl.
      `portal-test`, `validate-policy-scenarios`, `validate-secret-vocabulary`,
      `overlays`).
- [ ] `products/tool-gateway/uv.lock` regenerated with the direct `mcp` dependency (kernel
      lockfile untouched); dependency + MCP-server-artifact license/provenance review
      recorded.
- [ ] Living state docs updated (see spec `Impact`): `products/tool-gateway/README.md`,
      `docs/agentic-aiops-platform/architecture.md`, delivery-roadmap R6 status,
      `identity-and-authorization-design.md` §Service Identity Model (record the outbound
      user-delegated-identity target).
- [ ] `CHANGELOG.md` entry added referencing SPEC-069; `VERSION` bumped in lockstep
      (separate authorization).
- [ ] Spec index in `docs/specs/README.md` updated; spec status set to `delivered`. Note in
      the delivery record that SPEC-067 (ServiceNow) remains `draft`/PDI-gated and reuses
      this pilot's generic adapter — re-sequenced, not superseded — and that the **Layer-2
      runbook-typed-tool fast-follow** (number assigned at its own drafting) and the
      **outbound user-delegated-identity substrate**
      ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md), itself `draft`) are
      separate specs building on this adapter and on SPEC-068 respectively.
