# SPEC-054 Plan: Action-Level HITL Approval and the Change-Request Confirmation Card

## Approach

Four additive changes riding machinery that already exists, plus the two explicit
backstops that replace the accidental one R-2 removes:

1. **Declare the card's kind** (R-1) — one `approval_kind` field computed at park
   time from the *parked batch*, on the frame and the durable record. This makes
   the v0.34.1 headline-leak patch a consequence rather than a special case:
   `flow_summary` becomes structurally present **iff** `approval_kind == "flow"`.
2. **Park, don't deny — and replace the backstop** (R-2) — the gateway stops
   hard-denying an allowlisted unbound browser interaction; in the same slice the
   kernel clears its flow authority wherever the gateway clears its own binding,
   and every signed envelope declares its authority provenance (ADR-0010) which
   the gateway enforces with `BROWSER_FLOW_AUTHORITY_STALE`.
3. **Make the action card a change request** (R-3) — a per-call display
   projection assembled exactly where SPEC-050's `display_hint` is assembled, so
   it is a sibling of the signed parameters and cannot touch `args_digest`.
4. **Persist the card's message** (R-4) — mirror the `flow_summary` persistence
   path end to end so the inbox and the re-loaded transcript match the live card.

Nothing here is a new approval mechanism. The park, the card, the signature, the
receipt, the audit events, and the policy actions are all the SPEC-020/021/030/037
ones. ADR-0007 is extended in scope (one gate per *bound* flow, one gate per
*ad-hoc* action), not reversed.

Two invariants are load-bearing and pinned by test rather than by review:

- **`args_digest` is computed from `call["parameters"]` only** — not from the
  payload entry that carries it (`services/execution_signing.py:93`). So the R-3
  projection, added as a sibling key of `display_hint`, is structurally incapable
  of altering the digest, the signature, or gateway verification.
- **The provenance check is one-directional and fail-closed.** The declared
  `approval_kind` can only ever *add* a refusal; the guard set the gateway
  applies is still selected by `entry.flow` presence, never by the declared kind.
  A forged or absent value therefore degrades to today's behavior or to a denial,
  never to an allowance.

## Resolved At Plan Time

The spec delegated four items to this plan, and the pre-implementation code read
turned up two delivered drifts that this slice has to absorb because it edits the
same surfaces.

### 1. Stream-schema version: the delivered title lags the code

`shared/shared-contracts/schemas/agent-stream-event.schema.json` titles itself
**"Agent Stream Event (v9)"** and its description ledger ends at v9 (SPEC-051
R-6), while `AgentStreamEvent`'s docstring in `schemas/v2.py` already declares
**v10** with a v10 line for SPEC-053's `flow_intent`. SPEC-053 added
`flow_intent` to `flow_summary.properties` and documented it on that property's
description, but never advanced the schema's title or ledger.

