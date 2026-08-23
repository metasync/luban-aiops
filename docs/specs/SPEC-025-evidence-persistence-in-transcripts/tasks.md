# SPEC-025 Tasks: Evidence Persistence in Session Transcripts

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
Caps fixed by the measurement pass: entry 131,072 chars (`AGENT_EVIDENCE_ENTRY_MAX_CHARS`),
session budget 4,194,304 bytes (`AGENT_EVIDENCE_SESSION_MAX_BYTES`).

## R-1: Evidence store and kernel persistence hook

- [x] Extract DSN/backend-selection helpers from `agent_state_store.py` for reuse; add `evidence_store.py` with in-memory + Postgres backends behind the same `AGENT_STATE_STORE_BACKEND` knob, `session_evidence` DDL (plan Q1), TTL-refresh-on-read (`products/agent-platform/src/agent_service/services/`)
- [x] Entry cap + truncation marker, session budget + oldest-payload eviction (metadata kept, `"truncated"` marker) — enforced identically in both backends; boundary-value unit tests (`evidence_store.py`, `tests/test_evidence_store.py`)
- [x] `runtime_settings.py`: `AGENT_EVIDENCE_ENTRY_MAX_CHARS` / `AGENT_EVIDENCE_SESSION_MAX_BYTES` frozen-dataclass settings with the defaults above
- [x] Kernel hook: `stream_events` collects `tool_call`/`tool_result` frames while draining the sink, captures `turn_index` at turn start, persists best-effort next to `_snapshot_state`; fail-open unit test (persistence failure never fails the turn) (`runtime_kernel.py`)
- [x] Confirm-resume path persists its frames the same way; expire path documented as out of scope (`runtime_kernel.py`)
- [x] Redaction regression test: credential-shaped strings in a gateway result cannot survive into a stored frame (SPEC-009 choke point inherited by construction)
- [x] Observability: `evidence_store_writes_total{result}`, `evidence_frames_persisted_total`, `evidence_frames_truncated_total{reason}` counters (`core/observability.py`)

## R-2: Additive session-detail contract

- [x] `shared/shared-contracts/schemas/session-evidence.schema.json` (new): `EvidenceTurn` = `{turn_index, request_id, created_at, frames[]}` with frames referencing the `tool_call`/`tool_result` shapes of `agent-stream-event.schema.json`
- [x] `agent-session.schema.json`: additive `evidence_turns` field; `AgentSession` model + `read_session` assembly (empty list on no evidence, `null` on unreadable store — never 500) (`agent_service/schemas/v2.py`, `api/v2/routes.py`)
- [x] Session delete cascades evidence cleanup next to state cleanup, fail-open (`services/session_service.py`)
- [x] Platform-gateway pass-through: session-detail model gains `evidence_turns`, contract test binds the shared schema (additive-compat assertion: old clients unaffected)

## R-3: Portal replay parity

- [x] Session-detail adapter types `evidence_turns`; transcript loader attaches groups to assistant turns by `turn_index`, drops out-of-range groups (`web-ui/app/src/chat/transcript.ts`, sessions fetch path)
- [x] Replayed groups render through the existing `EvidenceCard` (same props shape, collapsed by default, same summary line); no card on turns without evidence
- [x] Vitest: replay assembly mapping (attach/drop), live-vs-replayed card props identity for the same turn fixture

## R-4: Traceability and metrics render

- [x] Card metadata row renders `request_id` + duration from persisted frames with the live formatter; correlation with audit `tool_invoked.request_id` asserted in test/doc
- [x] Summary metrics (tool calls / results / total duration) computed from persisted data identically to live

## Delivery close

- [x] Docs: root `CHANGELOG.md` entry, agent-platform README (store + env knobs), operator-portal README (replay parity), operator guide evidence section, dev-k8s README if overlay env ships
- [x] `make verify` green; browser walkthrough: run tool calls live → reload session → evidence card identical; budget/eviction behavior spot-checked via metrics
- [x] Spec status → `delivered`; open questions closed in spec changelog
