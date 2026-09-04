# SPEC-051: Browser Flow HITL Gate Enforcement and Password-Reset Sample Reconciliation (v0.33.0)

**Date:** 2026-09-04
**Slice:** R5 — Hardening and External Consumption (thirteenth R5 slice)
**Spec:** `docs/specs/SPEC-051-browser-flow-hitl-gate-enforcement/`
**ADRs:** ADR-0007 (one HITL gate per mutating browser flow, platform-side),
ADR-0008 (spec delivery requires requirement-to-test traceability and
exercised samples)

## What shipped

SPEC-049 R-4 specified that a `write`-class browser flow parks exactly one
confirmation card and that "approval unlocks the bound flow's interactions
for that session." Only the tool-gateway half shipped — flow binding, origin
allowlist, declared `risk_class`, and the step-budget deviation guard. The
agent-platform kernel never collapsed the per-write ASKs, so every write-tier
browser interaction parked its own card. A live password-reset test on the
deployed v0.32.0 exposed the gap: the operator was asked to approve the same
mutating flow six times. SPEC-051 completes R-4 platform-side and reconciles
the sample that surfaced it:

1. **Platform-enforced flow-unlock (R-1).** The first write-tier browser
   interaction in a `write`-class flow parks exactly one confirmation card
   through the existing SPEC-020 bridge. On approval the kernel records a
   session-scoped flow authority in a new `services/flow_approvals.py`
   (`FlowApproval`/`FLOW_APPROVALS`), and the permission middleware admits
   every subsequent write-tier `web.*` interaction in that flow without a
   further card via an optional `flow_signer` callback. Browser write tools
   never join any auto-allow list — the
   `test_browser_write_tools_never_auto_allowed_even_if_forced` invariant
   stays green — and non-browser mutating tools (`k8s.*`) are unaffected,
   continuing to gate per SPEC-021/030/037.

2. **Identity-scoped, time-bounded authority (R-1/R-2).** The authority is
   keyed on the chat session **and** the approved flow's identity
   (`skill_id` + `origin`). The kernel maintains that identity as a
   session-scoped `FlowContext` (`FLOW_CONTEXTS`) updated from each drained
   `web.navigate` result — the gateway-owned flow binding it reflects. If the
   session rebinds to a *different* `write`-class flow, `_sign_flow_execution`'s
   identity guard returns `None` and the next write re-parks a fresh card, so
   the ADR-0007 cross-flow-rebind auto-sign window is **eliminated**, not
   merely bounded. A new knob `AGENT_BROWSER_FLOW_APPROVAL_TTL` (default
   `900`s, `>= 0`) bounds how long the approval unlocks writes; `0` disables
   flow-unlock entirely, restoring the pre-SPEC-051 posture.

