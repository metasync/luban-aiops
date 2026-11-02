# v0.53.0 — Auto-Routing Selection and Platform Feature-Flag Transparency (SPEC-072)

Date: 2026-11-02
Release type: minor (additive operator-facing transparency — one new
authenticated read endpoint (`GET /api/v1/runtime/flags` + its agent-side
`GET /api/v2/runtime/flags`), one new `runtime:flags` policy action, and one new
`feature-flags.schema.json`; a reserved `auto` sentinel on the existing chat
`model` string field plus an additive `routing_available` boolean on the catalog
envelope. No new audit event type; `agent-runtime-metadata.schema.json` and
`agent-stream-event.schema.json` are byte-unchanged; the unauthenticated
`/api/v1/runtime` probe carries no flags. The router stays **default-off** — no
global default-on flip.)

## Summary

This release ships
[SPEC-072](../../specs/SPEC-072-auto-routing-and-platform-feature-flags/spec.md),
which surfaces two things the runtime already knows but did not expose. It
realizes the visibility thread
[SPEC-071 Open Question 4](../../specs/SPEC-071-agentscope-model-router/spec.md)
opened ("surface the routed model + `model_selected_by`") and the operator's
2026-11-02 follow-up request for an explicit routing choice plus a Settings ▸
Platform feature-flag inventory.

**First — an explicit "Auto (routed)" model choice.** [SPEC-071](../../specs/SPEC-071-agentscope-model-router/spec.md)
shipped per-turn routing and the dev overlay now runs it default-on, yet routing
fired only as an invisible side effect of leaving the model unset. An operator
who wants "let the platform pick" had no control to select. This release adds a
reserved `auto` sentinel on the chat `model` field, so choosing **Auto (routed)**
becomes an intentional, pinnable session posture rather than an accident of an
empty field.

**Second — a curated feature-flag inventory.** The critical opt-in platform
toggles are now readable at a glance from the portal's Settings ▸ Platform pane,
served by a **new authenticated `GET /api/v1/runtime/flags`** endpoint behind a
new `runtime:flags` policy action. Each flag is reported as a stable name plus an
on/off boolean — **never a secret value** — so an operator can verify what is
actually enabled in the live deployment without reading GitOps or exec-ing into a
pod.

Both features ship together in one release train. Feature A is an additive
model-catalog/chat-request change; Feature B adds a new discovery-safe read
endpoint, a new policy action, and a new contract schema.

## What shipped

### Feature A — the "Auto (routed)" selector (R-1…R-3)

- **R-1 — Catalog signal (`agent-platform`).** The catalog envelope gains an
  additive `routing_available` boolean, and the chat `model` field documents a
  reserved `auto` sentinel. `AgentKernel.routing_available()` —
  `bool(settings.model_router_enabled and settings.model_router_candidates)` — is
  the single keystone value; a startup guard in `build_entries` fails fast if any
  configured model is literally named `auto`, so the sentinel can never collide
  with a real entry. With routing off, `models[]` is byte-identical to v0.52.0.
- **R-2 — Resolution + pinning (`agent-platform`).** `_resolve_model` arms
  routing for `selected_by ∈ {auto, default}`, extending SPEC-024's audited
  precedence to `request > pinned > routed > default` without changing its
  request/pin semantics. Choosing `auto` **pins the sentinel** to the session, so
  a request-less turn re-arms routing each turn (the SPEC-071 `::routed`
  cache-key match survives a park/resume across all five `_resolve_model`
  callers). Fail-closed edges: an **explicit** `auto` while routing is
  unavailable returns `422`; a **pinned** `auto` whose routing is later removed
  degrades to the default model (no raise). A routed turn is attributed to the
  router (`model_selected_by == "router"`) on the structured-log path — no new
  audit event type.
- **R-3 — Portal selector (`operator-portal`).** `ModelSelect.tsx` leads with an
  explicit **Auto (routed)** entry **iff** `routing_available` is true; when
  routing is off the entry is absent and a single configured model still renders
  as a fixed label. A reopened session pinned to `"auto"` reconciles to the
  selected state.

### Feature B — the feature-flag inventory (R-4…R-6)

- **R-4 — Agent endpoint + schema (`agent-platform`, `shared-contracts`).** A new
  authenticated `GET /api/v2/runtime/flags` returns `AgentFeatureFlags`, the new
  `feature-flags.schema.json` envelope: an array of `{name, enabled, label?}`
  over a curated allowlist of nine deployment toggles —
  `model_routing`, `model_discovery`, `context_compression`,
  `outbound_delegated_identity`, `kernel_tracing`, `task_tools`,
  `reply_token_budget`, `hitl_bridging`, `signed_execution`. Discovery-safe by
  construction: a flag whose knob is a secret (e.g. `signed_execution` ←
  `execution_signing_key`) reports only configured / not configured, never the
  value. `model_routing` reuses `routing_available()`, so the catalog boolean
  (R-1), the `auto` branch (R-2), and this flag (R-4) read one value and can
  never disagree (failure-matrix row F3). Always-on invariants with no knob are
  deliberately absent — the inventory reports toggles, not invariants.
