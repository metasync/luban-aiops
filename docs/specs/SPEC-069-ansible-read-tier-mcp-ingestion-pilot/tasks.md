# SPEC-069 Tasks: Ansible Read-Tier MCP-Ingestion Pilot

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Approved — implementation authorized to begin.** SPEC-069 is `approved` (operator,
> 2026-10-12). The **five Open Questions were resolved by operator direction on 2026-10-11**
> (OQ-1 self-hosted open-source server behind a server-agnostic connector; OQ-2 two-layer
> model — this spec is the read-only discovery layer; OQ-3 `--check` removed from the read
> tier; OQ-4 user-delegated identity to the targets, mechanism extracted to
> [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); OQ-5 self-contained
> in-cluster validation). **Stage 0 closed 2026-10-13** — all six verify items are resolved
> and recorded in the Stage-0 findings below (dev artifact = real AWX + the MIT
> `SurgeX-Labs/awx-mcp-server`; the read-operation set + per-tool argument shapes pinned;
> `mcp==2.3.0` MIT confirmed; AAP auth, the self-contained topology, and the SPEC-068
> dependency confirmed), so **R-2–R-6 are unblocked** — each tool's exact `parameters_schema`
> still finalizes at R-2. The one production-path dependency
> ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md), itself `approved`) does
> not gate this read-only dev slice. R-1 is
> not built here — it is a dependency on the delivered
> [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (v0.47.0) for dev and
> on [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md) for the production
> user-delegated path. Approval authorizes implementation to begin; commit/push, deployment,
> and any version bump remain separate authorization boundaries **not** granted here. **Stage
> 0 was read-only and was the first thing executed at approval**; its OQ-1 server-artifact
> choice resolved to the **MCP-adapter path** (real AWX + the MIT `SurgeX-Labs/awx-mcp-server`),
> **not** the native `ansible-inventory` fallback, so R-2 target-specific implementation is
> now unblocked.
>
> **R-6 supply-chain correction (2026-10-17).** The Stage-0 dev-artifact pick
> `SurgeX-Labs/awx-mcp-server` was **dropped** at the R-6 review (stdio-only MCP, no declared
> license, `mcp>=1.0.0` vs the gateway's `mcp==2.3.0`). Corrected landscape: **production** =
> Red Hat's Apache-2.0 `ansible/aap-mcp-server` (`controller.*` read operationIds); **CI** = an
> in-cluster **thin mock** mirroring that surface + a mock managed host (SPEC-068 ephemeral-mock
> pattern; no live external call, OQ-5); **OSS alternative** = `lycorp-jp/awx-mcp` (Apache-2.0,
> native `AWX_MCP_READ_ONLY`). Real-AAP read-only validation is a documented operator step
> outside CI. See `spec.md` Changelog 2026-10-17; the dated Stage-0 findings below are kept as
> the historical record.

## Stage 0 — Verify (read-only; pins the residual OQ facts; confirms the SPEC-068 dependency and the topology)

- [x] Pin the exact **self-hosted** Ansible MCP-server artifact (AWX + community AWX MCP
      server, or a thin mock MCP server) and run the supply-chain/license/provenance review
      (OQ-1 residual) — record the chosen dev transport against R-2/R-6. If no self-hosted MCP
      server passes review, record the native-fallback decision and that the MCP substrate was
      **not** proven on this target.
      **Resolved (2026-10-13, operator pick): real AWX + the MIT `SurgeX-Labs/awx-mcp-server`,
      self-hosted in-cluster** (details + supply-chain/license/provenance review in the Stage-0
      closure findings below). A suitable MIT MCP server exists, so the native
      `ansible-inventory` fallback is **not** taken — the MCP substrate **is** proven on this
      target. R-2/R-6 cautions: the server's 3 mutating tools stay denied, and R-6 budgets for
      AWX's weight.
- [x] Fix the **read-only discovery** operation set + each tool's argument-validation shape
      (OQ-2 residual) — record against R-2/R-3: inventory host/group listing, `gather_facts`/
      setup reads, job-template listing, job log/status monitoring, environment health.
      **Confirm no `--check`/dry-run operation is admitted** (OQ-3 resolved).
      **Resolved (2026-10-13):** the minimal admitted set + per-tool `parameters_schema` shapes
      are pinned in the Stage-0 closure findings below (mapped from the chosen server's
      read-only tools); **no `--check`/dry-run and no mutating tool is admitted**. One honest
      gap: the chosen `awx-mcp-server` exposes **no host `gather_facts`/facts tool**, so live
      fact gathering is deferred to R-2 (native fallback or a later server tool) rather than
      faked (OQ-5).
- [x] Confirm what auth **AAP's MCP server** accepts for the delegated path (OQ-1/OQ-4
      residual) — record against R-1/R-4 as the input
      **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)** will consume; note
      that the production user-delegated path depends on that substrate (not built here) and
      that AAP's MCP server natively inherits user RBAC.
