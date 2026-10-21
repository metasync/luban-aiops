# SPEC-067 Plan: ServiceNow ITSM MCP-Ingestion Pilot (Read Tier)

> **Approved 2026-10-20 — binding; implementation authorized to begin.** This plan
> was authored alongside `spec.md` at drafting time per the SPEC-064/065/066
> same-session precedent and was provisional until approval. All six Open Questions
> are now resolved: OQ-1 (auth = OAuth2 `client_credentials` against a dedicated
> least-privilege read-only service account), OQ-4 (six read-tier tools —
> `servicenow.incident.list/.get`, `servicenow.change_request.list/.get`,
> `servicenow.user.get`, `servicenow.cmdb_ci.get`), and OQ-5 (a local mock Table-API
> responder in dev-k8s + a gated live-PDI operator check, never a CI dependency) were
> resolved by operator direction 2026-10-20; OQ-2 was resolved 2026-10-08 (credential
> substrate extracted to SPEC-068), OQ-3 on 2026-10-07 (transport; the REST/Table-API
> fallback was taken at Stage-0 2026-10-19), and OQ-6 moved to SPEC-068. R-1 is not
> built here — it is a dependency on
> [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (delivered
> v0.47.0). Target version is **v0.49.0** (SPEC-070's planning target re-slots to
> v0.50.0). Approval authorizes implementation to *begin* only: commit/push,
> deployment, and any `VERSION` bump remain separate authorization boundaries not
> granted by this document. **Stage 0 (verification) is complete** — its OQ-3
> transport-validation step was executed read-only 2026-10-19 against the operator's
> PDI (`dev417985`): ServiceNow's own MCP server is unavailable there, so the
> **REST/Table-API fallback is the taken transport** and R-2 below is a
> `servicenow_native` connector.

## Approach

The pilot now builds one move, not two. The target-agnostic credential extension that
was R-1 has been extracted to
[SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (OQ-2, resolved
2026-10-08); this plan therefore covers the ServiceNow-specific read-tier connector
(R-2–R-6) that **consumes** that substrate, plus R-1 as a dependency gate. Stage 0 has
pinned ServiceNow's auth scheme (OQ-1), read-tier operation set (OQ-4), and dev-cluster
validation model (OQ-5) — all resolved by operator direction at approval 2026-10-20 — so
R-2–R-6 are now **binding**. The stages are ordered so SPEC-068 lands and is tested
before any target-specific code depends on it.

0. **Verify** (Stage 0) — read-only — **COMPLETE.** Pinned the three facts the memos
   could not settle from the repository because they are properties of an external
   system, not decisions: ServiceNow's auth scheme (OQ-1 = OAuth2 `client_credentials`),
   the read-tier operation set (OQ-4 = six read tools), and whether the pilot can be
   validated against the dev cluster or needs a real tenant/PDI (OQ-5 = a local mock
   Table-API responder + a gated live-PDI check). Each was resolved by operator
   direction at approval 2026-10-20. **(The OQ-3 transport check was done read-only
   2026-10-19:** the PDI does not expose ServiceNow's own MCP server, so the
   REST/Table-API fallback is taken.**)**
1. **Depend** (Stage 1, R-1 → SPEC-068) — the outbound credential substrate (additive
   `scheme` field + connector-local token client + resolver seam, with redaction and
   fail-closed tests) is delivered by SPEC-068, not built here; this pilot consumes its
   resolver. SPEC-068 is target-agnostic and does not wait on this pilot's Stage 0.
2. **Connect** (Stage 2, R-2 + R-3) — the ServiceNow **REST/Table-API native
   connector** (`servicenow_native.py`, the OQ-3 fallback taken at Stage-0
   2026-10-19), reusing the SPEC-007 registry seam, plus deny-by-default
   coverage at the connector admission allowlist (the action-based bundle names no
   tool — R-3's faithful reinterpretation).
3. **Attribute** (Stage 3, R-4 + R-5) — audit fidelity (requester + acting service +
   target + tool + outcome) and the fail-closed/no-fabrication guardrail.
4. **Provision** (Stage 4, R-6) — secret sync + dev-k8s overlay wiring.
5. **Deliver** (Stage 5) — living-state docs, CHANGELOG, version; separate
   authorization.

## Design Per Requirement

### R-1: Outbound execution credential (dependency on SPEC-068)

- affected files / modules: **none in this spec.** The credential-scheme extension —
  the optional per-set `scheme`, the connector-local `oauth2_client_credentials` token
  client, and the reusable async auth-resolution seam — was extracted to
  [SPEC-068](../SPEC-068-outbound-execution-credential-schemes/spec.md) (OQ-2, resolved
  2026-10-08). See SPEC-068's plan for the design, alternatives (Option A
  connector-local chosen over B/C centralized), and test strategy.
- chosen approach here: **consume** SPEC-068's resolver seam. The ServiceNow MCP/REST
  session resolves its credential through SPEC-068 (never a pilot-local
  re-implementation); this pilot adds no credential code of its own.
- **OQ-1 gate:** ServiceNow's real scheme (Stage 0) selects **among** the schemes
  SPEC-068 already ships (`bearer` or `oauth2_client_credentials`). If Stage-0 finds a
  scheme SPEC-068 does not build (e.g. mTLS-only), that reopens SPEC-068's scope in a
  follow-up — it is not special-cased in this pilot.

### R-2: ServiceNow read-tier ingestion connector beneath the gateway

- affected files / modules: a new `products/tool-gateway/src/tool_gateway/ingestion/`
  ServiceNow **REST/Table-API native connector** (`servicenow_native.py`, mirroring
  the shipped `ansible_native.py`) + a `servicenow_binding.py` static tool declaration;
  registration into the existing `ToolRegistry`. **No new dependency** — the connector
  uses `httpx` (already present); `mcp>=2.3` is already a direct tool-gateway dep from
  SPEC-069 and is unused by this path.
- chosen approach (**OQ-3 fallback taken at Stage-0 2026-10-19**): a hand-rolled
  **REST/Table-API** connector that maps each operator-declared `servicenow.*` read
  tool to a ServiceNow Table-API GET (`/api/now/table/...`) into a
  `BaseTool`/`ToolDefinition` (SPEC-007 seam), authenticating via the R-1/SPEC-068
  credential set (scheme pinned by OQ-1). Governance stays tool-gateway-side: the
  connector registers only the six statically declared `servicenow.*` read tools (the
  `SERVICENOW_ADMITTED_TOOLS` allowlist) and never auto-discovers from the target. The
  kernel calls them through the existing
  signed-tool path (SPEC-037); no new kernel seam, and the kernel never becomes an MCP
  client. Stage-0 read-only verification on the operator's PDI (`dev417985`) found
  ServiceNow's own MCP server **unavailable** there, so the MCP-SDK path is not
  exercisable on this target.
- alternatives: (a) consume **ServiceNow's own MCP server** via the official `mcp`
  SDK (OQ-3's conditional primary, realized as SPEC-069's generic adapter) — **not
  exercisable on this PDI**; retained for a differently-entitled instance that exposes
  it; (b) build **our own MCP server** wrapping the REST API — **rejected** (a stateful
  hop + credential boundary that re-wraps the same `BaseTool` seam for one internal
  consumer; the `mcp-exposure-spike.md` "retain native connectors; own a server only on
  a documented adoption gap" posture, and none of its triggers apply); (c) a
  third-party ServiceNow MCP *server* — rejected (supply-chain/license risk, an extra
  stateful deployment, re-exposes our credential); (d) hand-rolling the MCP protocol —
  rejected (an official maintained SDK exists).
- **OQ-4 gate:** the concrete tool set and each tool's argument-validation shape are
  fixed in Stage 0 (the REST Table-API reads the operator names).

### R-3: Deny-by-default policy coverage for ServiceNow tools

- affected files / modules: the connector admission allowlist
  (`servicenow_binding.py`'s `SERVICENOW_ADMITTED_TOOLS`) and the gateway tool tests;
  **no `shared/shared-contracts/policies/` change.** The canonical bundle is
  **action-based** (role × action — `tools:invoke`/`tools:mutate`/`tools:list`/
  `secrets:deliver`) and names zero individual tools, so per-tool naming is
  unimplementable there.
- chosen approach (the SPEC-069 R-3 faithful reinterpretation): deny-by-default is
  enforced at the **gateway admission allowlist** — the connector registers only the
  six statically declared read tools; an unlisted name (including the deferred
  `problem`/`attachment` capabilities and any write name) is never registered, so
  invoking it returns `TOOL_NOT_FOUND`. Each admitted tool is read tier, riding the
  existing `tools:invoke` grant exactly as the `k8s.*`/`http.*`/`ansible.*` read tools
  do. With no bundle edit, `make sync-policy` is not invoked and
  `make validate-policy-scenarios` / `make validate-policy` / `make policy-diff` stay
  green **unchanged**; the read-tier-only and deny-by-default invariants are asserted
  by `test_servicenow_native.py` rather than a per-tool-name scenario.

### R-4: Audit fidelity for external ingestion

- affected files / modules: the tool-gateway audit emission path, keeping the
  requester and acting-service identities separate per ADR-0004's `sub`/`act`
  delegation and the identity model's separate-identity logging.
- chosen approach: emit requester identity + acting service identity + target system +
  tool name + outcome per call; assert no secret/token/`client_secret` reaches audit.

### R-5: Fail-closed and no-fabrication guardrail

- affected files / modules: the ServiceNow connector's error handling.
- chosen approach: map transport/timeout/HTTP-error to a failed tool outcome with a
  reason and a target-unavailable audit attribution; never return an empty "success."
  Mirrors SPEC-058's `http.get` "an upstream 4xx/5xx is a fact, not a tool error" rule.

### R-6: Secret provisioning and overlay wiring

- affected files / modules: the `sync-*.sh` secret-delivery scripts;
  `shared/platform-ops/gitops/dev-k8s/` (credential-set secret + overlay);
  `shared/shared-contracts/scripts/` (secret vocabulary, if OQ-6 requires).
- chosen approach: deliver the new fields through the existing sync model (never
  hand-edited in a consumer copy); wire the ServiceNow set into dev-k8s; keep
  `make validate-secret-vocabulary` and `make overlays` green.

## Sequencing And Dependencies

1. **Stage 0 — Verify** — depends on nothing; read-only — **COMPLETE (2026-10-20).**
   OQ-1 was pinned to OAuth2 `client_credentials` (one of the schemes SPEC-068 already
   ships, alongside `bearer`), so there is **no substrate change**; OQ-5 took the
   local-mock path — the connector is validated against a local mock target and live
   ServiceNow validation is a gated, separately-authorized operator step.
2. **Stage 1 — R-1 credential substrate (SPEC-068)** — a dependency, not built here;
   SPEC-068 is target-agnostic and does **not** depend on Stage 0. Gate: SPEC-068
   approved/built before this pilot authenticates a live target.
3. **Stage 2 — R-2 connector + R-3 policy** — depends on Stage 1.
4. **Stage 3 — R-4 audit + R-5 fail-closed** — depends on Stage 2.
5. **Stage 4 — R-6 provisioning + overlay** — depends on Stage 1 (fields) and Stage 2.
6. **Stage 5 — delivery boundary** — separate authorization (docs, CHANGELOG, version).

## Test Strategy

- unit tests: the REST-response→`ToolDefinition` mapping (the tool set is
  operator-declared, never target-derived); connector registration and read-tier-only
  exposure; the no-fabrication mapping (an upstream 4xx/5xx is a fact, never a
  fabricated success); and that the connector resolves its credential through
  SPEC-068's resolver (not a local re-implementation). The `credential_sets` parsing,
  bearer branch, and token-client cache/redaction tests live in SPEC-068. Redaction
  tests mirror SPEC-009 R-1's deterministic tool-output redaction.
- contract tests: policy-bundle scenarios (`make validate-policy-scenarios`),
  `make validate-policy` + `make policy-diff`, and `make validate-secret-vocabulary`.
- integration / overlay validation: `make overlays` renders the dev-k8s wiring; the
  connector is exercised against a **local mock ServiceNow REST target** (a stub
  `/api/now/table/...` responder, the `ansible-dev` mock pattern) so CI makes no live
  external call; live-PDI validation is a gated operator step per OQ-5's resolution
  (2026-10-20), never a CI dependency.

## Rollout And Migration

- deployment or configuration changes required: a ServiceNow credential-set entry
  (delivered through SPEC-068's provisioning model) + the `servicenow-dev` runtime-profile
  overlay and dev-k8s wiring. **No policy-bundle change** — the bundle is action-based,
  so read-tier `servicenow.*` tools ride the existing `tools:invoke` grant and
  deny-by-default lives at the connector admission allowlist (R-3).
- backward compatibility: the SPEC-068 substrate is inert until a non-`basic` set
  exists, and this pilot adds only the ServiceNow connector + its overlay (no bundle
  entries), so no current behavior moves.
- rollback approach: remove the ServiceNow credential set and its overlay; the
  REST connector is inert without them (it registers nothing when unconfigured, like
  `ansible_native.py`), so rollback needs no code revert and no bundle change. SPEC-068's
  additive scheme code is unaffected by this pilot's rollback.
