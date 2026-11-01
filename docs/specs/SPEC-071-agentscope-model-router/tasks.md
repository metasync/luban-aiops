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

## Stage 0: Seam verification (no product diff) — DONE 2026-11-01

- [x] Verify `ModelRouterMiddleware.on_reply` wrap order in the `_build_middlewares()` list
      (`runtime_kernel.py:551`, incl. the `target_authorization_enabled` reorder at :576-581)
      so the routed model is active for the inner model calls and observed by `TokenUsageMiddleware`
      — **confirmed**: `on_reply` and `on_model_call` are *separate* per-hook chains
      (`_agent.py:219-241`), so the router (on_reply only) and `TokenUsageMiddleware`
      (on_model_call only) never compete on order; the on_reply swap is active for the inner
      `_call_model`
- [x] Verify whether the router's classifier `generate_structured_output` (`_model_router.py:127`)
      — a call on a **separate** `ChatModelBase`, not the agent's model — rides
      `TokenUsageMiddleware.on_model_call`. If **not**, refine R-2's token-observation criterion
      (accept unobserved, or add one bounded counter) and record it in the spec changelog
      — **confirmed it does NOT** (it bypasses `_call_model`, the only `on_model_call` dispatch
      site, `_agent.py:3291-3383`); R-2/R-3 refined in the spec changelog 2026-11-01: the routed
      model's *reply* tokens stay observed, the *classification* call is unobserved while
      default-off, and R-3 measures it via a bounded counter
- [x] Verify the streaming attribution path: the effective (routed) model can ride an existing
      `chat_stream` event field with `agent-stream-event.schema.json` byte-unchanged
      — **confirmed**: the `model` field already exists on `message_end`
      (`agent-stream-event.schema.json:28-31`); the kernel hard-stamps `frame["model"] =
      bound_model_id` (`runtime_kernel.py:1375-1378`), so Stage 4 must repoint that stamp
- [x] Verify resume-key stability: `get_middleware_key()` / `middle_context[key][reply_id]`
      (`_model_router.py:91,95,106`) is stable across a confirmation park/resume
      — **confirmed**: `get_middleware_key()` returns the class name (`_base.py:296-303`) and
      `middle_context` is a plain `AgentState` field (`state/_state.py:294`) that rides the
      SPEC-017 snapshot via `_snapshot_state`/`_restore_state` (`runtime_kernel.py:679/649`)

## R-2: Opt-in per-turn model routing (binding on approval)

### Settings (`runtime_settings.py`) — DONE 2026-11-01

- [x] Add `model_router_enabled: bool = False`, `model_router_model: str | None`, and a parsed
      `model_router_candidates` (`name → (catalog model id, description)`), mirroring
      `compress_context_enabled` (:191, guard :324-332, env parse :557-559) — added a frozen
      `ModelRouterCandidateSpec(name, model_id, description)` (agentscope-type-free) + a
      `_model_router_candidates_from_env` JSON parser
- [x] Env parse: `AGENTSCOPE_MODEL_ROUTER_ENABLED` / `_MODEL` / `_CANDIDATES`
- [x] `__post_init__` guard: enabled + **no** candidate map ⇒ inert (middleware not registered,
      not an error); enabled + map + **no** classifier model ⇒ startup `ValueError`; malformed
      JSON / non-object / empty `model`|`description` ⇒ startup `ValueError`; an unknown/revoked
      catalog id in the map fails closed at build (Stage 3, against `MODEL_CATALOG`)

### Precedence + provenance (`routes.py`) — DONE 2026-11-01

- [x] Refactor `_resolve_model` (:263) to return `(model_id, selected_by)` with
      `selected_by ∈ {request, pin, default}`; the request/pin fail-closed (422) and
      catalog-normalization semantics are unchanged — all five callers unpack the tuple
      (incl. the `chat_confirm` 410-expiry branch, which had passed it through whole)
- [x] Compute `routing_allowed = (selected_by == default)` and thread it into the kernel reply
      call so only default-resolved turns arm the router (`request > pinned > routed > default`)
      — **Path A**: `pin_session_model` now fires only on an explicit `body.model`, so a session
      pin always means "a human chose", and default-resolved turns stay routing-armed

### Middleware wiring (`runtime_kernel.py`) — DONE 2026-11-01

- [x] Pass the per-turn routing flag through `_build_agent(..., routing_allowed)` (:878) and
      `ensure_agent(..., routing_allowed)` (:916, `::routed` cache-key suffix) into
      `_build_middlewares(routing_allowed)` (:595)
