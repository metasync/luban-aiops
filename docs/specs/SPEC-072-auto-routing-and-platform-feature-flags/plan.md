# SPEC-072 Plan: Auto-Routing Model Selection and Platform Feature-Flag Transparency

> **Binding.** `spec.md` is `approved` (2026-11-02) — all seven Open Questions ratified, OQ-5
> resolved as a new authenticated `runtime:flags` policy action. This plan is therefore firm,
> not provisional: it authorizes implementation to **begin**. It does **not** authorize a merge,
> commit/push, deployment, or a version bump — those are separate boundaries (the SPEC-071
> pattern), and the standing "review before any merge/deploy" constraint governs. Two features
> ship in one train: **A** the auto-routing selector (R-1…R-3), **B** the authenticated
> feature-flag panel (R-4…R-6), reconciled by R-7.

## Approach

Both features surface state the runtime already holds. **Feature A** makes SPEC-071's per-turn
routing an explicit, pinnable choice: a reserved `auto` sentinel on the chat `model` field plus
an additive `routing_available` boolean on the catalog envelope, so "let the platform pick"
becomes a selector entry instead of an invisible side effect of leaving the model unset.
**Feature B** exposes the curated opt-in flag inventory behind a **new authenticated**
`GET /api/v1/runtime/flags` gateway route (proxying a new agent `GET /api/v2/runtime/flags`)
gated by a **new** `runtime:flags` policy action — the unauthenticated `/api/v1/runtime` probe
and `AgentRuntimeMetadata` stay byte-unchanged (OQ-5).

The load-bearing design idea is a **single source of truth for routing availability**. One
kernel accessor — `AgentKernel.routing_available() == bool(settings.model_router_enabled and
settings.model_router_candidates)` (the deployment-level half of `_router_armed()`,
`runtime_kernel.py:595-608`, minus the per-turn `routing_allowed`) — feeds **all three**
consumers: R-1's catalog envelope boolean, R-2's `_resolve_model` auto/degrade branch, and R-4's
`model_routing` feature flag. Because the same expression drives the catalog signal and the
flag, failure-matrix row **F3** (cross-surface parity) holds *by construction*, and the kernel
can never disagree with the catalog about whether routing exists. Stages group the work:

- **Stage 0 — Seam verification (no product diff):** confirm the five integration facts this
  plan depends on (`_resolve_model` caller inventory + threading choice, the reserved-`auto`
  startup-guard location, the structured-log `model_selected_by` is not a closed-enum audit
  field, bundle-mirror parity gate, session-schema tolerance of a pinned `auto`).
- **Stage 1 — Routing-availability signal (R-1):** the kernel `routing_available()` accessor,
  the additive catalog envelope boolean, and the schema/model/route changes that carry it.
- **Stage 2 — `auto` sentinel resolution (R-2):** `_resolve_model` provenance + the chat/stream
  pin-and-arm changes + the reserved-sentinel startup guard + the chat-request schema note.
- **Stage 3 — Portal auto selector (R-3):** `api/models.ts`, `ModelSelect.tsx`, and the
  `ChatView.tsx` pin-reconciliation.
- **Stage 4 — Agent feature-flag endpoint (R-4):** the kernel `feature_flags()` mapping, the
  `AgentFeatureFlags` model, the new `/api/v2/runtime/flags` route, and `feature-flags.schema.json`.
- **Stage 5 — Gateway proxy + `runtime:flags` action (R-5):** `policy_engine.py`, the
  `agent_client`/`gateway_service` proxies, the new `/api/v1/runtime/flags` route, the four
  bundle mirrors, and `policy-scenarios.yaml`.
- **Stage 6 — Portal flags panel (R-6):** the authenticated `getRuntimeFlags()` client and the
  read-only `PlatformPane` section with graceful degradation.
- **Stage 7 — Contracts, docs, version reconciliation (R-7):** always; sweeps the living docs,
  configuration reference, authorization matrix, CHANGELOG, and the release-train version bump.

