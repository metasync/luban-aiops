# SPEC-072: Auto-Routing Model Selection and Platform Feature-Flag Transparency

## Status

- status: `delivered`
- owner: chi
- created: 2026-11-02
- approved: 2026-11-02 (all seven Open Questions ratified; **OQ-5 resolved as a new
  authenticated `runtime:flags` policy action** rather than riding the unauthenticated
  `/api/v1/runtime` probe — see `## Open Questions — resolved`)
- delivered: 2026-11-02 as **v0.53.0** — R-1…R-7 implemented; full root `make verify` green; a
  pre-ship code & doc review found no blocking issues. The router stays default-off. Commit/push
  and deployment remain separate gates.
- release slice: post-v0.52.0 train — runtime-transparency family; target version
  **v0.53.0** (a minor bump over v0.52.0), closing at the next release train.
- related ADRs: [ADR-0003](../../adr/0003-platform-owned-agent-service-contract.md)
  (platform-owned v2 contract), [ADR-0006](../../adr/0006-contract-purpose-invariant-enforcement.md)
  (contract-purpose invariant enforcement). **No new ADR is expected**: the contract changes
  are *additive* (a new optional catalog envelope boolean, a reserved sentinel value on an
  existing string field, and a **new** `feature-flags` schema on a **new** read endpoint), and
  the one new policy action `runtime:flags` joins the existing deny-by-default bundle exactly
  as `models:list`/`documents:read` did — within the established action-vocabulary discipline,
  not a change to the trust model.
