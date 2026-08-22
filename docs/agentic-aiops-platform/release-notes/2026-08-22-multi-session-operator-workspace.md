# Release Notes: 2026-08-22 — Multi-Session Foundations (SPEC-022, v0.8.0)

## Summary

SPEC-022 lands the multi-session backend, deliberately backend-first: the
session lifecycle API, the voice-readiness input contract, and the
`mutating-dev` deployment profile are all framework-agnostic surfaces,
while the portal's session-panel UI waits for the portal framework
rebuild spec (SPEC-022 Appendix A is its handoff contract).

Agent-platform gains a workspace view over sessions: list (most-recently-
active first, capped at 50, with `pending_confirmation` flags), detail
with a server-minted title and a best-effort transcript reconstructed
from the kernel state snapshot, and owner-only delete with
anti-enumeration `404`s and a `409` while a HITL confirmation is parked.
Platform-gateway proxies the surface under two new deny-by-default policy
actions (`session:list`, `session:delete`) that mirror the existing
`session:create` grants, and emits a durable `session_deleted` audit
event. Chat requests now carry an optional `input_modality`
(`text` | `voice`) that is metadata only — logged and audited, never
decision-bearing — and the SPEC-021 dev opt-in is promoted to the
committed `mutating-dev` kustomize profile.

Live testing on the dev cluster walked the full chain: create → voice
chat turn → list/detail with title and transcript → delete → post-delete
`404`, plus auditor `403`s and the durable audit chain. The walkthrough
also surfaced two defects, both fixed in-release: the session-detail
proxy leaked upstream errors as `500` (now `4xx` passthrough / `502`
mapping), and the audit-service `EventType` vocabulary was missing
`session_deleted` (ingest rejected the batch with `400`; the enum is
synced and pinned by a new contract-parity test).

## Change Set 1: Session workspace lifecycle API (R-1)

### Highlights

- `GET /api/v2/sessions` lists the caller's own sessions, most-recently-
  active first, capped at 50, each carrying a `pending_confirmation`
  flag computed TTL-agnostic from the HITL confirmation registry.
- `GET /api/v2/sessions/{id}` gains a server-minted title (first user
  turn, 80 characters, set once — never rewritten) and a best-effort
  transcript reconstructed from the kernel state snapshot;
  `transcript_available` marks the explicit fallback.
- `DELETE /api/v2/sessions/{id}` removes the session plus its state
  snapshot. Unknown and foreign ids both answer `404`
  (anti-enumeration); a parked HITL confirmation blocks delete with
  `409`.
- Session records carry `last_active_at` and `title` in both store
  backends (Postgres DDL bootstrap and in-memory), touched on create
  and chat.
- Platform-gateway proxies all three endpoints; `session:list` and
  `session:delete` are new deny-by-default protected actions granted to
  the five chat-capable roles (`auditor` denied), synced across all
  four policy bundle copies (12 rules validate). Deletes emit a durable
  `session_deleted` audit event. Upstream `4xx` passes through
  unchanged; transport failures and `5xx` map to `502`.

### Why It Matters

Operators can now manage conversation state: see their sessions, resume
by id, and reclaim the workspace without touching Redis or Postgres
directly. Every gate is role-enforced and audited; foreign-session
probing stays indistinguishable from unknown ids.

## Change Set 2: Voice-readiness contract (R-2)

### Highlights

- `input_modality` (`text` | `voice`, default `text`) is accepted by
  `POST /api/v1/chat`, the gateway proxy, the agent-platform v2 chat
  schema, and `agent-chat-request.schema.json`; invalid modalities fail
  with `422` before any upstream call.
- Invariant I — modality is never privilege: text and voice requests
  share identical policy, auto-allow, and HITL outcomes (parity-tested
  in both gateways).
- Invariant II — the confirm surface is unchanged: `chat/confirm`
  schemas carry no modality field and stay click-gated (regression-
  tested).
- The modality is recorded in the chat log event and mirrored into the
  `chat_completed` audit details; stream schema stays at v6.