Feature A (Stages 1-3) and Feature B (Stages 4-6) are independent except that Stage 4 reuses
Stage 1's `routing_available()` accessor for the `model_routing` flag; Stage 1 is therefore the
shared keystone and lands first.

## Design Per Requirement

### R-1: Catalog signals routing availability

- **Affected files / modules:**
  - `products/agent-platform/src/agent_service/runtime_kernel.py` — new `routing_available()`
    accessor beside `_router_armed()` (:595-608): `bool(self.settings.model_router_enabled and
    self.settings.model_router_candidates)`. The single source of truth for R-1/R-2/R-4.
  - `products/agent-platform/src/agent_service/services/model_catalog.py` — `public_models()`
    (:285-293) gains an optional `routing_available: bool = False` parameter and emits it in the
    envelope dict. The catalog holds no `RuntimeSettings` reference, so the value is threaded by
    the caller (keeps the catalog settings-free and unit-testable).
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — `list_models` (:1927-1937)
    computes `get_runtime_kernel().routing_available()` and passes it to `public_models(...)`.
  - `products/agent-platform/src/agent_service/schemas/v2.py` — `AgentModelCatalog` (:558-562)
    gains `routing_available: bool = False`.
  - `shared/shared-contracts/schemas/model-catalog.schema.json` — add an **optional**
    `routing_available: {"type": "boolean"}` to the envelope `properties` (NOT to `required`;
    `additionalProperties: false` retained; `models[]` and the closed `provider` enum untouched).
- **Chosen approach:** additive envelope boolean defaulting to `false`, so a v0.52.0 catalog
  stays valid and an older portal ignores it. **`auto` is never a catalog entry** — no synthetic
  `id == "auto"` is emitted, preserving SPEC-026 R-2's "entry id = model name" invariant and the
  closed provider enum.
- **Alternatives considered:**
  - *Inject a synthetic "Auto (routed)" catalog entry* — rejected: it would need a `provider`
    value outside the closed enum and would break the id-equals-model-name invariant, polluting
    audit attribution and the fail-closed unknown-id guard (OQ-1).
  - *Compute `routing_available` inside `public_models()` from a stored settings ref* — rejected:
    the catalog is deliberately settings-free; threading the boolean from the kernel accessor
    keeps one source of truth and the catalog trivially testable.

### R-2: `auto` sentinel selection and resolution

- **Affected files / modules:**
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — `_resolve_model` (:263-292)
    gains the `auto` branch and returns `selected_by ∈ {request, pin, auto, default}`; `chat`
    (:298-355) and `chat_stream` (:358-411) change the pin write and `routing_allowed`
    identically.
  - `products/agent-platform/src/agent_service/services/model_catalog.py` — the reserved-sentinel
    startup guard on the catalog-build path (where SPEC-026 R-2's duplicate-model-name guard
    lives — confirm at Stage 0).
  - `shared/shared-contracts/schemas/agent-chat-request.schema.json` — the `model` field
    description documents `auto` as the one non-catalog-id value accepted (the field is already
    `["string","null"]`, so this is a **description-only** change; no structural edit).
- **Chosen approach — resolution.** `_resolve_model(requested, pinned, routing_available)`:
  - `requested == "auto"` → if `routing_available` return `(default_entry.id, "auto")`, else
    raise `422` (fail-closed, the unknown-selection posture).
  - `requested` concrete → unchanged (catalog lookup, `422` if unknown) → `"request"`.
  - `pinned == "auto"` → if `routing_available` return `(default_entry.id, "auto")`, else
    **degrade** to `(default_entry.id, "default")` (no raise — mirrors SPEC-026 R-3's
    key-revocation degrade).
  - `pinned` concrete → unchanged → `"pin"`; else → `"default"`.
  The auto base id is the catalog **default entry** — the model the router swaps *from* and the
  fail-soft fallback if routing errors. Precedence `request(concrete|auto) > pinned(concrete|auto)
  > default` is an additive refinement of SPEC-024 R-3 / SPEC-071 R-2: an explicit choice
  (concrete *or* auto) still beats a pin.