- extends: [SPEC-024](../SPEC-024-runtime-llm-model-switching/spec.md) (runtime LLM model
  switching / audited choice / portal selector), [SPEC-026](../SPEC-026-multi-model-runtime-catalog/spec.md)
  (model-name entry identity + series override), [SPEC-027](../SPEC-027-live-model-discovery/spec.md)
  (live discovery), and [SPEC-071](../SPEC-071-agentscope-model-router/spec.md) (per-turn
  model routing). Realizes the visibility thread SPEC-071 Open Question 4 opened ("surface the
  routed model + `model_selected_by`") and the operator's 2026-11-02 follow-up request for an
  explicit routing choice plus a Settings ▸ Platform feature-flag inventory.

> SDD note: `spec.md` was drafted first and **approved 2026-11-02** — the operator ratified all
> seven Open Questions, resolving OQ-5 as the authenticated `runtime:flags` action. Approval
> authorizes the [plan](plan.md) / [tasks](tasks.md) below and lets implementation **begin**.
> It does **not** authorize a merge, commit/push, deployment, or a version bump — those are
> separate boundaries (the SPEC-071 pattern), and the standing "review before any merge/deploy"
> constraint still governs.

## Summary

Give operators two things the runtime already knows but does not expose. **First**, an explicit
**"Auto (routed)"** choice in the composer's model selector so per-turn routing (SPEC-071)
becomes an intentional, pinnable selection instead of an invisible side effect of leaving the
model unset. **Second**, a **feature-flag inventory** — the critical opt-in platform toggles
(model routing, live discovery, context compression, outbound delegated identity, kernel
tracing, task tools, reply-token budget, HITL bridging, signed execution) as name + on/off —
served by a **new authenticated `GET /api/v1/runtime/flags`** endpoint behind a new
`runtime:flags` policy action and rendered read-only in the portal's Settings ▸ Platform pane,
so an operator can verify at a glance what is enabled in the live deployment. Feature A is an
additive model-catalog/chat-request change; Feature B adds a new discovery-safe read endpoint,
a new policy action, and a new contract schema. Both ship together in one release train.

## Motivation

- **Routing is real but invisible.** SPEC-071 shipped per-turn routing; the dev overlay now
  runs it default-on. Yet there is no way to *choose* routing from the portal: it fires only
  when a turn resolves to `selected_by == "default"` (no explicit model, no pin — see
  `routes.py:311-319`). An operator who wants "let the platform pick" has no control to
  select. The 2026-11-02 live check confirmed the gap: the only proof of routing is the
  response `model` field and a kernel log line, not any UI affordance.
- **The pin semantics make an explicit "auto" genuinely useful.** The chat handler pins
  **only an explicit request** (`if body.model: pin_session_model(...)`, `routes.py:317-318`)
  — a default-resolved turn never writes a pin, so today routing re-arms on *every* unset turn
  but cannot be *chosen* or *pinned* as a session posture. An `auto` sentinel that pins as
  `auto` lets a session opt into routing durably and deliberately.
- **Platform posture is not observable.** `AgentRuntimeMetadata` (`schemas/v2.py:568-574`)
  exposes `runtime_mode / runtime_state / provider / model_name / hint / last_error` and **no
  feature flags**, even though `_build_middlewares()` (`runtime_kernel.py:610-686`) is the
  ground truth for which opt-in surfaces are armed. The Settings ▸ Platform pane
  (`SettingsView.tsx:194` `PlatformPane`) renders component health but cannot answer "is model
  routing / delegated identity / compression on right now?" without a `kubectl exec` into the pod.
- **The operator chose to gate the inventory.** Because a flag inventory describes how the
  platform is *deployed*, OQ-5 resolved to serve it behind an authenticated `runtime:flags`
  action (granted to the operational roles) rather than adding it to the unauthenticated
  `/api/v1/runtime` probe — defense-in-depth even though the payload is non-secret booleans.
- **Why this slice.** Both are the operator-facing completion of work already shipped
  server-side (SPEC-071 routing; the SPEC-018/064/065/070 opt-in kernel surfaces). They share
  one theme (surface runtime state/control to the portal) and one release train, so they are
  specified together.

## Requirements

Each requirement is stable now that this spec is `approved` and carries testable acceptance
criteria. R-1…R-3 deliver the auto-routing selector; R-4…R-6 deliver the authenticated
feature-flag panel; R-7 reconciles contracts, policy, docs, and version.

### R-1: Catalog signals routing availability

`GET /api/v2/models` gains an additive envelope boolean telling the portal whether an
"Auto (routed)" choice is meaningful. Routing availability is a *deployment* property (is the
router configured at all), independent of any single turn.

Acceptance criteria:

- `model-catalog.schema.json` gains an **optional** `routing_available: boolean` on the
  envelope (`additionalProperties: false` retained; `models[]` entries and their closed
  `provider` enum are **unchanged**). The field is additive and defaults to `false`, so an
  older portal ignores it and a v0.52.0 catalog stays valid.
- `AgentModelCatalog` (`schemas/v2.py:558`) gains `routing_available: bool = False`;
  `ModelCatalog.public_models()` (`model_catalog.py:285`) emits it.
- The value is the **same condition the kernel uses to arm the router** —
  `settings.model_router_enabled and bool(settings.model_router_candidates)` (mirrors
  `_router_armed()` at `runtime_kernel.py:595-608` minus the per-turn `routing_allowed`), so
  the catalog and the kernel can never disagree about whether routing exists. This is the same
  value R-4 reports as the `model_routing` flag, on a different (broader) surface.
- **`auto` is never a catalog model entry.** No entry with `id == "auto"` is ever emitted; the
  sentinel lives only in the chat-request `model` field (R-2) and the portal option (R-3). This
  preserves SPEC-026 R-2's "entry id equals the model name" invariant and the closed provider enum.
- Tests: envelope carries `routing_available: true` iff the router is enabled with a non-empty
  candidate map, else `false`; schema validation of both shapes; `models[]` is byte-identical
  to v0.52.0 for the same catalog (no synthetic entry injected).

### R-2: `auto` sentinel selection and resolution

The chat request `model` field accepts a reserved `auto` sentinel meaning "route this turn."
`_resolve_model` and the pin logic handle it so an explicit auto choice arms routing and a
pinned auto choice keeps arming it across turns.

Acceptance criteria:

- **Reserved sentinel.** `auto` is reserved: catalog construction fails startup with a clear
  error if any real model would take the id `auto` (collision guard, same posture as SPEC-026
  R-2's duplicate-model-name startup failure). `agent-chat-request.schema.json` documents
  `auto` as the one non-catalog-id value the `model` field accepts.
- **Resolution.** `_resolve_model(requested, pinned)` (`routes.py:263`) returns
  `selected_by ∈ {request, pin, auto, default}` (adds `auto`). Precedence is
  `request(concrete) > request(auto) > pinned(concrete) > pinned(auto) > default`, an additive
  refinement of SPEC-024 R-3 / SPEC-071 R-2 — an explicit choice (concrete *or* auto) still
  beats a pin. When `auto` resolves, the returned base model id is the catalog **default
  entry** (the model the router swaps *from*, and the fail-soft fallback if routing errors).
- **Routing arms for auto and default.** `routing_allowed = selected_by in {"auto", "default"}`
  (was `== "default"` at `routes.py:319` and `:384`). Both `POST /chat` and `GET /chat/stream`
  change identically.
- **Pin stores the sentinel, not the resolved base.** When `body.model == "auto"`, the session
  pin is written as `"auto"` (not the concrete default), so the next turn resolves
  `pinned == "auto"` → routing arms again. A concrete request still pins its concrete id
  (unchanged). This is the crux that makes auto a durable session posture.
- **Fail-closed vs. degrade (request/pin asymmetry, mirrors SPEC-026 R-3).** An explicit
  `model="auto"` when routing is **unavailable** (R-1 false) is refused `422` (same posture as
  an unknown model id). A session **pinned** `"auto"` whose routing later becomes unavailable
  (router disabled or candidate map emptied) **degrades to the catalog default**
  (`selected_by="default"`, no hard failure), exactly like a pin whose model lost credentials.
- **Attribution unchanged.** The SPEC-071 `model_selected_by ∈ {request, pin, router, default}`
  *audit* dimension is unchanged: an auto (or default) turn that routes attributes the serving
  model to `router`; the new `auto` value is a *resolution-provenance* detail on the structured
  log (`routes.py:329`), not a new audit `event_type` and not a new audit attribution value.
- **Identity/policy/HITL untouched.** `auto` is metadata only: it never influences
  authorization, HITL gating, or auto-allow (SPEC-024 R-3 posture). A parked-confirmation
  session still refuses a model change with `409` (`_reject_if_parked`, `routes.py:310`).
- Tests: explicit `auto` (routing on) arms routing + pins `"auto"`; second turn with no request
  re-arms from the pin; explicit `auto` (routing off) → `422`; pinned `auto` with routing
  removed → degrades to default, no raise; concrete request/pin still overrides auto; startup
  fails if a model is literally named `auto`; `model_selected_by == "router"` on a routed auto
  turn; `409` still returned for a parked session.

### R-3: Portal "Auto (routed)" selector entry

`ModelSelect.tsx` offers "Auto (routed)" as a first-class choice when the catalog says routing
is available, and the chat view honors a pinned `auto` on reopened sessions.

Acceptance criteria:

- `ModelCatalogResponse` (`api/models.ts:13`) gains `routing_available?: boolean` and
  `getModelCatalog` passes it through.
- When `catalog.routing_available` is `true`, the selector renders an **"Auto (routed)"**
  option (value `"auto"`) as its own group at the top of the dropdown, above the per-provider
  model groups. When `false`, the option is absent and the component is byte-identical to today.
- The **single-model fixed-label** shortcut (`ModelSelect.tsx:31-42`) now renders a dropdown
  when `routing_available` is true (one model + auto = two choices); it stays a fixed label
  only when there is exactly one model **and** routing is unavailable.
- Selecting "Auto (routed)" sends `model: "auto"` on the next turn and pins it; the selector
  keeps showing "Auto (routed)" as the session's choice while each turn's *actual* served model
  remains visible in the transcript/response `model` field (SPEC-071 OQ-4 visibility preserved).
- `ChatView.tsx`'s pin-reconciliation (`:1897-1904`, which checks `catalog.models.some(entry =>
  entry.id === detail.model)`) additionally accepts `detail.model === "auto"` when
  `routing_available`, so a reopened auto session shows "Auto (routed)" rather than falling
  back to the default.
- Tests (vitest, `ModelSelect.test.tsx` pattern): auto option present iff `routing_available`;
  single-model + routing renders a `Select` not the fixed label; choosing auto calls
  `onChange("auto")`; a pinned `"auto"` value renders as selected; catalog unavailable → still
  renders nothing.

### R-4: Authenticated feature-flag inventory (agent-service)

The agent-service exposes the curated feature-flag inventory on a **new** authenticated
read endpoint — **not** on the existing unauthenticated `/api/v2/runtime` probe, which stays
byte-unchanged. Flags are computed from live settings and never carry a secret value.

Acceptance criteria:

- **New endpoint** `GET /api/v2/runtime/flags` requiring the `X-User-ID` header (the same
  posture as `GET /api/v2/models`, `routes.py:1927-1937`), returning a new `AgentFeatureFlags`
  response model: `{ feature_flags: [{ name, enabled, label? }] }`.
- **New contract schema** `shared/shared-contracts/schemas/feature-flags.schema.json`
  (`additionalProperties: false`; `name` a stable snake_case id, `enabled` boolean, `label`
  optional human text). `AgentRuntimeMetadata` and `agent-runtime-metadata.schema.json` are
  **unchanged** — the unauthenticated probe never carries flags.
- The inventory is a **curated allowlist** derived from `RuntimeSettings` / `_build_middlewares()`:
  `model_routing` (enabled **and** candidates present — equal to R-1's `routing_available`),
  `model_discovery`, `context_compression`, `outbound_delegated_identity`
  (`target_authorization_enabled`), `kernel_tracing`, `task_tools`, `reply_token_budget`
  (budget configured), `hitl_bridging` (`hitl_confirm_timeout > 0`), `signed_execution`
  (signing key configured).
- **Discovery-safe by construction.** Each flag is a boolean plus a stable name/label — never a
  key, URL, JWKS, budget number, or timeout value. A flag whose underlying setting is a secret
  (e.g. `execution_signing_key`) reports only *configured / not configured*.
- Always-on invariants with no knob (permission, evidence, and SPEC-065 token-observation
  middleware) are **out of scope** — the panel reports toggles, not invariants.
- Tests: `feature_flags` reflects the settings (each flag flips with its knob); the payload
  contains no secret substring (assert against the runtime-secrets vocabulary); schema
  validation of `/api/v2/runtime/flags`; `/api/v2/runtime` stays byte-identical to v0.52.0;
  `model_routing` equals `routing_available` for the same settings.

### R-5: Gateway proxy + `runtime:flags` policy action

Platform-gateway relays the inventory behind a new `runtime:flags` policy action, mirroring the
`models:list` pass-through (`api/routes/models.py`) exactly.

Acceptance criteria:

- **New action** `ACTION_RUNTIME_FLAGS = "runtime:flags"` in `policy_engine.py`, added to
  `PROTECTED_ACTIONS`, following the `<resource>:<verb>` convention.
- **New route** `GET /api/v1/runtime/flags`: `resolve_request_identity` → `enforce_policy(
  ACTION_RUNTIME_FLAGS)` → proxy → `log_event("runtime_flags_listed", …)`. New
  `agent_client.feature_flags()` + `gateway_service.feature_flags()` with the `list_models`
  error posture (upstream 4xx passes through; transport/5xx → `502`).
- **Grant: the operational trio** `platform-admin`, `approver`, `operator` — matching the
  `documents:read`/`session:skill_draft`/`session:skill_graduate` convention for operational
  information. `developer`, `read-only-observer`, and `auditor` are **denied by default**
  (standard audited policy 403). Rationale: a flag inventory describes how the platform is
  deployed/configured — an operational concern, not a chat-surface read like `models:list`.
- **Bundle parity (SPEC-048).** The new rule is added identically to **all four** bundle
  mirrors — `shared/shared-contracts/policies/policy-default.yaml`,
  `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`,
  `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, and
  `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` — and `policy-scenarios.yaml`
  gains allow/deny expectations for `runtime:flags`. The bundle `version` (format version) does
  **not** bump on a rule edit; `make verify` runs `validate_policy` + the scenario harness.
- **The base `/api/v1/runtime` is unchanged** — it stays the unauthenticated probe and carries
  no flags. No new audit `event_type`: the read rides the existing gateway log event + the
  `_emit_policy_decision` every enforced action already records.
- Tests: `runtime:flags` allowed for the trio and denied (403) for developer/observer/auditor;
  scenario harness green; gateway `/api/v1/runtime/flags` relays the agent payload verbatim and
  validates against `feature-flags.schema.json`; a denied role's 403 carries `action:
  "runtime:flags"`; `/api/v1/runtime` still returns no `feature_flags`.

### R-6: Portal Settings ▸ Platform feature-flags panel

`PlatformPane` fetches the inventory over the authenticated client and renders it read-only,
degrading gracefully when the caller lacks `runtime:flags` or the probe fails.

Acceptance criteria:

- A new `getRuntimeFlags(signal?)` in `api/` mirrors `getModelCatalog` — `requestJson<…>(
  "/api/v1/runtime/flags")`, which attaches the session bearer (`client.ts:60-63`).
- `SettingsView.tsx`'s `PlatformPane` (`:194`) renders a **"Feature flags"** section: each
  flag's label (or name) with an on/off `Tag` reusing the pane's existing status vocabulary.
- **Graceful degradation.** On `403` (role lacks `runtime:flags`), on any `ApiError`, or when
  the field is absent, the section shows "unavailable" — the pane's existing degrade posture —
  rather than guessing or showing stale values. The unauthenticated component-health rows are
  unaffected and still render for every role.
- Read-only: the panel changes nothing and exposes no control — it is a verification surface,
  not a toggle UI (toggling flags stays a deploy-time/GitOps action).
- Tests (vitest): flags render with correct on/off state for a granted role; a `403`/error
  degrades the section to "unavailable" while the health rows persist; no secret value is
  rendered (only names/labels + booleans).

### R-7: Contracts, policy, documentation, and version reconciliation

Acceptance criteria:

- **Contracts touched (all additive):** `model-catalog.schema.json` (`routing_available`),
  `agent-chat-request.schema.json` (document the `auto` sentinel), a **new**
  `feature-flags.schema.json`, and — verify at plan time — `agent-session.schema.json` must
  tolerate a pinned `model` value of `"auto"` (the session-detail `model` field).
  `agent-runtime-metadata.schema.json` is **unchanged**. Contract fixtures and the gateway
  mirror models updated in lockstep.
- **Policy touched:** `policy_engine.py` (`ACTION_RUNTIME_FLAGS` + `PROTECTED_ACTIONS`), the
  four bundle mirrors, and `policy-scenarios.yaml`.
- `docs/guides/configuration-reference.md` documents the `auto` sentinel, the
  `routing_available` signal, and the feature-flag inventory (names + meaning + the
  `runtime:flags` grant), cross-referencing the SPEC-071 router knobs.
- `docs/agentic-aiops-platform/authorization-matrix.md` and `docs/guides/architecture-overview.md`
  gain the `runtime:flags` row/rule; `products/platform-gateway/README.md` notes the new gated
  route; `docs/specs/README.md` carries the SPEC-072 row (added at `draft`, updated on approval).
- Living docs on delivery: root `CHANGELOG.md` (accumulate under `## Unreleased` until the
  release train closes), the operator guide (how to read the Platform flags panel + choose
  Auto), product READMEs as needed, and a release note.