- **R-5 — Gateway proxy + policy action (`platform-gateway`).** A new
  `GET /api/v1/runtime/flags` proxies the agent endpoint behind the new
  `runtime:flags` policy action (grant: `platform-admin`, `approver`, `operator`;
  deny: `developer`, `read-only-observer`, `auditor`), relayed verbatim and
  logged as `runtime_flags_listed`. The action joins `policy_engine.py`
  (`ACTION_RUNTIME_FLAGS` + `PROTECTED_ACTIONS`), all four bundle mirrors (the new
  `allow-operators-runtime-flags` rule), and `policy-scenarios.yaml`, kept in
  parity by `make sync-policy`. The unauthenticated `/api/v1/runtime` probe stays
  flag-free.
- **R-6 — Portal panel (`operator-portal`).** `SettingsView.tsx`'s
  `PlatformPane` fetches the inventory over the authenticated client
  (`getRuntimeFlags`, mirroring `getModelCatalog`) and renders a read-only
  **Feature flags** section — each flag's label (or name) with an on/off `Tag`
  reusing the pane's existing status vocabulary. **Graceful degradation:** on
  `403` (role lacks `runtime:flags`), on any `ApiError`, or when the field is
  absent, the section shows *unavailable* while the unauthenticated
  component-health rows above persist for every role. It exposes no control —
  toggling flags stays a deploy-time/GitOps action.

## Changed

- **Living docs.** `docs/guides/configuration-reference.md` documents the `auto`
  sentinel, the `routing_available` signal, and the feature-flag inventory (names
  + meaning + the `runtime:flags` grant), cross-referencing the SPEC-071 router
  knobs; `docs/agentic-aiops-platform/authorization-matrix.md` and
  `docs/guides/architecture-overview.md` gain the `runtime:flags` row/rule;
  `products/platform-gateway/README.md` notes the new gated route; and the
  operator guide (`docs/guides/portal-user-guide.md`) explains how to choose
  **Auto (routed)** and how to read the Platform flags panel. The
  [delivery-roadmap](../delivery-roadmap.md) and the SPEC-071 visibility
  follow-up note are reconciled to point at this spec, and the
  [specs index](../../specs/README.md) row moves to `delivered`.
- **Doc-accuracy correction.** `docs/guides/architecture-overview.md`'s Default
  Policy Bundle table was corrected from "nineteen" to **twenty** allow rules and
  gained the previously-omitted `allow-operators-targets-authorize` row
  (SPEC-070), so the table now matches the shipped bundle (20 allow + 1
  `require-approval` = 21 rules). Found in the pre-ship code & doc review.
- **Contracts (all additive).** `model-catalog.schema.json` (`routing_available`),
  `agent-chat-request.schema.json` (the documented `auto` sentinel), the new
  `feature-flags.schema.json`, and `agent-session.schema.json` (already a free
  string, so a pinned `"auto"` needs no change). Gateway mirror models updated in
  lockstep; contract fixtures refreshed. `agent-runtime-metadata.schema.json` and
  `agent-stream-event.schema.json` are unchanged.

## Verification

- `make verify` green with the shipped diff: the eight product suites
  (agent-platform 1681 · tool-gateway 1066 · platform-gateway 481 · skills-hub
  291 · audit-service 147 · incident-service 138 · execution-runtime 94 ·
  identity-broker 63), 7 GitOps overlays + dashboards, policy (21 rules) +
  scenarios (api 151/96, tools 32/21), version-lockstep + secret-vocabulary +
  password-policy, the operator-portal suite (vitest 546) + `vite build`, the
  delegated custody/runtime/multiproc/edge legs, and the SPEC-063
  execution-failure campaign (795 passed, exit 0).
- The acceptance-to-test matrix (rows A1–A13 / F1–F9 / X1) is fully pinned: the
  catalog boolean and byte-stability, the `auto` arm/re-arm/`422`/degrade edges
  and router attribution, the `ModelSelect` "Auto (routed)"-iff-`routing_available`
  render, each flag's correct `enabled`, the no-secret-substring vocabulary guard,
  the cross-surface `model_routing == routing_available` parity (F3), the gateway
  verbatim relay + `runtime_flags_listed`, the developer/observer/auditor `403`,
  the flag-free `/api/v1/runtime` metadata contract, and the `PlatformPane`
  render + degrade-to-*unavailable* vitests.
- A pre-ship code & doc review (CodeReview) found no Critical/High/Medium issues;
  the one Low doc-accuracy finding (the architecture-overview allow-rule count)
  is corrected above.
- `make validate-version` green at **0.53.0** across the eight products and the
  portal.

## Posture

Additive and transparency-only. Feature A changes behavior **only** when an
operator explicitly selects **Auto (routed)** (which requires routing to be
enabled); with routing off the catalog, resolution, and selector are
byte-identical to v0.52.0, and the **router stays default-off** — any global
default-on flip remains a separate, measurement-gated operator decision
(SPEC-071 R-3). Feature B is **read-only**: the new endpoint exposes flag names
and booleans, never a secret value, and is gated by a new least-privilege
`runtime:flags` action added to the existing deny-by-default bundle exactly as
`models:list`/`documents:read` were — within the established action-vocabulary
discipline, not a change to the trust model. No new audit event type, no new
identity edge, and no execution-path change. Commit/push and deployment remain
separate gates.
