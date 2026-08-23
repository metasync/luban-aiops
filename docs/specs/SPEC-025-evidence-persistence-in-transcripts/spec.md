# SPEC-025: Evidence Persistence in Session Transcripts

## Status

- status: `draft`
- owner: chi
- created: 2026-08-23
- release slice: post-0.9.0 train (candidate alongside the SPEC-024 model
  dropdown reserved in `docs/agentic-aiops-platform/delivery-roadmap.md`)
- related ADRs: none new; extends SPEC-022 R-1 (transcripts), SPEC-011 R-4
  (evidence panels), SPEC-017 (kernel state persistence), and lifts the
  explicit v1 deferral recorded in
  `products/agent-platform/src/agent_service/services/session_transcript.py`
  ("Tool/evidence frames stay out of scope for v1 transcripts (chat text
  only); the evidence panel remains live-stream-scoped.")

## Summary

Persist the tool-evidence frames (`tool_call` / `tool_result`) of each turn
alongside the session transcript and render them in the portal whenever a
session is reopened, so the evidence card is consistent and complete in its
traceability and metrics whether the turn was observed live or replayed from
storage. Today evidence exists only inside a live SSE stream; reopening a
session shows the conversation without any of the tool activity that
produced it.

## Motivation

- The SPEC-023 live walkthrough (2026-08-23) surfaced the parity gap: after
  a session is reloaded (session switch, page refresh, deep link), the chat
  transcript renders but the evidence panel is empty, because transcripts
  are reconstructed from the kernel `AgentState.context` snapshot which
  carries only `user`/`assistant` chat text (SPEC-022 R-1 v1 scope).
- Operators reviewing past sessions cannot see which tools ran, what they
  returned, how long they took, or which request executed them — the
  traceability and metrics that the live evidence card provides
  (`SPEC-011` R-4) are lost the moment the stream closes.
- The gap grows with the multi-session workspace (SPEC-022/SPEC-023):
  switching sessions mid-day and returning later is now the normal
  workflow, so live-stream-only evidence is the exception case, not the
  rare one.
- Audit events (SPEC-013) record that tool calls happened, but they are a
  separate, role-gated surface; the evidence card is the operator-facing
  record and should stand on its own for reopened sessions.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Durable evidence frames per turn

The agent service persists the evidence frames of every streamed turn
(`tool_call`, `tool_result`) keyed by session and turn, with the call
metadata needed for traceability and metrics: `call_id`, `tool_name`,
`risk_level` where applicable, `request_id`, start/end timestamps (or
duration), and the result payload subject to existing redaction.

Acceptance criteria:

- Evidence frames survive service restarts for active sessions and are
  retrievable for any session whose transcript is retrievable.
- Result payloads pass through the SPEC-009 redaction path before storage;
  no credential or secret material can appear in stored evidence.
- Storage is bounded: per-evidence-entry and per-session caps are defined
  and enforced, with oversized results truncated with a visible marker
  (never a 500, never a silently dropped frame).
- Evidence persistence failures degrade best-effort — exactly like
  transcript extraction — never failing the chat turn itself.

### R-2: Additive session-detail contract

The `GET /api/v2/sessions/{session_id}` response carries the persisted
evidence attached to its turns as an additive field, and the
platform-gateway passes it through unchanged.

Acceptance criteria:

- `shared/shared-contracts` gains the evidence-frame schema shared by
  agent-platform and platform-gateway; gateway contract tests bind to it.
- Existing clients that ignore the new field behave exactly as today
  (backward compatible; `transcript_available` semantics unchanged).
- Sessions without stored evidence (pre-spec history, unrecoverable
  snapshot) answer with empty evidence, never an error and never
  fabricated frames.

### R-3: Portal evidence-card parity for reopened sessions

The rebuilt portal renders the same evidence card for reopened sessions as
for live turns: grouped entries by `call_id`, summary counts, and the
bounded scrollable result expander delivered with the SPEC-023 walkthrough
remediation.

Acceptance criteria:

- Reopening a session that ran tool calls renders the evidence card(s)
  inline with the corresponding assistant turns, collapsed by default with
  the live-render summary line (tool count / result count).
- The live-stream render and the replayed render are visually identical for
  the same turn (same component, same data shape).
- Turns without evidence render no evidence card (no empty placeholders).

### R-4: Traceability and metrics on persisted evidence

Each persisted evidence entry carries enough metadata for an operator to
trace a result back to its execution and to read its cost.

Acceptance criteria:

- Every evidence entry exposes its `request_id` and duration (or explicit
  "not recorded") in the card's metadata row.
- The `request_id` correlates with the audit trail (SPEC-013) and the
  observability surfaces (SPEC-005/SPEC-011), so an auditor can jump from a
  rendered result to the corresponding audit/tool-trace records.
- Summary metrics on the card (tool calls, results, total duration) are
  computed from persisted data identically to the live computation.

## Non-Goals

- Replaying HITL confirmation cards from history (SPEC-020 decisions stay
  recorded in the audit trail; the confirmation surface remains live-only).
- Search/aggregation over historical evidence (audit-trail query API owns
  that surface).
- Retro-filling evidence for sessions created before delivery; storage
  starts with the first turn streamed after deployment.
- Changes to audit event contracts or policy actions.

## Impact

- products touched: `products/agent-platform` (turn persistence +
  session-detail assembly), `products/operator-portal` (evidence rendering
  from session detail), `products/platform-gateway` (pass-through only,
  plus contract tests)
- contracts touched: `shared/shared-contracts` — additive evidence-frame
  schema on the session-detail payload
- identity / policy / audit / execution safety impact: none new — read
  paths keep existing session-owner scoping and 404 anti-enumeration;
  redaction (SPEC-009) applies before storage
- living state docs to update on delivery: root `CHANGELOG.md`,
  agent-platform and operator-portal `README.md` files, operator guide
  evidence section

## Open Questions

- Storage home for evidence frames: extend the SPEC-017 kernel state
  snapshot (single read path, grows snapshot size) versus a dedicated
  per-session evidence table in the SPEC-016 Postgres store (bounded
  growth, second read path). To be resolved in `plan.md`.
- Evidence retention policy: follow session lifetime exactly, or cap
  evidence rows independently for very long-lived sessions.
- Per-entry and per-session size caps (concrete numbers) — pending a
  measurement pass over live dev-k8s tool outputs.

## Changelog

- 2026-08-23: created as `draft` from the SPEC-023 walkthrough parity
  finding (evidence lost on session reload); numbering skips SPEC-024,
  which the delivery roadmap reserves for runtime LLM model switching.
