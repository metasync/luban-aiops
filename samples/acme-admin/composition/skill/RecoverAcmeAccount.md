---
title: Recover a Locked-Out ACME Admin Account
description: >
  Recover an acme-admin account a user is locked out of by running two existing
  single-target skills in declared order: reset the password through the
  console's browser UI, then clear the lock over its JSON API. A composition
  carries no authority of its own - it declares no web_target and no steps,
  mints no token and unlocks nothing - and each referenced sub-skill keeps its
  own confirmation card and its own approver. On a sub-skill failure, report
  which sub-skill failed and stop.
tags: [acme-admin, composition, runbook, account-recovery, password-reset, unlock, user-management]
version: "1.0"
kind: composition
sub_skills:
  - skill_id: samples/password-reset-resetacmepassword
    note: "Reset the account's password through the console UI. A bound browser flow; parks one flow card the approver decides."
  - skill_id: samples/lock-unlock-user-lockunlockuser
    note: "Clear the lock over the JSON API (unlock direction). Parks one action card. Run after the reset so the user can sign in with the new password."
---

## Purpose

Bring one locked-out acme-admin account back: issue it a new password, then
clear the lock, so the user can sign in again. Neither half is new — this
runbook **composes two skills that already exist and already ship in this
suite**, and adds nothing of its own except their order:

1. [`ResetAcmePassword`](../../password-reset/skill/ResetAcmePassword.md)
   (`samples/password-reset-resetacmepassword`) resets the password through the
   console's browser UI. It binds a flow and parks **one `flow` card**.
2. [`LockUnlockUser`](../../lock-unlock-user/skill/LockUnlockUser.md)
   (`samples/lock-unlock-user-lockunlockuser`) clears the lock with one
   `http.post` in the unlock direction. It parks **one `action` card**.

Common requests this runbook handles:

- "Carol locked herself out of acme-admin and forgot her password — get her back in"
- "Reset dave's password and unlock his account"
- "An account is locked and needs a new temporary password before it can be used"

This is the suite's worked example of a **composition** (SPEC-057): the thing a
reader has seen twice as two separate one-card skills, now named as one ordered
runbook — and the place to learn what a composition does *not* do.

## What a composition is — and what it is not

A composition is an **ordered reference list**, delivered to the agent as
grounded guidance. It is not a program, not a transaction, and above all not a
grant of authority:

- **It carries no authority of its own (ADR-0011).** It mints no token, unlocks
  no flow, and auto-approves no gate. Each sub-skill keeps its **own** HITL
  gate, enforced exactly as it is when the sub-skill runs alone: the browser
  flow's identity guard and the infra write's action card. Running the runbook
  therefore parks **two** cards — one per mutating sub-skill — never one card
  that "covers" the other.
- **It declares no `web_target` and no `steps`.** There is nothing for the
  platform to bind or replay. The two sub-skills declare their own targets; the
  composition only names them, in order.
- **Its `risk_class` is derived, not authored.** This document declares no
  `risk_class`. skills-hub derives one for display — `write` here, because a
  resolved sub-skill (`password-reset`) is `write` — and that badge is read by
  the catalogue UI and by nothing in the deviation guard, the identity guard or
  the policy engine. A composition can never talk its way into a scope its
  sub-skills do not already have.
- **There is no control flow.** A `sub_skills` item is `{ skill_id, note }` and
  nothing else: no `if`, no `loop`, no `retry`, no `on_fail`. The `note` is a
  sentence for the human and the model to read; it is never interpreted. The
  order in the list is the declared sequence, and the platform enforces nothing
  about it — the model may run the two in either order, skip one, or stop, and
  the gates are what make each choice safe.
- **It is not a transaction.** There is no rollback and no compensation. If the
  second sub-skill fails, the first sub-skill's change **stays made**. Report it
  and stop (below).

## Preconditions

Everything **both** sub-skills need — a composition adds no precondition and
relaxes none:

- The `acme-admin` app deployed (`make deploy-sample-app`), and this runbook plus
  both sub-skills packed into the skills-hub `samples` source
  (`make deploy-samples`). All three live in one source, so they resolve within
  a single sync cycle.
- The browser surface on (`GATEWAY_BROWSER_ENABLED`, origin allowlisted) for the
  reset, and the HTTP + mutating surfaces on (`GATEWAY_HTTP_ENABLED`,
  `GATEWAY_MUTATING_TOOLS_ENABLED`, origin allowlisted) for the unlock.
- The `acme-admin` credential set configured on the tool-gateway. Never paste
  the admin password, and never paste the new temporary password, into anything
  but the chat message the operator sends.
- `AGENT_HITL_CONFIRM_TIMEOUT` greater than `0` on agent-platform, or write-tier
  tools are excluded from the toolkit and neither card can appear.
- A `tools:mutate` grant for the caller's role and, under the default bundle, a
  **designated approver distinct from the operator**. Two mutating sub-skills
  means two approvals, and the same rule binds each: the requester cannot decide
  their own call.