**Resolution:** SPEC-054 retro-fits the missing v10 clause into the schema title
and description (recording SPEC-053's `flow_intent`, which already shipped), then
advances **v10 → v11** for `approval_kind` + `change_request`. The Pydantic
docstring gains a v11 line. After this slice the two surfaces agree, and the
ledger is truthful about what v10 was.

### 2. Redaction vocabulary: second copy + a `make verify` lockstep leg

The spec offered either publishing `_SECRET_QUERY_PARAMS` as data under
`shared/shared-contracts` or keeping a second copy in agent-platform pinned by a
drift test.

**Resolution: a second copy in agent-platform, pinned by a new `make verify`
leg** (`shared/shared-contracts/scripts/validate_secret_vocabulary.py` +
`make validate-secret-vocabulary` added to the `verify` target). Rationale:

- `validate_version.py` is the exact precedent — it enforces lockstep by
  textually globbing `products/*/pyproject.toml`, `products/*/src/*/metadata.py`,
  and `products/*/src/*/__init__.py` and comparing them to `VERSION`. A
  build-time script reading two products' constants crosses no runtime boundary
  and violates the no-cross-product-Python-import invariant not at all.
- The 2026-08-25 shared-extraction spike (roadmap backlog) retained
  **copy-with-parity** and recorded its revisit triggers (a sixth family / five
  copies of one family, 3+ behavioral changes to one family per quarter, a
  shared-sdk needed for another reason). This is a two-copy family with no
  behavioral churn; no trigger is met.
- The data-file options were rejected on risk, not effort: both make a
  *masking* vocabulary a runtime file dependency, so a missing or unmounted file
  fails **open** (nothing gets masked). A Python constant has no such failure
  mode. Mounting a new ConfigMap into two deployments for a 20-entry tuple is
  disproportionate.

The agent-platform copy is a module-level tuple with the same case-insensitive
substring semantics as `_is_secret_param`, and each copy carries a comment
naming its twin. The leg fails if the two tuples differ as sets.

### 3. `display_hint` is undeclared in a `additionalProperties: false` schema

`pending_calls.items` in `agent-stream-event.schema.json` declares
`additionalProperties: false` with properties
`[call_id, tool_name, parameters, risk_level, action]` — but SPEC-050 ships
`display_hint` on those entries (`services/hitl_confirmations.py:110`) and the
portal reads it (`api/sessions.ts:55`, `stream/decoder.ts:111`,
`chat/transcript.ts:153`). `display_hint` appears **nowhere** in
`shared/shared-contracts/`. It is a latent contract violation, invisible only
because no test validates a `display_hint`-bearing frame against the schema.

**Resolution:** declare `display_hint` while adding `change_request` to the same
`items` object in both `agent-stream-event.schema.json` and
`agent-session.schema.json`. This is in scope rather than scope creep because
R-3's tests must validate a *realistic* parked browser frame, and such a frame
carries `display_hint` — the tests would fail on the pre-existing drift.

### 4. execution-runtime is **not** "verify only" — Impact correction

The approved spec's Impact says `products/execution-runtime` needs no code
change. That is wrong, and the reason is structural: **the gateway never sees the
signed envelope.** Envelope verification lives in the worker
(`api/routes/handoff.py:127-149`, `verify_envelope` + `args_digest` comparison);
the worker then makes a plain
`POST {tool_gateway_url}/api/v2/tools/invoke` (`services/executor.py:71`) whose
payload is `{tool_name, parameters, request_id, session_id?}`. `grep` for
`args_digest|signature|verify_envelope` across `products/tool-gateway/src/`
returns one hit, and it is the string `"signature"` inside
`_SECRET_QUERY_PARAMS` — the gateway has no envelope awareness at all.

So R-2's criterion "the gateway enforces provenance on the browser write path"
cannot be met without the worker forwarding the **verified** kind.

**Resolution:** forward it, mirroring the SPEC-049 R-1 `session_id` precedent
verbatim in framing — `executor.py`'s existing comment calls `session_id` "a
correlation handle, not authority", and `approval_kind` is a *provenance* handle,
not authority. The worker forwards a value it has already verified inside the
HMAC. The gateway treats it as untrusted input whose only permitted effect is a
refusal (invariant 2 above), which preserves
`api/routes/tools.py`'s documented rule that body-carried data is never trusted
as identity.

Alternatives rejected: (a) gateway infers provenance from its own state —
impossible, it cannot know which builder signed; (b) kernel-side clearing alone —
already rejected by ADR-0010 as *sufficient* (it is a race: clearing depends on
the kernel having observed the flow-killing result before the next auto-sign);
(c) a new signed header on the invoke hop — heavier than the existing body-field
precedent for no gain, since the value is only ever fail-closed.

**This is the one plan-time item that contradicts an approved spec section.** It
changes no requirement text — R-2's acceptance criteria all still hold as
written — but it moves execution-runtime from "verify only" to "small change"
and adds one optional field to an internal payload. Flagged to the operator for
a spec-changelog record; not silently absorbed.

## Design Per Requirement

### R-1: Explicit `approval_kind` discriminator on the confirmation card

- affected files:
  - `products/agent-platform/src/agent_service/runtime_kernel.py` — at the
    confirmation-frame build site (where the v0.34.1 patch gates the flow
    headline on `_tool_names_have_browser_write`), compute
    `approval_kind = "flow" if (_tool_names_have_browser_write(names) and
    FLOW_CONTEXTS.get(session_id)) else "action"` and emit `flow_summary` from
    the same branch, so the two can never disagree. The patch's gate is subsumed:
    it becomes the `flow` branch of the discriminator.
  - `products/agent-platform/src/agent_service/schemas/v2.py` — `AgentStreamEvent`
    gains `approval_kind: str | None` and `change_request` rides `pending_calls`;
    the docstring records **v10 → v11**. `ConfirmationRecordModel` gains
    `approval_kind: str | None`.
  - `products/agent-platform/src/agent_service/services/hitl_confirmations.py` —
    `PendingConfirmation` gains `approval_kind`, set once at park time.
  - `products/agent-platform/src/agent_service/services/confirmation_records.py` —
    persist `approval_kind` (`TEXT` column, `ADD COLUMN IF NOT EXISTS`, INSERT +
    SELECT, row→model) mirroring `flow_summary`.
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — coerce
    `approval_kind` onto the session-detail confirmation entries, accepting only
    `"flow"`/`"action"` and omitting anything else.
  - `shared/shared-contracts/schemas/agent-stream-event.schema.json` and
    `agent-session.schema.json` — additive optional `approval_kind`
    (`enum: ["flow", "action"]`).
  - portal: `stream/models.ts` (`approvalKind`), `stream/decoder.ts`,
    `api/sessions.ts` (`ConfirmationRecord.approval_kind`), `chat/transcript.ts`
    (`confirmationRecordToCard`), `chat/ChatView.tsx` (branch on it).
- chosen approach: card-level, derived from the parked batch, exactly as
  `flow_summary` is carried — one rename-free wire name (`approval_kind`) from
  kernel to portal, camelCased only at the portal boundary.
- alternatives rejected: inferring the kind in the portal from
  `flow_summary` presence — rejected, that is the ambient-inference defect class
  R-1 exists to close, and it would leave the durable record without a declared
  kind for the inbox. Per-call kind — rejected, one card parks one batch and the
  batch has one kind.

### R-2: Ad-hoc browser interactions park as per-action signed gates, and flow authority can never outlive the gateway's binding

Four sub-groups, matching the spec. **The relaxation and both replacements ship in
one slice; none is independently revertable.**

*Park, don't deny:*

- `products/tool-gateway/src/tool_gateway/tools/browser_connector.py` —
  `gate_interaction` (L423-477) stops returning `BROWSER_FLOW_NOT_BOUND` as a
  hard deny when the **live** origin is allowlisted. The `flow is None` branch
  splits: non-allowlisted origin → still denied (unchanged, deny-by-default);
  allowlisted origin → fall through to the unbound path below rather than deny,
  so the kernel's per-action ASK is what gates it.
  `_WebInteractionTool._guarded_handle` (L903-911) needs no change — it already
  passes `require_write_class=(self.risk_level == "write")`.
- `WebFillCredentialTool` (L1058-1068) inherits the same relaxation as a
  `_WebInteractionTool` subclass; it stays `risk_level = "read"` and stays in
  `DEFAULT_AUTO_ALLOWED_TOOLS` (`services/kernel_middleware.py`), so only the
  gateway precondition moves. Unbound credential entry is **by reference only**
  (`credential_set` + `field`); a literal-value path is not added.
- The five `gate_interaction`-routed write tools thereby align with
  `web.evaluate`, which already parks-then-executes unbound via flow-optional
  `gate_capture` (L479-522).
- `products/tool-gateway/tests/` — `test_click_without_bound_flow_denied` is
  **replaced** by a park-then-execute expectation, not merely adjusted.

*Substitute guards:*

- `gate_interaction`'s unbound path re-validates the **live** origin against the
  allowlist using `entry.active_target.url` (frame-aware, SPEC-050 R-9) and
  halts on drift — the check `gate_capture` already performs for the read tier,
  lifted into the unbound write path. Without it a client-side redirect between
  `web.navigate` and the interaction lands an approved write on a drifted page.
- `GATEWAY_BROWSER_ALLOW_ORIGINS` stays deny-by-default; a non-allowlisted origin
  is refused with or without approval.
- **No step budget** is applied to the unbound path and **no knob is added**.
  Per-action consent is the bound; SPEC-055 budgets the accumulated sequence at
  graduation.

*Staleness backstop (replaces what the deny was doing):*

- `products/agent-platform/src/agent_service/runtime_kernel.py` — a new clearing
  path drops **both** `FLOW_CONTEXTS` and `FLOW_APPROVALS` for the session on a
  flow-killing `tool_result`. Sibling to `_record_flow_context` (L1372-1386),
  reusing the error-inspection shape already at L1427-1456: the gateway's
  `_denied` helper (L204-211) emits `status="denied"` with
  `error={"code", "message"}`, so the kernel reads
  `frame["error"]["code"]`. Clearing codes: `BROWSER_REDIRECT_NOT_ALLOWED`,
  `BROWSER_FLOW_DENIED`, `BROWSER_FLOW_ORIGIN_DEVIATED`,
  `BROWSER_FLOW_AUTHORITY_STALE`, plus a failed flow-binding navigate
  (`tool_name == "web.navigate"` and `status != "success"` — the two gateway
  sites that null `entry.flow`, `browser_connector.py` L640 and L657).
- `products/agent-platform/src/agent_service/services/execution_signing.py` —
  `build_requests` stamps `"approval_kind": "action"` into the envelope dict
  (L85-95) and `build_flow_request` stamps `"flow"` (L125-131), both **before**
  `sign_envelope`, so the value is inside the HMAC. `sign_envelope` and
  `canonical_digest` are unchanged.
- `shared/shared-contracts/schemas/execution-request.schema.json` — declare
  `approval_kind` as an optional `enum: ["action", "flow"]`. The schema is
  `additionalProperties: false`, so declaration is mandatory; it stays out of
  `required` so predating envelopes verify. While in the file, correct the stale
  `tool_name` description ("Sanitized tool name of the parked call") —
  `pending_calls_payload` (`hitl_confirmations.py:94-97`) deliberately emits the
  gateway canonical **dotted** name, as does `build_flow_request`, so both
  builders already agree and only the prose is wrong.
- `products/execution-runtime/` — **small change** (see Resolved At Plan Time 4):
  `api/routes/handoff.py` passes the verified `approval_kind` through to
  `services/executor.py`, which adds it to the invoke payload beside `session_id`
  with a matching "provenance handle, not authority" comment. `verify_envelope`
  is unchanged — it signs/verifies the canonical JSON of every field except
  `signature`, so a new optional field is covered automatically.
- `products/tool-gateway/src/tool_gateway/tools/browser_connector.py` — on the
  browser write path, a forwarded `approval_kind == "flow"` with
  `entry.flow is None` returns `_denied(..., "BROWSER_FLOW_AUTHORITY_STALE", ...)`.
  One-directional: an `"action"` claim never satisfies a bound-flow-only guard
  and never suppresses one.

*Invariants that do not move:*

- Browser write tools never join any auto-allow list; with bridging off
  (`hitl_confirm_timeout == 0`) an unbound browser write is denied, never
  silently executed — the existing auto-allow invariant test stays green.
- `_record_flow_approval` (L1614-1646) gains a `risk_class == "write"` condition
  before arming, so a read-class binding no longer produces an authority that can
  never execute (the gateway would deny it `BROWSER_FLOW_READ_ONLY`). A
  `flow`-kind card on a read-class binding is surfaced as such.
- Non-browser mutating tools and bound browser flows are unchanged.

### R-3: The action card is a change request

- affected files:
  - `products/agent-platform/src/agent_service/services/hitl_confirmations.py` —
    assemble the projection inside `pending_calls_payload()` beside the existing
    `entry["display_hint"]` (L110), whose adjacent comment (L106) already states
    the design rule this reuses: display data is added "so the args_digest for
    signing/verification stays unchanged". Shape:
    `{"summary": str, "fields": [{"label": str, "value": str, "masked": bool}]}`.
  - a new curated-formatter table in agent-platform keyed by canonical dotted
    tool name: `k8s.delete_pod`, the write-tier `web.*` family, and
    `web.fill_credential` (which emits `credential_set` + `field` and **never** a
    value). Every other tool falls through to a generic label→value projection,
    so no card regresses for want of a formatter and no formatter blocks the
    requirement.
  - `products/agent-platform/src/agent_service/services/secret_params.py` (new) —
    the second copy of the masking vocabulary plus `is_secret_param()`
    (Resolved At Plan Time 2), with the opaque-value list: fields masked
    wholesale regardless of name, starting with `web.type.text`.
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — coerce
    `change_request` on the session-detail pending-calls entries (mirror the
    `display_hint` coercion at L602-604, extended to the structured shape).
  - `shared/shared-contracts/schemas/` — declare `change_request` (and
    `display_hint`, Resolved At Plan Time 3) on `pending_calls.items` in both
    `agent-stream-event.schema.json` and `agent-session.schema.json`.
  - `products/agent-platform/src/agent_service/runtime_kernel.py` —
    `_confirmation_message` (L1574-1581) sources the informative message from the
    curated formatter's effect sentence where one exists, replacing the generic
    `"Tool execution requires your confirmation."` fallback for those tools.
  - portal: `stream/models.ts`, `stream/decoder.ts`, `api/sessions.ts`,
    `chat/transcript.ts`, and `chat/ChatView.tsx` — render `summary` as the lead
    line and `fields` as a table when present; fall back to today's tool-level
    rendering when absent. The collapsed "Technical details" expander stays.
- chosen approach: the projection is a **sibling** of `parameters` on the payload
  entry, so `canonical_digest(call["parameters"])` cannot see it. Masking is
  by-default (an allow-list of known-safe fields may render verbatim; everything
  else masks to `***`, key preserved).
- alternatives rejected: a bare-string projection — rejected, SPEC-055's
  secret-safe parameterized steps need the structured vocabulary and would
  otherwise have to migrate a string. Wiring the gateway middleware's ASK reason
  through verbatim — rejected: it interpolates the **sanitized** name
  (`web_click`), breaking the dotted-canonical convention, and it explains an
  implementation detail ("outside the auto-approve allow-list") rather than the
  change. Any middleware-derived reason must be canonicalized via
  `gateway_tool_name` first. Name-based masking alone — rejected as sufficient:
  `_is_secret_param("text")` is False, and the projection is assembled
  kernel-side where the gateway's known-secret value set (`entry.secret_values`,
  used for screenshot masking at L815) is not available.