- **Chosen approach — threading `routing_available`.** Pass it as an explicit third parameter,
  computed once per turn as `get_runtime_kernel().routing_available()`, rather than reading the
  kernel inside `_resolve_model`. SPEC-071 already refactored all five callers to unpack the
  `(model_id, selected_by)` tuple (incl. the `chat_confirm` 410-expiry branch), so they are
  already touched; an explicit parameter keeps `_resolve_model` unit-testable without a kernel
  double. Confirm the full caller inventory at Stage 0.
- **Chosen approach — pin stores the sentinel.** In both handlers, replace
  `if body.model: pin_session_model(session_id, resolved_model)` with a pin value of `"auto"`
  when the request was the sentinel, else the concrete `resolved_model`:
  `pin = "auto" if body.model == "auto" else resolved_model; if body.model: pin_session_model(
  session_id, pin)`. This is the crux that makes auto a **durable session posture** — the next
  request-less turn resolves `pinned == "auto"` and re-arms. A concrete request still pins its
  concrete id (unchanged).
- **Chosen approach — routing arms for auto and default.** `routing_allowed = selected_by in
  {"auto", "default"}` (was `== "default"` at :319 and :384). Both handlers change identically.
- **Chosen approach — attribution split.** The SPEC-071 audit `model_selected_by ∈ {request, pin,
  router, default}` is **unchanged**: an auto (or default) turn that routes attributes the serving
  model to `router`. The new `auto` value appears only in the routes *structured log*
  `model_selected_by` extra (:329, :392) as resolution provenance — a free-form log field, not a
  new audit `event_type` and not a new closed-enum audit attribution. Stage 0 confirms the log
  field is not enum-validated anywhere.
- **Chosen approach — reserved-sentinel guard.** Catalog construction raises a clear startup
  error if any real model entry or alias would take the id `auto` (same posture as SPEC-026 R-2's
  duplicate-name startup failure), so the sentinel can never collide with a real model.
- **Identity/policy/HITL untouched:** `auto` is metadata only; it never influences authorization,
  HITL gating, or auto-allow. A parked-confirmation session still refuses a model change with
  `409` (`_reject_if_parked`, :310/:377).
- **Alternatives considered:**
  - *Resolve `auto` to a concrete default and pin that* — rejected: pinning the concrete default
    would make the next turn `selected_by == "pin"`, so routing would **not** re-arm; the session
    would silently lose its auto posture. Pinning the sentinel is what keeps routing armed.
  - *Read routing availability inside `_resolve_model` from the kernel* — rejected: couples a
    pure resolution function to kernel state and complicates unit tests; the explicit parameter
    is cleaner and the callers are already touched.
  - *Hard-fail a pinned `auto` when routing is later disabled* — rejected: violates the
    request/pin asymmetry (SPEC-026 R-3); a pin degrades, only an explicit request fails closed.

### R-3: Portal "Auto (routed)" selector entry

- **Affected files / modules:**
  - `products/operator-portal/web-ui/app/src/api/models.ts` — `ModelCatalogResponse` (:13-16)
    gains `routing_available?: boolean`; `getModelCatalog` (:20-30) passes it through
    (`routing_available: response.routing_available ?? false`).
  - `products/operator-portal/web-ui/app/src/chat/ModelSelect.tsx` — render the auto option,
    adjust the single-model shortcut, and accept a pinned `"auto"` value.
  - `products/operator-portal/web-ui/app/src/chat/ChatView.tsx` — the pin-reconciliation
    (:1898-1905) additionally accepts `detail.model === "auto"` when `routing_available`.
  - `products/operator-portal/web-ui/app/src/chat/ModelSelect.test.tsx` (or the established
    vitest pattern) — the selector tests.
