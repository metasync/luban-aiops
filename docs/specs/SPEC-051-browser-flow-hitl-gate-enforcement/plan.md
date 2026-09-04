# SPEC-051 Plan: Browser Flow HITL Gate Enforcement and Password-Reset Sample Reconciliation

## Approach

Two independent defects, fixed together (the "defense in depth" the operator
chose): a **platform** change that enforces SPEC-049 R-4's flow-unlock in the
agent-platform kernel (one approval per mutating browser flow), and a
**sample** change that reconciles the password-reset demo to a single gate on
the destructive action. The platform change is the root-cause fix; the sample
change removes the contradiction that made the model improvise extra writes.
A third facet (R-6) makes the single card **flow-semantic** — it names the
bound workflow rather than the bare tool action — spanning the gateway
(surface the skill's `title`/`description` on the flow dict), the kernel
(extract it onto the confirmation frame), and the portal (render the headline
above the tool detail).

The platform design keeps the existing SPEC-037/038 signed-execution path
fully intact: the first browser write parks a card as today; on approval the
kernel records a flow authority scoped to the session **and the approved
flow's identity**; each subsequent browser write in that flow is admitted by
the permission middleware and **auto-signed** under that authority, then handed
off exactly like an approved-card execution. The tool-gateway deviation guard
stays the enforcement boundary.

Feasibility was verified against the worker: `execution-runtime` `handoff.py`
checks only the handoff token, required fields, the HMAC signature, the
`args_digest`, and single-flight on `execution_id` — it does **not**
cross-check `call_id` against a durable parked-call set. A kernel-signed
envelope (fresh `execution_id`/`call_id`, the new call's `args_digest`,
reusing the approving card's `confirm_id`/`decider`, same signing key) is
therefore accepted, and `execute_tool` forwards `session_id` so the gateway
deviation guard still bounds every unlocked write.

## Design Per Requirement

### R-1 / R-3: Platform flow-unlock and signed unlocked writes (agent-platform)

Design: one operator card per mutating browser flow. The kernel maintains a
session-scoped **`FlowContext`** — its reflection of the gateway-owned flow
binding, updated from each `web.navigate` result's `data["flow"]` (`skill_id`,
`origin`, `title`, `description`, `risk_class`, steps). The first browser write
parks normally (the card renders from `FlowContext` — see R-6); on approval the
kernel records a flow authority scoped to the session **and that flow's
identity**; subsequent `web.*` write interactions are ALLOWed and auto-signed
**only while `FlowContext` still matches the approved identity** (each still
individually signed, persisted, audited, and receipted). A rebind to a
different flow overwrites `FlowContext`, the identity no longer matches, and
the next write re-parks — this is what eliminates the ADR-0007 cross-flow
trade-off. The static auto-allow list is untouched — this is runtime,
flow-scoped session authority, not an allow-list entry, so the R-4/R-1
auto-allow invariant and its test stay green.

- **New `services/flow_approvals.py`** — two session-scoped, per-process stores
  (sibling pattern to `CONFIRMATION_REGISTRY`):
  - `FlowContext` dataclass (`session_id`, `skill_id`, `origin`, `title`,
    `description`, `risk_class`, `steps_used`, `max_steps`, `observed_at`
    monotonic) + `FlowContextStore` (`record(session_id, flow_dict)`,
    `get(session_id)`, `clear(session_id)`, `clear_all()`) + `FLOW_CONTEXTS`
    singleton — the kernel's reflection of the gateway flow binding, updated
    from each `web.navigate` result. `record` overwrites on a new
    `skill_id`/`origin`, which is how a rebind is detected.
  - `FlowApproval` dataclass (`session_id`, `confirm_id`, `owner_user_id`,
    `decider_user_id`, **`skill_id`, `origin`** — the approved flow identity —
    `approved_at` monotonic) + `FlowApprovalStore` (`record(...)`,
    `get(session_id)` honors TTL → expired returns `None`,
    `has_approval(session_id)`, `clear(session_id)`, `clear_all()`) +
    `FLOW_APPROVALS` singleton.
  - `BROWSER_WRITE_TOOLS` constant (dotted): `web.click`, `web.type`,
    `web.select`, `web.press_key`, `web.upload_file`, `web.evaluate`.
- **`services/execution_signing.py` — `build_flow_request(...)`** — a
  single-call sibling to `build_requests`:
  `build_flow_request(call_id, tool_name, parameters, flow_approval, key) -> dict`
  producing the same envelope shape (`execution_id` fresh;
  `confirm_id`/`session_id`/`owner_user_id`/`decider_user_id` from the flow
  authority; `tool_name` = canonical dotted name;
  `args_digest = canonical_digest(parameters)`; `requested_at`; `signature`).
  Reuses `sign_envelope`.
- **`services/kernel_middleware.py` — flow-unlock branch** —
  `GatewayPermissionMiddleware.__init__` gains an optional
  `flow_signer: Callable | None = None`. In `on_check_permission`, add a
  branch **after** the ALLOWED-state and KERNEL_LOCAL branches and **before**
  the final ASK: if the tool is a browser write (`gateway_tool_name` starts
  with `web.`, is in `BROWSER_WRITE_TOOLS`, and `is_read_only` is False)
  **and** `flow_signer` returns an envelope for
  `(tool_call, gateway_tool_name)` → return `ALLOW`; otherwise fall through
  to the existing ASK. Non-browser writes (`k8s.*`, etc.) are never affected.
- **`runtime_kernel.py` — signer, recording, arming:**
  - New `_sign_flow_execution(tool_call, gateway_tool_name) -> dict | None`
    (passed as `flow_signer` in `_build_middlewares`): reads `CHAT_SESSION_ID`;
    looks up `FLOW_APPROVALS.get(session_id)` (TTL-honored) **and
    `FLOW_CONTEXTS.get(session_id)`, returning `None` (→ fail-safe ASK) unless
    the approval's `skill_id`/`origin` match the current `FlowContext`** — the
    identity guard that makes a rebind re-park; requires
    `EXECUTION_REQUESTS.get()` to be a dict **and**
    `settings.execution_signing_key` (else `None` → fail-safe ASK); builds the
    envelope via `build_flow_request` (parameters parsed from `tool_call.input`,
    `call_id = tool_call.id`); **injects** it into the shared
    `EXECUTION_REQUESTS` dict; persists (`_persist_execution_request`) and
    audits (`_emit_execution_event("execution_requested", …)`) exactly like
    `_prepare_executions`; returns the envelope.
  - `resume_confirmation`: after `_prepare_executions`, when `confirmed` and
    the batch contains a browser write (via `pending.gateway_names` +
    `pending.risk_levels`), call `FLOW_APPROVALS.record(session_id,
    confirm_id=pending.confirm_id, owner_user_id=pending.user_id,
    decider_user_id=user_name, skill_id=pending.browser_flow.get("skill_id"),
    origin=pending.browser_flow.get("origin"))` — the identity captured on the
    parked card (R-6), so the authority is scoped to exactly the flow the
    operator approved; recorded **before** the resumed stream so same-turn
    subsequent writes unlock.
  - `_drain_trace_queue` records `FlowContext`: when a drained `tool_result`
    frame is a successful `web.navigate` whose `data` carries `flow`, call
    `FLOW_CONTEXTS.record(session_id, flow_dict)`. Both the live
    (`stream_events`) and resumed (`resume_confirmation`) paths drain through
    `_drain_trace_queue`, so this is the single population point; it runs
    before any later write in the same turn parks, so the card and the identity
    guard always see the current flow. A `web.navigate` binding a *different*
    skill overwrites the context — exactly how a rebind is detected.
  - `stream_events`: arm the same plumbing the resume path uses so cross-turn
    unlocked writes execute and receipt — set `EXECUTION_REQUESTS` to a fresh
    `{}`, set `EXECUTION_AUDIT_CONTEXT` from `FLOW_APPROVALS.get(session_id)`
    when present, and route both trace-drain blocks through the existing
    `_drain_trace_queue`. This is **inert for turns without a flow approval**
    (`{}` is never consulted because mutating tools still park;
    `_observe_tool_result` early-returns when no envelope matches `call_id`),
    so the common hot path is behavior-preserving. Reset the new contextvars
    in the existing `finally`.
- Alternative rejected (see ADR-0007): adding browser writes to
  `DEFAULT_AUTO_ALLOWED_TOOLS` — an auto-allowed mutating call has no signed
  envelope and fails closed at the handoff.

### R-2: Time-bounded, flow-scoped session authority (agent-platform)

- **`runtime_settings.py`** — add `browser_flow_approval_ttl: int = 900`
  (`AGENT_BROWSER_FLOW_APPROVAL_TTL`) with `>= 0` validation. `0` disables
  flow-unlock (every write parks, the pre-fix posture). `FlowApprovalStore.get`
  honors the TTL against `approved_at` (monotonic). The authority is keyed on
  the chat session id **and the approved flow's identity** (`skill_id` +
  `origin`) — the same handles the gateway flow binding uses — and `_sign_flow_
  execution` only unlocks while they still match the live `FlowContext`, so it
  carries no privilege beyond unlocking that one flow's browser writes for that
  session.