### R-4: Durable card-message parity

- affected files — mirror the `flow_summary` path end to end:
  - `products/agent-platform/src/agent_service/services/confirmation_records.py` —
    record-create parameter, `message TEXT` column,
    `ADD COLUMN IF NOT EXISTS` migration, INSERT/SELECT, row→model.
  - `products/agent-platform/src/agent_service/schemas/v2.py` —
    `ConfirmationRecordModel` gains `message: str | None` (verified absent today:
    `confirmations.items.properties` carries `flow_summary` but no `message`).
  - `products/agent-platform/src/agent_service/runtime_kernel.py` — compute the
    message **once** at park time and feed both the live frame and the durable
    record from that single value, so the paths cannot diverge.
  - `products/agent-platform/src/agent_service/api/v2/routes.py` — coerce it.
  - `shared/shared-contracts/schemas/agent-session.schema.json` — additive
    optional `message` on `confirmations.items`.
  - portal: `api/sessions.ts` (`ConfirmationRecord.message`) and
    `chat/transcript.ts` (`confirmationRecordToCard` sets `card.message`).
- chosen approach: identical to SPEC-051 R-6's `flow_summary` persistence, which
  is the parity precedent the requirement names.
- alternatives rejected: re-deriving the message in the portal from
  `pending_calls` — rejected, that is exactly the divergence R-4 closes, and a
  legacy row would derive a different string than the live card showed.