- **VERSION bumps in the product lockstep** at release (`make validate-version` green); target
  **v0.53.0** (MINOR — new operator-facing capability + a new policy action, additive contracts).
- The [delivery-roadmap](../../agentic-aiops-platform/delivery-roadmap.md) and the SPEC-071
  visibility follow-up note are reconciled to point at this spec.

## Failure modes and test matrix

Each row is an observable scenario, its required behavior, and the test that pins it.
`A` = auto-routing selector, `F` = feature-flag panel, `X` = cross-cutting.

| # | Scenario | Required behavior | Test |
| --- | --- | --- | --- |
| A1 | Router enabled + candidates; `GET /api/v2/models` | `routing_available: true`; no `auto` entry in `models[]` | catalog contract + unit |
| A2 | Router disabled or no candidates | `routing_available: false`; catalog byte-identical to v0.52.0 | catalog unit |
| A3 | Explicit `model="auto"`, routing available | routing arms; base = default entry; pin stored as `"auto"` | `_resolve_model` + chat handler |
| A4 | Second turn, no request, session pinned `"auto"` | routing re-arms from the pin (`selected_by="auto"`) | chat handler |
| A5 | Explicit `model="auto"`, routing unavailable | `422` fail-closed (unknown-selection posture) | chat handler |
| A6 | Session pinned `"auto"`, routing later disabled | degrades to catalog default; no raise; turn succeeds | `_resolve_model` |
| A7 | Concrete model requested/pinned while routing on | routing does **not** fire; `selected_by ∈ {request, pin}` | precedence test |
| A8 | A real model is literally named `auto` | startup fails with a clear reserved-sentinel error | catalog startup guard |
| A9 | Routed auto turn | response `model` = effective (routed) id; `model_selected_by="router"` | chat + attribution |
| A10 | Model change against a parked-HITL session | `409`, unchanged | parked-session test |
| A11 | Portal: `routing_available` true | "Auto (routed)" option rendered atop the dropdown | `ModelSelect.test.tsx` |
| A12 | Portal: single model + routing available | dropdown (not the fixed label) | `ModelSelect.test.tsx` |
| A13 | Portal: reopened session pinned `"auto"` | selector shows "Auto (routed)" selected | `ChatView` reconciliation |
| F1 | Knobs in a given configuration; `GET /api/v2/runtime/flags` | `feature_flags` reports each name's correct `enabled` | runtime-flags unit |
| F2 | Flags payload inspection | no secret substring (keys/JWKS/budget/timeout values) present | vocabulary guard |
| F3 | `model_routing` flag vs `routing_available` | identical for the same settings | cross-surface parity |
| F4 | `GET /api/v1/runtime/flags`, role ∈ {platform-admin, approver, operator} | `200`, flags relayed verbatim; schema-valid; `runtime_flags_listed` logged | gateway proxy test |
| F5 | `GET /api/v1/runtime/flags`, role ∈ {developer, observer, auditor} | `403` with `action: "runtime:flags"`; policy decision recorded | policy + proxy test |
| F6 | `GET /api/v1/runtime` (base probe), any/no role | unchanged; **no** `feature_flags` field | agent-runtime-metadata contract |
| F7 | Bundle parity + scenario harness | four mirrors identical; `policy-scenarios.yaml` allow/deny green under `make verify` | policy validate + harness |
| F8 | Portal: granted role | flags render label + on/off Tag | `PlatformPane` vitest |
| F9 | Portal: `403` / probe failure / field absent | flags section degrades to "unavailable"; health rows persist | `PlatformPane` vitest |
| X1 | Contract stability | unrelated v2 fields byte-stable; schemas additive; `agent-runtime-metadata` untouched; `make verify` green | contract suite |