- [x] Confirm the **self-contained** validation topology (OQ-5 resolved) — the self-hosted
      Ansible MCP server + a **mock managed host** deploy in-cluster (the SPEC-068 live-check
      pattern) so CI makes no live external call; record the topology (loopback sidecar vs
      in-cluster Service) against R-1/R-6. AAP read-only-mode validation is a documented
      operator step **outside CI**.
- [x] Confirm SPEC-068 (the delivered dev credential substrate, v0.47.0) is present and that
      OQ-5's topology either needs no credential (loopback) or a scheme SPEC-068 ships
      (`bearer`).
- [x] Pin the official `mcp` Python SDK version and run the supply-chain/license review
      before adding it as a direct tool-gateway dependency (inherited from SPEC-067 OQ-3).
      **Finding (2026-10-12):** license reviewed — MIT (`modelcontextprotocol/python-sdk`,
      v2 line); the exact version pin lands at R-2 with the direct dependency + `uv.lock`.
      **Resolved (2026-10-13):** current stable is **`mcp==2.3.0`** (MIT, `requires-python
      >=3.10`; tool-gateway `>=3.11`, repo `.python-version` 3.12 — compatible). Pin at R-2 in
      **tool-gateway's** `pyproject.toml` + `uv.lock` only; the kernel lockfile is untouched.

### Stage-0 findings (2026-10-12; items 1/2/6 closed 2026-10-13)

> **Superseded in part at the R-6 supply-chain review (2026-10-17).** The **item-1 dev-artifact
> pick below (`SurgeX-Labs/awx-mcp-server`) was dropped** — stdio-only MCP, no declared license,
> `mcp>=1.0.0` vs the gateway's `mcp==2.3.0`. The corrected landscape (production
> `ansible/aap-mcp-server` `controller.*`; CI in-cluster thin mock; OSS alternative
> `lycorp-jp/awx-mcp`) is recorded in `spec.md` Changelog 2026-10-17 and implemented in the R-2
> binding + Ansible dev overlay. The dated findings are preserved unchanged as the historical
> record; the item-2 read-operation set + argument shapes and items 3/4/5/6 remain valid.

Desk research plus the SPEC-070 approval closed the pure-fact Stage-0 items (3/4/5) on
2026-10-12. The two items that needed a hands-on artifact pin + supply-chain review (1/6),
and the read-operation set whose per-tool argument shapes follow the item-1 choice (2), were
**closed 2026-10-13** — the operator picked **real AWX + the MIT `SurgeX-Labs/awx-mcp-server`**
as the dev/CI target. All six Stage-0 verify items are now resolved; the findings below are
the record.