- legacy rows (NULL `message`) render no message line — today's behavior, never a
  broken or empty artifact.

### R-5: Delivery traceability per ADR-0008

- affected files: `docs/specs/SPEC-054-.../tasks.md` records one asserting test
  per acceptance criterion; the password-reset `demo.sh` chat leg stays green
  unchanged (the bound-flow one-gate path does not move).
- chosen approach: an interactive per-action browser-write demo under `samples/`
  **is** shipped, because R-2 makes the unbound login-then-mutate scenario
  reachable for the first time and ADR-0008 requires a shipped sample to be
  exercised by its own script in the verification path.
- `CONTRIBUTING.md` and `docs/specs/README.md` already carry the ADR-0008 gate
  text — verify only.

## Sequencing And Dependencies

1. **Contracts first** — `agent-stream-event.schema.json` (v9 title retro-fit +
   v11, `approval_kind`, `change_request`, `display_hint`),
   `agent-session.schema.json` (`approval_kind`, `change_request`,
   `display_hint`, `message`), `execution-request.schema.json` (optional
   `approval_kind` + the stale `tool_name` description fix). Everything validates
   against these.
2. **agent-platform signing + clearing** (R-2 backstops) — `execution_signing`
   stamps provenance; `runtime_kernel` clears on flow-killing results;
   `_record_flow_approval` requires `risk_class == "write"`. Depends on stage 1
   for the envelope schema. **This stage must land before or with stage 3, never
   after** — relaxing the gateway deny without the backstops is the fail-open
   path the review found.