## Non-Goals

- **No router behavioral change.** The classifier, candidate map, precedence, fail-soft, and
  resume semantics stay exactly as SPEC-071 delivered them; this spec only adds a way to
  *select* routing and to *observe* flags. No change to routing accuracy or the R-3 measurement.
- **No global default-on flip.** The kernel `model_router_enabled` default stays `False`;
  default-on remains a dev-overlay, measurement-gated operator decision (SPEC-071 R-3).
- **No flag *control* from the portal.** The panel is read-only verification; toggling any flag
  stays a deploy-time/GitOps action. No write endpoint.
- **The unauthenticated `/api/v1/runtime` probe is unchanged.** Flags do **not** ride it; they
  live only behind the authenticated `runtime:flags` action (OQ-5). `AgentRuntimeMetadata` and
  its schema are untouched.
- **No per-user/per-role flag *values***, no flag change-history, and no always-on-invariant
  reporting (permission/evidence/token-observation have no knob).
- **No change to the governed execution path, approval/HITL model, or read-only posture**, and
  no new audit `event_type`.
- **No new dependency** and no agentscope type leaks through the v2 contract (SPEC-018 gate 4).

## Impact

- **products touched:** `products/agent-platform` (catalog envelope, `_resolve_model`, chat +
  stream handlers, the new `/api/v2/runtime/flags` route + `AgentFeatureFlags` model, the
  settings→flags mapping, the reserved-sentinel startup guard), `products/platform-gateway`
  (`ACTION_RUNTIME_FLAGS` + `PROTECTED_ACTIONS`, the new `/api/v1/runtime/flags` route,
  `agent_client`/`gateway_service` proxies, the bundle), `products/operator-portal`
  (`ModelSelect`, `ChatView` reconciliation, `api/models.ts`, a new `api` flags client,
  `SettingsView` `PlatformPane`).