- **Chosen approach:** when `catalog.routing_available` is `true`, prepend an **"Auto (routed)"**
  option (value `"auto"`) as its own group at the top of the `Select`, above the per-provider
  groups (:46-58). The **single-model fixed-label** shortcut (:31-42) renders a dropdown when
  `routing_available` (one model + auto = two choices); it stays a fixed label only when there is
  exactly one model **and** routing is unavailable. The `known` guard (:45) also treats
  `value === "auto"` as known when `routing_available`, so a reopened auto session shows "Auto
  (routed)" selected. When `routing_available` is `false` the component is byte-identical to today.
- **Alternatives considered:** *put auto inside the first provider group* — rejected: it is not a
  model of any provider, so its own top group reads correctly and never implies a provider.

### R-4: Authenticated feature-flag inventory (agent-service)

- **Affected files / modules:**
  - `products/agent-platform/src/agent_service/runtime_kernel.py` — new `feature_flags()` method
    beside `runtime_metadata()` (:355-368) returning the curated nine as
    `[{"name", "enabled", "label"?}]`. `model_routing` reuses `self.routing_available()` (R-1's
    accessor) so F3 parity is structural.
  - `products/agent-platform/src/agent_service/schemas/v2.py` — new `AgentFeatureFlags` model
    (and a small `FeatureFlag` item model) beside `AgentRuntimeMetadata` (:568-574).
    `AgentRuntimeMetadata` is **unchanged**.
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — new
    `GET /api/v2/runtime/flags` route beside `runtime_metadata` (:1943-1954), requiring
    `X-User-ID` via `_user_id(x_user_id)` (the `list_models` posture, :1935), returning
    `AgentFeatureFlags.model_validate(kernel.feature_flags())`. The `/api/v2/runtime` route is
    untouched.
  - `shared/shared-contracts/schemas/feature-flags.schema.json` — **new** schema
    (`additionalProperties: false`; `name` a stable snake_case id, `enabled` boolean, `label`
    optional). `agent-runtime-metadata.schema.json` is **unchanged**.
  - `products/agent-platform/tests/test_contract_adapter.py` — a `/api/v2/runtime/flags`
    conformance test mirroring the runtime one (:52-55).
- **Chosen approach — the curated nine** (name ← setting):
  `model_routing` ← `routing_available()`; `model_discovery` ← `model_discovery_enabled` (:293);
  `context_compression` ← `compress_context_enabled` (:264); `outbound_delegated_identity` ←
  `target_authorization_enabled` (:235); `kernel_tracing` ← `kernel_tracing` (:251);
  `task_tools` ← `task_tools_enabled` (:255); `reply_token_budget` ← `reply_token_budget is not
  None` (:252); `hitl_bridging` ← `hitl_confirm_timeout > 0` (:282); `signed_execution` ←
  `bool(execution_signing_key)` (:300). This is the ground-truth inventory `_build_middlewares()`
  (:610-686) and `RuntimeSettings` already encode.
- **Chosen approach — discovery-safe by construction.** Each flag is a boolean plus a stable
  name/label — never a key, URL, JWKS, budget number, or timeout value. A flag whose setting is a
  secret (`execution_signing_key`) reports only *configured / not configured*. Always-on
  invariants with no knob (permission, evidence, SPEC-065 token-observation middleware) are out
  of scope — the panel reports toggles, not invariants.
- **Alternatives considered:**
  - *Extend `AgentRuntimeMetadata` / ride the unauthenticated `/api/v2/runtime`* — rejected by
    OQ-5: the operator chose an authenticated `runtime:flags` action for defense-in-depth, so the
    flags live on a new endpoint and the probe stays flag-free and byte-unchanged.
  - *Report the raw setting values (budget number, timeout seconds)* — rejected: it would leak
    configuration detail and, for `execution_signing_key`, a secret-existence signal beyond a
    boolean; name + enabled is the discovery-safe contract.

### R-5: Gateway proxy + `runtime:flags` policy action

