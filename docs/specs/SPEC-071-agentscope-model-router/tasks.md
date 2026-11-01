# SPEC-071 Tasks: Per-Turn Model Routing Adoption (AgentScope `ModelRouterMiddleware`)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Binding.** `spec.md` is `approved` (2026-11-01). These tasks authorize implementation to
> **begin** — not to merge, commit/push, deploy, version-bump, or flip default-on. R-1 is
> delivered by the [memo](../../workspace/agentscope-model-router-spike.md). Stage-0 findings
> gate Stages 3-4 and may refine R-2's token-observation criterion; record any refinement in
> the spec changelog before wiring.

## R-1: Four-point adoption-gate evaluation — DELIVERED

- [x] Land the spike memo under `docs/workspace/` with the four gate points, the 2.0.11
      evidence, and an explicit verdict — **clears all four**
      ([agentscope-model-router-spike.md](../../workspace/agentscope-model-router-spike.md) §3)
- [x] Record the resolved decision in `docs/workspace/agentscope-utilization-audit.md` §2
      (model-routing row) linking the memo
- [x] Resolve the memo's five design Open Questions (§7) as spec Open Questions — ratified by
      the operator 2026-11-01

## Stage 0: Seam verification (no product diff)

- [ ] Verify `ModelRouterMiddleware.on_reply` wrap order in the `_build_middlewares()` list
      (`runtime_kernel.py:551`, incl. the `target_authorization_enabled` reorder at :576-581)
      so the routed model is active for the inner model calls and observed by `TokenUsageMiddleware`
- [ ] Verify whether the router's classifier `generate_structured_output` (`_model_router.py:127`)
      — a call on a **separate** `ChatModelBase`, not the agent's model — rides
      `TokenUsageMiddleware.on_model_call`. If **not**, refine R-2's token-observation criterion
      (accept unobserved, or add one bounded counter) and record it in the spec changelog
- [ ] Verify the streaming attribution path: the effective (routed) model can ride an existing
      `chat_stream` event field with `agent-stream-event.schema.json` byte-unchanged
- [ ] Verify resume-key stability: `get_middleware_key()` / `middle_context[key][reply_id]`
      (`_model_router.py:91,95,106`) is stable across a confirmation park/resume

## R-2: Opt-in per-turn model routing (binding on approval)

### Settings (`runtime_settings.py`)

- [ ] Add `model_router_enabled: bool = False`, `model_router_model: str | None`, and a parsed
      `model_router_candidates` (`name → (catalog model id, description)`), mirroring
      `compress_context_enabled` (:191, guard :324-332, env parse :557-559)
- [ ] Env parse: `AGENTSCOPE_MODEL_ROUTER_ENABLED` / `_MODEL` / `_CANDIDATES`
- [ ] `__post_init__` guard: enabled + **no** candidate map ⇒ inert (middleware not registered,
      not an error); an unknown/revoked catalog id in the map fails closed at build

### Precedence + provenance (`routes.py`)

- [ ] Refactor `_resolve_model` (:261) to return `(model_id, selected_by)` with
      `selected_by ∈ {request, pin, default}`; the request/pin fail-closed (422) and
      catalog-normalization semantics (:272-285) are unchanged
- [ ] Compute `routing_allowed = (selected_by == default)` and thread it into the kernel reply
      call so only default-resolved turns arm the router (`request > pinned > routed > default`)

### Middleware wiring (`runtime_kernel.py`)

- [ ] Pass the per-turn routing flag through `_build_agent(..., routing_allowed)` (:799) into
      `_build_middlewares(routing_allowed)` (:551)
- [ ] Register `ModelRouterMiddleware(classifier_model=_build_model(model_router_model),
      candidates=[ChatModelCandidate(name, _build_model(cid), desc), …], instructions=…)` only
      when enabled AND `routing_allowed` AND the candidate map is non-empty (`_model_router.py:23-50`)
- [ ] Position it per Stage-0 #1 so the swap is active for the inner model calls

### Attribution + visibility

- [ ] Surface the **effective** (post-routing) model id + `model_selected_by ∈ {request, pin,
      router, default}` from the reply path; `AgentChatResponse.model` (:335) and the structured
      log (:308-316, :361-369) carry the effective id
- [ ] No new closed-enum audit `event_type`; `agent-stream-event.schema.json` byte-unchanged

### Tests (`products/agent-platform/tests/`)

- [ ] opt-in gating — off ⇒ middleware absent & byte-identical to v0.51.1; on + map ⇒ present;
      on + no map ⇒ inert
- [ ] precedence — an explicit request model and a live pin both suppress routing; only a
      default-resolved turn routes
- [ ] fail-soft — a classifier error and an unknown candidate each keep the agent's own model
      and never hard-fail the turn
- [ ] resume — a routed `reply_id` survives a confirmation park/resume; same model post-resume
- [ ] attribution — `model_selected_by = router` on a swap, else the pre-routing tier; response
      `model` = the effective id
- [ ] no agentscope type leak; `agent-stream-event.schema.json` byte-stability
- [ ] token observation of the routing call — or the refined disposition from Stage-0 #2

## R-3: Routing-accuracy measurement gate (harness only; no default flip)

- [ ] Offline harness over a labeled turn sample recording routing **accuracy**, added
      **per-reply latency**, and the classification call's **token cost** (reuse SPEC-065's
      `agent_llm_tokens_total`); explicitly not a CI dependency and not an R-2 merge gate
- [ ] Tune the candidate `description` criteria against the measurement
- [ ] Record that default-on is a **separate operator decision** gated on this measurement — not
      shipped in this spec

## R-4: Documentation, audit, and backlog reconciliation (always)

- [x] Add the SPEC-071 row to `docs/specs/README.md` — added at `draft`, advanced to `approved`
      2026-11-01 (update to `delivered` on delivery)
- [x] `docs/workspace/agentscope-utilization-audit.md` §2 model-routing row → "adopt — SPEC-071
      approved; wiring pending delivery", linking this spec (flip to the delivered outcome on delivery)
- [x] `docs/agentic-aiops-platform/delivery-roadmap.md` Exploration Backlog "Per-turn model
      routing" row → promoted to SPEC-071 (approved); close on delivery
- [ ] If it ships: `CHANGELOG.md` entry referencing SPEC-071 (`## 0.52.0`)
- [ ] If it ships: `docs/guides/configuration-reference.md` documents the knob + router-model id +
      candidate map (+ a Feature Activation Matrix row)
- [ ] If it ships: release note; VERSION bumps in the eight-product lockstep

## Delivery Gate

- [ ] All acceptance criteria in `spec.md` verified (R-2 wiring; R-3 harness; R-4 rows)
- [ ] Living state docs updated (see the spec `Impact` section)
- [ ] `make verify` green with the shipped diff — eight product suites, overlays, policy +
      version-lockstep + secret gates, operator-portal suite + build, SPEC-063 real-Postgres campaign
- [ ] Spec index in `docs/specs/README.md` updated to `delivered`
- [ ] Spec status set to `delivered` (target v0.52.0)
