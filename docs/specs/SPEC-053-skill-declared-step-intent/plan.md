# SPEC-053 Plan: Skill-Declared Step Intent on the Browser Confirmation Card

## Approach

One additive optional frontmatter key — `flow_intent` — carried **verbatim and
under the same name** along the existing SPEC-051 R-6 `flow_summary` path, from
the skill record to the confirmation card. No new frame, no new field name
space, no new policy action, no new audit event type, no new config knob. The
key is:

1. **Declared and validated** in the skill contract + skills-hub ingestion and
   persisted by both store backends (R-1).
2. **Carried** by the gateway flow binding into `web.navigate`'s
   `data["flow"]`, mirrored by the kernel `FlowContext`, emitted on
   `flow_summary`, allow-listed by the frame coercion, and added to the two
   `flow_summary` contract schemas (stream v9 → v10) (R-2).
3. **Rendered** by the portal as a plain-text decision line in the card's
   `.confirm-flow` headline block, above the demoted per-call technical detail
   (R-3).
4. **Demonstrated** by the password-reset sample (R-4).

`flow_intent` is display-only: it never feeds the flow identity, the deviation
guard, `risk_class` admission, the step budget, or the SPEC-037 signed envelope.
Skills that omit it render exactly as they do today.

Naming: the key is `flow_intent` at every hop (skill record → `FlowState` →
`to_dict()` → `FlowContext` → `summary()` → `_FLOW_SUMMARY_FIELDS` → both
schemas), camelCased to `flowIntent` only at the portal boundary — mirroring how
`title`/`description`/`risk_class` are carried verbatim and `risk_class` becomes
`riskClass`. This keeps a single rename-free wire name end to end.

## Design Per Requirement

### R-1: Additive skill-format declaration — `flow_intent`

- affected files:
  - `shared/shared-contracts/schemas/skill.schema.json` — add an optional
    `flow_intent` string property (`minLength: 1`, `maxLength: 200`) documented
    as the intent of the flow's gated mutating step, shown on the browser
    confirmation card; envelope stays `additionalProperties: false`.
  - `products/skills-hub/src/skills_hub/schemas/skill.py` — add
    `flow_intent: str | None = Field(default=None, max_length=200)` (the model is
    `extra="forbid"`, so the key must be declared explicitly).
  - `products/skills-hub/src/skills_hub/services/ingestion.py` — add
    `"flow_intent"` to `ALLOWED_KEYS`, a `MAX_FLOW_INTENT_CHARS = 200` constant,
    and validation in `_validate_frontmatter`: when present it must be a
    non-empty string ≤ 200 chars and **requires `web_target`** (mirroring
    `risk_class requires web_target`), else a precise `Rejection`. It does not
    require `risk_class: write`.
  - `products/skills-hub/src/skills_hub/services/skill_store.py` — Postgres:
    `ADD COLUMN IF NOT EXISTS flow_intent TEXT` in the migration block, add
    `flow_intent` to the insert/upsert column list + `ON CONFLICT … DO UPDATE`,
    the select column list, and the row→`Skill` mapping; in-memory: carry
    `flow_intent` in the stored payload and its rehydration. Both backends must
    round-trip it (the SPEC-050 dual-backend field-drop lesson).
- chosen approach: an optional sibling of the SPEC-049 R-3 flow-declaration keys
  (`web_target`/`risk_class`), validated and persisted exactly like them, so the
  blast radius is the well-trodden frontmatter path.
- alternatives rejected: a structured per-step list (e.g. `steps: [{intent, …}]`)
  — rejected, under SPEC-051 R-1 only the first write parks a card, so a list
  needs brittle live-DOM matching for no realized benefit; a single card-level
  string is the robust slice (see spec Non-Goals).

### R-2: The declared intent rides the flow binding to the frame and record

- affected files:
  - `products/tool-gateway/src/tool_gateway/tools/browser_sessions.py` —
    `FlowState` gains `flow_intent: str = ""` and includes it in `to_dict()`.
  - `products/tool-gateway/src/tool_gateway/tools/browser_connector.py` —
    `bind_flow` populates `flow_intent=str(skill.get("flow_intent") or "")`
    alongside `title`/`description`.
  - `products/agent-platform/src/agent_service/services/flow_approvals.py` —
    `FlowContext` gains `flow_intent: str = ""`, `record()` reads
    `str(flow.get("flow_intent") or "")`, and `summary()` emits `"flow_intent"`.
  - `products/agent-platform/src/agent_service/api/v2/routes.py` —
    `_FLOW_SUMMARY_FIELDS` adds `"flow_intent"` so `_coerce_flow_summary` keeps it
    (a non-string/absent value still degrades to omitted).
  - `products/agent-platform/src/agent_service/schemas/v2.py` — the
    `AgentStreamEvent` docstring records the additive bump **v9 → v10** with a
    v10 line; `flow_summary` stays `dict[str, Any]` (no field change).
  - `shared/shared-contracts/schemas/agent-stream-event.schema.json` and
    `agent-session.schema.json` — add `flow_intent` as an optional string under
    `flow_summary.properties` and extend the descriptions.
  - durable store `products/agent-platform/src/agent_service/services/confirmation_records.py`
    — **no change** (the whole `flow_summary` dict is persisted verbatim as
    JSONB, so the new field rides it); verify only.
- chosen approach: add the field to the single allow-list (`_FLOW_SUMMARY_FIELDS`)
  and the two schemas together, so the live frame and the durable record stay
  schema-conformant and a malformed/over-eager summary still cannot fail
  `additionalProperties: false`.
