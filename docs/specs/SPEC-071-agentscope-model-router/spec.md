# SPEC-071: Per-Turn Model Routing Adoption (AgentScope `ModelRouterMiddleware`)

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-11-01
- approved: 2026-11-01 (all five Open Questions ratified exactly as proposed by the operator)
- delivered: 2026-11-01 (v0.52.0; router ships default-off)
- release slice: Exploration Backlog — agentscope adoption family; target version **v0.52.0** (a minor bump over v0.51.1), delivered 2026-11-01
- related ADRs: [ADR-0006](../../adr/0006-contract-purpose-invariant-enforcement.md)
  (kernel exploitation follows SPEC-018's four-point adoption gate),
  [ADR-0002](../../adr/0002-reaffirm-agentscope-runtime-kernel.md) (AgentScope 2.0 as the
  runtime kernel). **No new ADR is expected**: like SPEC-064's `CompressContext`, this is
  an opt-in kernel middleware within the existing gate that extends SPEC-024's
  model-selection precedence rather than changing the contract or the authority model.
- lineage: promoted from the [model-router spike memo](../../workspace/agentscope-model-router-spike.md)
  (2026-11-01) and the [Exploration Backlog "Per-turn model routing" row](../../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog);
  resolves the [utilization-audit §2](../../workspace/agentscope-utilization-audit.md)
  model-routing row. Extends [SPEC-024](../SPEC-024-runtime-llm-model-switching/spec.md)
  (runtime LLM model switching / audited choice), SPEC-026/027 (the credential-gated
  `MODEL_CATALOG` + live discovery), [SPEC-065](../SPEC-065-r5-observability-token-cost-dashboards/spec.md)
  (always-on LLM-token observation), and the SPEC-017/018 kernel state + middleware discipline.

> SDD note: `spec.md` was drafted first and **approved 2026-11-01** — the operator ratified
> all five Open Questions exactly as proposed (see `## Open Questions — resolved`). R-1 (the
> four-point gate evaluation) is delivered by the memo — verdict: **clears**. Approval
> authorizes the R-2 opt-in wiring and the [plan](plan.md) / [tasks](tasks.md) below;
> implementation may **begin**. It does **not** authorize a merge, commit/push, deployment, a
> version bump, or any move to default-on — those are separate boundaries, and R-3's
> measurement gate must clear before default-on is even considered.

## Summary

Adopt — behind an opt-in, default-off kernel knob — agentscope 2.0.9/2.0.10's
`ModelRouterMiddleware`, which selects each reply's chat model by classifying the latest
user input over named candidates drawn from the existing credential-gated `MODEL_CATALOG`.
The R-1 spike scored it against SPEC-018's four-point adoption gate and found it **clears**
all four: it is a model-selection (`on_reply`) middleware, not a tool-execution surface, so
it adds no execution or identity edge, emits no evidence frame, keeps the read-only posture,
and leaks no agentscope type through the v2 contract. It is **resume-safe** (the decision
lives in `agent.state.middle_context[reply_id]`, covered by the SPEC-017 snapshot) and
**fail-soft** (any routing error or unknown candidate keeps the agent's own model). The one
design decision this spec fixes is how auto-routing reconciles with SPEC-024's audited
`request > pinned > default` precedence and attribution.

## Motivation

- **The surface is already pinned and unexamined.** v0.51.1 moved agentscope to 2.0.11,
  which carries `ModelRouterMiddleware` (2.0.9/2.0.10) and the `classifier` package.
  Consistent with the four-point adoption-gate discipline, that dependency refresh adopted
  none of the new surfaces and the headline-feature review deferred this one to a spec
  ([utilization-audit §2](../../workspace/agentscope-utilization-audit.md), backlog row).
  Deciding its disposition while the version is fresh prevents an "available-but-unexamined"
  drift in the lockfile.
- **It fills a real gap the platform does not cover today.** A turn's model is chosen by an
  explicit operator request, a session pin, or the profile default (SPEC-024
  `_resolve_model`). There is no automatic "cheap/fast model for simple turns, strong model
  for complex ones" path, so operators either over-provision an expensive model for every
  turn or hand-switch per turn. Auto-routing is the out-of-box agentscope answer.
- **Low-risk; it composes with existing machinery.** It reuses the credential-gated
  `MODEL_CATALOG` (SPEC-026/027), and the routed model's *reply* tokens stay observed by the
  always-on `TokenUsageMiddleware` (SPEC-065 R-1) because `on_reply` swaps `agent.model`
  before the inner `_call_model` runs (the router's *own* classification call is a separate
  direct `generate_structured_output` that bypasses `on_model_call` — see R-2, corrected at
  Stage-0). It rides the SPEC-017 snapshot for resume — the same integration shape as the
  delivered `CompressContext` ([SPEC-064](../SPEC-064-agentscope-compression-and-goal-pipeline/spec.md) R-2).
- **The provider caveat from the headline review is resolved.** The router accepts a plain
  `ChatModelBase` and routes via `generate_structured_output` — the same call the platform's
  threshold compression already uses — so it needs no OpenAI/TypeSafe classifier and no new
  dependency (memo §2.3).
- **Why this slice.** The backlog row's promotion trigger (operator approval to promote once
  the precedence + auditability questions are resolved) is met by this spec resolving them
  with proposed defaults.

## Requirements

Each requirement is stable once this spec is `approved` and carries testable acceptance
criteria. R-1 is delivered by the memo; R-2 binds only on approval; R-3 gates any move to
default-on; R-4 reconciles the living documentation.

### R-1: Four-point adoption-gate evaluation — DELIVERED

Score `ModelRouterMiddleware` against the SPEC-018 four-point adoption gate and record an
`adopt` / `keep out` verdict backed by evidence from the locked 2.0.11 install. The four
gate points: (1) deny-by-default policy + audit preserved, tool-gateway the only execution
surface; (2) identity via the gateway-forwarded delegated token only; (3) read-only
operational posture; (4) no agentscope types leak through the platform-owned v2 contract.

Acceptance criteria (satisfied):

- The [memo](../../workspace/agentscope-model-router-spike.md) landed under `docs/workspace/`
  recording the four gate points, the concrete 2.0.11 evidence (`middleware/_model_router.py`
  `on_reply`/`_route`, the `classifier` package, the kernel `_build_middlewares()` seam, the
  `MODEL_CATALOG`, and SPEC-024 `_resolve_model`), and an explicit verdict.
- **Verdict: clears all four gate points** (memo §3). Gate 1 — a model-selection middleware
  that executes no tool and reaches no infrastructure, with no `gateway_tool_name` so no
  evidence frame; gate 2 — no gateway call, no new identity edge; gate 3 — selects among
  already-read-only-configured models; gate 4 — the routed result reduces to a model id, no
  agentscope type on the v2 contract, `agent-stream-event.schema.json` byte-unchanged.
- The [utilization-audit §2](../../workspace/agentscope-utilization-audit.md) model-routing
  row records the resolved decision and links the memo (done 2026-11-01).

### R-2: Opt-in per-turn model routing — conditional adoption

**Binds only on approval.** Wire `ModelRouterMiddleware` as an opt-in, default-off kernel
surface that composes with SPEC-024 precedence, preserves auditability, and stays fail-soft
and resume-safe.

Acceptance criteria:

- **Opt-in, default off, inert when disabled.** A new knob (working name
  `AGENTSCOPE_MODEL_ROUTER_ENABLED`, default off) plus a router-model id and a candidate map
  (`name → catalog model id + description`), parsed like the other `AGENTSCOPE_*` settings
  and registered in `_build_middlewares()` (`runtime_kernel.py:551`) only when enabled. When
  disabled, no middleware is registered and behavior is byte-identical to v0.51.1.
- **Precedence `request > pinned > routed > default`.** The router selects **only** when the
  turn carries no explicit request and the session has no pin, so a human's explicit choice
  always wins — an additive extension of SPEC-024 R-3 `_resolve_model` (`routes.py:261`), not
  a change to its request/pin semantics.
- **Candidates come from the credential-gated `MODEL_CATALOG` only.** An unknown or revoked
  model can never be routed to: the SPEC-027 catalog swap keeps the set current and `_route`'s
  unknown-candidate guard is the backstop.
- **Router backend is an existing catalog `ChatModelBase`.** Routing uses
  `generate_structured_output`; `OpenAIClassifierModel` / `JevClassifierModel` are **not**
  wired, so no new provider or dependency is introduced.
- **Auditable.** The turn records the model actually used plus a
  `model_selected_by ∈ {request, pin, router, default}` attribution dimension, extending
  SPEC-024's audited choice. This is an attribution field on the existing turn/model record —
  **no new closed-enum audit `event_type`**.
- **Fail-soft.** A routing error or an unknown candidate keeps the agent's own model and never
  hard-fails a turn (pinned by a test).
- **Resume-safe.** The routed model for a `reply_id` survives a confirmation park/resume via
  `middle_context` + the SPEC-017 snapshot; the same model is used post-resume (pinned by a
  test).
- **Identity unchanged.** Routing makes no gateway call and introduces no identity edge
  (gate 2); the classifier model authenticates with its own catalog provider credential.
- **Contract boundary unchanged.** No agentscope type leaks through v2;
  `agent-stream-event.schema.json` stays byte-unchanged. If the routed model is surfaced to
  the portal it is a plain id in the existing SPEC-024/026 model field.
- **Token observation — corrected at Stage-0 (2026-11-01).** The routed model's *reply*
  tokens **are** observed by the existing `TokenUsageMiddleware`: `on_reply` swaps
  `agent.model` before the inner `_call_model` runs, and `_call_model` wraps `self.model`
  (dispatching `on_model_call`), so the serving model's usage rides SPEC-065 unchanged — no
  new instrumentation. The router's own *classification* call, however, is a direct
  `classifier_model.generate_structured_output` inside `_route` on a separate `ChatModelBase`;
  it does **not** pass through `_call_model`, so it is **not** observed by `TokenUsageMiddleware`.
  R-2 accepts that classification cost as unobserved while default-off (no new instrumentation);
  R-3's measurement gate captures it via a bounded measurement-only counter instead.
- **Tests.** opt-in gating (off ⇒ middleware absent, on ⇒ present); precedence (an explicit
  request/pin overrides the router); fail-soft on error and on unknown candidate; resume keeps
  the routed model; no type leak; `agent-stream-event.schema.json` byte-stability; the routed
  model's reply tokens ride SPEC-065 while the classification call is unobserved by design
  (asserted, not instrumented).

### R-3: Routing-accuracy measurement gate (before any default-on)

The router ships **default-off**. Any move to default-on, or to a broader candidate set, is
gated on a measurement — the [SPEC-066](../SPEC-066-skill-retrieval-ranking-fidelity/spec.md)
"measure before building" discipline applied to routing quality.

Acceptance criteria:

- A measurement on a representative turn sample records routing **accuracy** (did it select the
  intended tier?), the added **per-reply latency**, and the classification call's **token cost**
  (via a bounded measurement-only counter, since the classification call bypasses
  `TokenUsageMiddleware` and is therefore absent from the SPEC-065 metrics — see R-2).
- The candidate `description` criteria are tuned against that measurement, since routing quality
  is only as good as the criteria the classifier is given.
- Default-on is a **separate operator decision** evidenced by the measurement; absent it, the
  knob stays off.

### R-4: Documentation, audit, and backlog reconciliation

Acceptance criteria:

- [utilization-audit §2](../../workspace/agentscope-utilization-audit.md) model-routing row
  flips from "adopt candidate; spike done" to the delivered outcome, linking this spec.
- The [delivery-roadmap](../../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog)
  "Per-turn model routing" backlog row is promoted/closed to reflect the outcome.
- `docs/specs/README.md` gains the SPEC-071 row (added at `draft`; updated on approval/delivery).
- **If adopted and shipped:** a `CHANGELOG.md` entry references SPEC-071,
  `docs/guides/configuration-reference.md` documents the new knob + candidate map, a release
  note is written, and VERSION bumps in the eight-product lockstep.
- This spec's status/changelog records the outcome.

## Non-Goals

- The other 2.0.9–2.0.11 headline surfaces — `AskUser`, `agentscope.sop`, MCP tool progress
  streaming, RAG LLM-reranking, `TeamPipeline`, `A2AAgent` — stay in the audit/backlog and are
  **out of scope** here. The multi-agent surfaces are governed by the separate
  [multi-agent orchestration memo](../../workspace/multi-agent-orchestration-spike.md) and its
  pending superseding ADR, not by this spec.
- No change to the governed execution path (SPEC-037/038/063), the approval/HITL model
  (SPEC-020/030/031), skill-composition authority (SPEC-057 / ADR-0011), or the read-only posture.
- No dedicated classifier provider integration (`OpenAIClassifierModel` / `JevClassifierModel`)
  and no new dependency.
- No change to SPEC-024's explicit request/pin semantics beyond inserting `routed` between
  `pinned` and `default`.
- No dependency version change — agentscope is already pinned at 2.0.11 by v0.51.1; this spec
  changes disposition, not the lockfile.
- Per-role or multi-agent model selection is out of scope (it belongs to the multi-agent track).

## Impact

- **products touched:** `products/agent-platform` (kernel) only, and only if R-2 is approved;
  otherwise documentation-only. No other product is affected.
- **contracts touched:** none expected. `agent-stream-event.schema.json` stays byte-unchanged;
  the routed model surfaces (if at all) as a plain id in the existing SPEC-024/026 model field.
  A `model_selected_by` attribution field is additive on the turn/audit record.
- **identity / policy / audit / execution safety impact:** must be **none by design** (gate
  points 1–3). Routing is model-selection only; it executes no tool and reaches no
  infrastructure. Audit gains an attribution dimension, not a new event type.
- **living state docs to update on delivery:** `docs/workspace/agentscope-utilization-audit.md`,
  `docs/agentic-aiops-platform/delivery-roadmap.md`, `docs/specs/README.md`, and — only if it
  ships — `docs/guides/configuration-reference.md`, `CHANGELOG.md`, and a release note.

## Open Questions — resolved (ratified 2026-11-01)

The R-1 memo (§7) raised five design questions. The operator **ratified all five proposed
defaults exactly as written** on 2026-11-01, advancing this spec `draft` → `approved`. Each
resolved decision below is now binding on R-2.

1. **Precedence — proposed: `request > pinned > routed > default`.** The router chooses only
   when the operator made no explicit request and the session has no pin, so a human's explicit
   choice always wins (extends SPEC-024 R-3). Rationale: preserves the audited explicit-choice
   model; routing is a convenience default-setter, never an override.
2. **Candidate set — proposed: config-provided and minimal; routing disabled with no map.**
   Candidates (`name → catalog model id + description`) come from environment config, not
   hardcoded, so with no candidate map the knob has no effect. A sensible first set is two tiers
   — a fast/cheap model for simple turns and the profile's strong model for complex ones — but
   the operator names the actual catalog ids. Rationale: the catalog is deployment-specific
   (env-derived), so the spec fixes the shape, not the models.
3. **Router backend — proposed: an existing catalog `ChatModelBase` via
   `generate_structured_output`.** No `OpenAIClassifierModel` / `JevClassifierModel`, no new
   provider or dependency. Rationale: the chat-model path is provider-agnostic and already
   exercised by threshold compression.
4. **Visibility — proposed: surface the routed model + `model_selected_by` in the portal model
   field and the audit attribution.** Rationale: prevents a silent downgrade and keeps SPEC-024's
   "audited choice" property intact. *(Follow-up: the audit-attribution half shipped here in
   SPEC-071 — `model_selected_by ∈ {request, pin, default, router}`; the operator-facing portal
   half — an explicit "Auto (routed)" selector entry plus a Settings ▸ Platform feature-flag
   inventory — is realized by
   [SPEC-072](../SPEC-072-auto-routing-and-platform-feature-flags/spec.md).)*
5. **Default posture — proposed: opt-in, default-off, until R-3's measurement justifies broader
   enablement.** Rationale: routing quality depends on the candidate criteria; measure before
   trusting it by default.

## Changelog

- 2026-11-01: **delivered (v0.52.0)** — shipped under the operator's explicit ship-time
  authorization (R-4 docs + the VERSION lockstep bump; **no commit/push**, and default-on **not**
  flipped). R-2 wired the opt-in, default-off `ModelRouterMiddleware`
  (`AGENTSCOPE_MODEL_ROUTER_ENABLED` / `_MODEL` / `_CANDIDATES`; precedence
  `request > pinned > routed > default`; the effective model + `model_selected_by` attribution on
  the structured logs; fail-soft; resume-safe; `agent-stream-event.schema.json` byte-unchanged; no
  new dependency). R-3's offline harness plus a live A/B/C measurement on the 24-turn sample
  reached **100% accuracy** across every valid classifier (added latency ~0.46–0.83 s; ~330–440
  input + 10–34 output classification tokens per turn), so **no candidate `description` retuning
  was required**; the as-provisioned `qwen3-8b` classifier 404'd and demonstrated the fail-soft
  path (24/24 kept the agent's model) — a dev-catalog side-finding tracked separately. R-4
  reconciled the living docs, the configuration reference, `CHANGELOG.md`, and the
  [release note](../../agentic-aiops-platform/release-notes/2026-11-01-per-turn-model-routing.md).
  **The router stays default-off**; default-on remains a separate, measurement-gated operator
  decision, not made here.
- 2026-11-01: **Stage-0 seam verification (no product diff)** — verified the four design risks
  the [plan](plan.md) flagged against the locked agentscope 2.0.11 install and the 0.51.1 kernel:
  (S0-1) `on_reply` and `on_model_call` are built as *separate* per-hook chains (`_agent.py:219-241`),
  so `ModelRouterMiddleware` (on_reply only) and `TokenUsageMiddleware` (on_model_call only) never
  compete on wrap order; (S0-2) **the R-2 token-observation criterion was factually wrong and is
  corrected above** — the router's classification `generate_structured_output` is a direct call on a
  separate `ChatModelBase` inside `_route`, bypassing `_call_model` (the only `on_model_call`
  dispatch site, `_agent.py:3291-3383`), so it is *not* observed by `TokenUsageMiddleware`; only the
  routed model's *reply* tokens are (the on_reply swap is active for the inner `_call_model`);
  (S0-3) the routed model can ride the *existing* `model` field on `message_end`
  (`agent-stream-event.schema.json:28-31`, byte-unchanged), but the kernel currently hard-stamps
  `frame["model"] = bound_model_id` (`runtime_kernel.py:1375-1378`) with the pre-routing resolved id,
  so R-2 wiring must repoint that stamp at the actually-serving model; `model_selected_by` belongs on
  the audit/structured-log trail (SPEC-024 R-4 pattern), not the stream schema; (S0-4) resume-key
  stability holds — `get_middleware_key()` returns the class name (`_base.py:296-303`) and
  `middle_context` is a plain `AgentState` field (`state/_state.py:294`) that rides the SPEC-017
  snapshot via `_snapshot_state`/`_restore_state` (`runtime_kernel.py:679/649`) with no extra work.
  Refines R-2/R-3 wording only; no product, contract, policy, or version change.
- 2026-11-01: **approved** — the operator ratified all five Open Questions exactly as
  proposed (precedence `request > pinned > routed > default`; config-provided minimal
  candidate set, routing inert with no map; router backend = an existing catalog
  `ChatModelBase` via `generate_structured_output`; routed model + `model_selected_by`
  surfaced; opt-in / default-off until R-3's measurement). Target version v0.52.0; the
  [plan](plan.md) and [tasks](tasks.md) are written and binding; implementation is
  authorized to begin (not to merge, commit/push, deploy, version-bump, or flip default-on).
- 2026-11-01: created as `draft` — promotes the [model-router spike memo](../../workspace/agentscope-model-router-spike.md)'s
  "adopt (opt-in)" verdict into a spec and resolves the memo's five design Open Questions with
  **proposed defaults** for operator ratification. R-1 (four-point gate evaluation) is delivered
  by the memo (verdict: clears). Grounded in static inspection of the locked agentscope 2.0.11
  install and the agent-platform kernel at 0.51.1 (`c4214cf`). No product code, contract, policy,
  GitOps, deployment, or version change is authorized by this draft; `plan.md` / `tasks.md` follow
  approval.
