# SPEC-025 Plan: Evidence Persistence in Session Transcripts

## Measurement Pass (dev-k8s, 2026-08-23)

Tool-result `data` payloads were measured live through the real delegation
path (identity-service dev subject token → token exchange → tool-gateway
`POST /api/v2/tools/invoke`), covering every registered read-only tool in
the `dev-luban-aiops` namespace. `data` size = `len(json.dumps(result.data))`,
the exact serialization `ToolEvidenceMiddleware` applies before the SSE cap.

| tool | params | data chars |
|---|---|---:|
| k8s.get_pod | 1 named pod | 655 |
| incidents.list | — | 3,143 |
| k8s.list_pods | namespace | 3,384 |
| skills.search | `query=pod` | 3,558 |
| k8s.get_pod_logs | tail 100/500 | 4,963 |
| skills.list | — | 7,798 |
| k8s.get_events | namespace | **80,861** |

Distribution (n=9): min 655, median 4,963, p95 7,798, max 80,861. One
entry exceeds the SSE `data` cap (32,000 chars): `k8s.get_events` on a
busy namespace. Redaction already runs at the tool-gateway choke point
(SPEC-009) before any payload reaches agent-platform, so stored evidence
inherits it by construction.

## Approach

Persist evidence frames in a **dedicated `session_evidence` store** with the
same dual-backend pattern as the SPEC-017 agent state store (in-memory for
dev/CI, Postgres for deployed), written best-effort at the end of each
streamed turn from the frames the kernel already drains out of
`TOOL_EVIDENCE_SINK`. The session-detail read path assembles them into an
additive `evidence_turns` field; the portal reuses the existing
`EvidenceCard` component unchanged for replay. No changes to the SSE wire
contract, the live render, tool-gateway, identity, or policy.

Stages: evidence store + caps → kernel persistence hook → session-detail
contract (agent schema + shared-contracts + gateway pass-through) → portal
replay parity → delivery close (docs, metrics assertions, walkthrough).

## Open-Question Resolutions

### Q1: Storage home → dedicated `session_evidence` table

Rejected: embedding evidence in the SPEC-017 `AgentState` snapshot.

- The snapshot is rewritten whole after **every** turn
  (`_snapshot_state` → `save_state`); embedded evidence makes each write
  re-serialize the entire evidence history, growing snapshot size and
  restore time linearly with session tooling — restore deserializes the
  full `AgentState` including evidence the next turn doesn't need.
- Measurement shows a single `k8s.get_events` call contributes 80.9k
  chars; a handful of diagnostic calls would dominate the snapshot blob
  that SPEC-017 exists to keep compact (conversation context).
- A dedicated store gives per-entry/per-session caps and eviction
  (R-1), cascade delete with the session, and an independent failure
  domain — an evidence-store outage degrades evidence only, never the
  snapshot restore path.

The store mirrors `agent_state_store.py` mechanics: backend selected by the
same `AGENT_STATE_STORE_BACKEND` value (one knob, same DSN), `CREATE TABLE
IF NOT EXISTS` DDL on Postgres init, TTL refresh folded into reads exactly
like state rows. Schema:

```sql
CREATE TABLE IF NOT EXISTS session_evidence (
    session_id      TEXT NOT NULL,
    request_id      TEXT NOT NULL,
    turn_index      INTEGER NOT NULL,   -- assistant turn ordinal (0-based)
    frame_index     INTEGER NOT NULL,   -- order within the turn
    frame           JSONB NOT NULL,     -- tool_call / tool_result payload
    created_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (session_id, turn_index, frame_index)
);
CREATE INDEX IF NOT EXISTS idx_session_evidence_session
    ON session_evidence (session_id, turn_index, frame_index);
```

`turn_index` is the count of `assistant` messages already in the agent
context when the streamed turn begins — deterministic replay mapping to the
n-th assistant transcript turn with no timestamp dependence.

### Q2: Retention → follows session lifetime, budget-bounded

- Evidence rows are deleted with their session: `session_service` delete
  calls the evidence store's delete alongside the existing state cleanup
  (same fail-open semantics — an evidence-delete failure never fails the
  session delete). No independent TTL: sessions already carry the lifetime
  semantics, and evidence is meaningless without its session.
- Long-lived sessions are bounded by the per-session storage budget below:
  when the budget is exceeded, the store evicts the **oldest** turns'
  `tool_result` data payloads (frames keep all metadata; `data` is replaced
  with `null` and a `"truncated": {"reason": "session_budget"}` marker).

### Q3: Size caps (from measurement)

- **Per entry: 131,072 chars (128 KiB)** — env
  `AGENT_EVIDENCE_ENTRY_MAX_CHARS`. Covers the measured max (80.9k for
  `k8s.get_events`) with ~60% headroom; oversized payloads are truncated
  to the cap with a `"truncated": {"reason": "entry_cap"}` marker on the
  frame (R-1: visible marker, never dropped). Deliberately decoupled from
  the 32k SSE cap: the stream cap protects live bandwidth, the storage cap
  protects the database — replay should show more than the live frame did,
  not less.
- **Per session: 4,194,304 bytes (4 MiB)** — env
  `AGENT_EVIDENCE_SESSION_MAX_BYTES`. A measured typical diagnostic turn
  costs <100 KiB; the budget allows ~30–40 heavy turns before eviction
  starts, and bounds worst-case per-session growth for the dev Postgres
  PVC. Eviction targets oldest result payloads first (Q2), preserving
  metadata so the card's counts and metrics stay exact.
- Both caps are enforced identically by both backends (dev/CI parity) and
  covered by unit tests at the boundary values.