- alternatives rejected: putting the intent on each `pending_calls` entry —
  rejected, the intent is skill-authored and card-level (one gate per flow),
  whereas `pending_calls` are built from the model's runtime tool call; injecting
  authored text there is awkward and would need per-call plumbing.

### R-3: The card renders the authored intent as its lead decision line

- affected files:
  - `products/operator-portal/web-ui/app/src/stream/models.ts` — `FlowSummary`
    gains `flowIntent?: string`.
  - `products/operator-portal/web-ui/app/src/api/sessions.ts` —
    `ConfirmationFlowSummary` gains `flow_intent?: string`.
  - `products/operator-portal/web-ui/app/src/stream/decoder.ts` — the
    `flow_summary` mapper adds `flowIntent: asString(record.flow_intent)`.
  - `products/operator-portal/web-ui/app/src/chat/transcript.ts` — the durable
    replay mapper adds `flowIntent: summary.flow_intent`.
  - `products/operator-portal/web-ui/app/src/chat/ChatView.tsx` —
    `ConfirmationCardView` renders `card.flowSummary.flowIntent` inside
    `.confirm-flow` as a distinct emphasized line (visibly the "what you are
    approving" sentence, set apart from the bold `title` headline and the muted
    `description`), inserted as **text** (never `dangerouslySetInnerHTML`). The
    block's existing `title || origin` guard is widened to also render when only
    `flowIntent` is present.
- chosen approach: reuse the R-6 headline block and its inline-style grammar; the
  intent line is plain text so an authored string cannot inject markup, and the
  per-call `displayHint` + `Technical details` expander (post-live #2c) stay
  untouched below it.
- alternatives rejected: replacing the skill `description` with the intent —
  rejected, `description` is delivered R-6 behaviour and serves a different
  purpose (when/why to use the skill); the intent is additive.

### R-4: Password-reset sample declares its gated-step intent

- affected files: `samples/web-checks/password-reset/skill/ResetUserPassword.md`
  (add `flow_intent` describing the "Confirm reset" write; bump `version`),
  `samples/web-checks/password-reset/README.md` and `WALKTHROUGH.md` (note the
  card now leads with the authored intent). `demo.sh` needs no assertion change
  (it already asserts one `web.click` card); the chat leg, when run, exercises the
  declared intent end to end.
- chosen approach: the sample is the canonical exercised demo (ADR-0008), so it
  declares the key and its docs stay in agreement (the SPEC-051 R-4 discipline).

## Sequencing And Dependencies

1. Contracts first: `skill.schema.json` + the two `flow_summary` schemas
   (R-1/R-2) — everything validates against these.
2. skills-hub: model + ingestion + dual store (R-1) — depends on stage 1.
3. tool-gateway: `FlowState` + `bind_flow` (R-2) — depends on stage 2 (the skill
   record carries the key).
4. agent-platform: `FlowContext`/`summary`/`record` + `_FLOW_SUMMARY_FIELDS` +
   v2 docstring (R-2) — depends on stage 3 (the flow dict carries the key).
5. operator-portal: models/sessions types + decoder + transcript + card (R-3) —
   depends on stage 4 (the frame/record carry the key).
6. Sample reconciliation (R-4) — depends on stage 2 (validation accepts the key).
7. Tests per stage; living-state docs + CHANGELOG on delivery — depends on all.

## Test Strategy

- skills-hub (`pytest`): ingestion accepts a valid `flow_intent` and persists it
  through **both** store backends; rejects a > 200-char or non-string value and a
  `flow_intent` without `web_target`; a skill without it ingests unchanged;
  `validate_document` accepts/rejects with the same reasons; the full-record GET
  returns it and the list `summary()` shape is unchanged.
- tool-gateway (`pytest`): `bind_flow` carries `flow_intent` onto `FlowState` and
  into `data["flow"]`; absent → `""`; the deviation guard / step budget / origin
  allowlist behaviour is byte-for-byte unchanged whether or not it is present.
- agent-platform (`pytest`): `FlowContext.summary()` emits `flow_intent`;
  `_coerce_flow_summary` keeps a string `flow_intent` and drops a non-string one;
  a `confirmation_request` frame with `flow_intent` validates against
  `agent-stream-event.schema.json` (v10) and a `ConfirmationRecordModel` with it
  validates against `agent-session.schema.json`; the durable store round-trips it
  (in-memory + Postgres JSONB); a display-only assertion that the gate/signing
  path never reads it.
- operator-portal (`vitest`): decoder maps wire `flow_intent` → `flowIntent`;
  transcript replays it from the durable record; `ConfirmationCardView` renders
  the intent line when present, renders as today when absent (no empty node), and
  renders an intent containing markup as escaped text (no injected element).
- contract parity: the schema `flow_summary` property set and `_FLOW_SUMMARY_FIELDS`
  stay in lockstep (a frame/record carrying `flow_intent` validates; an unknown
  key is still stripped).
- integration: `make verify` green (all products, overlays, policy, version
  lockstep); the password-reset `demo.sh` chat leg exercises the declared intent.

## Rollout And Migration

- deployment/configuration changes: none. No new env var, secret, policy action,
  audit event type, or overlay change.
- backward compatibility: purely additive and fail-safe. Older skills (no
  `flow_intent`) ingest and render unchanged; older frames/records without the
  field still validate (`flow_summary` fields are all optional) and render as
  today; the Postgres migration is an idempotent `ADD COLUMN IF NOT EXISTS`. A
  portal served by an older gateway simply sees no `flow_intent` and falls back.
- data migration: none beyond the idempotent column add; existing rows get NULL
  `flow_intent`, which coerces to omitted.
- rollback: revert the delivery commit; the added column is harmless if left in
  place (unused NULLs), so no destructive down-migration is required.