- **contracts touched (all additive):** `model-catalog.schema.json`, `agent-chat-request.schema.json`,
  a **new** `feature-flags.schema.json`, and possibly `agent-session.schema.json` (pinned `model`
  may be `"auto"`). `agent-runtime-metadata.schema.json` and `agent-stream-event.schema.json`
  stay byte-unchanged. No closed enum is widened except the documented `auto` sentinel on the
  free-string `model` field.
- **policy touched:** one new action `runtime:flags` (granted to `platform-admin`/`approver`/
  `operator`), added to `policy_engine.py` + `PROTECTED_ACTIONS` + all four bundle mirrors +
  `policy-scenarios.yaml`. Deny-by-default semantics unchanged; no new audit `event_type`.
- **identity / execution safety impact:** none by design. `auto` and the flags are metadata;
  `auto` never influences authorization, HITL, or auto-allow. The flags read is authenticated
  and policy-gated, discloses only booleans, and is recorded by the existing policy-decision
  emission + a gateway log event.
- **living state docs to update on delivery:** root `CHANGELOG.md`, `docs/specs/README.md`,
  `docs/guides/configuration-reference.md`, `docs/agentic-aiops-platform/authorization-matrix.md`,
  `docs/guides/architecture-overview.md`, the operator guide, `products/platform-gateway/README.md`,
  a release note, and `VERSION` (lockstep bump at the release train).