3. **execution-runtime forwarding** (R-2) — `handoff.py` → `executor.py`. Depends
   on stage 2 (a stamped value to forward).
4. **tool-gateway relaxation + provenance enforcement** (R-2) — `gate_interaction`
   unbound path, live-origin re-check, `web.fill_credential`, and the
   `BROWSER_FLOW_AUTHORITY_STALE` refusal. Depends on stages 2 and 3.
5. **agent-platform card assembly** (R-1 + R-3 + R-4) — `approval_kind` at the
   frame site, the projection + formatter table + secret vocabulary, the durable
   `approval_kind`/`change_request`/`message` persistence and coercion. Depends
   on stage 1; independent of stages 2-4.
6. **Vocabulary lockstep leg** — `validate_secret_vocabulary.py` + the root
   `Makefile` `verify` target. Depends on stage 5 (the second copy exists).
7. **operator-portal** (R-1 + R-3 + R-4) — models, decoder, transcript, sessions
   types, card rendering. Depends on stage 5.
8. **Samples + tests per stage; living-state docs, CHANGELOG, version lockstep,
   and the release note on delivery.** Depends on all. The deferred clean v0.34.1
   image rides this slice's `make build`.

## Test Strategy

- **agent-platform (`pytest`)**
  - R-1: `approval_kind == "flow"` iff the batch has a browser write *and* a flow
    is bound; `"action"` otherwise; `flow_summary` present iff `"flow"` (the
    headline-leak class asserted structurally impossible, including the exact
    v0.34.1 regression — a `k8s.delete_pod` card with a lingering flow context).
  - R-2 clearing: each flow-killing code drops **both** `FLOW_CONTEXTS` and
    `FLOW_APPROVALS`; a failed `web.navigate` drops both; a success does not;
    after clearing, the next `web.*` write does **not** auto-sign.
  - R-2 provenance: `build_requests` → `"action"`, `build_flow_request` →
    `"flow"`; the value is inside the signature (tampering with it invalidates
    verification); an envelope without it still verifies.
  - R-2 arming: `_record_flow_approval` does not arm on an unbound batch or on a
    read-class binding; arms on a `write`-class binding.
  - R-3: curated `summary` for `k8s.delete_pod` and a write-tier `web.*`;
    generic fallback for an uncurated tool; `web.fill_credential` shows
    `credential_set` + `field` and never a value; name-based masking on a
    secret-named parameter; **opaque-value masking on `web.type.text`**;
    `args_digest` byte-identical with and without the projection.
  - R-4: the durable record round-trips `message` on both backends; the live
    frame and the durable record carry the same string from one computation;
    a NULL-message legacy row degrades without an empty artifact.
  - contract: a realistic parked browser frame (carrying `flow_summary`,
    `display_hint`, `change_request`, `approval_kind`) validates against
    `agent-stream-event.schema.json` v11, and a record against
    `agent-session.schema.json`.
