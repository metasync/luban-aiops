# SPEC-067 Tasks: ServiceNow ITSM MCP-Ingestion Pilot (Read Tier)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Approved 2026-10-20 — binding; implementation authorized to begin.** SPEC-067 is
> `approved`: all six Open Questions are resolved (OQ-1, OQ-4, OQ-5 by operator
> direction 2026-10-20; OQ-2 2026-10-08 by extracting the credential substrate to
> SPEC-068; OQ-3 on 2026-10-07; OQ-6 moved to SPEC-068). R-1 is not built here — it is
> a dependency on
> [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (delivered
> v0.47.0). Approval authorizes implementation to *begin* only: commit/push,
> deployment, and any `VERSION` bump remain separate authorization boundaries not
> granted here. **Stage 0 (read-only verification) is COMPLETE** — it pinned the auth
> scheme (OQ-1 = OAuth2 `client_credentials`), the read-tier operation set (OQ-4 = six
> read tools), and the validation model (OQ-5 = a local mock Table-API responder + a
> gated live-PDI operator check), so the ServiceNow connector (Stage 2) is unblocked.
> *(Stage-0's OQ-3 transport check was executed read-only 2026-10-19 on the operator's
> PDI `dev417985`: ServiceNow's own MCP server is unavailable there, so the
> REST/Table-API fallback is taken and R-2 below is a `servicenow_native` connector.)*

## Stage 0 — Verify (read-only; resolves OQ-1, OQ-4, OQ-5; validates the OQ-3 transport decision; confirms the SPEC-068 dependency)

- [x] Pin ServiceNow's actual auth scheme for the **REST Table API** (OQ-1; Stage-0
      confirmed REST-only on the PDI — no MCP server) — **RESOLVED 2026-10-20:** OAuth2
      `client_credentials` against a dedicated least-privilege read-only service account
      (Basic a dev bootstrap; mTLS out). A scheme SPEC-068 already ships — no substrate
      change; recorded against R-1's `scheme` vocabulary in `spec.md` OQ-1.
- [x] Fix the read-tier ServiceNow operation set + each tool's argument-validation
      shape (OQ-4) — **RESOLVED 2026-10-20:** six read tools
      (`servicenow.incident.list/.get`, `servicenow.change_request.list/.get`,
      `servicenow.user.get`, `servicenow.cmdb_ci.get`), each with a bounded argument
      schema (fixed table, allowlisted field projection, capped `sysparm_limit`,
      `sys_id` validation); `change_request` in scope by operator amendment, attachments
      + `problem` deferred. Recorded against R-2/R-3 in `spec.md` OQ-4.
- [x] Establish dev-cluster validation feasibility vs a real tenant/PDI (OQ-5) —
      **RESOLVED 2026-10-20:** validate against a local mock Table-API responder in
      dev-k8s (the SPEC-069 `ansible-dev` pattern; CI makes no live call) + live-PDI
      validation as a gated operator check, never a CI dependency. Recorded against the
      plan's Test Strategy in `spec.md` OQ-5.
- [x] Confirm SPEC-068 (the extracted credential substrate, OQ-2 resolved 2026-10-08)
      is approved/delivered before this pilot authenticates a live target, and that
      OQ-1's scheme is one SPEC-068 already ships — **CONFIRMED:** SPEC-068 delivered
      v0.47.0; `oauth2_client_credentials` is a shipped scheme, so OQ-1's selection
      needs no substrate change.
- [x] Validate the OQ-3 transport decision on the target (resolved 2026-10-07) —
      **DONE 2026-10-19** (read-only browser + Table-API GETs on the operator's PDI
      `dev417985`, Australia build): ServiceNow's own MCP server is **UNAVAILABLE**
      (AI Platform / AI Agent Studio / AI Control Tower not provisioned; no MCP-named
      `sys_plugins` entry even available to activate; no MCP Server Console route;
      Now Assist Admin shows "Requires plugin install"). A provisioning/entitlement
      gap, not a release gap → **the REST/Table-API fallback is taken**; R-2 is
      re-scoped to a `servicenow_native` connector. No screenshots (browser viewport
      unavailable); evidence is structured Table-API reads + verbatim UI strings.
- [x] Pin the official `mcp` Python SDK version + supply-chain/license review —
      **satisfied by SPEC-069** (`mcp>=2.3,<3.0`, MIT, already a direct tool-gateway
      dependency). Not on the ServiceNow REST connector's critical path: the REST path
      uses `httpx` and adds **no** new dependency.

