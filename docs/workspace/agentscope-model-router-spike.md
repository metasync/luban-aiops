# Spike: AgentScope 2.0.9/2.0.10 `ModelRouterMiddleware` + `classifier` — Adoption-Gate Evaluation

Status: assessment complete (2026-11-01). `ModelRouterMiddleware` **clears**
SPEC-018's four-point adoption gate and is recommended for **opt-in** adoption as
candidate **SPEC-071** (wiring is *not* authorized by this memo). No runtime change,
no implementation, and no spec-status flip are part of this assessment.
Date: 2026-11-01
Spec home: candidate **SPEC-071** — number assigned only on promotion, per the memo-first rule
Roadmap home: [Exploration Backlog](../agentic-aiops-platform/delivery-roadmap.md#exploration-backlog) — the "Per-turn model routing" row
Audit home: [agentscope-utilization-audit.md §2](agentscope-utilization-audit.md) — the model-routing row
Evidence baseline: repository at 0.51.1 (`c4214cf`); static inspection of the locked
agentscope 2.0.11 install (`middleware/_model_router.py`, `classifier/`) and the
agent-platform kernel integration (`runtime_kernel.py`, `services/model_catalog.py`,
`api/v2/routes.py`), 2026-11-01. No agent was run, no routing decision was executed,
and nothing was deployed.

## 1. Question and recommendation

> Does agentscope's `ModelRouterMiddleware` (auto per-turn chat-model selection by
> classifying the user input) clear SPEC-018's four-point adoption gate, and should
> the platform wire it — given Luban already has runtime model switching (SPEC-024),
> a credential-gated `MODEL_CATALOG` (SPEC-026/027), and always-on LLM-token
> observation (SPEC-065)?

**Recommendation: adopt, opt-in, default off, as a separately approved SPEC-071.**
It clears all four gate points because it is a *model-selection* middleware
(`on_reply`), not a tool-execution surface: it swaps `agent.model` among models
already in the credential-gated `MODEL_CATALOG`, executes no tool, reaches no
infrastructure, emits no evidence/SSE frame, introduces no identity edge, and keeps
the read-only posture. Two properties make it a good fit for Luban's HITL model:

- **Resume-safe by construction.** The routing decision is stored in
  `agent.state.middle_context[key][reply_id]` — the *same* snapshot-covered bucket
  SPEC-018 (`ReplyBudgetControlMiddleware`) and SPEC-065 use — so a reply that parks
  on a confirmation and later resumes **keeps the model it was routed to**.
- **Fail-soft by construction.** Any routing error, or a choice of an unknown
  candidate, logs a warning and keeps the agent's own model — it never hard-fails a
  turn.

The one **open design question** a SPEC must resolve is precedence and
auditability: Luban's SPEC-024 already resolves a turn's model as
`request > pinned > default` and treats the choice as *audited*. Auto-routing must
slot **below** an explicit request/pin and **above** the default, and the routed
model must be emitted as the turn's audited model attribution — not a silent
override (§4, §5).

The four gate points (SPEC-018): (1) deny-by-default policy + audit preserved,
tool-gateway the only execution surface; (2) identity carried only by the
gateway-forwarded delegated token; (3) read-only operational posture; (4) no
agentscope types leak through the platform-owned v2 contract.

## 2. What the surface is (locked 2.0.11)

- `ChatModelCandidate` (`middleware/_model_router.py:24`) is a dataclass
  `{name: str, model: ChatModelBase, description: str}` — `name` is the stable label
  the classifier returns, `description` is "when this candidate should be selected."
- `ModelRouterMiddleware(classifier_model, candidates, instructions=_DEFAULT_INSTRUCTIONS)`
  (`_model_router.py:37`, `__init__` at `:45`) rejects duplicate candidate names,
  builds a `ChoiceQuestion` from the candidate descriptions, and a JSON schema
  `{"choice": {"enum": names}}`.
- `classifier_model` is typed `ClassifierModelBase | ChatModelBase` — **either** a
  dedicated classifier **or** an ordinary chat model.

### 2.1 The routing mechanism (`on_reply`, `_model_router.py:84`)

The hook swaps `agent.model` for the selected candidate **for the duration of one
reply**, and restores the original in a `finally`:

- It reads `routed = agent.state.middle_context.get(key, {})`. On a **resume**
  (`inputs` is not a fresh `Msg`/`list`) it restores
  `self._models.get(routed.get(agent.state.reply_id), original_model)` — the model
  chosen before the park.
- On a **fresh** reply's `ReplyStartEvent` it calls `_route(latest_user_text)`,
  stores `middle_context[key] = {event.reply_id: name}`, and sets
  `agent.model = self._models.get(name, original_model)`.
- `finally: agent.model = original_model` — the swap never mutates the agent's
  configured model beyond the reply.