- **tool-gateway (`pytest`)**
  - an allowlisted unbound write is no longer denied `BROWSER_FLOW_NOT_BOUND`
    (replacing `test_click_without_bound_flow_denied`); a non-allowlisted origin
    still is; unbound `web.fill_credential` is admitted by reference; an unbound
    write still parks rather than executing without approval.
  - live-origin re-check: a drift between `web.navigate` and the interaction
    halts the unbound write.
  - provenance: `flow` + no bound flow → `BROWSER_FLOW_AUTHORITY_STALE`;
    `action` + bound flow → the bound-flow guard set still applies unchanged;
    absent → today's behavior (the one-directional fail-closed property pinned
    explicitly).
  - bound-flow behavior byte-for-byte unchanged: origin match, `risk_class`,
    step budget, `BROWSER_FLOW_READ_ONLY`, `BROWSER_FLOW_EXHAUSTED`.
  - the auto-allow invariant test stays green; browser writes are in no
    auto-allow list.
- **execution-runtime (`pytest`)** — the forwarded `approval_kind` reaches the
  invoke payload; `verify_envelope` accepts an envelope with and without it; a
  tampered `approval_kind` fails verification.
- **operator-portal (`vitest`)** — decoder maps `approval_kind` →
  `approvalKind` and `change_request` → `changeRequest`; transcript replays both
  plus `message` from the durable record; the card renders the flow headline for
  `flow`, the change-request layout (`summary` lead + `fields` table) for
  `action`, and today's tool-level rendering when both are absent; masked fields
  render `***`; a `summary` containing markup renders as escaped text.