## R-1: Outbound execution credential (dependency on SPEC-068 — not built here)

The credential-scheme extension was extracted to
[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (OQ-2, resolved
2026-10-08); its parsing, token client, resolver seam, redaction, fail-closed, and
provisioning tasks (and OQ-6) live in SPEC-068's `tasks.md`.

- [x] Gate: SPEC-068 is delivered (v0.47.0) before this pilot authenticates a live
      target; the ServiceNow connector resolves its credential through SPEC-068's
      resolver seam (no pilot-local re-implementation). **DONE:** `servicenow_native.py`
      imports and awaits `resolve_outbound_auth` (SPEC-068's seam); no pilot-local
      credential code.

## R-2: ServiceNow read-tier ingestion connector beneath the gateway

*(Re-scoped 2026-10-19 to the OQ-3 REST fallback — a `servicenow_native` connector
mirroring the shipped `ansible_native.py`. Authorized to begin: SPEC-067 is `approved`
2026-10-20; the six read tools are pinned by OQ-4.)*

- [x] ~~Add the official `mcp` SDK as a direct tool-gateway dependency~~ — **not
      needed for the REST path**: `mcp>=2.3` is already a direct dep (SPEC-069) and
      unused here; the REST connector uses `httpx` (already present). **No new
      dependency.**
- [x] Add the ServiceNow **REST/Table-API native connector** (`servicenow_native.py`)
      + a static `servicenow_binding.py` tool declaration, mapping each
      operator-declared `servicenow.*` read tool to a Table-API GET
      (`/api/now/table/...`) on the SPEC-007 `BaseTool`/`ToolDefinition`/`ToolRegistry`
      seam, admitting only policy-named tools
      (`products/tool-gateway/src/tool_gateway/ingestion/`). **DONE 2026-10-20:** the
      six OQ-4 read tools register read-tier on the shared registry seam (wired in
      `app.py::_build_tool_registry` behind `GATEWAY_SERVICENOW_ENABLED`, tuple shape
      unchanged); tables, field projections, and tiers are gateway-owned binding
      config, never target-derived.
- [x] Resolve the REST credential through SPEC-068's resolver seam (scheme pinned by
      OQ-1); no pilot-local credential re-implementation; no token in a result or log.
      **DONE:** `_resolve_auth` delegates to `resolve_outbound_auth`
      (`oauth2_client_credentials`); tests assert the bearer token reaches the target
      but never the result envelope/secret, and an unresolved set fails closed.
- [x] Wire calls through the existing signed-tool path (SPEC-037); confirm no new
      kernel seam and the kernel is never an MCP client. **DONE:** the tools are
      ordinary `BaseTool`s on the existing `ToolRegistry`, so they ride the shipped
      signed-tool path; the connector is pure `httpx` REST — no MCP substrate, no
      kernel change.
- [x] Tests: tools register and are callable; read-tier-only (no mutating operation
      exposed); the tool set is operator-declared (never target-derived); fail-closed
      on an upstream 4xx/5xx (no fabricated success); requester + acting-service
      identity carried to the target (`products/tool-gateway/tests/`). **DONE:**
      `test_servicenow_native.py` (31 tests) covers registration/tier, the
      operator-declared set, projection, pre-transport validation, fail-closed on
      4xx/5xx/timeout/unreachable/non-JSON, and the credential seam; the full
      tool-gateway suite is green (592 passed, incl. the 9 gateway-level R-3/R-4/R-5
      tests added below). **Identity nuance:** the connector
      addresses the target with the gateway's *acting-service* credential only
      (`target_identity_mode="acting_service"`, asserted); the *requester* identity
      rides the gateway audit path (R-4), and per-user delegation to the target is
      SPEC-070's seam — deliberately not wired here.

## R-3: Deny-by-default policy coverage for ServiceNow tools

- [x] Deny-by-default at the **gateway admission allowlist**, not the bundle
      (`products/tool-gateway/src/tool_gateway/ingestion/servicenow_binding.py`).
      **DONE (SPEC-069 R-3 faithful reinterpretation):** the canonical bundle
      (`shared/shared-contracts/policies/policy-default.yaml`) is **action-based**
      (role × `tools:invoke`/`tools:mutate`/`tools:list`/`secrets:deliver`) and names
      **zero** individual tools, so "name each read tool in the bundle" is
      unimplementable as literally written. Deny-by-default is therefore enforced by
      `SERVICENOW_ADMITTED_TOOLS` — the connector registers only the six statically
      declared read tools; an unlisted name (incl. the deferred `problem`/`attachment`
      capabilities and any write name) is never registered → `TOOL_NOT_FOUND`. **No
      bundle edit; `make sync-policy` not invoked.**
- [x] Read-tier-only + deny-by-default invariants asserted; `make validate-policy-scenarios`,
      `make validate-policy`, and `make policy-diff` stay green **unchanged** (bundle
      byte-identical, no drift). **DONE:** `test_servicenow_native.py::DenyByDefaultTests`
      (3 tests) — an unlisted `servicenow.*` name returns `TOOL_NOT_FOUND`; every
      admitted def is `risk_level="read"` with `extra_required_actions==()`; an unlisted
      tool at the gateway is a `tool_invoked` error, **not** a target outage. The policy
      gates are untouched because the bundle does not change.

## R-4: Audit fidelity for external ingestion

- [x] Emit requester + acting-service identity + target system + tool name + outcome
      per ServiceNow call (`products/tool-gateway/`). **DONE:** the connector sets
      `source_system="servicenow"` on every result's evidence and declares the opt-in
      `audit_attribution` hook (`target_identity_mode="acting_service"`); the shipped
      SPEC-069 gateway seam (`gateway_service.invoke_tool` → `resolve_audit_attribution`)
      folds requester `sub`/`act`/`username`/`roles`, `target_system`, `tool_name`, and
      `status` into both the `tool_invoked` log event and the durable audit event.
- [x] Tests: audit record carries all five fields; no secret/token/`client_secret`
      appears in audit or logs (`products/tool-gateway/tests/`). **DONE:**
      `test_servicenow_native.py::AuditFidelityTests` (2 tests) — a success audit carries
      subject/username/actor/roles + `details.target_system="servicenow"` + `tool_name` +
      `status="success"` + `target_identity_mode="acting_service"` (no `failure_class`);
      under OAuth2 `client_credentials` the token/`client_secret`/`password` are absent
      from both the audit event and the log stream while the bearer still reaches the
      target.

## R-5: Fail-closed and no-fabrication guardrail

- [x] Map transport/timeout/HTTP-error to a failed outcome with a reason + a
      target-unavailable audit attribution; never an empty "success"
      (`products/tool-gateway/`). **DONE:** `SERVICENOW_TIMEOUT`/`SERVICENOW_UNREACHABLE`
      map to a failed result whose `audit_attribution` adds
      `failure_class="target_unavailable"`; an upstream 4xx/5xx is a fact
      (`SERVICENOW_UPSTREAM_ERROR`) with **no** `failure_class` — distinct from both an
      outage and a policy denial.
- [x] Tests: simulated outage/timeout yields a failed outcome, not a fabricated result
      (`products/tool-gateway/tests/`). **DONE:**
      `test_servicenow_native.py::FailClosedAuditTests` (4 tests) — `ConnectTimeout` and
      `ConnectError` → 400 error with `failure_class="target_unavailable"` +
      `target_system="servicenow"`; an upstream 500 → error with **no** `failure_class`;
      a missing identity → 403 `policy_decision`/deny with **no** `failure_class`
      (outage ≠ denial).

## R-6: Secret provisioning and overlay wiring

- [x] Deliver the new credential fields (`scheme`, `token_url`, `client_id`,
      `client_secret`) through the `sync-*.sh` model — never hand-edited in a consumer
      copy (`shared/platform-ops/`). **DONE:** `sync-servicenow-credentials.sh` (one
      generator / two sinks, mirroring `sync-ansible-credentials.sh`) writes the
      `oauth2_client_credentials` set to BOTH `tool-gateway-servicenow-credentials`
      (`credential-sets.json`, what the connector resolves) and `servicenow-mock-credentials`
      (`client-id`/`client-secret`/`access-token`, what the mock's OAuth + bearer gates
      validate) so the two cannot drift; secrets ride temp files (never `--from-literal`
      /argv), an idempotent `cleanup()` + `trap … EXIT INT TERM` guarantees no raw value
      survives a mid-script failure, `SKIP_SERVICENOW_CREDENTIALS=true` skips both sinks
      (each then fails closed), and operator overrides (`SERVICENOW_CLIENT_ID`/`_SECRET`/
      `_TOKEN_URL`) repoint at a real PDI. Wired into `dev-k8s/deploy.sh`.
- [x] Wire the ServiceNow credential set into the dev-k8s overlay; keep
      `make overlays` and `make validate-secret-vocabulary` green
      (`shared/platform-ops/gitops/dev-k8s/`). **DONE:** new resource-bearing profile
      `runtime-profiles/servicenow-dev/` — a thin mock Table-API + `/oauth_token.do`
      responder (`mock_servicenow_table_api.py`, reusing the tool-gateway image) as
      Deployment/Service/NetworkPolicy, `servicenow.env` (`GATEWAY_SERVICENOW_*`),
      `kustomization.yaml` (ConfigMap off the real `.py`), and the
      `tool-gateway-servicenow-credentials.yaml` strategic-merge patch. Wired into
      `dev-k8s/kustomization.yaml` (resources + configMapGenerator env + patch), root
      `Makefile` `OVERLAYS`, `select-runtime-profile.sh` (rejection guard + heredoc),
      `verify-runtime-profile.sh`, `deploy-overlay.sh` (guarded retag), and
      `e2e/servicenow-check.sh` (+ `make e2e`). **Gates green:** `make overlays` renders
      all six overlays (incl. `servicenow-dev` + `dev-k8s`); the dev-k8s render carries
      all five `GATEWAY_SERVICENOW_*` keys, the credential mount, and the mock resources;
      `make validate-secret-vocabulary` unchanged-green; the mock's OAuth grant, bearer
      gate, list/get reads, `sysparm_limit`, and 404 fail-closed are smoke-proven.

## Delivery Gate

- [x] Stage 0 facts recorded and all Open Questions resolved in `spec.md`
      (OQ-2 resolved 2026-10-08, OQ-3 on 2026-10-07, OQ-6 moved to SPEC-068; OQ-1,
      OQ-4, OQ-5 resolved by operator direction 2026-10-20). Spec is `approved` (2026-10-20), now
      `delivered` (v0.49.0).
- [x] SPEC-068 (the outbound credential substrate) delivered — v0.47.0; this pilot's
      connector depends on its resolver seam.
- [x] All acceptance criteria in `spec.md` verified; `make verify` green (incl.
      `portal-test`, `validate-policy-scenarios`, `validate-secret-vocabulary`,
      `overlays`). **DONE (2026-10-20):** the full aggregate `make verify` re-ran green on
      the bumped tree — every product suite passed (agent-platform 1538, tool-gateway 592
      incl. the new `test_servicenow_native.py`, and 394/291/140/138/79/61 across the
      rest), `validate-policy-scenarios` OK (144 api + 26 tools), `validate-version`
      `OK: all product and portal versions match VERSION=0.49.0`, `portal-test` 494+43, the
      secret-delivery demo, `overlays` (all six incl. `servicenow-dev`), and the SPEC-063
      real-Postgres crash campaign `792 passed, 2 deselected … exit 0`.
- [x] No new tool-gateway dependency for the REST path (`httpx` present; `mcp>=2.3`
      already added by SPEC-069, unused here) — confirm `uv.lock` needs no change and
      record that the REST connector adds nothing. **DONE:** `git diff` shows
      `products/tool-gateway/uv.lock` and `pyproject.toml` carry only the coordinated
      0.49.0 version bump (no dependency change); the
      connector is pure `httpx`, and the R-6 mock reuses the tool-gateway image's
      existing `starlette`/`uvicorn` runtime deps (it ships as a mounted ConfigMap, not a
      package import), so neither the connector nor the overlay adds a dependency.
- [x] Living state docs updated (see spec `Impact`): `products/tool-gateway/README.md`
      (connector bullet + delivered prose), `docs/guides/tool-configuration.md` (ServiceNow
      connector tool table + deep-dive), delivery-roadmap R6 status + Exploration Backlog row,
      and `identity-and-authorization-design.md` §Service Identity Model. (The `Impact` list's
      `docs/agentic-aiops-platform/architecture.md` does not exist; `architecture-overview.md`
      carries no connector enumeration, so the connector reference lives in
      `tool-configuration.md` alongside the Ansible connector.)
- [x] `CHANGELOG.md` entry added referencing SPEC-067 (`## 0.49.0 — 2026-10-20`);
      `VERSION` bumped 0.48.0 → 0.49.0 in lockstep across the build surface (`make
      validate-version` OK; each `uv.lock` regenerated by `uv lock`, one changed line each).
- [x] Spec index in `docs/specs/README.md` updated (SPEC-067 row → `delivered`); spec
      status set to `delivered` in `spec.md` with a delivery changelog entry.
