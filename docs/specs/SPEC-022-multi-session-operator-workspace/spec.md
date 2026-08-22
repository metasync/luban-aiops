# SPEC-022: Multi-Session Foundations — Session API, Voice-Readiness Contract, and Mutating-Dev Profile

## Status

- status: `delivered`
- owner: chi
- created: 2026-08-22
- approved: 2026-08-22
- release slice: R5 operator workspace — first slice (0.8.0 train)
- related ADRs: none new; builds on SPEC-016/017 (durable sessions and kernel
  state), SPEC-020 (HITL confirmation bridging — parked confirmations are
  session-scoped), SPEC-021 (bounded mutating actions — opt-in deployment
  posture), SPEC-012 (operator-enablement discipline)

## Summary

Deliver the framework-agnostic foundations of the multi-session operator
workspace: a session lifecycle API (list/get-with-transcript/delete) exposed
through agent-platform and proxied by platform-gateway under new
deny-by-default policy actions; a minimal voice-readiness contract
(`input_modality` plus two recorded invariants) so future voice-to-text input
lands without protocol changes and without ever bypassing human approval; and
the SPEC-021 dev opt-in promoted to a committed, environment-scoped kustomize
profile (`runtime-profiles/mutating-dev`) so dev-k8s redeploys stop clobbering
the mutating-tools test posture while every other environment stays
deny-by-default.

The portal UI for the multi-session workspace is **deliberately deferred** to
the portal framework rebuild spec (SPEC-023 candidate): the portal may be
rebuilt on an AI UI framework (Ant Design X, AgentScope Spark, or similar)
with built-in multi-session and voice components, and building the session
panel in the current hand-rolled vanilla-JS UI would be throwaway work. The
deferred UI requirements are preserved verbatim in Appendix A as the handoff
contract for that spec.

## Motivation

- Sessions are already durable (SPEC-016 Postgres store) and the session
  store already implements `list_sessions_by_user` and `delete_session` —
  the capability exists below the API surface but is exposed nowhere:
  agent-platform has no list/delete/transcript endpoints and
  platform-gateway only proxies `POST /api/v1/sessions`. Any future portal
  UI — vanilla or framework-based — needs exactly this API; landing it first
  delivers value immediately and de-risks the rebuild.
- SPEC-020 parked confirmations are session-scoped. Multi-session workflows
  require knowing *which* session is awaiting a decision; the API surfaces
  that state (`pending_confirmation`) so any UI can badge parked work.
- Voice-to-text is a stated usability goal, and candidate rebuild frameworks
  ship voice input components. The right preparation is contract discipline,
  not an STT integration: a schema-extensible chat request
  (`input_modality`) and recorded invariants (modality is metadata, never a
  privilege; approval stays an explicit UI action). Doing this now makes the
  future voice work UI-only.
- The portal may be rebuilt on an AI UI framework (separate discussion).
  Shipping backend and contracts first keeps this spec immune to that
  decision; shipping the session-panel UI first would not.
- SPEC-021's dev opt-in currently lives in a manual flag flip plus an
  out-of-band RBAC apply; every `make deploy` reverts it. A committed
  environment-scoped profile removes the drift while keeping the base and
  all non-dev overlays deny-by-default.
- The known single-owner named-session pitfall (foreign-owner sessions
  hidden behind 404) must be addressed deliberately as session surfaces
  grow; this spec pins the ownership model before any UI makes it
  load-bearing.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Session management API surface

Agent-platform exposes session lifecycle operations over its v2 API and
platform-gateway proxies them under new deny-by-default policy actions.

Acceptance criteria:

- Agent-platform adds `GET /api/v2/sessions` (list the caller's sessions,
  most-recently-active first, capped at 50), `DELETE /api/v2/sessions/{id}`
  (owner-only; foreign or unknown ids return 404 per the anti-enumeration
  house convention), and extends `GET /api/v2/sessions/{id}` with the
  session transcript (ordered user/assistant turns reconstructed from
  durable kernel state; when no transcript is recoverable the response
  carries `transcript_available: false` rather than failing).
- Session records carry a server-minted `title` (first user message, capped
  at 80 characters, never model-supplied) and `last_active_at`; both are
  returned by list and get.
