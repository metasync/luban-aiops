# SPEC-053: Skill-Declared Step Intent on the Browser Confirmation Card

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-05
- approved: 2026-09-05
- delivered: 2026-09-05 (v0.34.0)
- release slice: R5 — Hardening and External Consumption (fifteenth R5
  slice, v0.34.0)
- related ADRs: ADR-0008 (spec delivery traceability gate); lineage:
  realizes the follow-up SPEC-051 R-6 explicitly deferred ("structured
  per-step plan rendering … needs a skill-format change touching the skills
  contract and ingestion path"), extends SPEC-049 R-3 (the browser-flow
  frontmatter declaration — `web_target`/`risk_class`) and SPEC-014 R-1 (the
  skill envelope), and rides the SPEC-051 R-6 flow-headline plumbing
  (gateway flow binding → kernel confirmation frame → portal card)

## Summary

The single confirmation card a `write`-class browser flow parks is
**flow-semantic** today (SPEC-051 R-6): it headlines the bound skill's
`title`, `description`, target `origin`, and `risk_class`, and the post-live
UX patch (#2c, v0.33.x) demoted the raw per-call DOM label and arguments into
prose + a "Technical details" expander. What the card still cannot say is
**what the gated mutation actually achieves** — the operator approves "Reset
User Password in Admin Portal" (the workflow) over a folded `web.click`, but
never reads a plain, authored sentence like *"Submit the password reset for
the target user, permanently changing their credentials."* That sentence is
the operator-facing point of the approval, and only the skill author can write
it.

This spec adds one **additive, optional skill-format key — `flow_intent`** —
a short authored statement of what the flow's gated mutating step is meant to
accomplish. It rides the **exact** SPEC-051 R-6 path (skill record → gateway
`bind_flow`/`FlowState` → `web.navigate`'s `data["flow"]` → kernel
`FlowContext.summary()` → the `flow_summary` on the confirmation frame and the
durable record → the portal card), so the card gains one prominent
**decision line** above the demoted technical detail. Because SPEC-051 R-1
collapses a mutating flow to **exactly one gate** (the first write-tier
interaction parks the sole card), a single card-level `flow_intent` maps 1:1
to that card — this deliberately sidesteps the "brittle to map a static
declaration to a live click" problem that a per-step list would reintroduce.

`flow_intent` is **display-only and never a security input**: the gateway
deviation guard (origin allowlist, declared `risk_class`, step budget) and the
SPEC-037 signed-execution path stay authoritative and unchanged. It adds **no
new policy action and no new audit event type**; it does bump the additive
stream contract (v9 → v10) and the two `flow_summary` schemas, and it adds one
optional key to the skill contract and its ingestion/store path. Skills that
do not declare it render exactly as they do today.

## Motivation

- The 2026-09-05 live browser-flow test surfaced this directly (suggestion
  #2b): *"for the approval card for web/browser action, currently it shows the
  dom element label as the description and the dom content as the action
  content which makes it look too technical … could we put a proper
  description on what this is to achieve by doing this browser action? this
  info should be provided in the skill markdown for this particular 'write' or
  mutating step."* The operator chose the **skill-declared** source: authored
  and stable, curated by the same team that writes the skill.
- SPEC-051 R-6 named the workflow but explicitly deferred the declared-step
  intent: its Non-Goal reads *"skills declare no machine-readable step list
  today (steps live in the tutorial prose), so rendering them needs a
  skill-format change touching the skills contract and ingestion path — a
  larger blast radius than this gate fix warrants. Deferred to a follow-up
  spec."* This is that follow-up, scoped to the smallest robust slice.
- The card already carries the skill's `title`/`description` verbatim from the
  gateway flow binding; adding one more authored frontmatter string to the same
  payload is a well-trodden, low-risk extension of a delivered path rather than
  a new mechanism.
- Why now: R5 is the hardening/release-adoption slice, and the browser-flow
  approval UX is the surface operators actually touch. Bundling this with
  SPEC-052 (skill content viewer) completes the "operators can read and trust
  a skill" theme from the same live test.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Additive skill-format declaration — `flow_intent`

The skill contract and the skills-hub ingestion/store path gain one optional
frontmatter key, `flow_intent`: a short human statement of what the flow's
gated mutating step accomplishes. It is validated like the other SPEC-049 R-3
flow-declaration keys and persisted verbatim by both store backends.

Acceptance criteria:

- `skill.schema.json` adds an optional `flow_intent` string property
  (`minLength: 1`, `maxLength: 200`) documented as the intent of the flow's
  gated mutating step, shown on the browser confirmation card; the envelope
  stays `additionalProperties: false` and every existing field is unchanged.
- skills-hub ingestion accepts `flow_intent` in `ALLOWED_KEYS`; a document
  carrying it validates and ingests, and one without it ingests unchanged (the
  key is optional). `flow_intent` **requires `web_target`** (mirroring
  `risk_class requires web_target`) and must be a non-empty string ≤ 200
  chars, else the document is rejected with a precise reason through the
  existing `Rejection` path. It does **not** require `risk_class: write` (it is
  simply unused for read-class flows, which park no card).
- The `Skill` pydantic model (`extra="forbid"`) carries
  `flow_intent: str | None`; **both** store backends persist and return it —
  the Postgres store gains an idempotent `ADD COLUMN IF NOT EXISTS flow_intent`
  plus insert/upsert/row-mapping coverage, and the in-memory store carries it
  in its payload — so no field is dropped in either backend (the SPEC-050
  dual-backend lesson).
- `flow_intent` travels in full-record responses (GET by id) exactly like the
  other flow-declaration keys; the list/search `summary()` representation is
  unchanged in shape (it already carries the non-body frontmatter).
- `validate_document` (the SPEC-044 R-2 shared single source of truth) accepts
  a well-formed `flow_intent` and rejects a malformed one with the same reason
  vocabulary.

### R-2: The declared intent rides the flow binding to the frame and record

The gateway flow binding and the kernel confirmation plumbing carry
`flow_intent` end to end on the **existing** SPEC-051 R-6 `flow_summary` path —
no new frame, contract field name space, policy action, or audit event type.

Acceptance criteria:

- tool-gateway `FlowState` gains a `flow_intent: str = ""` field populated at
  `bind_flow` from the fetched skill's `flow_intent` and exposed in `to_dict()`
  (so it rides `web.navigate`'s `data["flow"]`); a skill that declares none
  yields `""`.
- The kernel `FlowContext` mirrors it (`flow_intent` field, read in `record()`
  from `flow.get("flow_intent")`, emitted by `summary()`), and
  `_FLOW_SUMMARY_FIELDS` adds `"flow_intent"` so `_coerce_flow_summary` keeps it
  on the live `confirmation_request` frame and strips it to schema-conformant
  form (a non-string or absent value degrades to omitted, never failing the
  frame's `additionalProperties: false`).
- Both `flow_summary` schemas (`agent-stream-event.schema.json` and
  `agent-session.schema.json`) add `flow_intent` as an optional string property
  with an updated description; the `AgentStreamEvent` docstring records the
  additive bump **v9 → v10**. The durable `confirmation_records` store already
  persists `flow_summary` verbatim as JSONB, so the new field rides it with no
  column change (verify only), and a durable/replayed card serves the same
  `flow_intent` as the live frame.
- `flow_intent` is **display-only**: a test asserts it never feeds the flow
  identity, the deviation guard, the origin allowlist, the `risk_class`
  admission, the step budget, or the signed-execution envelope — the gate
  behaviour is byte-for-byte unchanged whether or not it is present.
- Non-browser confirmations (`k8s.*`, etc.) carry no `flow_summary` and are
  unaffected; a browser flow whose skill declares no `flow_intent` produces the
  same frame/record it does today (empty string coerced to omitted).

### R-3: The card renders the authored intent as its lead decision line

The portal confirmation card surfaces `flow_intent` as a prominent, plain-text
**decision line** in the flow-headline block, above the demoted per-call
technical detail, so the operator reads what the action achieves before the DOM
label/arguments.

Acceptance criteria:

- `FlowSummary` (stream model), `ConfirmationFlowSummary` (durable wire type),
  the live decoder (`decoder.ts`), and the durable replay mapper
  (`transcript.ts`) each carry `flow_intent` → `flowIntent` (the same
  snake→camel convention as `risk_class` → `riskClass`), so the live card and a
  replayed/durable card render identically.
- `ConfirmationCardView` renders `flowSummary.flowIntent` inside `.confirm-flow`
  as a distinct emphasized line (visibly the "what you are approving" sentence,
  set apart from the skill `title` headline and the muted `description`); it is
  inserted as **text** (never `dangerouslySetInnerHTML`), so an authored intent
  cannot inject markup.
- When `flow_intent` is absent/empty the card renders exactly as it does today
  (title/description/origin/risk_class headline + the #2c technical-detail
  expander) — no empty line, no layout regression, and non-browser cards are
  unchanged.
- The intent line never replaces the existing tool detail: the `web.click`
  name, the parsed element `displayHint`, and the folded raw parameters all
  remain present (the operator can still inspect the technical action).

### R-4: Password-reset sample declares its gated-step intent

The `samples/web-checks/password-reset` skill demonstrates the key so the
canonical demo shows a fully-authored card, and the sample docs stay in
agreement (the SPEC-051 R-4 reconciliation discipline).

Acceptance criteria:

- `ResetUserPassword.md` declares a `flow_intent` describing the sole write
  (the "Confirm reset" click) — e.g. *"Submit the password reset for the target
  user, permanently changing their admin-portal credentials."* — and its
  `version` is bumped.
- The skill still validates through `validate_document` and ingests; the demo's
  deterministic legs stay green and the chat leg (when run) parks one card whose
  `flow_summary` carries the declared `flow_intent`.
- README/WALKTHROUGH note that the card now leads with the authored intent for
  the gated mutation.

### R-5: Delivery traceability per ADR-0008

This spec is delivered under the ADR-0008 gate.

Acceptance criteria:

- Every R-1..R-4 acceptance criterion maps to at least one automated test (or,
  for the sample chat leg, `demo.sh`) recorded in `tasks.md`.
- The password-reset sample demo is exercised as part of the verification path
  (its `demo.sh` chat leg), satisfying ADR-0008's exercised-sample rule.
- `docs/specs/README.md` carries the SPEC-053 row and this spec's status
  transitions are recorded in its Changelog.

## Non-Goals

- **No model-emitted per-action intent** (the alternative source I flagged —
  an agent-filled `intent` argument on the write-tier `web.*` tools). The
  operator chose the skill-declared source; a model-emitted line is a separate,
  larger runtime/tool-contract change and is not bundled here.
- **No structured multi-step plan rendering** (SPEC-049 R-4's literal "declared
  steps" as a machine-readable list). Under SPEC-051 R-1's one-gate-per-flow
  invariant only the first write parks a card, so a per-step list with
  live-DOM matching would add brittleness and blast radius for no realized
  operator benefit; a single card-level `flow_intent` is the robust slice. A
  richer step model, if ever needed, is a further follow-up.
- **No new policy action, no new audit event type.** The intent is display
  payload on the existing confirmation path; `tool_invoked` /
  `execution_requested` / `confirmation_decided` are unchanged.
- **No change to gate behaviour or execution safety.** The deviation guard,
  origin allowlist, `risk_class` admission, step budget, TTL-bounded flow
  authority, and SPEC-037 signed-execution envelope are untouched; `flow_intent`
  is never consulted for any authorization decision.
- **No new configuration knob.** The declaration is opt-in per skill (absence
  of the key = today's rendering); there is nothing to toggle at runtime.
- **No credential/secret content in `flow_intent`.** It is static authored
  prose (≤ 200 chars); runtime secrets stay in named credential sets and the
  chat-supplied parameters the gateway already redacts (SPEC-049 R-5). Authoring
  guidance says so; no new redaction path is added for it.
- **No re-opening of SPEC-049/051** (delivered/frozen); this spec realizes a
  deferred follow-up by reference and does not alter their requirements.

## Impact

- products touched:
  - `products/skills-hub` — `schemas/skill.py` (add `flow_intent`),
    `services/ingestion.py` (`ALLOWED_KEYS` + `_validate_frontmatter`),
    `services/skill_store.py` (Postgres `ADD COLUMN` + insert/upsert/row map,
    in-memory payload), and tests.
  - `products/tool-gateway` — `tools/browser_sessions.py` (`FlowState`
    field + `to_dict()`), `tools/browser_connector.py` (`bind_flow`), and tests.
  - `products/agent-platform` — `services/flow_approvals.py` (`FlowContext`
    field + `record()` + `summary()`), `api/v2/routes.py`
    (`_FLOW_SUMMARY_FIELDS`), `schemas/v2.py` (docstring v9 → v10; the
    `flow_summary` field is already `dict[str, Any]`), the durable
    `confirmation_records` path (verify only — JSONB carries it verbatim), and
    tests (contract-adapter coercion/parity + record round-trip).
  - `products/operator-portal/web-ui/app` — `src/stream/models.ts`
    (`FlowSummary`), `src/api/sessions.ts` (`ConfirmationFlowSummary`),
    `src/stream/decoder.ts`, `src/chat/transcript.ts`,
    `src/chat/ChatView.tsx` (`ConfirmationCardView`), and component/decoder/
    transcript tests.
- samples / shared touched: `samples/web-checks/password-reset` (skill +
  README/WALKTHROUGH); `shared/shared-contracts/schemas/skill.schema.json`
  (add `flow_intent`), `agent-stream-event.schema.json` and
  `agent-session.schema.json` (add `flow_intent` to `flow_summary`).
- contracts touched: **yes — additive.** `skill.schema.json` gains one optional
  property; the two `flow_summary` schemas gain one optional string property
  (stream contract v9 → v10). All changes are additive and
  backward-compatible (older records/frames without the field validate and
  render unchanged).
- identity / policy / audit / execution safety impact: none new. No policy
  action, no audit event type, no authorization input; `flow_intent` is
  display-only and rendered as escaped text. Execution safety (SPEC-037 signed
  envelope, gateway deviation guard) is unchanged.
- living state docs to update on delivery: root `CHANGELOG.md`, `VERSION`
  (+ lockstep constants) if released as its own version,
  `docs/agentic-aiops-platform/release-notes/` (new note + index),
  `docs/guides/configuration-reference.md` only if a knob is added (none
  planned), `docs/specs/README.md` (SPEC-053 row → `delivered`), the skill
  authoring guide (the new optional key), and the affected RepoWiki pages
  (skills-hub ingestion, browser flow, confirmation card).

## Open Questions

- none

## Changelog

- 2026-09-05: created as `draft` from the 2026-09-05 post-live-test feedback
  (suggestion #2b — the browser approval card shows DOM/technical detail
  instead of an authored "what this achieves" line), at the operator-chosen
  **skill-declared** intent source. Scoped to the smallest robust slice: one
  additive optional `flow_intent` frontmatter key carried card-level on the
  existing SPEC-051 R-6 `flow_summary` path (one gate per flow ⇒ one intent per
  card), realizing the per-step-intent follow-up SPEC-051 R-6 deferred; the
  model-emitted-intent alternative and structured multi-step rendering are
  Non-Goals.
- 2026-09-05: approved as drafted (no scope changes) by the operator; status
  `draft → approved`. plan.md and tasks.md follow, then implementation across
  skills-hub / tool-gateway / agent-platform / operator-portal + the three
  additive contract schemas and the password-reset sample, bundled with
  SPEC-052 into the next (deferred) release.
- 2026-09-05: delivered (v0.34.0). Implemented across skills-hub
  (`flow_intent` schema/model/ingestion/dual store), tool-gateway
  (`FlowState`/`bind_flow`), agent-platform (`FlowContext.summary()`,
  `_FLOW_SUMMARY_FIELDS`, stream v9 → v10, both `flow_summary` schemas), and
  operator-portal (decoder/transcript `flowIntent`, `ConfirmationCardView`
  decision line), plus the password-reset sample declaration. Status
  `approved → delivered`; skills-hub 57, tool-gateway browser connector 96,
  agent-platform 798, portal 283 all green, `make verify` green at VERSION
  0.34.0.
