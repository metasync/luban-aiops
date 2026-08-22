# SPEC-022 Plan: Multi-Session Foundations — Session API, Voice-Readiness Contract, and Mutating-Dev Profile

## Approach

Everything this spec needs below the API surface already exists: durable
Postgres sessions with list/delete (`session_store.py`), kernel state
snapshots (`agent_state_store`, SPEC-017), session-scoped HITL parking
(SPEC-020), and kustomize runtime-profile composition (deepseek/dashscope/
openai). The work is therefore almost entirely *surface*: new agent-platform
v2 endpoints, two new platform-gateway proxy routes and policy actions, a
tiny schema extension, and one new kustomize profile. No kernel changes, no
new stores, no new services, and — by deliberate decision — no portal UI
changes beyond what already exists (the multi-session UI is the rebuild
spec's job; Appendix A of the spec is its contract).

Stages: contracts & policy actions (R-1 contracts, R-2 schema) →
agent-platform session API (R-1) → platform-gateway proxies (R-1) →
voice-readiness wiring + invariant tests (R-2) → mutating-dev profile +
deploy docs (R-3) → guides & matrix (R-4) → delivery close (version 0.8.0,
`make build`, `make verify`, changelog, release note).

## Design Per Requirement

### R-1: Session management API surface

**Agent-platform v2 endpoints** (all behind the existing `X-User-ID`
identity header):

- `GET /api/v2/sessions` — `session_store.list_sessions_by_user(user_id)`,
  sorted by `last_active_at` desc, capped at 50. Response items:
  `{session_id, title, created_at, last_active_at, pending_confirmation}`.
- `GET /api/v2/sessions/{id}` — existing route extended with `title`,
  `last_active_at`, `pending_confirmation`, and
  `{transcript_available, transcript: [...]}`.
- `DELETE /api/v2/sessions/{id}` — ownership check identical to
  `read_session` (foreign/unknown → 404); refuse with 409 when the HITL
  registry holds a parked confirmation for the session; otherwise
  `session_store.delete_session` and drop any kernel state snapshot for the
  session.

**Title minting**: `runtime_kernel` records the first user turn of a session
into the session record (80-char cap, plain text, server-side) at stream
start; later turns never rewrite it. Sessions created before this change
surface `title: null` and any UI renders the session id fragment.

**Transcript reconstruction**: the kernel state snapshot (SPEC-017 R-3)
persists the conversation memory; the read path extracts ordered
`(role, content, created_at)` turns from the snapshot's message list.
Decision: reconstruction is best-effort — any extraction failure returns
`transcript_available: false` with empty `transcript`, never a 500 and never
partial fabricated turns. Tool/evidence frames are out of scope for v1
transcripts (chat text only); the evidence panel remains live-stream-scoped,
documented as a known limitation.

**`pending_confirmation`**: `hitl_confirmations` registry gains
`has_pending(session_id) -> bool`; list/get call it per session. This reads
in-memory state — accurate for the single-replica dev deployment; documented
as such (spec risk table).

**`last_active_at`**: session store updates it on create and on every chat
turn start (existing touch point where sessions are fetched for streaming);
Postgres backend adds the column via the existing idempotent DDL bootstrap
(fail-open semantics unchanged).

### R-2: Voice-readiness contract

- `input_modality: Literal["text", "voice"] = "text"` added to
  `ChatRequest` (platform-gateway `schemas/api.py`), the agent-platform v2
  chat schema, and `agent-chat-request.schema.json` (optional, default
  `text`; `additionalProperties` stays forbidden).
- Platform-gateway forwards the field to agent-platform and records it in
  the chat `log_event` and the `chat_request`-related audit details dict.
- Invariant I test (platform-gateway + agent-platform): policy evaluation,
  auto-allow, and HITL parking produce identical outcomes for `text` and
  `voice` requests — modality appears only in logs/audit.
- Invariant II is documentation + a regression test that `chat/confirm`
  schema rejects any modality-like field (decision surface unchanged).
- The Approval and HITL guide gains a "Voice readiness" subsection stating
  both invariants; the configuration reference documents the field.

### R-3: Environment-scoped mutating deployment profile

- `runtime-profiles/mutating-dev/`:
  - `kustomization.yaml` — `resources: [tool-gateway-pod-delete.yaml]` and
    `configMapGenerator: [{name: platform-runtime-config, behavior: merge,
    envs: [mutating.env]}]`
  - `mutating.env` — `GATEWAY_MUTATING_TOOLS_ENABLED=true`
  - `tool-gateway-pod-delete.yaml` — moved verbatim from
    `base/tool-gateway/` (namespace-scoped Role/RoleBinding, delete verb
    only)
- `dev-k8s/kustomization.yaml` — add `- ../runtime-profiles/mutating-dev`
  after the existing provider profile; root `Makefile` `OVERLAYS` gains the
  new profile; `mutating-demo.sh` needs no change (it reads live ConfigMap
  state and asserts whichever posture it finds).
- Docs: dev-k8s README opt-in section rewritten (profile mechanism +
  same-tag `kubectl rollout restart deployment/tool-gateway` note +
  deactivation = remove the profile line + `make deploy` + RBAC delete);
  Approval and HITL guide activation checklist updated to match.

### R-4: Documentation and authorization matrix

- Authorization matrix: two new action rows (`session:list`,
  `session:delete`) with the same role grants as `session:create`; policy
  bundle gains the matching rules (bundle copies stay byte-identical via
  `make sync-policy`; rule count increases and `validate-policy` pins it).
- Guides: note that the session API is available now while the
  multi-session UI ships with the portal rebuild spec; troubleshooting
  guide gains "history unavailable" and parked-confirmation semantics
  entries where the API behavior is operator-visible.

## Test Plan

- Unit: session list cap/ordering/ownership, delete 404/409 paths, title
  minting cap, transcript extraction + fallback flag, `has_pending` wiring,
  modality invariant I parity test, schema validation rejects bad modality.
- Contract: `agent-chat-request` schema diff test (optional field, default),
  policy matrix tests for the two new actions across all six roles.
- Overlay: `make overlays` renders five overlays including mutating-dev;
  rendered dev-k8s ConfigMap carries the merged flag while a profile-less
  render does not.
- Gate: `make build` then `make verify`; API walkthrough via curl/port-forward
  against dev-k8s before delivery close (UI walkthrough moves to the rebuild
  spec).

## Versioning

Delivery bumps the lockstep version to **0.8.0** (new platform capability:
minor bump).