### R-4: Password-reset sample reconciliation (Design 1 — gate on "Confirm reset")

Pick the design the pages' own comment already describes and that gates the
**destructive** action: login is read-tier (`fill_credential` → auto-submit),
and the single write is the **"Confirm reset"** click. This also restores the
original recorded intent (auto-redirect/auto-submit login; sole `web.click`
on the reset submit button).

- **`shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml`**
  — `admin-reset-index.html`: **remove the reset auto-submit block** (the
  `if (newPw && targetUser !== "unknown") setTimeout(... doReset ...)` at
  ~lines 245-255); **keep** the URL auto-fill (~213-216) so the form
  pre-fills from `?newpw=` and waits for the click. `admin-index.html`:
  **keep** the login auto-submit (`_autoLoginTimer`) — authentication stays
  read-tier. Lightly clarify the comment (~58-61) that the reset form
  pre-fills but does not auto-submit.
- **`samples/web-checks/password-reset/skill/ResetUserPassword.md`** (version
  1.1 → 1.2) — frontmatter description: single HITL gate on the final
  **"Confirm reset"** action (the destructive mutation), not on
  authentication. Procedure: fill admin creds (`web.fill_credential` ×2) →
  login auto-submits (no click); snapshot the user list; `web.navigate` to
  `/admin/users/reset/?user=<email>&newpw=<pw>` (auto-fills both fields,
  read-tier); **`web.click` "Confirm reset"** = the flow's single write-tier
  interaction / the one card; snapshot + screenshot to verify. Tutorial notes
  explain why the gate is on the reset, why login is read-tier, and why the
  URL pre-fill keeps the confirm-click as the sole write.