### 2.2 `_route` — two interchangeable backends (`_model_router.py:112`)

- If `classifier_model` is a `ClassifierModelBase`, it is called with the
  `ChoiceQuestion` and the `ChoiceAnswer.choice` is taken.
- **Otherwise (a plain `ChatModelBase`)** it calls
  `classifier_model.generate_structured_output(messages=[SystemMsg(prompt),
  UserMsg(text)], structured_model=schema)` and reads `res.content["choice"]`.
- **Fail-soft:** any exception logs "Chat model routing failed, keeping the agent's
  model" and returns `None`; a `name` not in `self._models` logs "Routing model
  selected unknown candidate …, keeping the agent's model" and returns `None`.
- `_latest_user_text` (`:152`) routes on the most recent user message text; no text
  ⇒ `None` (keep the agent's model).

### 2.3 The classifier package — and why Luban needs none of it

`agentscope.classifier` ships `ClassifierModelBase` (`classifier/_base.py:13`,
constructed from a `CredentialBase` + `model` name), and two concrete providers:
`OpenAIClassifierModel` (`classifier/_openai/_model.py:125`, built on the OpenAI SDK
with `api_key` + `base_url`) and `JevClassifierModel`
(`classifier/_jev/_model.py:70`, built on a **`TypeSafeCredential`** / TypeSafe API,
`_jev/_model.py:80`). Both are **provider-specific**.

**This resolves the Tier-review caveat** ("verify `OpenAIClassifierModel` against
dashscope/deepseek/luban"). Luban does **not** need either dedicated classifier: the
`ChatModelBase` path (§2.2) routes with `generate_structured_output`, which the
platform's configured chat models already support — the identical call the
threshold `CompressContext` path relies on today ([SPEC-064 R-1 §2.1](agentscope-compression-goal-pipeline-spike.md)).
So an existing `MODEL_CATALOG` model can be the router with **no new provider,
credential, or dependency**.

## 3. Gate scoring

| Gate point | Verdict | Evidence |
|---|---|---|
| 1. Policy + audit; tool-gateway the only **execution** surface | **Pass** | The middleware executes no tool and reaches no infrastructure — it selects among already-configured chat models and calls one model to classify. It has no `gateway_tool_name`, so `ToolEvidenceMiddleware.on_acting` passes it through with no evidence frame, and `_count_gateway_tools` is unaffected. **Condition:** the routed model must be recorded as the turn's audited model attribution (§4.2), extending — not bypassing — SPEC-024's audited choice; no new audit `event_type` is required (it is an attribution field on the existing turn/model events). |
| 2. Identity via the delegated token only | **Pass** | Routing makes no gateway call, so it introduces no identity edge. The classifier (a `MODEL_CATALOG` chat model) authenticates with that entry's own provider credential — the same model-provider credential the kernel already uses to call it — not a user-identity path. The `DELEGATED_TOKEN` contextvar is untouched. |
| 3. Read-only operational posture | **Pass** | It selects among models that are themselves read-only-configured, and adds only a model inference (the classification). No filesystem, sandbox, workspace, or mutation surface. The posture is unchanged. |
| 4. No agentscope types through the v2 contract | **Pass** | The middleware sets `agent.model` internally and the routed result reduces to a model **id/name** string. No agentscope type crosses the v2 SSE boundary; `agent-stream-event.schema.json` stays byte-unchanged. If the routed choice is surfaced to the portal it is a plain id in the existing SPEC-024/026 model field. |

Unlike the multi-agent surfaces ([multi-agent orchestration memo](multi-agent-orchestration-spike.md)),
`ModelRouterMiddleware` clears all four points **as shipped**. The remaining work is
integration design, not an architecture change.

## 4. Integration design a SPEC-071 must fix

### 4.1 Precedence with SPEC-024 (the pivotal decision)

Today `routes.py:261 _resolve_model` resolves a turn's model as
**`request > pinned > default`** (an explicit request that is not in the catalog
fails closed with 422; a pin is honored while it still exists). Auto-routing must be
inserted as: **`request > pinned > routed > default`** — the router chooses only when
the operator made no explicit request and the session has no pin, so a human's
explicit choice always wins. The router's `candidates` are drawn from the same
credential-gated `MODEL_CATALOG` (`services/model_catalog.py:50`), so an unknown or
revoked model can never be routed to (the catalog swap of SPEC-027 keeps the set
current; `_route`'s unknown-candidate guard is the backstop).

### 4.2 Auditability

SPEC-024 made the model choice *audited* ("pinning and audit attribution carry model
names"). The routed choice must be attributed the same way — the turn records the
model actually used, plus a `model_selected_by ∈ {request, pin, router, default}`
dimension so an operator/auditor can tell an auto-routed turn from an explicit one.
This is an attribution field on existing events, not a new closed-enum `event_type`.

### 4.3 Wiring (mirrors the existing opt-in kernel features)

- A default-off knob (e.g. `AGENTSCOPE_MODEL_ROUTER_ENABLED`) plus a router-model id
  and a candidate map (`{name → catalog model id, description}`), parsed like the
  other `AGENTSCOPE_*` settings.
- Register `ModelRouterMiddleware` in `_build_middlewares()`
  (`runtime_kernel.py:551`) beside `TokenUsageMiddleware` (SPEC-065 R-1) — one more
  list entry, constructed only when the knob is on. Candidate `ChatModelBase`
  instances reuse the kernel's existing per-entry model construction
  (`runtime_kernel.py:393`, `:423`).
- Ordering: the router is an `on_reply` middleware and is independent of the
  `on_model_call` `TokenUsageMiddleware` and the `on_check_permission` /
  `on_acting` gateway middlewares, so stack position does not change their behavior.

### 4.4 Cost, latency, and measurement

The router adds **one extra model call per reply** (the classification). Its tokens
are already observed by SPEC-065's `TokenUsageMiddleware` (an `on_model_call`), so
the overhead is measurable, not hidden. A SPEC should (a) recommend a cheap router
model, (b) measure routing **accuracy** on real traffic before any default-on, since
the choice quality is only as good as the candidate `description` criteria, and
(c) confirm the added latency is acceptable for the interactive portal turn.

### 4.5 No conflict with `CompressContext`

Both are opt-in kernel features that ride the SPEC-017 snapshot: compression mutates
`state.context`/`state.summary`; the router mutates `agent.model` (reply-scoped) and
`state.middle_context`. They are orthogonal and can be enabled independently.

## 5. Risk assessment

- **Worst case is a suboptimal model choice**, not a safety breach: the router cannot
  fabricate evidence, bypass the gateway, or mutate state. Fail-soft (§2.2) bounds
  the downside to "the agent keeps its own model."
- **Silent downgrade risk:** an auto-route to a weaker model could confuse operators.
  Mitigated by §4.2 (surface + audit the routed choice) and by shipping default-off
  until §4.4's accuracy measurement is in hand.
- **No fabrication surface:** the routing prompt selects among named candidates; it
  authors no content that enters the transcript or evidence store.

## 6. Go/no-go and next decision

- **`ModelRouterMiddleware`: go for a SPEC (candidate SPEC-071)**, gated on operator
  approval. R-1 (this memo) is assessment-only; it clears the four-point gate.
- **R-2 (a future SPEC-071)** would be a small, opt-in, default-off kernel change —
  one settings knob, one candidate map, one `_build_middlewares()` entry — plus the
  SPEC-024 precedence reconciliation (`request > pinned > routed > default`), the
  `model_selected_by` audit attribution, the routing-accuracy measurement, and tests
  (opt-in gating; resume keeps the routed model via `middle_context`; fail-soft on
  error/unknown candidate; no evidence frame / no type leak;
  `agent-stream-event.schema.json` byte-stability; token attribution of the routing
  call). It is **not** authorized by this memo.
- **This memo is documentation-only.** It does not flip the audit row to "adopt,"
  change product code, assign SPEC-071, or authorize deployment. The operator
  decides whether to promote.

## 7. Open questions for the operator

1. **Precedence:** confirm the router sits below an explicit request/pin and above
   the default (`request > pinned > routed > default`, §4.1).
2. **Candidates:** which `MODEL_CATALOG` models are routable, and what
   `description`/criteria drive the choice (e.g. cheap-fast vs strong-reasoning)?
3. **Router backend:** reuse an existing catalog chat model via
   `generate_structured_output` (recommended — no new dependency), or add a dedicated
   `OpenAIClassifierModel`/`JevClassifierModel` (adds an OpenAI/TypeSafe provider
   dependency; not recommended)?
4. **Visibility:** surface the routed model + `model_selected_by` in the portal and
   audit (recommended yes)?
5. **Default posture:** ship opt-in/default-off until a routing-accuracy measurement
   on real traffic justifies broader enablement (recommended)?

## Changelog

- 2026-11-01: initial assessment. Static inspection of the locked agentscope 2.0.11
  `ModelRouterMiddleware` + `classifier` and the agent-platform kernel integration at
  0.51.1 (`c4214cf`). Verdict: **clears** the four-point gate; recommended for
  opt-in adoption as candidate SPEC-071, pending the SPEC-024 precedence +
  auditability reconciliation and a routing-accuracy measurement. Corrected the
  Tier-review caveat: the provider-agnostic path is the `ChatModelBase` /
  `generate_structured_output` backend, not `JevClassifierModel` (which is
  TypeSafe-specific). No runtime implementation, live test, deployment, or
  spec-status change.
