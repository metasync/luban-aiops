# SPEC-071 Plan: Per-Turn Model Routing Adoption (AgentScope `ModelRouterMiddleware`)

> **Binding.** `spec.md` is `approved` (2026-11-01) — all five Open Questions ratified as
> proposed. This plan is therefore firm, not provisional: it authorizes implementation to
> **begin**. It does **not** authorize a merge, commit/push, deployment, a version bump, or
> any move to default-on (R-3's measurement gate governs that). R-1 is already delivered by
> the [spike memo](../../workspace/agentscope-model-router-spike.md); the work here is R-2's
> opt-in wiring, R-3's measurement harness, and R-4's documentation reconciliation.

## Approach

Wire `ModelRouterMiddleware` as an opt-in, default-off kernel surface that composes with —
never overrides — SPEC-024's audited `request > pinned > default` precedence, inserting
`routed` between `pinned` and `default`. The router classifies the latest user input over
named candidates drawn from the credential-gated `MODEL_CATALOG` and swaps the reply's chat
model; it is resume-safe (`agent.state.middle_context[key][reply_id]`, rides the SPEC-017
snapshot) and fail-soft (any error or unknown candidate keeps the agent's own model). The
load-bearing design problem is **provenance threading**: `_resolve_model` runs per-turn in
`routes.py` and knows whether the model came from a request, a pin, or the default, but the
router swaps `agent.model` at reply time *inside* the kernel — so the router must be armed
**only** for default-resolved turns, and the model actually used must be surfaced back for
attribution. Stages group the requirements:

- **Stage 0 — Seam verification (no product diff):** confirm the four integration facts this
  plan depends on against the locked 2.0.11 install and the 0.51.1 kernel (middleware wrap
  order, classifier-token observation, streaming attribution path, resume key stability).
- **Stage 1 — Settings (R-2):** add the opt-in knob, router-model id, and candidate map to
  `RuntimeSettings`, following the `compress_context_enabled` pattern.
- **Stage 2 — Precedence + provenance (R-2):** extend `_resolve_model` to return
  `selected_by` and gate routing to default-resolved turns.
- **Stage 3 — Middleware wiring (R-2):** register `ModelRouterMiddleware` in
  `_build_middlewares()` only when enabled and routing is allowed for the turn.
- **Stage 4 — Attribution + visibility (R-2):** surface the effective model + `model_selected_by`
  back through the reply path into the response/log without a contract-byte change.
- **Stage 5 — Measurement harness (R-3):** the accuracy / latency / token-cost measurement
  that gates any future default-on; ships the harness, not a default flip.
- **Stage 6 — Documentation reconciliation (R-4):** always; resolves the audit row, backlog
  row, spec index, and — only if it ships — CHANGELOG / config-reference / release note.

## Design Per Requirement

### R-1: Four-point adoption-gate evaluation — DELIVERED

Delivered by the [memo](../../workspace/agentscope-model-router-spike.md) (verdict: **clears**
all four). No work in this plan beyond R-4's row reconciliation. Evidence anchors:
`middleware/_model_router.py` `on_reply` (:84-110) / `_route` (:112+); the kernel
`_build_middlewares()` seam (`runtime_kernel.py:551`); `MODEL_CATALOG` + SPEC-024
`_resolve_model` (`api/v2/routes.py:261`).

### R-2: Opt-in per-turn model routing — the implementation

- **Affected files / modules:**
  - `products/agent-platform/src/agent_service/runtime_settings.py` — new
    `model_router_enabled: bool = False`, `model_router_model: str | None`,
    `model_router_candidates` (parsed), a `__post_init__` guard, and the env parse, all
    mirroring `compress_context_enabled` (:191, guard :324-332, parse :557-559).
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — `_resolve_model` (:261)
    returns provenance; `chat` (:291) and `chat_stream` (:339) thread it and surface the
    effective model + `model_selected_by`.
  - `products/agent-platform/src/agent_service/runtime_kernel.py` — `_build_middlewares()`
    (:551) registers the router; `_build_agent()` (:799) passes the per-turn routing flag;
    the reply path returns the effective model.
  - `products/agent-platform/tests/` — gating, precedence, fail-soft, resume, no-type-leak,
    schema-stability, token-attribution tests.

- **Chosen approach — candidate config.** `AGENTSCOPE_MODEL_ROUTER_ENABLED` (default off)
  plus `AGENTSCOPE_MODEL_ROUTER_MODEL` (the classifier model id, resolved through
  `MODEL_CATALOG`) plus a candidate map `AGENTSCOPE_MODEL_ROUTER_CANDIDATES` parsed into
  `name → (catalog model id, description)` pairs. With no candidate map the knob is **inert**
  (middleware not registered) — Open Question 2's "routing disabled with no map." Each
  candidate's model is built with the existing `_build_model(catalog_id)`, so an unknown or
  revoked id can never be routed to (the catalog is the only source; `_route`'s
  unknown-candidate guard at `:96-99`/`:107` is the backstop).

- **Chosen approach — precedence `request > pinned > routed > default`.** `_resolve_model`
  gains a `selected_by ∈ {request, pin, default}` return (a pure refactor of :272-285; the
  request/pin fail-closed semantics are unchanged). Routing is armed **only** when
  `selected_by == default` — i.e. no explicit request and no live pin — so a human's explicit
  choice always wins and the router can never override it. The armed flag is threaded
  `_build_agent(..., routing_allowed=…) → _build_middlewares(routing_allowed=…)`.

- **Chosen approach — router backend.** Pass a plain catalog `ChatModelBase` as
  `classifier_model` (`ModelRouterMiddleware.__init__`, `_model_router.py:45-50`), which
  routes via `generate_structured_output` (`:127`) — provider-agnostic, the same call
  threshold compression already exercises. `OpenAIClassifierModel` / `JevClassifierModel` are
  **not** wired, so no new provider or dependency (Open Question 3).

- **Chosen approach — attribution + visibility.** The reply path surfaces the **effective**
  model id (post-routing) and `model_selected_by ∈ {request, pin, router, default}` so
  `AgentChatResponse.model` (:335) and the structured log (:308-316, :361-369) reflect what
  actually served the turn — preventing a silent downgrade (Open Question 4). This is an
  attribution field on the existing turn/model record; **no new closed-enum audit
  `event_type`** and **no `agent-stream-event.schema.json` byte change** — the routed model
  rides the existing model field/frame.

- **Alternatives considered:**
  - *Let the router always run and rely on `_resolve_model` staying authoritative* — rejected:
    the middleware swaps `agent.model` at reply time and would override a request/pin,
    breaking precedence; arming only default-resolved turns is the clean invariant.
  - *Wire a dedicated `OpenAIClassifierModel` / `JevClassifierModel`* — rejected: both are
    provider-specific (`JevClassifierModel` takes a `TypeSafeCredential`), adding a dependency
    and an identity edge for no benefit over the chat-model path.
  - *Return the pre-routing resolved model and log the routed one only kernel-side* — rejected:
    the response `model` field would misreport what served the turn, defeating the visibility
    goal and SPEC-024's "audited choice" property.
  - *Hard-fail a turn on a routing error* — rejected: violates fail-soft; `_route` already
    keeps the agent's own model on error/unknown, and a test pins it.

- **Design risks carried as Stage-0 verification (not assumed):**
  1. **Middleware wrap order.** Confirm where `ModelRouterMiddleware`'s `on_reply` must sit in
     the `_build_middlewares()` list so the routed model is active for the inner model calls
     (and observed by `TokenUsageMiddleware`'s `on_model_call`), given the existing
     reorder-when-`target_authorization_enabled` logic (:576-581).
  2. **Classifier-token observation.** The router's `generate_structured_output` is a call on
     a *separate* `ChatModelBase`, not the agent's model — verify whether it actually rides
     `TokenUsageMiddleware.on_model_call`. If it does **not**, R-2's "token observation reuses
     SPEC-065, no new instrumentation" criterion needs a minimal refinement (either accept the
     routing call as unobserved, or add one bounded counter); surface the finding before
     implementing rather than assuming the spec text holds.
  3. **Streaming attribution.** `chat_stream` resolves the model before headers go out
     (:343-344) but routing happens at `ReplyStartEvent` inside the stream — confirm the
     effective model can ride an existing event field with no schema-byte change.
  4. **Resume-key stability.** Confirm `middle_context[key]` (`get_middleware_key()`) is stable
     across a confirmation park/resume so the same routed model is used post-resume.

### R-3: Routing-accuracy measurement gate (before any default-on)

- **Affected files / modules:** a measurement harness under `products/agent-platform/` (offline,
  not a CI dependency), reusing SPEC-065's `agent_llm_tokens_total` for the classification-call
  cost. No default flip ships in this spec.
- **Chosen approach:** on a representative turn sample, record routing **accuracy** (did it
  select the intended tier?), added **per-reply latency**, and the classification call's
  **token cost**; tune the candidate `description` criteria against it. Default-on stays a
  **separate operator decision** evidenced by this measurement — the SPEC-066 "measure before
  building" discipline applied to routing quality.
- **Alternatives considered:** shipping default-on immediately (rejected — routing quality is
  only as good as the criteria, unmeasured); a full A/B in production (rejected for this slice —
  an offline harness over a labeled sample is sufficient to gate the decision).

### R-4: Documentation, audit, and backlog reconciliation

- **Affected files / modules:** `docs/workspace/agentscope-utilization-audit.md` (§2 model-routing
  row), `docs/agentic-aiops-platform/delivery-roadmap.md` (Exploration Backlog row),
  `docs/specs/README.md` (this spec's row), this spec's status/changelog; and **only if it
  ships** `CHANGELOG.md`, `docs/guides/configuration-reference.md` (knob + candidate map +
  Feature Activation Matrix row), and a release note.
- **Chosen approach:** flip the audit row from "adopt candidate; spike done" to the delivered
  outcome linking this spec; keep the audit as the single source of truth for surface disposition.

## Sequencing And Dependencies

1. **Stage 0 — seam verification** — depends on nothing (2.0.11 pinned by v0.51.1). **Gate:**
   its four findings (esp. #1 wrap order and #2 classifier-token observation) must land before
   Stage 3/4, and may refine R-2's token-observation criterion.
2. **Stage 1 — settings** — depends on Stage 0. Independent of Stages 2-4.
3. **Stage 2 — precedence + provenance** — depends on Stage 1 (the knob/flag exist to thread).
4. **Stage 3 — middleware wiring** — depends on Stages 1-2 (settings + `routing_allowed`).
5. **Stage 4 — attribution + visibility** — depends on Stage 3 (the effective model exists to
   surface); must keep `agent-stream-event.schema.json` byte-unchanged.
6. **Stage 5 — measurement harness (R-3)** — depends on Stages 1-4 (a working opt-in router to
   measure); ships the harness only, never a default flip.
7. **Stage 6 — documentation reconciliation (R-4)** — depends on the final outcome; always runs.

## Test Strategy

- **unit tests (`products/agent-platform/tests/`):**
  - *opt-in gating* — knob off ⇒ no `ModelRouterMiddleware` registered and behavior
    byte-identical to v0.51.1; knob on with a candidate map ⇒ registered; knob on with **no**
    candidate map ⇒ inert (not registered).
  - *precedence* — an explicit request model and a live pin both suppress routing
    (`selected_by ∈ {request, pin}`, router not armed); only a default-resolved turn routes.
  - *fail-soft* — a classifier error and an unknown candidate each keep the agent's own model
    and never hard-fail the turn.
  - *resume* — a routed `reply_id` survives a confirmation park/resume via `middle_context` +
    the SPEC-017 snapshot; the same model is used post-resume.
  - *attribution* — `model_selected_by` reports `router` when the router swapped, else the
    pre-routing tier; the response `model` field carries the effective id.
- **contract tests:** assert `agent-stream-event.schema.json` is byte-unchanged and no
  agentscope type leaks through the v2 contract (the existing schema-stability guard).
- **token observation:** assert the classification call's tokens are recorded — **or**, if
  Stage-0 finding #2 shows they are not on the `on_model_call` path, assert the refined
  disposition (unobserved-by-design or one bounded counter) instead.
- **integration / overlay validation:** no GitOps, policy-bundle, or deployment change. The
  configuration-reference drift check and root `make verify` (overlays, version/policy/secret
  gates) must stay green; the SPEC-063 execution-failure campaign is unaffected (routing makes
  no gateway call and touches no dispatch claim).
- **measurement harness (R-3):** runs offline over a labeled turn sample; explicitly **not** a
  CI dependency and **not** a merge gate for R-2 (it gates a *future* default-on decision).

## Rollout And Migration

- **Deployment / configuration:** one new default-off knob (`AGENTSCOPE_MODEL_ROUTER_ENABLED`)
  plus the router-model id and candidate map, documented in the configuration reference. No
  GitOps overlay change is required to keep the default posture; enabling is per-deployment.
- **Backward compatibility:** default-off means sessions behave exactly as at v0.51.1; the
  `_resolve_model` provenance refactor is behavior-preserving for request/pin/default. No
  contract, schema, or storage migration.
- **Rollback:** disable the knob (inert immediately). Routed state is kernel-owned agent state
  (`middle_context`) that a disabled middleware simply stops populating — no destructive
  migration. A keep-out-at-Stage-0 finding (e.g. classifier tokens unobservable and judged
  unacceptable) stops before any wiring ships.
