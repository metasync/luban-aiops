# v0.52.0 — Per-Turn Model Routing: Opt-In, Default-Off, Measured (SPEC-071)

Date: 2026-11-01
Release type: minor (an `agent-platform` kernel model-selection slice — no new
route, action, contract, JSON schema, audit event type, or execution path;
`agent-stream-event.schema.json` is byte-unchanged and no agentscope type leaks
through the v2 contract. Ships **default-off**; no GitOps overlay change is
required to keep the default posture, and enabling is per-deployment.)

## Summary

This release ships
[SPEC-071](../../specs/SPEC-071-agentscope-model-router/spec.md), the opt-in
adoption of agentscope 2.0.11's `ModelRouterMiddleware`. It closes the "Per-turn
model routing" [delivery-roadmap](../delivery-roadmap.md#exploration-backlog)
backlog row and resolves the
[utilization-audit §2](../../workspace/agentscope-utilization-audit.md)
model-routing entry, giving the platform an automatic "cheap/fast model for
simple turns, strong model for complex ones" path that **composes with** — rather
than replaces — [SPEC-024](../../specs/SPEC-024-runtime-llm-model-switching/spec.md)'s
audited model choice.

The surface was already pinned but unexamined: v0.51.1's agentscope 2.0.11
refresh carried `ModelRouterMiddleware` and the `classifier` package and, under
the four-point adoption-gate discipline, adopted none of the new surfaces. R-1
scored the middleware and found it **clears** all four gate points — it is a
model-selection (`on_reply`) middleware, not a tool-execution surface, so it adds
no execution or identity edge, emits no evidence frame, keeps the read-only
posture, and leaks no agentscope type through the platform-owned v2 contract.

**The router ships default-off.** R-3's live measurement (below) is the evidence
an operator would use to consider default-on; that flip is a **separate operator
decision** and is deliberately **not** made here.

## What shipped

- **R-2 — Opt-in wiring.** Three `AGENTSCOPE_*` settings register the middleware
  in `AgentKernel._build_middlewares()` only when enabled with a non-empty
  candidate map:
  - `AGENTSCOPE_MODEL_ROUTER_ENABLED` (default `false`),
  - `AGENTSCOPE_MODEL_ROUTER_MODEL` — the classifier's catalog model id,
  - `AGENTSCOPE_MODEL_ROUTER_CANDIDATES` — a JSON `name → {model, description}`
    map drawn from the credential-gated `MODEL_CATALOG`.

  With no candidate map the knob is **inert** (middleware not registered);
  enabled with a map but no classifier model fails startup fast (`ValueError`).
  When disabled, the kernel is byte-identical to v0.51.1.
- **Precedence `request > pinned > routed > default`.** The router selects only
  when the turn carries no explicit request and the session has no pin, so a
  human's explicit choice always wins — an additive extension of SPEC-024
  `_resolve_model`, not a change to its request/pin semantics.
- **Attribution + visibility.** The reply path surfaces the **effective**
  (post-routing) model id in `AgentChatResponse.model` and the existing
  `message_end` frame `model` field; a `model_selected_by ∈ {request, pin,
  router, default}` dimension rides the **structured logs only** — no new
  closed-enum audit `event_type` and no stream-schema change.
- **Fail-soft + resume-safe.** A routing error or an unknown candidate keeps the
  agent's own model and never hard-fails a turn; the routed model for a
  `reply_id` survives a confirmation park/resume via `middle_context` + the
  SPEC-017 snapshot. The routed model's *reply* tokens stay observed by the
  always-on `TokenUsageMiddleware` (SPEC-065); the router's own classification
  call bypasses `_call_model` and is deliberately unobserved while default-off.
- **Router backend is an existing catalog `ChatModelBase`.** Routing uses
  `generate_structured_output` — the same call the platform's threshold
  compression already uses — so `OpenAIClassifierModel` / `JevClassifierModel`
  are **not** wired and no new provider or dependency is introduced.
- **R-3 — Routing-accuracy measurement harness**
  (`products/agent-platform/harness/routing_accuracy.py` + `routing_sample.json`).
  Offline, outside `tests/` (so never pytest-collected and not part of
  `make verify`), it reuses the production `_build_middlewares(routing_allowed=True)`
  wiring for zero drift and wraps the classifier's `generate_structured_output` in
  a measurement-only shim plus a bounded token counter to capture the
  classification call's cost — the cost the SPEC-065 metrics do not see.

## Measured outcome (R-3, live)