- **AAP MCP-server auth (item 3 — resolved).** Red Hat AAP's MCP server authenticates each
  user via **OAuth 2.x authorization-code** (or a **PAT**) against **AAP Gateway's own**
  authorization server (`/o/authorize/`, `/o/token/`) and **inherits the requesting user's
  RBAC**; AAP 2.6 enforces **no PKCE** and provides **no automatic OIDC discovery**, and
  documents authorization-code + password grants — **not** RFC 8693 token-exchange or OBO.
  This is exactly the fact **[SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md)**
  OQ-3 consumed to resolve its mechanism to per-user OAuth authorization-code
  ([ADR-0015](../../adr/0015-outbound-user-delegated-identity-via-per-user-oauth.md),
  accepted 2026-10-12). Source: Red Hat AAP 2.6 "Authenticate with OAuth" MCP-server docs.
- **Self-contained topology (item 4 — confirmed).** The dev slice validates against a
  **self-hosted Ansible MCP server + a mock managed host** deployed in-cluster (the SPEC-068
  ephemeral-mock live-check pattern) so **CI makes no live external call**; AAP
  read-only-mode validation is a documented operator step **outside CI**. The
  loopback-sidecar-vs-in-cluster-Service pick is recorded at R-6.
- **SPEC-068 present (item 5 — confirmed).** The dev outbound-credential substrate is
  delivered (**v0.47.0**); the topology needs either no credential (loopback) or a `bearer`
  scheme SPEC-068 already ships.
- **`mcp` SDK (item 6 — RESOLVED 2026-10-13).** The official SDK is
  `modelcontextprotocol/python-sdk`, **MIT-licensed** — the license/provenance review passes.
  Current stable is **`mcp==2.3.0`** (`requires-python >=3.10`; tool-gateway `>=3.11`, repo
  `.python-version` 3.12 — compatible). The **exact pin lands at R-2** in **tool-gateway's**
  `pyproject.toml` + `uv.lock` only; the kernel lockfile is untouched (`mcp` stays
  transitive-only there via AgentScope).
- **Dev server artifact (item 1 — RESOLVED 2026-10-13, operator pick; SUPERSEDED at the R-6
  supply-chain review 2026-10-17 — `SurgeX-Labs/awx-mcp-server` dropped; see the note above and
  `spec.md` Changelog).** The server-agnostic
  connector dev-validates against a **self-hosted** stand-in. Supply-chain/license/provenance
  review of the candidate landscape:
  - **`SurgeX-Labs/awx-mcp-server`** (PyPI `awx-mcp-server`) — **MIT** ✓; third-party/community
    provenance (not official Red Hat); a **16-tool read-write** surface over AWX REST API v2;
    needs a real AWX instance behind it. **← chosen.**
  - **`ansible/ansible.mcp_builder`** (ex-`redhat-cop`) — **GPL-3.0-or-later**, Ansible-org
    **Technology Preview**, and the **wrong shape**: a collection that builds Execution
    Environments containing *AWS/Azure/GitHub* MCP servers, not an Ansible-target read server.
    Noted as the production EE-packaging mechanism AAP uses, not a dev stand-in.
  - **thin mock MCP server** — trivial provenance, exact read-only surface, matches the
    SPEC-068 ephemeral-mock pattern; **not** chosen as primary (the operator preferred
    real-AWX fidelity), retained as an option if AWX's weight becomes a CI problem.
  - official **AAP** MCP server — **licensed**, the **production** target (operator read-only
    validation outside CI), not a free dev stand-in. Do **not** select
    `ansible-collections/ansible.mcp` (opposite direction — Ansible as an MCP *client*).

  **Decision: real AWX + the MIT `SurgeX-Labs/awx-mcp-server`, self-hosted in-cluster** (so CI
  still makes no live external call, OQ-5). A suitable MIT MCP server exists, so the
  MCP-ingestion substrate **is** proven on this target and the native `ansible-inventory`
  fallback is **not** taken (it stays documented). Two recorded cautions for R-2/R-6: (1) the
  server's **3 mutating tools — `job_launch`, `job_cancel`, `project_update` — MUST be denied**
  by the admission allowlist (never named in the bundle at any tier); (2) R-6 must budget for
  **AWX's weight** (Postgres/Redis/web/task containers) in the dev-k8s overlay.