- [x] Register `ModelRouterMiddleware(classifier_model=_build_model(model_router_model),
      candidates=[ChatModelCandidate(name, _build_model(cid), desc), …])` only when enabled AND
      `routing_allowed` AND the candidate map is non-empty (:647-674); an unknown/revoked catalog
      id raises `UnknownModelError` at build (fail-closed)
- [x] Appended after the always-on stack; Stage-0 #1 confirmed `on_reply` (router) and
      `on_model_call` (TokenUsage) are separate chains, so list position does not affect the swap

### Attribution + visibility — DONE 2026-11-01

- [x] `BlockingReply.effective_model` (additive; the two-value `__iter__` contract preserved)
      carries the routed id from `_effective_model_id(agent)`; `AgentChatResponse.model` and the
      `message_end` frame's existing `model` field report the effective id, else the resolved
      tier. `model_selected_by ∈ {request, pin, default}` rides the routes log and `router` the
      kernel's "model routing served turn" log — structured logs only, never the v2 contract
- [x] No new closed-enum audit `event_type`; `agent-stream-event.schema.json` byte-unchanged
      (still v13; the full-suite contract guard stays green)

### Tests (`products/agent-platform/tests/`) — DONE 2026-11-01

> `tests/test_model_router.py` (27 tests) + the updated doubles across the suite; the full
> agent-platform suite is green (1660 passed).

- [x] opt-in gating — off ⇒ middleware absent & the stack independent of the flag; on + map ⇒
      present (classifier + candidates built from catalog ids); on + no map ⇒ inert; an unknown
      candidate id ⇒ fail-closed at build
- [x] precedence — an explicit request model and a live pin both suppress routing; only a
      default-resolved turn routes (routes derivation + end-to-end Path-A pin threading)
- [x] fail-soft — a classifier error and an unknown candidate each keep the agent's own model
      and never hard-fail the turn (drives the real `ModelRouterMiddleware.on_reply`)
- [x] resume — a routed `reply_id` reuses its stored choice without re-routing (classifier not
      re-invoked); the `::routed` cache key makes a park/resume reuse the armed agent
- [x] attribution — `_effective_model_id` maps the routed candidate to its catalog id (`None`
      when routing did not fire / failed soft); the response `model` and the `message_end` frame
      carry the effective id; `model_selected_by = router` on the kernel routing log
- [x] no agentscope type leak; `agent-stream-event.schema.json` byte-stability (still v13; a
      routed `message_end` frame validates against the unchanged schema)
- [x] token observation — the refined Stage-0 #2 disposition, asserted not instrumented: the
      router is `on_reply`-only and TokenUsage `on_model_call`-only, and the classifier's direct
      `generate_structured_output` never reaches the model-call observation point

## R-3: Routing-accuracy measurement gate (harness only; no default flip) — harness + live measurement DONE 2026-11-01

> `products/agent-platform/harness/routing_accuracy.py` (+ the labeled `routing_sample.json`)
> is the offline measurement harness. It lives outside `tests/` and is not `test_*.py`, so
> `uv run pytest` never collects it (verified: `--collect-only` shows no harness items and the
> suite is unchanged at 1660 passed) and no make target invokes it — explicitly not a CI
> dependency and not an R-2 merge gate. `--self-test` drives the *real*
> `ModelRouterMiddleware._route` against a deterministic stub classifier (no credentials, no
> network) and asserts accuracy, both fail-soft paths, per-reply latency, and the token
> accounting — green.

- [x] Offline harness over a labeled turn sample recording routing **accuracy**, added
      **per-reply latency**, and the classification call's **token cost** — reuses the production
      wiring (`AgentKernel._build_middlewares(routing_allowed=True)`, zero drift) and captures the
      classification cost via a **bounded measurement-only counter** mirroring SPEC-065's
      `agent_llm_tokens_total{provider,model,direction}` shape (the classification call bypasses
      `TokenUsageMiddleware`, so it is absent from the emitted metrics by design — see R-2).
      Evidence writes to the gitignored `.workspaces/spec071-evidence/<run_id>/measurement.json`