- **Affected files / modules:**
  - `products/platform-gateway/src/platform_gateway/services/policy_engine.py` — new
    `ACTION_RUNTIME_FLAGS = "runtime:flags"` beside `ACTION_MODELS_LIST` (:58) with a SPEC-072
    comment, added to `PROTECTED_ACTIONS` (:93-119).
  - `products/platform-gateway/src/platform_gateway/services/agent_client.py` — new
    `feature_flags(settings, request_id, user_id)` mirroring `list_models` (:126-138): GET
    `{agent_service_url}/api/v2/runtime/flags` with `_headers(request_id, user_id)`.
  - `products/platform-gateway/src/platform_gateway/services/gateway_service.py` — new
    `feature_flags(settings, request_id, user_id)` mirroring `list_models` (:491-516): upstream
    4xx passes through; transport/5xx → `502`.
  - `products/platform-gateway/src/platform_gateway/api/routes/runtime.py` — add the
    `GET /api/v1/runtime/flags` handler mirroring `models.py` (:19-45): `resolve_request_id` →
    `resolve_request_identity` → `enforce_policy(ACTION_RUNTIME_FLAGS)` → `feature_flags(...)` →
    `log_event("runtime_flags_listed", …)`. The base `/api/v1/runtime` handler (:9-13) is
    **unchanged**. `runtime.router` is already registered (`api/router.py:23`), so **no new
    registration** is needed.
  - The **four** bundle mirrors — `shared/shared-contracts/policies/policy-default.yaml`,
    `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`,
    `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`, and
    `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml` — each gain an identical
    `allow-operators-runtime-flags` rule (the `allow-operators-skill-graduate` shape, :363-372).
  - `shared/shared-contracts/policies/policy-scenarios.yaml` — allow/deny expectations for
    `runtime:flags` in the `api:` section (the `secrets:deliver` shape, :22-27).
- **Chosen approach — grant the operational trio.** `roles_any: ["platform-admin", "approver",
  "operator"]`, `actions_any: ["runtime:flags"]`, `outcome: allow` — matching the
  `documents:read`/`session:skill_draft`/`session:skill_graduate`/`tools:mutate`/`secrets:deliver`
  convention for operational information. `developer`, `read-only-observer`, and `auditor` are
  **denied by default** (standard audited 403). Rationale: a flag inventory describes how the
  platform is deployed/configured — an operational concern, unlike `models:list` which is a
  chat-surface read granted broadly (incl. observer) because it is discovery-safe for chatting.
- **Chosen approach — bundle parity (SPEC-048).** The new rule lands identically in all four
  mirrors; the bundle `version: 1` (a **format** version) does **not** bump on a rule edit.
  `policy-scenarios.yaml` gains an allow expectation for the trio and a deny expectation for
  `["developer", "read-only-observer", "auditor", "unknown"]`, so the harness's grant-coverage
  check (`make verify`) stays green.
- **Chosen approach — no new audit surface.** The read rides the existing gateway log event
  (`runtime_flags_listed`) plus the `_emit_policy_decision` every enforced action already records;
  no new closed-enum audit `event_type`.
- **Alternatives considered:**
  - *Grant `runtime:flags` broadly like `models:list`* — rejected: OQ-5's defense-in-depth choice
    treats deployment posture as an operational read, not a chat-discovery read.
  - *Put the route in a new `runtime_flags.py`* — rejected: `/api/v1/runtime/flags` is a path
    child of `/api/v1/runtime`, `runtime.py` is tiny, and co-location avoids a new
    `api/router.py` registration line; the two handlers keep distinct per-handler auth postures
    (the probe stays unauthenticated, the flags route calls `enforce_policy`).
  - *Ride the existing `models:list` action* — rejected: it would over-expose flags to observer
    and conflate two distinct capabilities under one action name.

### R-6: Portal Settings ▸ Platform feature-flags panel