- **lockstep** — `make validate-secret-vocabulary` fails when the two tuples
  diverge and passes when they agree.
- **integration** — `make verify` green (all products, overlays, policy,
  scenarios, version lockstep, the new vocabulary leg); the password-reset
  `demo.sh` chat leg green unchanged; the new per-action browser-write sample
  exercised by its own script.

## Rollout And Migration

- **deployment/configuration changes:** none. No new env var, secret, policy
  action, audit event type, or overlay change. The one new `make verify` leg is a
  build-time check, not a runtime dependency.
- **backward compatibility:** additive and fail-safe throughout.
  - Frames/records without `approval_kind` render today's tool-level card; the
    portal branch falls through rather than assuming a kind.
  - Envelopes predating `approval_kind` still verify (optional on a
    `additionalProperties: false` schema, out of `required`), and the gateway's
    provenance check treats an absent value as "no extra refusal".
  - Declaring `display_hint` legitimizes a field already in production traffic;
    no client changes.
  - Postgres migrations are idempotent `ADD COLUMN IF NOT EXISTS`; existing rows
    get NULL `approval_kind`/`message`, which coerce to omitted.
  - **Mixed-version window:** an old worker forwarding no `approval_kind` to a
    new gateway loses only the extra staleness refusal — the kernel-side clearing
    (stage 2) still applies, so the window is no less safe than today. A new
    worker against an old gateway sends a field the old gateway ignores. Neither
    direction fails open.
  - The R-2 relaxation is a **behavior** change operators will notice: an ad-hoc
    browser interaction on an allowlisted origin now parks a card instead of
    erroring. That is the intended fix, and it is what the new sample
    demonstrates.
- **data migration:** none beyond the idempotent column adds.
- **rollback:** revert the delivery commit. The added columns are harmless NULLs
  if left in place, so no destructive down-migration is required. Rolling back
  restores the `BROWSER_FLOW_NOT_BOUND` hard deny and, with it, the accidental
  staleness backstop — the pre-spec posture, which fails closed.
- **the deferred v0.34.1 build:** dev-k8s currently runs the dirty tag
  `0.34.0-dev-k8s-123c4b6-dirty-20260906161715`. This slice's `make build`
  produces the first clean image carrying A's headline-leak gate, so the
  deferral closes here rather than needing its own release.
