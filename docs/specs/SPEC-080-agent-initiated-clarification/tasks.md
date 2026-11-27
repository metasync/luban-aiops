# SPEC-080 Tasks: Agent-Initiated Clarification (a read-only `AskUser` park/resume beside the HITL confirmation path)

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.

> **Binding as of approval 2026-11-25.** Derived from [plan.md](plan.md); all seven Open Questions were
> ratified exactly as recommended. Approval authorizes implementation to **begin** — **not** to merge,
> commit/push, deploy, or version-bump (each a separate gate). Target version **v0.62.0**, bumped only
> at the release gate.

## R-3: v2 SSE frame pair, v13 → v14 (contract first)

- [x] Add `clarification_request` + `clarification_result` to the `type` enum + field schemas; bump the
  title v13 → v14; `additionalProperties: false` holds; no existing frame changes
  (`shared/shared-contracts/schemas/agent-stream-event.schema.json`)
- [x] Mirror both frames in the agent-platform pydantic models with a closed `Literal` enum
  (`products/agent-platform/src/agent_service/schemas/v2.py`)
- [x] Mirror the gateway passthrough model
  (`products/platform-gateway/src/platform_gateway/services/gateway_service.py`)
- [x] Contract-parity test binds the gateway model to the v14 schema (the packaged contract-parity suite)

## R-1: A clarification park kind on the shared substrate

- [x] Add `park_kind` to `PendingConfirmation` + a `park_kind` param to `register(...)`; the
  one-per-session slot holds either kind (`products/agent-platform/src/agent_service/services/hitl_confirmations.py`)
- [x] Carry the projected questions + `clarification_id` on a parked clarification (same file)
- [x] Extend the SPEC-031 durable record store with the `park_kind` discriminator + an additive migration
  (`products/agent-platform/src/agent_service/services/confirmation_records.py`; migration under `shared/shared-contracts/`)
- [x] Unit: `park_kind` slot + mutual exclusion; the durable record survives a simulated re-login
  (`products/agent-platform/tests/`)

## R-2: The kernel's first external-execution handler

- [x] Add the `RequireExternalExecutionEvent` branch beside `kernel_confirmations.py:116-119` — detect the
  parked `AskUser`, project → `clarification_request`, register the park, end the stream without
  `message_end` (`products/agent-platform/src/agent_service/services/kernel_confirmations.py`)
- [x] Add `resume_clarification(...)` as a sibling to `resume_confirmation(...)` (`:427`) — build
  `execution_results` (prose `output` + `AskUserMetadata`), inject `ExternalExecutionResultEvent`,
  re-drive the same turn (same file)
- [x] Reuse `expire_confirmation` → `UserInterruptEvent` for TTL expiry + operator cancel of a parked clarification
- [x] Unit: park → project → register → resume-by-injection; expire/cancel; the confirmation branch stays
  byte-identical (`products/agent-platform/tests/`)

## R-4: Park-kind-aware 409 guard + answer endpoint

- [x] `_reject_if_parked` names the parked kind in the 409
  (`products/agent-platform/src/agent_service/api/v2/routes.py:229`)
- [x] Add `POST /api/v2/sessions/{id}/clarification/answer` → `resume_clarification`, race-resilient
  (`already_resolved`) (`products/agent-platform/src/agent_service/api/v2/routes.py`)
- [x] Gateway proxy route (`products/platform-gateway/src/platform_gateway/`)
- [x] Unit: 409 for both kinds; the answer validates against the parked questions; a duplicate/stale
  answer → `already_resolved` (`products/agent-platform/tests/`)

## R-5: Opt-in, flag-gated wiring

- [x] Add `AGENT_ASKUSER_ENABLED` (default **off**) to runtime settings
  (`products/agent-platform/src/agent_service/` config/settings)
- [x] Admit `AskUser` to the toolkit only when the flag is on
  (`products/agent-platform/src/agent_service/services/kernel_toolkits.py`)
- [x] Register the flag in the SPEC-072 `runtime:flags` inventory; the dev overlay opts in
  (`shared/platform-ops/gitops/dev-k8s/`)
- [x] Unit: flag off ⇒ the unscoped chat path is byte-identical (no new frame/park/event)
  (`products/agent-platform/tests/`)

## R-6: The v1 `AskUser` feature surface (full shape minus `preview`)

- [x] Project the full `AskUserParams` (`questions[1-4]`, `header ≤12`, `context?`, `multi_select`,
  `options[2-4]`) minus `preview` (`products/agent-platform/src/agent_service/services/kernel_confirmations.py`)
- [x] Round-trip `AskUserMetadata{answers}` with `multi_select` + the auto-"Other" free text
- [x] Unit: the projection + validation mirror the agentscope constraints; no `preview` field exists in v14