## Design Per Requirement

### R-1: Durable evidence frames per turn

- affected files: `products/agent-platform/src/agent_service/services/
  evidence_store.py` (new), `services/agent_state_store.py` (shared DSN/
  backend-selection helpers extracted for reuse), `runtime_kernel.py`,
  `runtime_settings.py`
- approach: `EvidenceStore` with in-memory and Postgres backends behind the
  existing `AGENT_STATE_STORE_BACKEND` knob; `save_turn(session_id,
  request_id, turn_index, frames)` applies the entry cap per
  `tool_result.data`, computes the session budget, evicts oldest result
  payloads on overflow, and inserts atomically. `runtime_kernel.
  stream_events` collects `tool_call`/`tool_result` frames while draining
  the sink (they already carry `request_id`/`session_id`) and persists them
  in a best-effort `_persist_evidence` step next to `_snapshot_state` —
  never raising into the turn. The confirm-resume path persists its frames
  the same way. The expire path emits no frames to a client and persists
  nothing (out of scope, recorded here). `turn_index` is captured from the
  agent context at turn start.
- redaction: none new — payloads arrive post-SPEC-009 redaction at the
  tool-gateway choke point; the plan adds a regression test asserting a
  credential-shaped string cannot survive into a stored frame.
- alternatives: persist inside `ToolEvidenceMiddleware` (rejected: the
  middleware has no store access or turn boundaries; the sink-drain point
  in the kernel is the single place where frames carry request identity);
  write-through to audit-service (rejected: audit is role-gated and
  metadata-only by design — its `details` deliberately exclude payloads).

### R-2: Additive session-detail contract

- affected files: `shared/shared-contracts/schemas/session-evidence.schema.
  json` (new) and `agent-session.schema.json` (additive `evidence_turns`),
  `agent_service/schemas/v2.py`, `api/v2/routes.py` `read_session`,
  `products/platform-gateway` session-detail model + contract tests
- approach: `AgentSession` gains `evidence_turns: list[EvidenceTurn] |
  None` where `EvidenceTurn = {turn_index, request_id, created_at, frames}`
  and `frames` reuse the `tool_call`/`tool_result` shapes of
  `agent-stream-event.schema.json` (referenced, not duplicated). Sessions
  with no stored evidence answer `evidence_turns: []` (or `null` when the
  store is unreadable — degrades like `transcript_available=false`, never
  500). Platform-gateway adds the field to its pass-through model and its
  contract test binds to the shared schema, mirroring the SPEC-022
  transcript field treatment.
- alternatives: attach `evidence` inside each transcript turn object
  (rejected: changes the shape of SPEC-022 turn objects consumed by
  existing clients; a top-level additive field keeps every existing turn
  byte-identical).

### R-3: Portal evidence-card parity

- affected files: `products/operator-portal/web-ui/app/src/chat/
  transcript.ts` (replay assembly), `sessions/useSessionWorkspace.ts` or
  the session-detail fetch path (evidence intake), `EvidenceCard`
  consumers, `src/stream/__tests__/` + new replay tests
- approach: the session-detail adapter types `evidence_turns` and the
  transcript loader attaches each group to the assistant message at its
  `turn_index` (out-of-range groups are dropped, never crash). The replayed
  groups render through the **same** `EvidenceCard` component the live
  stream uses — identical props shape (frames array), collapsed by default
  with the same summary line. Turns without a group render no card.
- alternatives: a separate replay card component (rejected: parity is the
  requirement; two components would drift).

### R-4: Traceability and metrics on persisted evidence

- affected files: evidence store (`created_at` written by the store),
  portal `EvidenceCard` metadata row, agent-platform `core/observability.py`
- approach: every stored frame keeps the live-frame fields (`call_id`,
  `tool_name`, `evidence.duration_ms`, `evidence.risk_level`,
  `status`, `error`), and each group carries `request_id` — the card's
  metadata row renders request id + duration from persisted data with the
  same formatter as live. New counters: `evidence_store_writes_total
  {result=ok|error}`, `evidence_frames_persisted_total`,
  `evidence_frames_truncated_total {reason=entry_cap|session_budget}` —
  the standard observability-module pattern. `request_id` correlation with
  the audit trail is asserted by doc/test only (the audit `tool_invoked`
  event already records the same `request_id`).
- alternatives: recompute duration server-side (rejected: `evidence.
  duration_ms` from the gateway is authoritative and already on the frame).

## Test Plan

- evidence store: both backends — save/read round-trip, entry-cap
  truncation marker at boundary, session-budget eviction order (oldest
  first, metadata kept), cascade delete, TTL-refresh-on-read, unreadable
  store degrades to empty.
- kernel hook: streamed turn persists frames with correct `turn_index` and
  `request_id`; persistence failure never fails the turn (fail-open test);
  confirm-resume turn persists; blocking turns persist nothing.
- contract: `evidence_turns` validates against the new shared schema;
  additive-compat test (old client ignores the field); gateway pass-through
  test binds the shared schema.
- portal: Vitest — replay assembly attaches groups by `turn_index`,
  out-of-range drop, no-card-for-no-evidence, identical card props between
  a live fixture turn and its replayed twin.
- gates: `make verify` (includes version/lockstep + policy validation).

## Delivery Notes

- No version bump in this spec's commits; the release commit that closes
  the slice handles `VERSION` lockstep per convention.
- Living docs on delivery: root `CHANGELOG.md`, agent-platform and
  operator-portal READMEs (evidence persistence + new env knobs), operator
  guide evidence section, dev-k8s README if env defaults ship in the
  overlay.
