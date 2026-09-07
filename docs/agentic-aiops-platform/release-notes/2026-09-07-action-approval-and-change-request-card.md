# Action-Level Approval and the Change-Request Card (v0.35.0)

Date: 2026-09-07

A release train delivering SPEC-054, the sixteenth R5 slice and the **B**
phase of the operator-approved A→B→C HITL redesign (A = the v0.34.1
SPEC-051 R-6 headline-leak patch, landed; B = this spec; C = ADR-0009 +
SPEC-055 skill graduation, gated on B reaching `delivered`). It makes
**action** approval first-class beside **flow** approval, relaxes the
gateway so an ad-hoc browser write on an allowlisted origin parks as a
per-action signed gate instead of being hard-denied, and turns every action
card into a readable, secret-masked **change request**. Backend, contracts,
portal, guides, and one new sample touched; no new policy actions, no new
audit event types.

## SPEC-054: Action-level approval and the change-request card

### R-1 — an explicit `approval_kind` discriminator

- The confirmation contract carried two approval subjects but only one was
  first-class: a **flow** approval (a `write`-class browser web-check flow
  bound at `web.navigate(skill_id=…)`) collapsed to one gate and rendered a
  flow-semantic headline (SPEC-051 R-6), while an **action** approval (an
  ad-hoc mutating call) rendered only a bare tool name. The card's kind was
  inferred from ambient session state, which is exactly what leaked a
  lingering flow headline onto a later non-browser card in v0.34.0.
- An explicit `approval_kind: flow | action` discriminator now rides the
  `confirmation_request` frame **and** the durable record, computed on one
  kernel branch (`"flow" if browser_flow else "action"`) with `flow_summary`
  present iff the kind is `flow`. A card's kind and its headline come from the
  same branch, so they can never disagree — the structural fix behind the
  v0.34.1 patch, which gated the headline on a write-tier predicate.
- The stream contract advances **v9 → v11**, retro-fitting the v10 clause
  SPEC-053 shipped but never recorded (`schemas/v2.py` already declared v10)
  and declaring the latent `display_hint` on `pending_calls.items` that
  SPEC-050 emits and the portal reads but no `additionalProperties: false`
  schema had accepted.

### R-2 — unbound browser writes park per-action, kept fail-closed

- Five of the six write-tier browser tools previously hard-denied
  `BROWSER_FLOW_NOT_BOUND` when no flow was bound, so an ad-hoc browser
  interaction on an allowlisted origin could not be approved at all. The deny
  is relaxed: an unbound allowlisted browser write now **parks a per-action
  signed gate**. N unbound writes park N cards — there is no flow-unlock on
  the unbound path, so approving one never unlocks the next.
- The review behind this spec found `BROWSER_FLOW_NOT_BOUND` was load-bearing
  as the platform's *only* staleness backstop, so the relaxation ships
  **together with** the two replacements that keep it fail-closed:
  - the kernel clears `FLOW_CONTEXTS`/`FLOW_APPROVALS` wherever the gateway
    clears its own binding, so a flow-killing result leaves no stale
    auto-signing authority; and
  - every signed envelope declares its **authority provenance** under
    **ADR-0010** — an `approval_kind` stamped inside the HMAC by whichever
    builder signs. The execution-runtime worker (which is what actually
    verifies the envelope) forwards the value it has already authenticated as
    untrusted-as-identity correlation data, mirroring the SPEC-049 `session_id`
    precedent, and the gateway enforces it **one-directionally** with a new
    `BROWSER_FLOW_AUTHORITY_STALE` refusal — a declared kind can only ever add
    a refusal, never remove one, and the guard set applied is still selected
    by the gateway's own flow binding.
- Read-tier `web.fill_credential` joins the relaxation. It is a ref-addressed
  interaction tool that inherited the same flow-binding precondition, so
  relaxing writes alone would have left the motivating login-then-mutate
  scenario broken and pushed credential entry toward `web.type` with a literal
  secret in the arguments, the card, the durable record, the audit trail, and
  `args_digest`. Unbound credential entry is now **reference-only**. The
  unbound path gets a `gate_capture`-style live-origin re-check (halt on
  drift); no step budget bounds it — per-action consent is the bound, and
  SPEC-055 budgets the accumulated sequence at graduation.