- **Read-only operation set + argument shapes (item 2 — RESOLVED 2026-10-13).** The admitted
  set is **read-only discovery only**, kept **minimal** (memo §2: "a large catalog is not
  itself a use case"), mapped from the chosen server's read tools to canonical `ansible.*`
  typed tools (category `ansible`, `risk_level: read`), each with a JSON-Schema
  `parameters_schema` (the SPEC-007 `ToolDefinition` shape; exact schemas finalized at R-2).
  Pinned admitted set + argument shapes, one per named capability:
  - **inventory host/group listing** — `ansible.list_inventories` `{ name_filter?: string,
    limit?: int }`; `ansible.get_inventory` `{ inventory: string }` (required; hosts/groups
    within an inventory)
  - **job-template listing** — `ansible.list_job_templates` `{ name_filter?: string, limit?: int }`
  - **job log/status monitoring** — `ansible.get_job` `{ job_id: string }` (required; status);
    `ansible.get_job_stdout` `{ job_id: string, tail?: int }` (required `job_id`; log)
  - **environment health** — `ansible.get_environment_health` `{}` (maps the server's
    `env_test` / `env_get_active`)

  **Server read tools NOT admitted** (no use case yet; admit later only on a named need):
  `get_job_template`, `list_jobs`, `job_events`, `list_projects`. **Denied / never admitted:**
  the mutating `job_launch`, `job_cancel`, `project_update` (write tier — absent from the
  admission allowlist), any playbook-run/runbook-execution name (Layer-2 fast-follow), and **any
  `--check`/dry-run** operation (OQ-3 — the server exposes none; none admitted). **Gap
  recorded:** the server exposes **no host `gather_facts`/facts tool**, so the spec's
  "`gather_facts`/setup reads" capability is **deferred to R-2** (a native
  `ansible-inventory`/facts fallback or a later server tool) rather than faked (OQ-5 "defer,
  don't fake"). Argument shapes follow the `k8s.*` connector convention; server-advertised
  metadata never sets tier (R-2 invariant).

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

- [x] Add the official `mcp` SDK as a direct tool-gateway dependency
      (`products/tool-gateway/pyproject.toml` + `uv.lock`; kernel lockfile untouched).
- [x] Add the **generic, server-agnostic** MCP ingestion adapter that consumes an MCP server
      and maps discovered tools into the SPEC-007 `BaseTool`/`ToolDefinition`/`ToolRegistry`
      seam as **typed tools**, admitting only allowlisted tools (the allowlist is gateway
      connector config, not a per-tool-name policy-bundle entry) and treating server metadata
      as untrusted (`products/tool-gateway/src/tool_gateway/`). Tool admission + tier mapping
      are **configuration**, not adapter code — so the same adapter binds a self-hosted
      AWX/mock server (dev), AAP read-only mode (production), a future ServiceNow binding
      (SPEC-067), and the Layer-2 runbook-tool binding.
- [x] Add the Ansible **read-only** target binding (endpoint, admitted read tool names, tier
      mapping); authenticate the MCP session via the R-1 dev credential scheme or loopback;
      implement the native read-only fallback connector (`ansible-inventory` shell-out, **no
      `--check`**) for the OQ-1 fallback path.
- [x] Wire calls through the existing signed-tool path (SPEC-037); confirm no new kernel
      seam and the kernel is never an MCP client.
- [x] Tests: tools register as typed tools and are callable; **read-tier-only** (no
      playbook-run/runbook-execution/mutating operation exposed, **no `--check`/dry-run tool
      admitted**); **server-agnostic** (the same adapter maps a self-hosted server's tools and
      an AAP read-only config without adapter-code change); server-advertised metadata never
      sets tier/auto-approves; requester + acting-service identity carried; the adapter
      resolves any dev credential through SPEC-068's resolver
      (`products/tool-gateway/tests/`).

## R-3: Deny-by-default policy coverage for Ansible tools

- [x] **No policy-bundle change — the bundle is action-based, not per-tool-name.** The
      canonical bundle (`shared/shared-contracts/policies/policy-default.yaml`) authorizes
      role × action (`tools:list`/`tools:invoke`/`tools:mutate`/`secrets:deliver`) and names
      no tool. Each admitted Ansible tool registers at **read tier**, which the gateway maps
      to `tools:invoke` alone (never `tools:mutate`) — the same existing `allow-operators-tools`
      grant that `k8s.*`/`http.*` read tools already ride — so `make sync-policy` is **not**
      invoked and the bundle stays byte-identical.
- [x] **Deny-by-default is enforced at the gateway admission allowlist** (connector config),
      not the bundle: an unlisted server tool is never registered, so invoking it returns
      `TOOL_NOT_FOUND`. No write/admin, playbook-run, runbook-execution, or `--check`/dry-run
      Ansible name is admitted (structurally absent from the allowlist), so no Ansible tool can
      ever derive `tools:mutate`.
- [x] Proven by the gateway tool tests
      (`products/tool-gateway/tests/test_ansible_mcp_ingestion.py`: read-tier-only registration
      + the deny-by-default allowlist). `make validate-policy-scenarios`, `make validate-policy`,
      and `make policy-diff` stay green **unchanged** (no bundle edit → no drift).

## R-4: Audit fidelity and user-delegated attribution

- [x] Emit requester + acting-service identity + target system + tool name + outcome per
      Ansible call (`products/tool-gateway/`), keeping requester and acting-service separate
      per ADR-0004 `sub`/`act`.
- [x] Record the **dev-vs-production per-user-RBAC distinction** (OQ-4): production
      attributes each call to the requesting user end to end (via the R-1 dependency
      [SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md); AAP inherits user
      RBAC); dev records Luban-side attribution to the principal
      while the target-side identity is the self-hosted server's own — the audit record makes
      this explicit rather than implying target-side per-user RBAC the dev topology lacks.
- [x] Tests: audit record carries all five fields + the delegation distinction; no
      secret/token/`client_secret` appears in audit or logs
      (`products/tool-gateway/tests/`).

## R-5: Fail-closed and no-fabrication guardrail (dry-run is never read-tier)

- [x] Map transport/timeout/HTTP-error to a failed outcome with a reason + a
      target-unavailable audit attribution; never an empty "success"
      (`products/tool-gateway/`).
- [x] Assert **no read-tier tool invokes `--check`/dry-run** and the admitted read set
      contains no operation whose safety depends on check mode (OQ-3); document that any
      dry-run preview is a **Layer-2 action-tier** concern (a fact about a plan), never a
      read-tier guarantee.
- [x] Tests: simulated outage/timeout yields a failed outcome, not a fabricated result; the
      admitted read-tool set contains no dry-run/`--check` operation
      (`products/tool-gateway/tests/`).

## R-6: Target provisioning and overlay wiring

- [x] Deploy the **self-hosted** Ansible MCP server (or native fallback) + a mock managed
      host to the dev-k8s namespace through the overlay (reusing the SPEC-068 live-check
      ephemeral-mock pattern); keep `make overlays` green
      (`shared/platform-ops/gitops/dev-k8s/`).
      **Delivered (2026-10-17):** the `runtime-profiles/ansible-dev` overlay ships the thin mock
      MCP server (`ansible-mock-mcp` Deployment/Service/NetworkPolicy on the tool-gateway image,
      script mounted from the `ansible-mock-mcp-server` ConfigMap) = the mock managed host, wired
      into `dev-k8s` (resources + `ansible.env` + the tool-gateway credential patch), the root
      `OVERLAYS`, `select-runtime-profile.sh`/`verify-runtime-profile.sh`, and `deploy-overlay.sh`
      (guarded `set image`). `make overlays` green (5 overlays) and the dev-k8s render verified.
      *The live in-cluster `make deploy` + gated live-check run is deferred to the next
      cluster-available window (the dev API went unresponsive mid-session); not a code gap —
      OQ-5 means CI makes no live external call.*
- [x] Deliver any credential fields the topology needs through the `sync-*.sh` model — never
      hand-edited in a consumer copy; keep `make validate-secret-vocabulary` green
      (`shared/platform-ops/`).
      **Delivered (2026-10-17):** `sync-ansible-credentials.sh` generates one mock bearer and
      writes it to **both** sinks (the gateway `tool-gateway-ansible-credentials` credential-set
      file and the mock's `ansible-mock-credentials` secret) so they cannot drift; called from
      `dev-k8s/deploy.sh`. `make validate-secret-vocabulary` green; the two-sink logic + operator
      override (`ANSIBLE_MCP_BEARER_TOKEN`/`ANSIBLE_MCP_CREDENTIAL_SET`) proven via a kubectl shim.
- [x] Ensure inventory source, endpoint, admitted-tool list, and executable path are operator
      configuration in the overlay (never model-selected); CI makes no live external call.
      **Delivered (2026-10-17):** endpoint/transport/credential-set are `GATEWAY_ANSIBLE_MCP_*`
      in `ansible.env` (platform-runtime-config); the admitted-tool list + argument shapes are
      gateway config in `ansible_binding.py`; the target is the in-cluster `ansible-mock-mcp`
      Service, so no live external call is made (OQ-5).
- [x] Add a gated live-check script (mirroring `shared/platform-ops/e2e/http-check-demo.sh`)
      proving the end-to-end inventory/facts read against the deployed gateway, with the
      fail-closed negative control and redaction assertions. Document **AAP read-only-mode
      validation** as an operator step run outside CI (no licensed instance in CI).
      **Delivered (2026-10-17):** `shared/platform-ops/e2e/ansible-mcp-check.sh` (wired into
      `make e2e`) — unauth→401, delegated operator token, the enabled/disabled ConfigMap branch, a
      fail-closed negative control (denied `ansible.launch_job_template` + `INVALID_PARAMETERS`),
      gated live reads (skip with a note when the target is unreachable), and a bearer-redaction
      assertion. The **AAP read-only validation runbook** (operator step outside CI) is documented
      in `docs/guides/tool-configuration.md`. *Live cluster run deferred with box 1.*

> **R-6 Layer-2 strengthening.** `products/tool-gateway/tests/test_ansible_mcp_streamable_http.py`
> runs a **real** `mcp` SDK server over streamable-HTTP in-process, so CI exercises the connector's
> live `_open_mcp_session` wire path (not a stub). Part of the 550-test green tool-gateway suite
> (2026-10-17).

## Delivery Gate

- [x] Stage 0 residual facts recorded; all five Open Questions show their 2026-10-11 operator
      resolutions in `spec.md`. **Stage 0 closed 2026-10-13** — all six verify items resolved
      (read-op set + argument shapes pinned; `mcp==2.3.0` MIT confirmed). The dev-artifact pick
      was **corrected at the R-6 supply-chain review (2026-10-17)**: `SurgeX-Labs/awx-mcp-server`
      dropped (stdio-only MCP, no license, `mcp>=1.0.0` vs `mcp==2.3.0`); production
      `ansible/aap-mcp-server` (`controller.*`), CI in-cluster thin mock, OSS alternative
      `lycorp-jp/awx-mcp` — see `spec.md` Changelog.
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
      ([SPEC-070](../SPEC-070-outbound-user-delegated-identity/spec.md), itself `approved`) are
      separate specs building on this adapter and on SPEC-068 respectively.