A 24-turn labeled sample (`routing_sample.json`), measured against the live dev
providers. `_route` invokes **only** the classifier — the candidate models are
routing *targets* whose `description` text the classifier reads and are never
called — so the classifier alone determines both accuracy and the measured
overhead:

| Config | Classifier | Accuracy | Added latency (mean / p95) | Classification tokens (in + out / turn) |
|---|---|---|---|---|
| A (as-provisioned) | `qwen3-8b` | **0.0%** — 24/24 fail-soft | — (classifier 404'd) | — (0 calls booked) |
| A-retry | `qwen-flash` | **100.0%** (24/24) | 464 ms / 527 ms | 329 + 10 |
| B | `deepseek-v4-flash` | **100.0%** (24/24) | 758 ms / 912 ms | 440 + 34 |
| C (cross-provider deep) | `deepseek-v4-flash` | **100.0%** (24/24) | 828 ms / 1069 ms | 440 + 34 |

Configs A-retry and C route to a `fast`/`deep` pair (`qwen-flash`/`qwen3.8-max`
and `deepseek-v4-flash`/`qwen3.8-max`); B routes `deepseek-v4-flash`/`deepseek-v4-pro`.
B and C share a classifier and differ **only** in the deep candidate, yet returned
identical accuracy and identical token cost — empirically confirming that
candidate identity is irrelevant to the measurement and only the classifier and
the candidate `description` text drive it.

**Tuning outcome: none required.** The baseline `fast` / `deep` `description`
criteria saturate accuracy at 100% across every valid classifier, so the
reference sample is cleanly separable and no wording change improves it. The
measurement instead **pins the real default-on decision inputs**: classifier
choice (`qwen-flash` is the cheapest/fastest at 100%), added per-reply latency
(~0.46–0.83 s), and the classification token overhead (~330–440 input + 10–34
output per turn) that bypasses SPEC-065 by design.

**Config A's 0% is a real fail-soft demonstration, not a harness defect.** The
as-provisioned classifier id `qwen3-8b` 404s at the live DashScope compatible-mode
API; the router kept the agent's own model on all 24 turns (exit 0, 24 WARNINGs,
0 tokens booked) exactly as designed. Evidence for all four runs:
`.workspaces/spec071-evidence/config{A,A2,B,C}-*/measurement.json` (gitignored).

## Changed

- **Living docs.** `docs/guides/configuration-reference.md` gains the three router
  knobs and a Feature Activation Matrix row (grouped with the other opt-in kernel
  middleware); the [delivery-roadmap](../delivery-roadmap.md#exploration-backlog)
  backlog row and the
  [utilization-audit §2](../../workspace/agentscope-utilization-audit.md)
  model-routing entry are marked delivered/closed; and the
  [specs index](../../specs/README.md) row moves to `delivered`. **No JSON schema
  or contract change.**

## Verification

- `make verify` green, including the `agent-platform` suite and the new
  `test_model_router.py` (opt-in gating; precedence; fail-soft on error and on an
  unknown candidate; resume keeps the routed model; attribution; no type leak;
  `agent-stream-event.schema.json` byte-stability; the routed model's reply tokens
  ride SPEC-065 while the classification call is unobserved by design).
- The R-3 harness `--self-test` drives the *real* `ModelRouterMiddleware._route`
  against a deterministic stub classifier (no credentials, no network) and is
  **not** collected by pytest or invoked by any make target.
- `make validate-version` green at **0.52.0** across the eight products and the
  portal.

## Posture

Behavior-changing only when explicitly enabled; **inert and byte-identical to
v0.51.1 while default-off** (the shipped posture). No route, action, contract,
JSON schema, audit-event-type, or execution-path change, and no new identity edge
— the classifier authenticates with its own existing catalog provider credential,
so no new secret is introduced. Routing is model-selection only and reaches no
infrastructure, so identity, policy, and execution-safety semantics are unchanged
(SPEC-018 gate points 1–3). Any move to default-on, or to a broader candidate set,
remains gated on this measurement and is a separate operator decision.

### Side finding (outside SPEC-071 scope)

The live run surfaced a dev-catalog misconfiguration: 3 of the 5
`DASHSCOPE_MODELS` ids provisioned in the dev runtime profile (`qwen3-8b`,
`qwen3-14b`, `qwen3-30b-a3b`) 404 at the real DashScope API; only `qwen3.8-max`
and `qwen3.8-27b` resolve. The committed `runtime-secrets.example.env` carries two
of the invalid ids. The router is unaffected (it never invokes candidate models),
and this is tracked as a separate fix — recorded here so the next release sees it.