## Open Questions — resolved (ratified 2026-11-02)

All seven Open Questions are resolved; each decision below is binding on R-1…R-7.

1. **Auto representation — resolved: a reserved `auto` sentinel on the chat `model` field + an
   additive `routing_available` envelope boolean; NOT a synthetic catalog model entry.** A fake
   entry would violate the closed `provider` enum and SPEC-026 R-2's "id = model name"
   invariant, and would pollute audit attribution and the fail-closed unknown-id guard.
2. **Auto precedence & attribution — resolved: routing arms for `selected_by ∈ {auto, default}`;
   an explicit `auto` beats a concrete pin; the SPEC-071 `model_selected_by` audit vocabulary
   stays `{request, pin, router, default}`** (an auto turn that routes attributes to `router`);
   `auto` is added only to `_resolve_model`'s resolution-provenance log value.
3. **Auto when routing is unavailable — resolved: explicit `model="auto"` → `422` fail-closed;
   a pinned `"auto"` → degrade to the catalog default** (mirrors the existing request/pin
   asymmetry and SPEC-026 R-3's key-revocation degrade).
4. **Feature-flag inventory scope — resolved: the curated nine-flag allowlist in R-4**
   (model_routing, model_discovery, context_compression, outbound_delegated_identity,
   kernel_tracing, task_tools, reply_token_budget, hitl_bridging, signed_execution), each
   name + enabled (+ optional label), no secret values; always-on invariants excluded.
5. **Feature-flag exposure surface — resolved (operator choice): a NEW authenticated
   `GET /api/v1/runtime/flags` behind a new `runtime:flags` policy action**, granted to the
   operational trio `platform-admin`/`approver`/`operator` and denied to
   `developer`/`read-only-observer`/`auditor`. The flags do **not** ride the unauthenticated
   `/api/v1/runtime`; `AgentRuntimeMetadata` is unchanged. Chosen over the unauthenticated
   probe for defense-in-depth: a flag inventory describes deployment posture, so it is treated
   as an operational read even though the payload is non-secret booleans.
6. **One spec vs. two — resolved: one spec, two requirement groups.** Both share the portal and
   a single release train; splitting would duplicate the contract-versioning and docs work.
7. **Target version — resolved: v0.53.0** (MINOR bump; additive contracts + a new policy action
   + new operator-facing capability), accumulating under `## Unreleased` until the train closes.

## Changelog

- 2026-11-02: **delivered as v0.53.0.** R-1…R-7 implemented and the full root `make verify` is
  green (eight product suites — agent-platform 1681 · tool-gateway 1066 · platform-gateway 481 ·
  skills-hub 291 · audit-service 147 · incident-service 138 · execution-runtime 94 ·
  identity-broker 63; 7 overlays + dashboards; policy 21 rules + scenarios; version-lockstep +
  secret-vocabulary + password-policy; portal vitest 546 + `vite build`; the delegated
  custody/runtime/multiproc/edge legs; and the SPEC-063 execution-failure campaign 795 passed,
  exit 0). A pre-ship code & doc review found no blocking issues; its one Low finding — the
  `architecture-overview.md` Default Policy Bundle table undercounting the allow rules
  (“nineteen” → **twenty**, adding the omitted `allow-operators-targets-authorize` row) — is
  corrected. VERSION + the 18 product literals bumped 0.52.0 → 0.53.0 (`make validate-version`
  green); the spec index and this status flipped to `delivered`; `CHANGELOG.md` closed into
  `## 0.53.0` with a [release note](../../agentic-aiops-platform/release-notes/2026-11-02-auto-routing-and-platform-feature-flags.md).
  The router stays default-off. Commit/push and deployment remain separate gates.
- 2026-11-02: **implementation begun — Stage-0 seam verification complete.** One refinement over
  the approved text: `_resolve_model` has **five** callers, not two — beyond `chat`/`chat_stream`,
  the park/expire/resume paths (`chat_confirm`'s 410-expiry branch and its resume `_events`, and
  `_reject_if_parked`) also resolve the model and gate `routing_allowed` on `selected_by ==
  "default"`. R-2's `routing_allowed = selected_by in {"auto", "default"}` therefore applies to
  **all five** so a parked auto session resumes/expires on the same router-armed agent (the
  SPEC-071 `::routed` cache-key match); the `auto` resolution, pin-the-sentinel, and 422/degrade
  logic are unchanged from the approved design. S0-2…S0-5 confirmed as planned: the reserved-`auto`
  guard lands in `build_entries` (which runs at module-import startup, so it fails startup; live
  `refresh_catalog` fail-softs); `model_selected_by` is free-form structured-log only (no
  closed-enum validation anywhere); bundle parity is maintained by `make sync-policy` (canonical →
  three mirrors); `agent-session.schema.json`'s `model` is already a free string.
- 2026-11-02: **approved** — the operator ratified all seven Open Questions, resolving **OQ-5
  as a new authenticated `runtime:flags` policy action** (`GET /api/v1/runtime/flags`, granted
  to `platform-admin`/`approver`/`operator`) rather than extending the unauthenticated
  `/api/v1/runtime`. This reshaped R-4 (a new `/api/v2/runtime/flags` agent endpoint + a new
  `feature-flags.schema.json` instead of extending `AgentRuntimeMetadata`), R-5 (the gateway
  proxy + the new action across `policy_engine.py`, the four bundle mirrors, and
  `policy-scenarios.yaml`), and R-6 (an authenticated portal fetch that degrades on `403`), and
  added the policy footprint to Impact/Non-Goals/the failure matrix. Target version v0.53.0;
  the [plan](plan.md) and [tasks](tasks.md) are written and binding — implementation is
  authorized to *begin* (not to merge, commit/push, deploy, or version-bump).
- 2026-11-02: created as `draft` — promotes the operator's 2026-11-02 follow-up request (an
  explicit "Auto (routed)" model choice + a Settings ▸ Platform feature-flag panel) into a
  spec, grounded in static inspection of the v0.52.0 surfaces (`routes.py` `_resolve_model` /
  chat handlers, `model_catalog.py`, `schemas/v2.py` `AgentRuntimeMetadata` / `AgentModelCatalog`,
  `runtime_kernel.py` `_build_middlewares` / `runtime_metadata`, the gateway `runtime_status`,
  `policy_engine.py` + the `policy-default.yaml` bundle, `ModelSelect.tsx` / `api/models.ts` /
  `SettingsView.tsx` `PlatformPane`, and the `model-catalog` / `agent-runtime-metadata` /
  `agent-chat-request` schemas). Seven Open Questions carried proposed defaults. No product
  code, contract, policy, GitOps, deployment, or version change was authorized by the draft.