- **`README.md` + `WALKTHROUGH.md`** — update the "How it works" steps, "Key
  design decisions" (gate = reset, not login), the WALKTHROUGH Step 4/5, the
  ASCII sequence diagram, and "Key Observations" to Design 1.
- **`samples/web-checks/password-reset/demo/demo.sh`** — chat leg asserts
  **exactly one** card (`len(cards) == 1`) whose `executions[0].tool_name ==
  'web.click'` with a signed receipt; **remove** the second-card tolerance
  (~247-274). Update the narrative comments (~19-28). Deterministic legs
  [1/5]-[5/5] unchanged (they only check pages are served, not the
  auto-submit JS).

### R-5: Delivery traceability (ADR-0008)

- `tasks.md` records the criterion → test mapping below.
- `CONTRIBUTING.md` gains the delivery-gate text (Testing + Design Review
  Checklist); `docs/specs/README.md` Enforcement gains a line. These land in
  Phase 1 with the ADRs so the gate is visible before delivery.

### R-6: Flow-semantic confirmation card (tool-gateway + agent-platform + operator-portal)

Design: the card headline is assembled from the bound skill's declared
metadata, which **already rides `web.navigate`'s result** — the gateway sets
`data["flow"] = entry.flow.to_dict()` (`browser_connector.py`). The gateway gap
is that `FlowState.to_dict()` omits the human-readable `title`/`description`;
the kernel/portal gap is that nothing reads the flow dict. The kernel side is
**shared with R-1's `FlowContext`** — one maintained session-scoped state, two
consumers (identity guard + card) — so R-6 adds no separate extraction path.
No new contract:

- **tool-gateway — `tools/browser_sessions.py`**: `FlowState` gains
  `title: str = ""` and `description: str = ""`; `to_dict()` adds both keys.
  **`tools/browser_connector.py` `bind_flow`**: populate them from the fetched
  skill (`skill.get("title")`, `skill.get("description")`) — the same `skill`
  dict already read for `web_target`/`risk_class`. No handler or
  deviation-guard change; the flow dict keeps riding `data["flow"]`.
- **agent-platform — `runtime_kernel.py`**: `_build_confirmation_frame` reads
  the session's `FlowContext` (`FLOW_CONTEXTS.get(session_id)`, maintained by
  `_drain_trace_queue` per R-1 — **not** a park-time frame walk) and passes its
  summary to the parked confirmation. **`services/hitl_confirmations.py`**:
  `PendingConfirmation` gains a `browser_flow: dict` field (the captured
  `FlowContext` summary — `skill_id`, `origin`, `title`, `description`,
  `risk_class`); the confirmation-request frame carries a card-level
  `flow_summary` from it — absent when no flow is bound (→ tool-level
  fallback). Capturing the identity on the card is also what lets
  `resume_confirmation` scope the `FlowApproval` to the approved flow (R-1).
  The per-call `pending_calls_payload` is unchanged (tool detail stays as-is).
- **operator-portal — `web-ui/app/src`**: `stream/decoder.ts` reads
  `payload.flow_summary` into the `ConfirmationRequestFrame`;
  `stream/models.ts` + `stream/useChatStream.ts` (`ConfirmationCard`) carry an
  optional `flowSummary`; `chat/ChatView.tsx` `ConfirmationCardView` renders a
  headline block (title, description, `origin` · `risk_class`) above the
  per-call list when present, falling back to today's rendering when absent.
  `api/sessions.ts` + `chat/transcript.ts` carry `flow_summary` on the durable
  record so the approvals inbox (`views/control/ApprovalsView.tsx`) and session
  detail replay the same headline.
- Alternative rejected: putting the headline in each `pending_calls` entry —
  the flow describes the whole card, not one call, and duplicating it per call
  misrepresents a multi-step flow as N separate actions. A card-level
  `flow_summary` matches the "one decision per flow" model (ADR-0007).
- Alternative rejected: a park-time `_extract_browser_flow` backward-walk over
  `evidence_frames` (mirroring `_extract_browser_element_map`) — it is a
  heuristic bound to frame ordering and to the *current turn's* evidence list,
  so a flow bound in an earlier turn would be missed. The maintained
  `FlowContext` is authoritative, cross-turn, and already required by R-1's
  identity guard, so R-6 reuses it rather than adding a second, weaker path.

## Sequencing And Dependencies

1. Phase 1 governance artifacts (ADR-0007, ADR-0008, this spec triad, index +
   roadmap + CONTRIBUTING rows) — depends on nothing; **pauses for operator
   approval** before any code.
2. `flow_approvals.py` (`FlowContext` + `FlowApproval` stores) +
   `build_flow_request` — depends on stage 1 approval.
3. `kernel_middleware.py` flow-unlock branch — depends on stage 2.
4. `runtime_kernel.py` — `_drain_trace_queue` records `FlowContext`;
   `_sign_flow_execution` identity guard + signer/recording/arming;
   `runtime_settings.py` TTL — depends on stages 2-3.