- **Affected files / modules:**
  - a new `getRuntimeFlags(signal?)` in `products/operator-portal/web-ui/app/src/api/` mirroring
    `getModelCatalog` (`api/models.ts:20-30`) — `requestJson<{ feature_flags: … }>(
    "/api/v1/runtime/flags")`, which attaches the session bearer (`client.ts:60-63`) and throws
    `ApiError` on non-2xx (`client.ts:92-98`).
  - `products/operator-portal/web-ui/app/src/views/control/SettingsView.tsx` — `PlatformPane`
    (:194-357) gains flags state + a fetch in its `useEffect` (:200-219) and a read-only
    **"Feature flags"** section after the components `Table` (:343-354).
  - the `PlatformPane` vitest.
- **Chosen approach:** render each flag's `label ?? name` with an on/off `Tag` reusing the pane's
  existing status vocabulary (`statusTag`/`unavailable()`/`checking()`, :180/:245/:274). **Graceful
  degradation:** on `403` (role lacks `runtime:flags`), on any `ApiError`, or when the field is
  absent, the section shows "unavailable" — the pane's existing degrade posture — while the
  unauthenticated component-health rows are unaffected and still render for every role.
  Read-only: the panel changes nothing and exposes no control (toggling flags stays a
  deploy-time/GitOps action).
- **Alternatives considered:** *fold the flags into the components `Table` as extra rows* —
  rejected: the health rows are unauthenticated and always render, whereas the flags fetch is
  authenticated and role-gated; mixing them would make the whole table appear to degrade on a
  403. A separate section isolates the degrade.

### R-7: Contracts, policy, documentation, and version reconciliation

- **Affected files / modules:** the three touched schemas + the new `feature-flags.schema.json`
  (and the gateway mirror models), `policy_engine.py` + the four bundle mirrors +
  `policy-scenarios.yaml`, and the living docs.
- **Chosen approach:** all contract changes are additive; contract fixtures and the gateway
  mirror models update in lockstep. `agent-session.schema.json`'s `model` field is already
  `["string","null"]` (a free string, :44-46), so a pinned `"auto"` is **structurally tolerated
  today** — only its description gains a note (confirmed at Stage 0; no structural edit).
  `agent-runtime-metadata.schema.json` and `agent-stream-event.schema.json` stay byte-unchanged.
  Docs: `docs/guides/configuration-reference.md` (the `auto` sentinel, `routing_available`, the
  flag inventory + the `runtime:flags` grant, cross-referencing the SPEC-071 router knobs),
  `docs/agentic-aiops-platform/authorization-matrix.md` + `docs/guides/architecture-overview.md`
  (the `runtime:flags` row/rule), `products/platform-gateway/README.md` (the new gated route),
  `docs/specs/README.md` (this spec's row → `delivered` on delivery), the operator guide (how to
  read the flags panel + choose Auto), the delivery-roadmap + the SPEC-071 visibility follow-up
  note, root `CHANGELOG.md` (accumulate under `## Unreleased`), and a release note.
- **Version:** VERSION bumps in the product lockstep at the release train (`make
  validate-version` green); target **v0.53.0** (MINOR — new operator-facing capability + a new
  policy action + additive contracts). The bump is a **release-train** action, not part of
  implementation begin.

## Sequencing And Dependencies

1. **Stage 0 — seam verification** — depends on nothing. **Gate:** its findings (esp. the
   `_resolve_model` caller inventory and the reserved-`auto` guard location) must land before
   Stage 2; a surprise (e.g. the log field *is* enum-validated) is recorded in the spec changelog
   before wiring.
2. **Stage 1 — routing-availability signal (R-1)** — depends on Stage 0. The **keystone**: its
   `routing_available()` accessor is reused by Stages 2 and 4.
3. **Stage 2 — `auto` sentinel resolution (R-2)** — depends on Stage 1 (the accessor to consult).
4. **Stage 3 — portal auto selector (R-3)** — depends on Stages 1-2 (the envelope boolean + the
   auto semantics).
5. **Stage 4 — agent feature-flag endpoint (R-4)** — depends on Stage 1 (reuses
   `routing_available()` for the `model_routing` flag); independent of Stages 2-3.
6. **Stage 5 — gateway proxy + `runtime:flags` (R-5)** — depends on Stage 4 (the agent endpoint
   to proxy).