### R-3 — the secret-masked change-request projection

- Every action card becomes a **change request**: a display-only
  `{summary, fields[]}` projection (each field `{label, value, masked?}`)
  assembled from a curated per-tool map plus a generic fallback, with a
  per-tool opaque-value rule for what name-based masking cannot catch.
- The projection is assembled as a **sibling** of `parameters`, never inside
  it, so `canonical_digest(parameters)` and the signed `args_digest` stay
  byte-identical — the change request is display-only and never a security
  input. Secret values are masked to `***` before they reach the card.

### R-4 — durable card-message parity

- The card's top-line `message` rendered on the live operator stream but
  vanished on any durable render (the approver/admin inbox and the owner's
  transcript on re-login) because it was frame-only. It is now computed once
  at park time and persisted on the durable record, mirroring the
  `flow_summary` path, so a re-login and the inbox render exactly the card the
  live stream showed.

### R-5 — operator-portal decode and render

- The portal decodes all three fields data-drivenly (`decoder.ts` coerces
  `approval_kind` — only `"flow"`/`"action"` survive — and `change_request` —
  a `summary`-bearing object only — mirroring the kernel/`routes.py`
  coercion), and `confirmationRecordToCard` replays them from the durable
  record. `ChatView.tsx` renders the flow headline for `flow`, the
  change-request layout (`summary` lead line + optional `fields` table, masked
  values pre-masked, every value escaped JSX text) for `action`, and today's
  tool-level rendering when both are absent, so a malformed or pre-v11 payload
  degrades gracefully rather than to an empty node. The "Technical details"
  expander stays.

## The unbound per-action sample

- A new `samples/web-checks/adhoc-password-reset/` tutorial drives the same
  admin password reset as `web-checks/password-reset` but **ad-hoc, with no
  bound flow**, so each mutating browser action parks its own per-action
  change-request card. The runbook deliberately declares **no `web_target`**,
  so a flow cannot bind (`SKILL_NOT_WEB_FLOW`) and the unbound path is
  platform-enforced regardless of model behavior — the crisp unbound
  counterpart to the bound-flow one-gate sample. Login uses reference-only
  `web.fill_credential`; the sole write is the "Confirm reset" click. Its
  `demo.sh` exercises the path per ADR-0008 (deterministic legs plus an opt-in
  chat leg asserting every parked card is `action`-kind with a change request
  and every execution signed).

## Secret-vocabulary lockstep gate

- A new `validate_secret_vocabulary.py` leg joins `make verify`, textually
  comparing the agent-platform and tool-gateway secret-parameter tuples (the
  `validate_version.py` pattern — regex-from-source, never import-based, so it
  honors the no-cross-product-import invariant and fails *closed*). It reports
  drift in both directions and treats a missing file or unfindable tuple as a
  hard failure, so the two masking vocabularies R-3's projection relies on
  cannot silently diverge.

## Untouched / guarantees

No new policy actions and no new audit event types. The change-request
projection and `flow_intent` are display-only — the HITL gate, the deviation
guard, and the SPEC-037 signed execution path never read them, and
`args_digest` is unchanged. Browser write tools still never join any
auto-allow list. The authority-provenance check is one-directional and
fail-closed: forwarded provenance is untrusted input with no authority. ADR-0007
is extended, not reversed; ADR-0010 is accepted.

## Verification

Version lockstep 0.35.0 validated across all products and the portal.
`make verify` green (all product pytest, kustomize overlays, policy rules and
scenarios, version lockstep, and the new `validate-secret-vocabulary` leg);
agent-platform 854, tool-gateway 330, portal 303 all green; `npm run build`
clean. The clean 0.35.0 image also carries the deferred v0.34.1 headline-leak
gate (dev-k8s previously ran a dirty 0.34.0 tag).