5. R-6 flow-semantic card — gateway `FlowState`/`bind_flow`/`to_dict()`
   (independent of stages 2-4); kernel `_build_confirmation_frame` reads
   `FlowContext` → `PendingConfirmation.browser_flow` + confirmation-frame
   `flow_summary` (lands alongside stage 4's `runtime_kernel.py` edits); portal
   decoder/model/`ConfirmationCardView` + durable record (depends on the kernel
   frame field).
6. Sample reconciliation (pages YAML, skill, README, WALKTHROUGH, demo.sh) —
   independent of stages 2-5; can proceed in parallel.
7. Tests + `make verify` + local redeploy + live re-check — depends on stages
   4-6.
8. Delivery bookkeeping (version bump, CHANGELOG, release note, config
   reference, flip the four SDD surfaces + ADR statuses) — depends on stage 7.

## Test Strategy

- unit tests:
  - new `tests/test_flow_approvals.py` — `FlowApprovalStore`
    record/get/has/clear + TTL expiry + `clear_all`; `FlowContextStore`
    record/get/clear, and a rebind (new `skill_id`/`origin`) overwrites the
    context (R-1/R-2).
  - `tests/test_execution_signing.py` — `build_flow_request` envelope shape,
    `verify_envelope` passes, `args_digest == canonical_digest(parameters)`,
    `confirm_id`/`decider` come from the flow authority (R-3).
  - `tests/test_kernel_middleware.py` — the invariant test
    `test_browser_write_tools_never_auto_allowed_even_if_forced` stays green
    (no flow approval → ASK); add: browser write + recorded approval +
    identity-matching `FlowContext` + armed `EXECUTION_REQUESTS` +
    `flow_signer` → ALLOW and an envelope injected; browser write + no approval
    → ASK; non-browser write (`k8s_*`) + approval → ASK; browser write +
    approval but `EXECUTION_REQUESTS` unset → ASK (fail-safe); browser write +
    approval whose identity does **not** match the current `FlowContext`
    (rebind) → ASK (R-1/R-3).
  - `tests/test_runtime_kernel.py` — a drained `web.navigate` result records
    `FlowContext`; approving a browser-write card records a flow approval
    carrying the card's `skill_id`/`origin`; approving a non-browser write does
    not; a subsequent browser write in the resumed stream is auto-signed
    (envelope in `EXECUTION_REQUESTS`, `execution_requested` audited) and does
    not park a second card; after a rebind to a different flow the next browser
    write re-parks instead of auto-signing (R-1/R-3).
  - `tests/test_runtime_kernel.py` (R-6) — a parked browser-write confirmation
    frame carries `flow_summary` (title/description/origin/risk_class) read
    from the maintained `FlowContext`, including when the flow was bound in an
    *earlier* turn (the case a park-time walk would miss); no bound flow → no
    `flow_summary` (tool-level fallback).
  - tool-gateway browser tests (R-6) — `FlowState.to_dict()` includes
    `title`/`description`; `bind_flow` populates them from the fetched skill;
    `web.navigate`'s `data["flow"]` carries them.
  - operator-portal `web-ui/app/src/**/__tests__` (R-6) — `decoder` maps
    `flow_summary` → `flowSummary`; `ConfirmationCardView` renders the headline
    (title/description/origin/risk) above the tool detail when present and
    falls back to tool-level rendering when absent.
- contract tests: none (no shared-contract schema change; the
  confirmation-frame `flow_summary` is an additive internal field and
  `data["flow"]` already exists on `web.navigate`).
- integration / overlay validation: `make verify` renders the `browser-dev`
  overlay (pages ConfigMap) green; the password-reset `demo.sh` chat leg
  exercises the sample end-to-end (R-4) and is the ADR-0008 exercised-sample
  step (R-5).

## Rollout And Migration

- deployment/configuration: `AGENT_BROWSER_FLOW_APPROVAL_TTL` documented in
  `docs/guides/configuration-reference.md` (default `900`; `0` disables). No
  GitOps secret or policy-bundle change; the sample pages ship as a ConfigMap
  regenerated by `make deploy`, and the sample skill re-ingests on a
  skills-hub rollout restart (`make deploy-samples`) — no image rebuild for
  sample-content changes.
- backward compatibility: the `stream_events` arming is provably inert for
  turns without a flow approval, so non-browser chat is unchanged; browser
  reads and non-browser writes are unaffected. R-6 is additive — `flow_summary`
  is a new optional frame field and the portal headline renders only when
  present, so a card with no bound flow (or an older kernel) renders exactly as
  today. `VERSION` bumps MINOR `0.32.0 → 0.33.0` (a new R5 slice) with
  lockstep constants.
- rollback: set `AGENT_BROWSER_FLOW_APPROVAL_TTL=0` to restore per-action
  gating without a redeploy of code; the sample pages/skill revert with the
  ConfigMap. No data migration to reverse.