- The caller names the **target user** and the **direction** for the second
  step (here, unlock). Ask if either is missing. A supplied temporary password
  stays supported. If no password is supplied, follow the reset sub-skill's
  `secrets.generate_password(policy="default", handoff="portal_copy")` branch;
  its strength policy is `shared/shared-contracts/policies/password-policy.yaml`.
  Generation is read tier and adds no approval. It does not authorize either
  mutation. Never invent or restate the generated value; the requester uses
  the one-time **Copy password** control.

## Procedure

Two sub-skills, in the declared order, each gated on its own. The order is a
recommendation to the model, not a platform-enforced sequence: reset first so
the account has a usable password, then unlock so the user can sign in with it.

1. **Reset the password** by following
   `samples/password-reset-resetacmepassword` against the target user. This
   binds the browser flow and parks **one `flow` card** on the "Confirm reset"
   click. A designated approver decides it; on approval the reset executes and
   the sub-skill verifies the new `password_changed_at` and bumped `revision`
   from the JSON API. Wait for that verification before continuing.

2. **Clear the lock** by following `samples/lock-unlock-user-lockunlockuser` in
   the **unlock** direction against the same user. This parks **one `action`
   card** on the single `http.post`. A designated approver decides it; on
   approval the unlock executes and the response reports `locked: false` and a
   further bumped `revision`.

3. **Report the outcome of both.** The account now has a new password and is
   active. Quote each sub-skill's own evidence — the reset's
   `password_changed_at` and the unlock's `revision` — rather than a single
   blended "done", so the operator can see which step produced which fact.

**On failure, report which sub-skill failed and stop.** A composition is not a
transaction: there is no rollback and no compensation. If step 1 is denied or
errors, do not attempt step 2 — the account still has its old password and its
lock, and half-recovering it is worse than not starting. If step 1 succeeds and
step 2 is denied or errors, **the password is already changed** and the account
is still locked; say exactly that, name the sub-skill that stopped, and do not
retry around the denial, re-phrase it, or reach for the other surface as a
workaround. A denial is an answer.

**Re-entry.** The completed prefix is recoverable from the platform's signed
execution receipts, which are swept at **30 days** (`execution_records.py:31`).
Inside that window an operator resuming the runbook can see that step 1 already
ran; outside it, restart from the beginning. Either way each sub-skill re-gates
on re-entry — a receipt is a record, not a standing approval.

## Interpretation

Read each sub-skill's own Interpretation section for its refusals; nothing about
composing them changes what a `409`, a `404` or a denial means. Two facts are
specific to the runbook:

- **Two cards is the correct count, not a stuck flow.** If the operator sees one
  card for the reset and, after approving it, a second for the unlock, that is
  the runbook working: each mutating sub-skill gates on its own. A single card
  that claims to authorise both would be the bug — and the platform has no
  mechanism to produce one, because the composition carries no authority.
- **A `409 NO_OP_MUTATION` on step 2** means the account was already active.
  Nothing changed and the revision did not move; report "already unlocked" and
  treat the runbook as complete for that step. It is an answer, not a failure,
  and it is not a reason to re-run step 1.
- **A cross-source sub-skill resolves eventually.** Both sub-skills here ship in
  the same `samples` source, so they resolve in one cycle. A composition whose
  sub-skill lives in a *different* source is rejected on the sync cycle before
  that source has synced, and accepted on a later one — eventual consistency,
  documented rather than papered over. This runbook deliberately does not depend
  on it.

## Tutorial notes (skill authoring guidance)

**Why compose these two, in this order?**
Because they are the two mutating skills the suite already ships, they address
one store over two surfaces, and "reset then unlock" is a recovery a real
operator actually performs. The order is a suggestion the model may follow or
depart from; what makes departing safe is that each step still gates. A
composition that ordered two steps where the second depended on the first having
been *approved* would be leaning on the platform to enforce sequence — and the
platform deliberately does not.

**Why is the mixed browser + infra pair the interesting demo?**
`password-reset` binds a browser flow and parks a `flow` card; `lock-unlock-user`
makes one `http.post` and parks an `action` card. Composing them yields **two
cards of two kinds** in one runbook, which is more than either sub-skill parks
alone (one each) — the clearest live demonstration that a composition's gate
count is the **sum** of its sub-skills' gates, and that no card claims authority
over a sub-skill it does not name.

**Why no `web_target`, no `steps`, no `risk_class` here?**
Declaring a `web_target` would imply the composition binds a browser flow of its
own; declaring `steps` would imply a platform interpreter replays it; declaring a
`risk_class` would imply an author knows the composite's blast radius better than
the union of its parts. skills-hub rejects all three on a `kind: composition`
document, so the runbook cannot claim a scope it does not have. The derived
`write` badge is display-only.

**Why is verification still each sub-skill's job?**
So the runbook never becomes the place a reader has to trust. Step 1 reports the
reset from the JSON API, step 2 reports the unlock's revision, and the two agree
against one store. A composition that verified on their behalf would hide which
half produced the evidence — the same reason `LockUnlockUser` and
`CheckUserStatus` are separate skills to begin with.
