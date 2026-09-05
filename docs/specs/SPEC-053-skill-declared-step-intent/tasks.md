# SPEC-053 Tasks: Skill-Declared Step Intent on the Browser Confirmation Card

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

## R-1: Additive skill-format declaration — `flow_intent`

- [ ] add the optional `flow_intent` string property (`minLength: 1`, `maxLength: 200`) to `shared/shared-contracts/schemas/skill.schema.json`
- [ ] add `flow_intent: str | None = Field(default=None, max_length=200)` to `skills_hub/schemas/skill.py` (`products/skills-hub/`)
- [ ] add `"flow_intent"` to `ALLOWED_KEYS`, a `MAX_FLOW_INTENT_CHARS = 200`, and validation in `_validate_frontmatter` (non-empty string ≤ 200; requires `web_target`) in `services/ingestion.py` (`products/skills-hub/`)
- [ ] persist `flow_intent` in **both** store backends: Postgres `ADD COLUMN IF NOT EXISTS flow_intent TEXT` + insert/upsert/select columns + row→`Skill`; in-memory payload + rehydration (`services/skill_store.py`, `products/skills-hub/`)
- [ ] skills-hub tests: valid `flow_intent` ingests + round-trips through both backends; > 200 chars / non-string / missing `web_target` rejected with precise reasons; absent key ingests unchanged; `validate_document` parity; full-record GET returns it, list `summary()` shape unchanged (`products/skills-hub/tests/`)

## R-2: The declared intent rides the flow binding to the frame and record

- [ ] `FlowState` gains `flow_intent: str = ""` + `to_dict()` entry (`tools/browser_sessions.py`, `products/tool-gateway/`)
- [ ] `bind_flow` populates `flow_intent=str(skill.get("flow_intent") or "")` (`tools/browser_connector.py`, `products/tool-gateway/`)
- [ ] `FlowContext` gains `flow_intent`, `record()` reads it, `summary()` emits it (`services/flow_approvals.py`, `products/agent-platform/`)
- [ ] `_FLOW_SUMMARY_FIELDS` adds `"flow_intent"` (`api/v2/routes.py`, `products/agent-platform/`)
- [ ] `AgentStreamEvent` docstring records v9 → v10 (`schemas/v2.py`, `products/agent-platform/`)
- [ ] add `flow_intent` to `flow_summary.properties` in `agent-stream-event.schema.json` and `agent-session.schema.json` (`shared/shared-contracts/schemas/`)
- [ ] tool-gateway tests: `bind_flow` carries `flow_intent` into `data["flow"]`; absent → `""`; guard/step-budget/origin behaviour unchanged with and without it (`products/tool-gateway/tests/`)
- [ ] agent-platform tests: `summary()` emits it; coercion keeps a string / drops a non-string; a frame with `flow_intent` validates against the stream schema and a record against the session schema; durable round-trip (in-memory + Postgres JSONB); display-only (the gate/signing path never reads it) (`products/agent-platform/tests/`)

## R-3: The card renders the authored intent as its lead decision line

- [ ] `FlowSummary` gains `flowIntent?: string` (`src/stream/models.ts`) and `ConfirmationFlowSummary` gains `flow_intent?: string` (`src/api/sessions.ts`) (`products/operator-portal/web-ui/app/`)
- [ ] decoder maps `flowIntent: asString(record.flow_intent)` (`src/stream/decoder.ts`) and transcript replays `flowIntent: summary.flow_intent` (`src/chat/transcript.ts`) (`products/operator-portal/web-ui/app/`)
- [ ] `ConfirmationCardView` renders `flowSummary.flowIntent` as an emphasized plain-text decision line in `.confirm-flow` (widening the render guard to include it); never `dangerouslySetInnerHTML` (`src/chat/ChatView.tsx`) (`products/operator-portal/web-ui/app/`)
- [ ] portal tests: decoder + transcript map the field; card renders the intent line when present, renders as today when absent (no empty node), and renders markup in the intent as escaped text (`products/operator-portal/web-ui/app/`)

## R-4: Password-reset sample declares its gated-step intent

- [ ] add `flow_intent` (the "Confirm reset" intent) to `ResetUserPassword.md` and bump `version` (`samples/web-checks/password-reset/skill/`)
- [ ] note the intent-led card in `README.md` / `WALKTHROUGH.md` (`samples/web-checks/password-reset/`)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (R-1…R-5)
- [ ] `make verify` green (all product pytest incl. skills-hub/tool-gateway/agent-platform; overlays; policy; version lockstep)
- [ ] portal `npm test` and `npm run build` green
- [ ] password-reset `demo.sh` chat leg exercised (ADR-0008)
- [ ] living state docs updated: skill-authoring guide (new optional key), affected RepoWiki pages (skills-hub ingestion, browser flow, confirmation card)
- [ ] `CHANGELOG.md` entry added referencing SPEC-053
- [ ] spec index in `docs/specs/README.md` set to `delivered`
- [ ] spec status set to `delivered`