- Platform-gateway proxies `GET /api/v1/sessions`,
  `GET /api/v1/sessions/{id}` (existing route extended), and
  `DELETE /api/v1/sessions/{id}` gated by new `session:list` and
  `session:delete` actions in the policy bundle (granted to the same roles
  as `session:create`); every decision is logged and session lifecycle
  events (`session_deleted`) reach the durable audit trail.
- List and get responses include `pending_confirmation: bool`, derived from
  the HITL confirmation registry for that session, so a UI can badge parked
  work without polling the stream.

### R-2: Voice-readiness contract

The chat contract becomes modality-aware without implementing any speech
capability.

Acceptance criteria:

- The chat request schema (platform-gateway `ChatRequest`, agent-platform v2
  chat schemas, and the shared `agent-chat-request` contract) accepts an
  optional `input_modality` with enum `text | voice`, defaulting to `text`;
  unknown values are rejected by schema validation (extra fields remain
  forbidden).
- The resolved modality is carried into the gateway's chat log event and the
  `chat_request` audit details so dictated turns are traceable end to end.
- Invariant I: modality is metadata, never privilege — no code path grants
  different tool admission, auto-allow, or policy outcomes based on
  `input_modality`; pinned by test.
- Invariant II: HITL decisions stay explicit UI actions — `POST
  /api/v1/chat/confirm` is the only decision surface, is unchanged, and the
  Approval and HITL guide records that voice input may never approve or deny
  (approval requires a deliberate pointer action on the confirmation card).
  The rebuild spec must re-assert Invariant II against whichever framework
  it adopts.

### R-3: Environment-scoped mutating deployment profile

The SPEC-021 dev opt-in becomes a committed kustomize profile; the base
stays deny-by-default.

Acceptance criteria:

- New overlay `shared/platform-ops/gitops/runtime-profiles/mutating-dev/`
  merges `GATEWAY_MUTATING_TOOLS_ENABLED=true` into
  `platform-runtime-config` via `configMapGenerator` `behavior: merge` and
  carries the pod-delete Role/RoleBinding (moved from
  `base/tool-gateway/tool-gateway-pod-delete.yaml`).
- `dev-k8s/kustomization.yaml` includes the profile; the root `Makefile`
  adds it to `OVERLAYS` so `make verify` renders it; a fresh clone deployed
  via `make deploy` yields the opted-in dev posture with no manual steps.
- `base/tool-gateway/runtime-config.env` keeps
  `GATEWAY_MUTATING_TOOLS_ENABLED=false`; any overlay that does not include
  the profile remains byte-identical to today's deny-by-default posture;
  `mutating-demo.sh` still passes against a default (disabled) posture when
  the profile is absent.
- The dev-k8s README and the Approval and HITL guide replace the manual
  opt-in runbook with the profile mechanism, including the
  `kubectl rollout restart deployment/tool-gateway` note for same-tag
  ConfigMap changes.

### R-4: Documentation and authorization matrix

Acceptance criteria:

- `docs/agentic-aiops-platform/authorization-matrix.md` documents
  `session:list` and `session:delete` grants for every role.
- The configuration reference documents any new settings or contract fields
  the delivery introduces; guides note that the multi-session *UI* arrives
  with the portal rebuild spec while the API is already available.
- CHANGELOG, spec index, and roadmap updated at delivery; release note
  follows the established structure.

## Appendix A: Deferred portal UI requirements (handoff to the rebuild spec)

The following requirements were drafted for this spec and are deferred
verbatim to the portal framework rebuild spec (SPEC-023 candidate), which
must satisfy them on the chosen framework:

- **Session panel**: the chat view lists the operator's sessions with title,
  relative last-active time, and an amber *awaiting approval* badge when
  `pending_confirmation` is true; the panel refreshes on session lifecycle
  events and at most every 30 seconds otherwise.
- **Switch/resume**: switching loads the target session's transcript (or an
  explicit "history unavailable" state), repoints the active stream and
  confirm endpoints at that session, persists the active session id per
  browser tab, and closes any in-flight stream of the previous session.