## R-7: A portal clarification card, owner-answerable in-line

- [x] Render the owner-answerable clarification card (questions, options, `multi_select`, "Other")
  (`ClarificationCardView` exported from `products/operator-portal/web-ui/app/src/chat/ChatView.tsx`,
  beside the confirmation-card rendering — the portal keeps both cards inline in `ChatView.tsx` rather
  than as separate sibling files)
- [x] Handle `clarification_request` / `clarification_result` in the SSE adapter
  (`products/operator-portal/web-ui/app/src/stream/useChatStream.ts`)
- [x] Submit the answer to the R-4 endpoint; render the resumed same-turn stream
  (`products/operator-portal/web-ui/app/src/chat/ChatView.tsx`)
- [x] Re-render the answered card from the durable record on re-login
- [x] Portal Vitest tests for the card + adapter (`products/operator-portal/web-ui/app/src/chat/__tests__/`)

## R-8: Audit rides the turn events; the enum stays closed

- [x] Assert no new `event_type`; the parking/resuming turn is bracketed by `chat_started` /
  `chat_completed` (`products/agent-platform/tests/`)
- [x] The audit-contract drift guard passes with the enum unchanged at 23 values
  (`shared/shared-contracts/`)

## Evidence — four-point gate + gated live-check

> **SPEC-018 four-point-gate mapping (recorded 2026-11-25).** A clarification re-affirms the four-point
> gate at a posture strictly *less* than the confirmation path: **1 — deny-by-default + audit:** `AskUser`
> executes nothing and mints **no** new `event_type` — the parking/resuming turn rides the **closed**
> `chat_started` / `chat_completed` bracket (the enum stays at 23; `test_contract_parity.py::
> TestClarificationRidesTheClosedAuditEnum` + the audit-service drift guard
> `test_event_type_enum_is_closed_and_unchanged_at_23` pin it, and the gateway
> `ClarificationAnswerAuditTests` pin the runtime `chat_completed` emission + repark-stays-unattributed).
> **2 — identity on the one token:** the owner parks and answers over the *same* gateway-forwarded
> delegated bearer token on the existing v2 surface; no new principal, claim, or identity edge, and no
> approver identity is minted (the owner answers in-line, OQ-5). **3 — read-only posture:** a
> clarification carries `questions`/`options`, never a mutating `pending_call`/`risk_level`; it never
> stages, dispatches, or auto-approves — the gated live-check asserts **zero** `execution_requested` /
> `execution_completed` / `confirmation_decided` across the whole session family and a durable
> `park_kind=clarification` / `status=answered` card with **zero** `pending_calls`. **4 — no agentscope
> types on the wire:** the v14 `clarification_request` / `clarification_result` frames are platform-owned
> projections of `AskUserParams` minus `preview` (`test_clarification_projection.py`), and the resume is
> injected in-process as an `ExternalExecutionResultEvent` — no agentscope event/tool type crosses the
> contract.

- [x] A gated billable live-check mirroring the confirmation live-check: park a clarification → the owner
  answers → same-turn resume; assert **no** mutation, **no** dispatch, **no auto-approval**
  (`shared/platform-ops/e2e/clarification-livecheck.sh` + the mocked-I/O
  `products/agent-platform/tests/test_clarification_livecheck.py` collected by `make test`, wired via
  `make clarification-livecheck`)
- [x] Map the four-point gate per point (deny-by-default + audit; delegated-token identity; read-only
  posture; no agentscope types on the wire) in this file's evidence at delivery