3. **Unlocked writes stay signed, audited, receipted, gateway-guarded (R-3).**
   Every write admitted under a flow authority carries the same
   execution-safety guarantees as an approved-card execution:
   `build_flow_request` in `services/execution_signing.py` signs a fresh
   envelope (new `execution_id`, the call's own `args_digest`, reusing the
   card's `confirm_id`/`decider_user_id` and the platform signing key) that
   rides the existing SPEC-037/038 handoff, is persisted
   (`execution_requested`) and audited, and produces a receipt on completion.
   The tool-gateway deviation guard (origin allowlist, declared `risk_class`,
   step budget `GATEWAY_BROWSER_FLOW_MAX_STEPS`) still bounds every unlocked
   write, with the session id forwarded on the write path.

4. **Flow-semantic confirmation card (R-6).** Realizes the second half of
   SPEC-049 R-4 ("the card names the skill, target origin, and declared
   steps"), also never implemented. The single card now headlines the
   **workflow** the operator is approving — the bound skill's declared
   `title`, `description`, target `origin`, and `risk_class` (e.g. "Reset
   User Password in Admin Portal") — instead of a bare tool action like
   `web.click` on `<button> "Sign in"`. The triggering tool action is
   retained as secondary detail. The headline is assembled from frontmatter
   that already rides `web.navigate`'s `data["flow"]`: tool-gateway
   `FlowState` gains `title`/`description` (populated at `bind_flow` from the
   fetched skill, exposed in `to_dict()`), the kernel renders the card from
   the same maintained `FlowContext` R-1 keys on and carries a `flow_summary`
   on the confirmation-request frame, and the portal decodes it onto the card
   above the tool detail. When no flow is bound the card falls back to
   today's tool-level rendering — no regression. Structured per-step plan
   rendering (R-4's literal "declared steps") is deferred to a follow-up spec:
   skills declare no machine-readable step list today, so it needs a
   skill-format change with a larger blast radius than this gate fix warrants.

5. **Durable, replayed headline (R-6).** Approvals-inbox and session-detail
   cards render the same headline as the live card via a new nullable
   `flow_summary` JSONB column on `confirmation_records`, added by an
   additive ALTER-TABLE migration in `initialize()` and written with
   `psycopg.types.json.Jsonb` adaptation (a bare dict cannot be adapted to
   JSONB — a live-Postgres smoke test is mandatory because unit tests over
   fake drivers cannot catch it).

6. **Password-reset sample reconciled (R-4).** The sample was internally
   inconsistent: the skill/README/WALKTHROUGH named the admin sign-in click
   as the single write, while the target pages auto-submitted both the login
   and the reset, and the pages' own comment said the gate belongs on
   "Confirm reset." The reset form now pre-fills from the URL and does
   **not** auto-submit, so the sole write-tier interaction — and the single
   HITL gate — lands on the destructive "Confirm reset" click; login stays
   read-tier auto-submit. The skill (`ResetUserPassword.md`, v1.1 → v1.2),
   README, WALKTHROUGH, and `demo.sh` all agree, and the demo's second-card
   tolerance is removed in favor of a one-card assertion.

## Validation

- `make verify` green at 0.33.0: every product suite — including the new
  agent-platform `test_flow_approvals.py` (store record/get/has/clear, TTL
  expiry, `clear_all`, identity keying), the extended `test_execution_signing.py`
  (`build_flow_request` envelope/verify/digest/authority),
  `test_kernel_middleware.py` (flow-unlock ALLOW/ASK matrix + the never-auto-allowed
  invariant), `test_runtime_kernel.py` (`_record_flow_approval` +
  `_sign_flow_execution` auto-sign/fail-safe/rebind), `test_confirmation_records.py`
  (durable `flow_summary` round-trip), the tool-gateway `FlowState`
  serialization + navigate-headline tests, and the portal decoder/transcript/
  useChatStream `flowSummary` tests — plus all four overlays, policy
  validation, the scenario guard, and version lockstep. (The
  execution-runtime cross-verification harness, which loads agent-platform's
  `execution_signing.py` in isolation, was extended to stub the new
  `agent_service.services.flow_approvals` annotation import.)
- Live on the canonical `dev-k8s` deployment: `make build` + `make deploy` +
  `make deploy-samples SAMPLE=web-checks/password-reset` rolled the new tag
  out, re-ingested the v1.2 skill, and served the reconciled pages.
- `RUN_CHAT_LEG=true demo.sh` proved the invariant end-to-end: a scripted
  password reset parked **exactly one** card and every write-tier browser
  interaction in the flow (the model mixed `web.click` with `web.evaluate`)
  was auto-signed under it with a valid receipt. A live-Postgres smoke
  confirmed the durable `flow_summary` persists as real JSONB
  (`jsonb_typeof(flow_summary) = object`, title "Reset User Password in Admin
  Portal").
- The live portal re-check of the original reset-password scenario showed a
  single approval gate headlined **"Reset User Password in Admin Portal"**
  with the target origin and "write flow" tags and the tool actions retained
  as secondary detail — directly resolving the operator-facing confusion that
  motivated R-6.

## Parked

SPEC-051 adds no durable or cross-process flow-approval/flow-context store
(both are per-process, session-scoped; a restart drops them, re-parks the
next write, and re-renders the card tool-level — all fail safe), no structured
per-step plan rendering on the card (deferred to a follow-up spec that would
change the skill format), and no change to tool-gateway step-budget exhaustion
behavior (an over-budget unlocked write is denied by the gateway rather than
re-parked — a minor, fail-closed deviation from R-4's "escalates to ASK"
letter, documented in ADR-0007). SPEC-049 stays delivered/frozen; SPEC-051
completes its R-4 by reference. No retroactive re-validation of other
delivered specs against ADR-0008 (a follow-up sweep is advisable but out of
scope).