7. **Stage 6 — portal flags panel (R-6)** — depends on Stage 5 (the gateway route to fetch).
8. **Stage 7 — contracts/docs/version (R-7)** — depends on the final outcome; always runs.

Stages 2-3 (Feature A) and 4-6 (Feature B) may proceed in parallel after Stage 1.

## Test Strategy

- **unit tests (`products/agent-platform/tests/`):**
  - *R-1* — envelope carries `routing_available: true` iff the router is enabled with a non-empty
    candidate map, else `false`; `models[]` is byte-identical to v0.52.0 for the same catalog (no
    synthetic entry injected).
  - *R-2* — explicit `auto` (routing on) arms routing + pins `"auto"`; a second request-less turn
    re-arms from the pin (`selected_by == "auto"`); explicit `auto` (routing off) → `422`; pinned
    `auto` with routing removed → degrades to default, no raise; a concrete request/pin still
    overrides auto; startup fails if a model is literally named `auto`; a routed auto turn reports
    `model_selected_by == "router"`; a parked session still returns `409`.
  - *R-4* — `feature_flags` reflects the settings (each flag flips with its knob);
    `model_routing` equals `routing_available` for the same settings (F3); the payload contains no
    secret substring (assert against the runtime-secrets vocabulary); `/api/v2/runtime` stays
    byte-identical to v0.52.0.
- **contract tests:** `feature-flags.schema.json` validates `/api/v2/runtime/flags`;
  `model-catalog.schema.json` validates both `routing_available` shapes; assert
  `agent-runtime-metadata.schema.json` and `agent-stream-event.schema.json` are byte-unchanged and
  no agentscope type leaks through the v2 contract (the existing schema-stability guard).
- **policy tests (`products/platform-gateway/tests/`):** `runtime:flags` allowed for the trio and
  denied (`403` carrying `action: "runtime:flags"`) for developer/observer/auditor; the gateway
  `/api/v1/runtime/flags` relays the agent payload verbatim; `/api/v1/runtime` still returns no
  `feature_flags`; the scenario harness + bundle-parity gate are green under `make verify`.
- **portal tests (vitest):** *R-3* — the auto option is present iff `routing_available`; a single
  model + routing renders a `Select` not the fixed label; choosing auto calls `onChange("auto")`;
  a pinned `"auto"` renders selected; catalog unavailable → renders nothing. *R-6* — flags render
  with the correct on/off state for a granted role; a `403`/error degrades the section to
  "unavailable" while the health rows persist; no secret value is rendered.
- **integration / overlay validation:** the dev-k8s overlay renders the new bundle rule; root
  `make verify` (eight product suites, overlays, policy + version-lockstep + secret gates,
  operator-portal suite + build) stays green. No new dependency; no GitOps topology change beyond
  the bundle rule.

## Rollout And Migration

- **Deployment / configuration:** no new knob is required to keep the default posture — the
  feature-flag panel simply reports the existing settings, and the auto selector appears only when
  the deployment already enabled routing (`model_router_enabled` + a candidate map). The new
  `runtime:flags` bundle rule ships in all four mirrors; enabling the selector in a deployment is
  the same SPEC-071 opt-in as before (no global default-on flip — the kernel
  `model_router_enabled` default stays `False`).
- **Backward compatibility:** every contract change is additive and defaults to the v0.52.0
  behavior — `routing_available` defaults `false` (auto option absent), the `auto` sentinel is
  accepted only when routing is available, `AgentRuntimeMetadata` / the unauthenticated
  `/api/v1/runtime` probe are byte-unchanged, and `agent-session.schema.json` already tolerates a
  pinned `"auto"`. An older portal ignores the new envelope boolean and never sends `auto`.
- **Rollback:** the auto selector disappears when routing is disabled (`routing_available`
  `false`); a session pinned `"auto"` degrades to the catalog default with no raise. The flags
  panel is read-only and its route can be withdrawn by reverting the bundle rule (deny-by-default
  floor immediately 403s it). No storage migration and no destructive state.