> **Acceptance-criteria → asserting-test mapping (ADR-0008; recorded 2026-11-27).** Every `spec.md`
> acceptance criterion is pinned by ≥1 test. **R-1** (one-per-session slot + mutual exclusion; durable
> re-login; no approver/inbox/self-approval) → `test_hitl_confirmations.py::test_registry_park_kind_defaults_to_confirmation`,
> `::test_registry_clarification_park_occupies_shared_slot`, `test_confirmation_records.py::test_save_and_load_round_trips_park_kind_and_questions`,
> `::test_clarification_never_enters_approver_inbox`. **R-2** (the `RequireExternalExecutionEvent` branch
> beside the untouched confirm branch; `UserInterruptEvent` abort; no agentscope object on the wire) →
> `test_hitl_confirmations.py::test_stream_events_parks_and_emits_clarification_request`, `::test_resume_clarification_injects_external_execution_result`,
> `::test_resume_clarification_resolves_entry_on_stream_error`, `::test_expire_confirmation_closes_parked_clarification`.
> **R-3** (two additive v14 `type` values; `additionalProperties:false`; no existing frame change; gateway
> parity) → `test_contract_adapter.py::test_clarification_frames_v14_contract_and_projection_parity` + the
> packaged contract-parity suite. **R-4** (409 names the parked kind; the answer endpoint resumes;
> stale/duplicate → `already_resolved`) → `test_hitl_confirmations.py::test_parked_clarification_rejects_new_turns_naming_kind`,
> `::test_answer_clarification_rejects_unknown_question`, `::test_answer_clarification_rejects_unknown_option`,
> `::test_answer_clarification_streams_clarification_result_first`, `::test_duplicate_answer_clarification_fails_closed_already_resolved`
> + the gateway `test_clarification_answer.py`. **R-5** (flag off ⇒ byte-identical unscoped path; default
> off; the flag in the inventory) → `test_runtime_kernel.py::test_askuser_absent_when_flag_off_keeps_toolkit_byte_identical`,
> `::test_askuser_admitted_when_flag_on_and_excluded_from_gateway_count`, `::test_askuser_only_toolkit_when_gateway_empty`,
> `::test_feature_flags_report_each_knob`. **R-6** (full `AskUserParams` minus `preview`; `multi_select` +
> auto-"Other"; no `preview` in v14) → `test_clarification_projection.py` + `test_hitl_confirmations.py::test_build_clarification_frame_projects_ask_user_minus_preview`,
> `::test_build_clarification_frame_truncates_long_header`. **R-7** (card renders from `clarification_request`,
> posts an answer that resumes, re-renders from the durable record, no approver inbox) →
> `ClarificationCard.test.tsx` + the portal stream/chat Vitest legs + `test_contract_adapter.py::test_answered_clarification_record_conforms_to_session_contract`.
> **R-8** (no new `event_type`; the turn bracketed by `chat_started`/`chat_completed`; the drift guard
> passes at 23) → `test_contract_parity.py::TestClarificationRidesTheClosedAuditEnum` + the audit-service
> `test_contracts.py::test_event_type_enum_is_closed_and_unchanged_at_23` + the gateway `ClarificationAnswerAuditTests`.
> Root `make verify` green confirms the aggregate.

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (each `R-x` maps to ≥1 asserting test — ADR-0008; see
  the mapping recorded in the Evidence section above, 2026-11-27)
- [x] living state docs updated (see spec `Impact`: the guide layer, the roadmap Exploration Backlog row,
  a dated release note) — **guide layer + roadmap row done 2026-11-27** (`approval-and-hitl.md`,
  `portal-user-guide.md`, `configuration-reference.md` ×3, the Exploration Backlog row); the **dated
  release note written + indexed 2026-11-27** (`release-notes/2026-11-27-spec-080-agent-initiated-clarification.md`)
- [x] `CHANGELOG.md` entry added referencing SPEC-080 (accumulated under `## Unreleased`, then **closed
  into `## 0.62.0 — 2026-11-27`** at the release gate)
- [x] spec index in `docs/specs/README.md` flipped to `delivered` — **done 2026-11-27** at the release gate
- [x] spec status set to `delivered`; target version **v0.62.0** bumped at the release gate — **done
  2026-11-27** (`VERSION` 0.61.1 → 0.62.0 across the 27-file lockstep surface; `make validate-version`
  + `make sync` green)
- [x] root `make verify` green (incl. the 795-case SPEC-063 execution-failure campaign) — full run
  **2026-11-27 at v0.61.1**, every leg exit 0 (all 7 overlays rendered; docs-check 0 unresolved env
  vars; policy-scenarios 163 api + 42 tools; each product suite + portal Vitest 50 + 601 green; the
  delegated custody/runtime/multiproc/edge proofs over real docker + TLS; the SPEC-063 campaign **795
  passed, 2 deselected, exit 0** in 0:34:41). After the **0.61.1 → 0.62.0** bump (literals only — no
  logic delta) the version- and doc-sensitive legs were **re-verified at 0.62.0**: `make
  validate-version` → *OK … match VERSION=0.62.0*, `make sync --frozen` green across all 8 products,
  and `make docs-check` → *PASS* (0 orphaned, 0 unresolved env vars); no first-party test hard-codes a
  version literal, so the bump cannot break a suite. The version-independent legs (overlays, policy,
  dashboards, delegated proofs, the SPEC-063 campaign) rest on the 0.61.1 full run.
- [x] **v0.62.0 release committed** at the release gate (2026-11-27) — the version bump + the full
  SPEC-080 delivery (code, tests, contracts, docs) are committed to `main` in this release commit.
  **Push / tag / deploy remain separate gates** (held — not authorized by approval; a push is gated
  behind an offered L3 deep security review).