- [x] Tune the candidate `description` criteria against the measurement — **live measurement run
      2026-11-01** (operator-directed; credentials sourced transiently from the dev-k8s
      `agent-platform-runtime-secrets`, keys never printed or recorded). Three configs over the
      24-turn reference sample, report-only (no accuracy gate):
      - **A / dashscope as-provisioned** (classifier `qwen3-8b`) → **0%, 24/24 fail-soft**: the
        real DashScope compatible-mode API 404s `qwen3-8b` — 3 of the 5 provisioned
        `DASHSCOPE_MODELS` ids (`qwen3-8b`, `qwen3-14b`, `qwen3-30b-a3b`) are not listed at that
        endpoint (only `qwen3.8-max` / `qwen3.8-27b` are valid). A real-provider validation of the
        fail-soft path: every turn kept the agent's model, no hard failure, 0 tokens booked.
      - **A-retry / dashscope** (classifier `qwen-flash`, deep `qwen3.8-max`) → **100%**; added
        latency mean 464ms (p95 527); classification cost 329 in / 10 out per turn.
      - **B / deepseek** (classifier `deepseek-v4-flash`, deep `deepseek-v4-pro`) → **100%**;
        added latency mean 758ms (p95 912); 440 in / 34 out per turn.
      - **C / cross-provider** (classifier `deepseek-v4-flash`, deep `qwen3.8-max`) → **100%**;
        mean 828ms (p95 1069); accuracy + token cost identical to B, confirming only the
        *classifier* and the *descriptions* drive the measurement (candidate ids are never called).

      **Tuning outcome: none required** — the baseline `fast` / `deep` descriptions saturate
      accuracy at 100% across every valid classifier, so the reference sample is cleanly separable
      and no wording change improves it. The measurement instead pins the real default-on inputs:
      classifier choice (`qwen-flash` is cheapest/fastest at 100%), added per-reply latency
      (~0.46-0.83s), and the classification token overhead (~330-440 input/turn) that bypasses
      SPEC-065 by design. Evidence: `.workspaces/spec071-evidence/config{A,A2,B,C}-*/measurement.json`.
      Default-on stays a **separate operator decision — not flipped**. Side finding (outside
      SPEC-071 scope): the dev cluster's provisioned `DASHSCOPE_MODELS` carries 3 ids the provider
      rejects; worth correcting separately.
- [x] Record that default-on is a **separate operator decision** gated on this measurement — not
      shipped in this spec: recorded in the harness docstring + report footer and here. The router
      ships default-off; the harness never flips the knob and no default change ships in SPEC-071

## R-4: Documentation, audit, and backlog reconciliation (always)

- [x] Add the SPEC-071 row to `docs/specs/README.md` — added at `draft`, advanced to `approved`
      2026-11-01, **flipped to `delivered` on delivery 2026-11-01** (with a v0.52.0 delivery clause)
- [x] `docs/workspace/agentscope-utilization-audit.md` §2 model-routing row → "adopt — SPEC-071
      approved; wiring pending delivery", linking this spec — **flipped to the delivered outcome
      2026-11-01** ("adopted (opt-in, default-off); delivered as v0.52.0" + the R-3 measurement)
- [x] `docs/agentic-aiops-platform/delivery-roadmap.md` Exploration Backlog "Per-turn model
      routing" row → promoted to SPEC-071 (approved); **closed on delivery 2026-11-01** (delivered
      v0.52.0; intro count reconciled — five candidates remain open)
- [x] If it ships: `CHANGELOG.md` entry referencing SPEC-071 (`## 0.52.0`) — **added** (links the
      release note; records default-off + the R-3 measurement)
- [x] If it ships: `docs/guides/configuration-reference.md` documents the knob + router-model id +
      candidate map (+ a Feature Activation Matrix row) — **added** (3 env rows grouped with the
      opt-in kernel knobs + the Feature Activation Matrix row after SPEC-064)
- [x] If it ships: release note; VERSION bumps in the eight-product lockstep — **done**
      (`release-notes/2026-11-01-per-turn-model-routing.md`; VERSION 0.51.1 → 0.52.0 across 27
      files — VERSION + 8 pyproject + 8 metadata + 2 `__init__` + 8 uv.lock self-entries;
      `make validate-version` green)

## Delivery Gate

- [x] All acceptance criteria in `spec.md` verified (R-2 wiring pinned by `test_model_router.py`;
      R-3 harness + the live A/B/C measurement at 100%; R-4 rows swept)
- [x] Living state docs updated (see the spec `Impact` section) — utilization-audit §2,
      delivery-roadmap backlog, `docs/specs/README.md`, configuration-reference, `CHANGELOG.md`,
      and the release note
- [x] `make verify` green with the shipped diff — eight product suites, overlays, policy +
      version-lockstep + secret gates, operator-portal suite + build, SPEC-063 real-Postgres campaign
      — **re-run 2026-11-01 against the v0.52.0 shipped diff: exit 0 in 43m19s** (agent-platform 1660
      passed incl. `test_model_router.py`; operator-portal 537 passed + vite build; SPEC-063 campaign
      **795 passed, 2 deselected, exit 0**; zero failures across every stage; version-lockstep gate
      green at 0.52.0). Uncommitted; no commit/push; default-on not flipped
- [x] Spec index in `docs/specs/README.md` updated to `delivered`
- [x] Spec status set to `delivered` (target v0.52.0) — delivered 2026-11-01