### Why It Matters

When voice input lands (likely with the portal rebuild), the transport
contract already exists and its safety invariants are pinned in tests —
no privilege surface opens with it.

## Change Set 3: Mutating-dev runtime profile (R-3)

### Highlights

- New `shared/platform-ops/gitops/runtime-profiles/mutating-dev/`
  profile promotes the SPEC-021 opt-in into the committed dev posture:
  `GATEWAY_MUTATING_TOOLS_ENABLED=true` is merged into
  `platform-runtime-config` by the dev-k8s overlay, and the pod-delete
  RBAC now rides the profile.
- The profile is wired into `dev-k8s` and the root `OVERLAYS` gate
  (`make overlays` renders five overlays); `select-runtime-profile.sh`
  preserves it across LLM provider switches; `verify-runtime-profile.sh`
  filters it from the provider check.
- Base and all LLM profiles keep `false` — the fail-closed SPEC-021
  default is untouched everywhere dev-k8s is not explicitly opted in.
- Dev-k8s README documents the profile mechanism, the same-tag rollout
  note, and a deactivation runbook.

### Why It Matters

The bounded write capability (SPEC-021) is now declaratively on in the
one environment meant for it, and off everywhere else by construction —
no manual ConfigMap edits to drift out of sync.

## Change Set 4: Docs, matrix, and in-release fixes (R-4)

### Highlights

- Authorization matrix documents the live matrix transparency for the
  session lifecycle actions; architecture overview adds
  `session:list`/`session:delete` (plus previously missing
  `chat:confirm`/`tools:mutate`) to the Protected Actions table and
  corrects the bundle rule count to twelve.
- Approval and HITL guide gains the voice-readiness subsection and the
  mutating-dev Layer-2 note; configuration reference documents the
  `input_modality` request field; troubleshooting gains transcript-
  fallback and delete-`409` symptom sections.
- Fixed in-release (walkthrough findings): the session-detail proxy now
  passes upstream `4xx` through instead of leaking `500`, and the
  audit-service `EventType` Literal was synced with the contract schema
  (`session_deleted`) — with a new test pinning model/contract enum
  parity so this drift cannot recur silently.

## Validation

- `make verify` green: 1,040 tests across seven products (agent-platform
  298, platform-gateway 166, audit-service 72, tool-gateway 196, plus
  identity/incident/skills), five kustomize overlays render, policy
  bundle (12 rules) and version lockstep (0.8.0) validate.
- `make build` + `make deploy` green against dev-k8s; cluster ConfigMap
  carries `GATEWAY_MUTATING_TOOLS_ENABLED=true` via the profile merge,
  pod-delete RBAC rides the profile, all nine deployments healthy.
- Live API walkthrough through platform-gateway: session create →
  `input_modality=voice` chat turn (10 pods answered) → list shows the
  minted title and `last_active_at` → detail shows a 2-entry transcript
  (`transcript_available: true`) → delete `200` → get/re-delete `404` →
  auditor list `403` (`session:list` denied by policy) → durable
  `session_deleted` audit event and `chat_completed` with
  `{"input_modality": "voice"}` confirmed in the audit trail.

## Known Limitations

- The portal has no multi-session UI yet; the API is the integration
  surface until the portal framework rebuild consumes Appendix A.
- Transcripts are best-effort reconstructions from the kernel state
  snapshot; sessions whose snapshot lacks message history report
  `transcript_available: false` rather than a partial or fabricated
  transcript.
- Delete does not cascade to audit history by design — the audit trail
  is append-only and retains the session's events.

## Related Documents

- `docs/specs/SPEC-022-multi-session-operator-workspace/` (spec, plan, tasks)
- `docs/guides/approval-and-hitl.md` (voice-readiness subsection)
- `docs/guides/configuration-reference.md` (`input_modality` field)
- `shared/platform-ops/gitops/dev-k8s/README.md` (mutating-dev profile)
- `CHANGELOG.md` (0.8.0)