- **New/delete**: *New session* uses the existing create path; *Delete*
  requires an in-UI confirmation and is refused (client- and server-side,
  HTTP 409) for sessions with a parked confirmation.
- **Confirmation anchoring**: confirmation cards remain anchored to the
  session that parked them; approving/denying from a switched-into session
  resumes that session's stream exactly as today.
- **Incident deep links**: the incident view's `incident-<id>` session
  pinning must open as another session in the panel rather than replacing
  the active one.
- **Voice input**: if the chosen framework ships a voice input component, it
  sends ordinary chat requests with `input_modality: "voice"` and satisfies
  R-2 Invariant II (no voice-driven approvals).
- **Model dropdown**: out of scope here; owned by the runtime model
  switching slice (SPEC-024 candidate) with its UI landing in the rebuild.

## Non-Goals

- Portal UI implementation for the session workspace (deferred — Appendix A).
- Portal framework selection, adoption, or rebuild (own spec; spike memo
  first per the roadmap promotion rule).
- Speech-to-text engines, audio capture, or transport.
- Runtime LLM model switching / provider selection backend (own spec,
  SPEC-024 candidate).
- Cross-user session sharing, handoff, or admin session inspection beyond
  existing audit trails.
- Policy-center `require_approval` semantics (separate R4 slice).
- Session export/backup, and kernel-side SQL storage migration.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Confirmation registry is in-memory (single agent-platform replica); a restart loses parked batches regardless of this spec | Existing SPEC-020 limitation; R-1 only *reports* registry state and documents the caveat; no new durability promise |
| Transcript reconstruction from kernel state snapshots may be incomplete for old sessions | Explicit `transcript_available` flag; never fabricate history; UI state defined in Appendix A |
| Session list growth / N+1 queries against Postgres | Cap at 50, single indexed query by owner, `last_active_at` ordering pinned in tests |
| Multi-user named-session ownership confusion (known pitfall: 404 hides foreign owners) | Sessions created through the portal are always fresh server-minted ids owned by the caller; named-session semantics stay an incident-service integration detail, documented in the plan |
| Dev posture divergence (dev opted in, everything else deny-by-default) surprises operators | Profile inclusion is a one-line visible decision in `dev-k8s/kustomization.yaml`; guides state the invariant explicitly |
| Rebuild spec changes the API shape after delivery | Appendix A is written against the R-1 contract; any API change re-opens this spec before the rebuild consumes it |

## Alternatives Considered

- **Build the session-panel UI now in the vanilla-JS portal** — rejected:
  the portal framework rebuild discussion makes this likely throwaway work;
  the API delivers the value without it, and Appendix A preserves the UI
  requirements intact.
- **Fold the framework rebuild into this spec** — rejected: mixes a backend
  contract with a frontend-platform migration, makes the spec unreviewable,
  and holds the session API hostage to a framework decision.
- **Portal-local session history (localStorage only)** — rejected: history
  would not survive device/browser changes and would diverge from the
  durable audit trail; the store already supports the real thing.
- **Cross-user session visibility for admins** — rejected for this slice:
  anti-enumeration convention and audit trail already cover oversight.
- **Defaulting `GATEWAY_MUTATING_TOOLS_ENABLED=true`** — rejected: inverts
  the SPEC-021 fail-closed contract; the environment-scoped profile (R-3)
  delivers the ergonomics without weakening the default.

## Open Questions

None blocking; transcript reconstruction strategy is decided in plan.md.

## Changelog

- 2026-08-22: drafted for review
- 2026-08-22: restructured — portal UI (former R-2) deferred to the portal
  framework rebuild spec; requirements renumbered, Appendix A added as the
  handoff contract
- 2026-08-22: approved; implementation started (0.8.0 train)
- 2026-08-22: delivered in 0.8.0 — all R-1…R-4 acceptance criteria
  verified; `make build` + `make verify` green; live walkthrough on
  dev-k8s covered create/chat(voice)/list/detail/delete, 404/403/409
  posture, and the durable `session_deleted` audit chain. Two
  walkthrough findings were fixed in-release: the session-detail proxy
  now passes upstream 4xx instead of leaking 500, and the audit-service
  `EventType` vocabulary was synced with the contract schema
  (`session_deleted`) with an enum-parity test added.
