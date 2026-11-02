# SPEC-072 Tasks: Auto-Routing Model Selection and Platform Feature-Flag Transparency

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs. Failure/test
matrix rows (`A*` auto-routing, `F*` feature-flags, `X*` cross-cutting) are referenced per task
and consolidated in [Acceptance-to-test matrix](#acceptance-to-test-matrix).

> **Binding.** `spec.md` is `approved` (2026-11-02) — all seven Open Questions ratified, OQ-5
> resolved as a new authenticated `runtime:flags` policy action. These tasks authorize
> implementation to **begin** — not to merge, commit/push, deploy, or version-bump. Stage-0
> findings gate Stage 2 (and may refine R-2's attribution criterion); record any refinement in
> the spec changelog before wiring. Feature A = R-1…R-3; Feature B = R-4…R-6; R-7 reconciles.

## Stage 0: Seam verification (no product diff) — DONE 2026-11-02

- [x] S0-1 — Inventory `_resolve_model`'s callers (`api/v2/routes.py:263`; SPEC-071 refactored all
      five to unpack `(model_id, selected_by)`, incl. the `chat_confirm` 410-expiry branch) and
      confirm the explicit `routing_available` third parameter threads cleanly through each
      — **confirmed, with a refinement**: there are **five** callers — `chat` (:311), `chat_stream`
      (:378), `chat_confirm` expiry (:455), `chat_confirm` resume `_events` (:503), and
      `_reject_if_parked` (:239). The three park/expire/resume callers gate `routing_allowed` on
      `selected_by == "default"`, so they must also move to `in {"auto", "default"}` — otherwise a
      parked auto session resumes/expires on a non-routed agent and misses the SPEC-071 `::routed`
      cache key. Recorded in the spec changelog 2026-11-02.
- [x] S0-2 — Locate SPEC-026 R-2's duplicate-model-name startup guard on the catalog-build path
      (`services/model_catalog.py`) so the reserved-`auto` guard sits on the same construction step
      — **confirmed**: `build_entries`' `seen` loop (`:198-207`) raises `ValueError` on a duplicate
      id; the startup catalog is built at module import (`_STARTUP_ENTRIES = build_model_catalog(…)`,
      `:322`), so a `ValueError` there fails startup, while live `refresh_catalog` (`:296-316`)
      catches it and keeps the previous catalog (fail-soft). The reserved-`auto` guard joins that
      loop; aliases can never be `auto` (the provider enum is closed).
- [x] S0-3 — Confirm the routes *structured-log* `model_selected_by` extra (`routes.py:329`, `:392`)
      is free-form (not validated against a closed enum), so adding `"auto"` is contract-safe, and
      that the kernel audit attribution vocabulary stays `{request, pin, router, default}` (A9)
      — **confirmed**: `model_selected_by` appears only in the two routes `LOGGER.info(... extra={})`
      dicts, a kernel docstring, and docs/tests — no schema, pydantic `Literal`, or audit enum
      validates it, so `"auto"` is a safe resolution-provenance value; the kernel's `router`
      attribution (the "model routing served turn" log) is untouched.
- [x] S0-4 — Confirm the four bundle mirrors are kept equivalent by a `make verify` policy-parity
      gate and the exact insertion point for `allow-operators-runtime-flags` (after
      `allow-operators-skill-graduate`, `policy-default.yaml:363-372`)
      — **confirmed, mechanism corrected**: parity is not a `verify` diff gate but `make sync-policy`
      (`Makefile:150-157`), a `cp` of the canonical `shared/shared-contracts/policies/policy-default.yaml`
      to the three `POLICY_TARGETS`. So the rule is authored once in the canonical bundle, then
      synced; `validate-policy` + `validate-policy-scenarios` run against canonical, and the
      platform-gateway tests load its product-local mirror (so sync is required for them to pass).
- [x] S0-5 — Confirm `agent-session.schema.json`'s `model` field (`:44-46`, `["string","null"]`)
      already tolerates a pinned `"auto"` — **verified 2026-11-02**: free string, so only its
      description needs a note; no structural edit (R-7)

## R-1: Catalog signals routing availability — DONE 2026-11-02

- [x] Add `AgentKernel.routing_available()` beside `_router_armed()` (`runtime_kernel.py:595-608`):
      `bool(settings.model_router_enabled and settings.model_router_candidates)` — the single
      source of truth reused by R-2 and R-4 (`products/agent-platform/.../runtime_kernel.py`);
      `_router_armed` refactored to `bool(routing_allowed and self.routing_available())`
- [x] `public_models(routing_available: bool = False)` emits it in the envelope
      (`services/model_catalog.py:285-300`); `list_models` passes
      `get_runtime_kernel().routing_available()` (`api/v2/routes.py:1927-1941`)
- [x] `AgentModelCatalog` gains `routing_available: bool = False` (`schemas/v2.py:558-566`)
- [x] `model-catalog.schema.json`: add **optional** `routing_available: {"type":"boolean"}` to the
      envelope `properties` (not `required`; `additionalProperties:false` + `models[]` + the closed
      `provider` enum unchanged) (`shared/shared-contracts/schemas/model-catalog.schema.json`)
- [x] Tests: envelope `routing_available` true iff router enabled + non-empty candidates, else
      false; `models[]` byte-identical to v0.52.0 (no synthetic entry); both shapes schema-validate
      (`products/agent-platform/tests/test_model_catalog.py`, `test_model_router.py`) — **A1, A2, X1**
      — 55 passed

## R-2: `auto` sentinel selection and resolution — DONE 2026-11-02

- [x] `_resolve_model(requested, pinned, routing_available)` adds the `auto` branch and returns
      `selected_by ∈ {request, pin, auto, default}`: explicit `auto` + available → `(default.id,
      "auto")`; explicit `auto` + unavailable → `422`; pinned `auto` + available → `(default.id,
      "auto")`; pinned `auto` + unavailable → degrade `(default.id, "default")`; concrete
      request/pin unchanged (`api/v2/routes.py:263-292`)
- [x] Thread `routing_available = get_runtime_kernel().routing_available()` into all `_resolve_model`
      callers (per S0-1)
- [x] `chat` (`:317-319`) + `chat_stream` (`:382-384`): pin the **sentinel** when the request was
      `auto` (`pin = "auto" if body.model == "auto" else resolved_model`), and set
      `routing_allowed = selected_by in {"auto", "default"}`
- [x] Reserved-sentinel startup guard: catalog construction raises a clear error if any entry or
      alias id == `"auto"` (per S0-2, same posture as SPEC-026 R-2's duplicate-name failure)
      (`services/model_catalog.py`)
- [x] `agent-chat-request.schema.json`: `model` description documents `auto` as the one
      non-catalog-id value accepted (description-only; the field is already `["string","null"]`)
- [x] Tests: explicit `auto` (on) arms + pins `"auto"`; request-less second turn re-arms from the
      pin; explicit `auto` (off) → `422`; pinned `auto` (routing removed) → degrades, no raise;
      concrete request/pin overrides auto; startup fails on a model named `auto`; routed auto turn
      → `model_selected_by == "router"`; parked session still `409`
      (`test_model_router.py`, `test_model_catalog.py`, `test_hitl_confirmations.py`) — **A3, A4,
      A5, A6, A7, A8, A9, A10** — 1676 passed (full agent-platform suite)

## R-3: Portal "Auto (routed)" selector entry — DONE 2026-11-02

- [x] `ModelCatalogResponse` gains `routing_available?: boolean`; `getModelCatalog` passes it
      through (`?? false`) (`operator-portal/.../src/api/models.ts:13-30`)
- [x] `ModelSelect.tsx`: when `routing_available`, prepend an **"Auto (routed)"** option (value
      `"auto"`) as its own top group; render a dropdown (not the fixed label) for a single model +
      routing; treat `value === "auto"` as known (`chat/ModelSelect.tsx:31-70`)
- [x] `ChatView.tsx` pin-reconciliation accepts `detail.model === "auto"` when `routing_available`
      (`chat/ChatView.tsx:1898-1905`)
- [x] Tests (vitest): auto option present iff `routing_available`; single-model + routing renders a
      `Select`; choosing auto calls `onChange("auto")`; a pinned `"auto"` renders selected; catalog
      unavailable → renders nothing (`chat/ModelSelect.test.tsx`) — **A11, A12, A13**
      — 543 passed (full portal suite); `tsc --noEmit` clean

## R-4: Authenticated feature-flag inventory (agent-service) — DONE 2026-11-02

- [x] Add `AgentKernel.feature_flags()` beside `runtime_metadata()` (`runtime_kernel.py:355-368`)
      returning the curated nine `[{name, enabled, label?}]`; `model_routing` reuses
      `self.routing_available()` (structural F3 parity)
- [x] Map the nine from `RuntimeSettings`: `model_routing`, `model_discovery` (:293),
      `context_compression` (:264), `outbound_delegated_identity` (:235), `kernel_tracing` (:251),
      `task_tools` (:255), `reply_token_budget` (:252 `is not None`), `hitl_bridging` (:282 `> 0`),
      `signed_execution` (:300 `bool(key)`) — booleans/names/labels only, never a secret value
- [x] New `AgentFeatureFlags` (+ `FeatureFlag` item) model beside `AgentRuntimeMetadata`
      (`schemas/v2.py:568-574`); `AgentRuntimeMetadata` **unchanged**
- [x] New route `GET /api/v2/runtime/flags` requiring `X-User-ID` (`_user_id(x_user_id)`, the
      `list_models` posture :1935) beside `runtime_metadata` (`api/v2/routes.py:1943-1954`);
      `/api/v2/runtime` untouched
- [x] New `shared/shared-contracts/schemas/feature-flags.schema.json` (`additionalProperties:false`;
      `name` snake_case id, `enabled` boolean, `label` optional); `agent-runtime-metadata.schema.json`
      **unchanged**
- [x] Tests: `feature_flags` flips with each knob; `model_routing == routing_available`; no secret
      substring in the payload (runtime-secrets vocabulary); `/api/v2/runtime` byte-identical to
      v0.52.0; contract-adapter conformance for `/api/v2/runtime/flags`
      (`products/agent-platform/tests/`, `test_contract_adapter.py:52-55`) — **F1, F2, F3, F6, X1**
      — 1681 passed (full agent-platform suite)

## R-5: Gateway proxy + `runtime:flags` policy action — DONE 2026-11-02

- [x] `ACTION_RUNTIME_FLAGS = "runtime:flags"` beside `ACTION_MODELS_LIST` (`policy_engine.py:58`)
      + add to `PROTECTED_ACTIONS` (`:93-119`) with a SPEC-072 comment
- [x] `agent_client.feature_flags(settings, request_id, user_id)` mirrors `list_models`
      (`:126-138`) → GET `/api/v2/runtime/flags` with `_headers(request_id, user_id)`
- [x] `gateway_service.feature_flags(settings, request_id, user_id)` mirrors `list_models`
      (`:491-516`): upstream 4xx passthrough; transport/5xx → `502`
- [x] `GET /api/v1/runtime/flags` handler in `api/routes/runtime.py` mirroring `models.py:19-45`
      (`resolve_request_id` → `resolve_request_identity` → `enforce_policy(ACTION_RUNTIME_FLAGS)` →
      `feature_flags(...)` → `log_event("runtime_flags_listed", …)`); base `/api/v1/runtime`
      (`:9-13`) **unchanged**; no new `api/router.py` registration (`runtime.router` already included)
- [x] Add the identical `allow-operators-runtime-flags` rule (`roles_any: [platform-admin,
      approver, operator]`, `actions_any: [runtime:flags]`, `outcome: allow`) to **all four**
      bundle mirrors — `shared/shared-contracts/policies/policy-default.yaml`,
      `products/platform-gateway/src/platform_gateway/policies/policy-default.yaml`,
      `products/tool-gateway/src/tool_gateway/policies/policy-default.yaml`,
      `shared/platform-ops/gitops/dev-k8s/base/shared/policy.yaml`; bundle `version` stays `1`
      — synced via `make sync-policy`; all 4 byte-identical (sha256 unique=1), each carries the rule once
- [x] `policy-scenarios.yaml` `api:` section — allow for the trio + deny for
      `["developer","read-only-observer","auditor","unknown"]` (the `secrets:deliver` shape, `:22-27`)
- [x] Tests: `runtime:flags` allowed for the trio, denied (`403` carrying `action:"runtime:flags"`)
      for developer/observer/auditor; gateway relays the agent payload verbatim + schema-valid;
      `/api/v1/runtime` still returns no `feature_flags`; scenario harness + bundle parity green
      (`products/platform-gateway/tests/`) — **F4, F5, F6, F7**
      — 481 passed (full platform-gateway suite); validate-policy 21 rules OK;
      validate-policy-scenarios api 151 (96 granted pairs) + tools 32 (21 granted pairs) OK

## R-6: Portal Settings ▸ Platform feature-flags panel — DONE 2026-11-02

- [x] New `getRuntimeFlags(signal?)` mirroring `getModelCatalog` → `requestJson<{feature_flags:…}>(
      "/api/v1/runtime/flags")` (attaches the session bearer, `client.ts:60-63`)
      (`operator-portal/.../src/api/`) — added as a new `api/runtime.ts`
- [x] `PlatformPane` (`SettingsView.tsx:194-357`): flags state + an authenticated fetch in the
      `useEffect` (`:200-219`) + a read-only **"Feature flags"** section after the components
      `Table` (`:343-354`), each flag `label ?? name` with an on/off `Tag` reusing the pane's
      status vocabulary
- [x] Graceful degradation: on `403`/`ApiError`/absent field the section shows "unavailable"; the
      unauthenticated component-health rows persist for every role; read-only (no control)
- [x] Tests (vitest): flags render correct on/off for a granted role; a `403`/error degrades the
      section to "unavailable" while health rows persist; no secret value rendered
      (`views/control/` pane test) — **F8, F9**
      — new `SettingsView.test.tsx` (3 tests); full portal suite 546 passed; tsc clean

## R-7: Contracts, policy, documentation, and version reconciliation — DONE 2026-11-02 (bullets 1–4; 5–6 deferred to the ship/release-train gate)

- [x] Contract fixtures + gateway mirror models updated in lockstep for `routing_available`, the
      `auto` sentinel note, and the new `feature-flags` schema; `agent-session.schema.json` `model`
      description notes a pinned `"auto"` (structure already tolerates it, S0-5);
      `agent-runtime-metadata.schema.json` + `agent-stream-event.schema.json` byte-unchanged
      — `agent-session.schema.json` `model` description gained the pinned-`"auto"` note (JSON
      validated); the other two confirmed byte-unchanged in `git status`; no gateway mirror
      pydantic models exist (the proxy relays dicts) and there is no contract-fixtures dir, so
      those lockstep parts are no-ops
- [x] `docs/guides/configuration-reference.md` — the `auto` sentinel, `routing_available`, the
      flag inventory (names + meaning) + the `runtime:flags` grant, cross-referencing the SPEC-071
      router knobs
      — added a Feature Activation Matrix row + a new "Auto-Routing Selection and Feature-Flag
      Transparency (SPEC-072)" section (auto-sentinel / `routing_available` prose, the 9-flag
      inventory table with each flag's env-var knob, the `runtime:flags` grant)
- [x] `docs/agentic-aiops-platform/authorization-matrix.md` + `docs/guides/architecture-overview.md`
      — the `runtime:flags` row/rule; `products/platform-gateway/README.md` — the new gated route
      — authorization-matrix.md gained a SPEC-072 prose paragraph; architecture-overview.md's
      allow-rule table gained the `allow-operators-runtime-flags` row and its count corrected to
      "twenty" (also adding the previously-missing SPEC-070 `allow-operators-targets-authorize`
      row, so the enumeration now matches the shipped 20-allow-rule bundle);
      platform-gateway/README.md gained the `runtime:flags` gated-route bullet
- [x] Operator guide — how to read the Platform flags panel + choose "Auto (routed)";
      delivery-roadmap + the SPEC-071 visibility follow-up note reconciled to point at this spec
      — portal-user-guide.md gained the "Auto (routed)" selector bullet (Selecting a model) + the
      Settings ▸ Platform **Feature flags** paragraph; the delivery-roadmap SPEC-071 row and
      SPEC-071's own OQ-4 note now forward-reference SPEC-072
- [x] `docs/specs/README.md` SPEC-072 row → `delivered` on delivery (added at `draft`, advanced to
      `approved` 2026-11-02) — flipped to `delivered` 2026-11-02 with a delivery note + release-note link
- [x] On ship: root `CHANGELOG.md` entry under `## Unreleased` referencing SPEC-072; a release note;
      VERSION bumps in the product lockstep to **v0.53.0** (`make validate-version` green) — a
      release-train action, not part of implementation begin
      — DONE 2026-11-02: `## Unreleased` closed into `## 0.53.0 — 2026-11-02` (SPEC-072 summary +
      Added/Changed/Fixed + release-note link); release note
      `2026-11-02-auto-routing-and-platform-feature-flags.md` written; VERSION + all 18 product
      version literals bumped 0.52.0 → 0.53.0; `make validate-version` green

> Bullets 5–6 **fired at the 2026-11-02 ship gate** (the explicitly-authorized release-train
> action): `docs/specs/README.md` is now `delivered` and VERSION is `0.53.0`. Commit/push stays a
> separate, not-yet-authorized gate.

## Acceptance-to-test matrix

Maps each failure/test-matrix row in `spec.md` to the requirement and test that pins it.

| Row | Requirement | Pinned by |
| --- | --- | --- |
| A1 | R-1 | catalog contract + unit (`routing_available: true`; no `auto` entry) |
| A2 | R-1 | catalog unit (`false` + `models[]` byte-identical to v0.52.0) |
| A3 | R-2 | `_resolve_model` + chat handler (auto arms, base = default, pin `"auto"`) |
| A4 | R-2 | chat handler (request-less turn re-arms from the pin) |
| A5 | R-2 | chat handler (explicit auto, routing off → `422`) |
| A6 | R-2 | `_resolve_model` (pinned auto, routing removed → degrade, no raise) |
| A7 | R-2 | precedence test (concrete request/pin suppresses routing) |
| A8 | R-2 | catalog startup guard (a model named `auto` fails startup) |
| A9 | R-2 | chat + attribution (routed auto → `model_selected_by == "router"`) |
| A10 | R-2 | parked-session test (model change → `409`) |
| A11 | R-3 | `ModelSelect.test.tsx` (auto option iff `routing_available`) |
| A12 | R-3 | `ModelSelect.test.tsx` (single model + routing → dropdown) |
| A13 | R-3 | `ChatView` reconciliation (reopened pinned `"auto"` shows selected) |
| F1 | R-4 | runtime-flags unit (each name's correct `enabled`) |
| F2 | R-4 | vocabulary guard (no secret substring) |
| F3 | R-1 + R-4 | cross-surface parity (`model_routing == routing_available`) |
| F4 | R-5 | gateway proxy test (trio `200`, verbatim relay, `runtime_flags_listed`) |
| F5 | R-5 | policy + proxy test (developer/observer/auditor `403` w/ `action`) |
| F6 | R-4 + R-5 | agent-runtime-metadata contract (`/runtime` flag-free, both layers) |
| F7 | R-5 | policy validate + scenario harness (four mirrors identical; `make verify`) |
| F8 | R-6 | `PlatformPane` vitest (granted role renders label + on/off Tag) |
| F9 | R-6 | `PlatformPane` vitest (`403`/error → "unavailable"; health rows persist) |
| X1 | R-1/R-4/R-7 | contract suite (additive schemas; `agent-runtime-metadata` untouched) |

## Delivery Gate

- [x] All acceptance criteria in `spec.md` verified (R-1…R-7); the acceptance-to-test matrix green
      — R-1…R-7 all DONE; the A1–A13 / F1–F9 / X1 rows are pinned by the green suites below
- [x] Living state docs updated (see the spec `Impact` section): configuration-reference,
      authorization-matrix, architecture-overview, operator guide, `platform-gateway/README.md`,
      delivery-roadmap, the SPEC-071 visibility note, `CHANGELOG.md`, and the release note
      — all DONE: the seven living state docs (R-7) plus, at the 2026-11-02 ship gate, `CHANGELOG.md`
      (closed into `## 0.53.0`) and the release note
- [x] `make verify` green with the shipped diff — eight product suites, overlays, policy +
      version-lockstep + secret gates, operator-portal suite + build
      — full `make verify` green 2026-11-02: agent-platform 1681 · tool-gateway 1066 ·
      platform-gateway 481 · skills-hub 291 · audit-service 147 · incident-service 138 ·
      execution-runtime 94 · identity-broker 63; 7 overlays + dashboards; policy 21 rules +
      scenarios (api 151/96, tools 32/21); version-lockstep + secret-vocab + password-policy;
      portal vitest 546 + `vite build` ✓; delegated custody/runtime/multiproc/edge; and the
      SPEC-063 execution-failure campaign 795 passed (exit 0)
- [x] Spec index in `docs/specs/README.md` updated to `delivered` — done 2026-11-02
- [x] Spec status set to `delivered` (target v0.53.0) — `spec.md` status flipped, plus a `- delivered:`
      line and a Changelog entry added 2026-11-02
- [x] Commit/push, deployment, and the VERSION bump remain **separate gates** — not authorized by
      approval; the standing "review before any merge/deploy" constraint governs
      — CLOSED at the 2026-11-02 ship gate under explicit user authorization: VERSION bumped to
      0.53.0 (lockstep across VERSION + 8 pyproject.toml + 8 metadata.py + 2 __init__.py + 8 uv.lock;
      `make validate-version` green) and a fresh full `make verify` re-run green on the release tree
      (exit 0; SPEC-063 campaign 795 passed / 2 deselected); this delivery is committed as
      `feat: deliver SPEC-072 … as v0.53.0` and tagged `v0.53.0`, with the L3 deep security review
      offered before the push to `origin/main`, then the local cluster rebuilt/redeployed onto the
      delivery commit
