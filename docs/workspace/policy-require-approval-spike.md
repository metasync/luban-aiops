# Spike: `require_approval` Policy Semantics (next R4 slice, SPEC-030 candidate)

Status: spike complete — recommended shape below; promotion to SPEC-030 draft attached
Date: 2026-08-25
Roadmap home: delivery-roadmap "Bounded mutating actions" row — "Policy-center `require_approval` semantics remain the next R4 slice"
Verified against: policy engine and contracts at 0.11.1 (SPEC-004/019/020/021 as delivered)

## 1. Question

SPEC-021 shipped the first mutating tool triple-gated: gateway risk-tier
admission → read-only-by-construction auto-allow → SPEC-020 HITL
confirmation. But *who may confirm* a mutating run is today fixed by
bundle grants (`chat:confirm` + `tools:mutate` both include `operator`),
so the requesting operator can self-confirm their own destructive action.
The Tier-1 policy specification names the fix: `require_approval` as a
first-class decision outcome ("approval is a policy outcome, not a UI
feature"). What is the smallest decision-complete slice that makes
approval requirements data-driven policy, without building the full
policy-center approval-queue service?

## 2. Findings — verified current state

- **The contract already reserves the outcome.** `policy-rule.schema.json`
  documents `require_approval` and `allow_with_conditions` as reserved for
  a future schema revision; `policy-decision.schema.json` likewise reserves
  `approval_tier` and `conditions`. Both are titled "(v1)".
- **Two evaluation engines, deliberately non-parity.** platform-gateway
  and tool-gateway each own a `policy_engine.py` (action_authz slice,
  allow/deny only, deny-by-default, explicit-deny-wins, priority between
  allows); `test_module_parity.py` explicitly excludes them because they
  own different action vocabularies. platform-gateway evaluates API
  actions (`enforce_policy`), tool-gateway evaluates tool invocations
  (incl. `tools:mutate` on the delegated — i.e. confirmer's — identity).
- **The confirmation machinery is the enforcement substrate.** SPEC-020
  delivers park/resume, `POST /api/v1/chat/confirm` (action `chat:confirm`),
  `confirmation_decided` audit events, and portal confirmation cards.
  SPEC-020's spike memo already fixed the two-layer model: kernel HITL
  confirmation (session operator, inline) vs platform approval workflow
  (designated approver) — and reserved the audit `confirmation` dimension
  for exactly this reuse.
- **The transparency surface anticipates it.** `policy_matrix.py`
  (SPEC-019 R-2) renders the live role × action matrix from the bundle;
  the HITL spike memo's transparency-consistency point requires approval
  requirements to render there consistently with the audit trail.
- **`approver` is a real role with no approval-specific power today.**
  authorization-matrix.md defines `approver` ("approve-only" on mutating
  actions, "may approve within assigned environments"), but the deployed
  bundle grants it the same chat/actions surface as operators.

## 3. Options weighed

| Option | Shape | Cost | Verdict |
|---|---|---|---|
| A. Outcome semantics only | Extend rule/decision schemas + both engines with `require_approval`; enforcement = 403 "approval required" (blocking, no queue) | Small | Honest but operator-invisible: nothing can ever proceed; pure contract plumbing |
| B. Semantics + confirmation-bridge enforcement | A plus: when a mutating run's policy answer is `require_approval`, the SPEC-020 confirmation flow becomes approver-gated — only identities the policy authorizes to decide may answer, requester ≠ confirmer (no self-approval), decision rendered in the live matrix and enriched `confirmation_decided` audit | Medium | **Recommended** — reuses every delivered substrate; first data-driven approval requirement operators can actually experience |
| C. Full approval queue + policy-center service | Standalone service, queue persistence, tiers, two-person rules, change windows | Large | Deferred — this is the R5-shaped remainder; SPEC-030's enforcement contract must not block it |

## 4. Recommended shape (SPEC-030 candidate)

### 4.1 Contract revision (schema bump v1 → v2)

- `policy-rule.schema.json`: `decision.outcome` enum gains
  `require_approval`; `decision` gains an optional `approval` object
  (`decided_by_roles`: who may answer; `allow_self_approval`: bool,
  default false). `allow_with_conditions` stays reserved.
- `policy-decision.schema.json`: `decision` enum gains
  `require_approval`; `approval_tier` stays reserved for the queue
  service; matched-rule provenance already rides `matched_rule_ids`.
- Per ADR-0006 this is a deliberately grown control semantic, not a
  purpose change; the four bundle copies (shared-contracts, two packaged,
  two overlays via `make sync-policy`) move in lockstep.

### 4.2 Evaluation semantics (both engines, identical rules)

- Precedence: explicit `deny` > `require_approval` > `allow` (a mixed
  match is answered with the strongest requirement — the safe default).
- Between multiple `require_approval` matches: highest priority wins and
  its `approval` object rides the decision, mirroring the allow path.
- Bundles containing `require_approval` rules for actions with no
  enforcement bridge fail bundle validation at load time (no silent
  403-only semantics) — same loud-failure posture as `PolicyLoadError`.

### 4.3 Enforcement bridge (platform-gateway `chat:confirm` path)

- When the parked call's tool action (`tools:mutate` family) evaluates to
  `require_approval`, the confirm route checks the **confirmer** against
  the decision's `decided_by_roles`, and — unless the rule explicitly
  allows it — rejects self-approval (confirmer subject ≠ session owner
  subject) with a structured 403 naming the requirement.
- The tool-gateway keeps evaluating `tools:mutate` allow/deny against the
  delegated (confirmer's) token unchanged — the approval gate rides the
  answer path, so a confirmed call still passes admission exactly as
  today. `require_approval` in the tool-gateway bundle is out of scope
  for this slice (its invocation path has no pre-approval substrate).

### 4.4 Transparency and audit

- `policy_matrix.py` gains a third cell state `requires_approval` (the
  permissions view already renders matrix cells; additive column/value).
- `confirmation_decided` audit events gain the matched approval rule id
  and a `self_approval_blocked` outcome where applicable — reusing the
  confirmation dimension SPEC-020 reserved.
- The portal confirmation card shows an "approver required" badge and,
  for unauthorized viewers, a read-only card instead of approve/deny
  buttons.

### 4.5 Default bundle posture

- `policy-default.yaml` gains one `require_approval` rule on
  `tools:mutate` with `decided_by_roles: [approver, platform-admin]` and
  self-approval blocked — making the dev-k8s mutating demo require a
  distinct approver identity, which is exactly the governance story the
  authorization matrix already promises.

## 5. Open questions for the spec phase

1. **Observer visibility**: should a `read-only-observer` see parked
   approval-pending cards read-only (transparency) or nothing (session
   privacy)? Leaning read-only, mirroring SPEC-022 session visibility
   rules — decide against the existing session-scoping code.
2. **Expiry interaction**: parked calls already expire after
   `AGENT_HITL_CONFIRM_TIMEOUT`; confirm the approver-gated flow needs no
   separate approval TTL in this slice (answer: no — same registry).
3. **Synthetic identity path**: developer/synthetic identities hold roles
   by policy; decide whether a synthetic identity may ever be a confirmer
   (leaning: no — `decided_by_roles` excludes them via bundle authoring,
   documented not coded).
4. **Matrix API compatibility**: `GET /api/v1/policy/matrix` consumers
   (portal) must accept the new cell value; version the response field
   additively rather than bumping the endpoint.

## 6. Recommendation

Promote to **SPEC-030: Require-Approval Policy Semantics** as the next R4
slice (0.12.0 train). Scope: contract revision, evaluation semantics in
both engines, the `chat:confirm` enforcement bridge, matrix/audit/portal
transparency, and the default-bundle rule. Explicitly out of scope: the
policy-center service, approval queues, tiers beyond the reserved field,
two-person rules, change windows, and `allow_with_conditions` — those are
the R5 remainder and the enforcement contract above must stay compatible
with them.
