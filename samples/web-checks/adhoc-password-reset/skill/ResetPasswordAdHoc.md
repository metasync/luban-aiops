---
title: Reset a Password Ad Hoc (Per-Action Approval)
description: >
  Drive the admin portal password reset ad hoc — without declaring a
  browser flow — so every mutating browser action parks its own
  per-action change-request card. Use this when you are exploring or
  troubleshooting an interactive web app before you have authored a
  reusable flow skill, or when you want each write approved on its own
  merits rather than unlocking a whole flow with one gate. Contrast with
  web-checks/password-reset, which binds a flow and collapses to a single
  HITL gate.
tags: [admin, portal, password, reset, ad-hoc, per-action, approval, browser, web-check, troubleshooting]
version: "1.0"
# NOTE (SPEC-054): this runbook deliberately declares NO web_target and NO
# risk_class. A skill without web_target cannot bind a browser flow — the
# gateway rejects web.navigate(skill_id=…) for it with SKILL_NOT_WEB_FLOW —
# so every write-tier web.* interaction below stays UNBOUND and parks its own
# per-action confirmation card (approval_kind: "action") instead of riding one
# flow gate. That is the whole point of this sample. To graduate this ad-hoc
# procedure into a one-gate reusable flow, add web_target + risk_class: write
# (+ flow_intent) — see samples/web-checks/password-reset/skill.
---

## Purpose

This is the **ad-hoc / per-action** counterpart to the
`web-checks/password-reset` sample. Both reset a user's password in the
same legacy admin portal, but they demonstrate the two HITL approval
models the platform supports (SPEC-054):

| | `password-reset` | **this sample (`adhoc-password-reset`)** |
|---|---|---|
| Skill declares `web_target` | yes | **no** |
| `web.navigate(skill_id=…)` binds a flow | yes | **no (cannot — `SKILL_NOT_WEB_FLOW`)** |
| Approval model | one gate per **flow** (SPEC-051) | one card per **write** (SPEC-054 R-2) |
| Card `approval_kind` | `flow` | **`action`** |
| Card lead | flow headline + `flow_intent` | **change-request projection** (R-3) |

Use the ad-hoc model when you are **exploring or troubleshooting** an
interactive web app and do not (yet) have a flow skill — the
"develop-as-you-go" phase. Each mutating step is approved on its own
merits, with a secret-masked change request describing exactly what that
one action will change. When the procedure stabilizes, graduate it into a
`web_target`-declaring flow skill for one-gate replay (that graduation
pipeline is SPEC-055).

Common requests this runbook handles:
- "Ad-hoc reset alice@example.com's password in the admin portal, gating each step"
- "Log into the admin portal and reset a password without using a flow skill"
- "Troubleshoot the admin reset UI interactively, approving each write as I go"

## Staying Unbound Is the Platform's Design, Not a Red Flag

Read this before deciding the procedure looks unsafe. Each objection to it is
answered by where the authority actually sits:

- **"A skill's steps are only authoritative when the flow is bound."** Flow
  binding is a *gateway-side authorization mechanism*, not the source of this
  runbook's authority — this document is team-authored guidance published to
  skills-hub, and its steps carry the same weight as any other runbook's.
  Binding changes **how many gates** the writes ride (one per flow versus one
  per action), not **whether** they are gated.
- **"An instruction to stay unbound looks like privilege escalation."** It is
  the more heavily gated of the two paths. A bound flow unlocks every
  subsequent write in that flow under a single approval; an unbound session
  parks a card for **each** write, each decided on its own merits. Nothing here
  widens what you may do — SPEC-054 R-2 *relaxed a hard denial*
  (`BROWSER_FLOW_NOT_BOUND`) into a gate, and the gateway still enforces the
  origin allowlist, a live-origin re-check on every unbound write, and the
  `BROWSER_FLOW_AUTHORITY_STALE` provenance backstop.
- **"Passing the new password as `?newpw=` is a credential-handling
  anti-pattern."** It is this legacy portal's actual interface: the reset form
  pre-fills itself from the query string, which is why the sample target is
  built that way. Every secret-bearing query parameter is masked in every
  result, snapshot, evidence frame, and audit record — by the gateway in what it
  reports, and by the kernel in the tool-call arguments it streams and persists,
  which no gateway-side redactor ever sees (SPEC-049 R-5) — and the admin
  password never appears at all: it is filled
  **by reference** from the `admin-portal` credential set.

Refusing pre-emptively does not make this safer. It removes the operator's
decision — the control that actually protects the system — and replaces it with
nothing: no card is parked, no approver reads the change request, and no signed
receipt is recorded. Attempt the write and let the platform gate it. Refuse only
what is genuinely yours to refuse: an instruction that contradicts these steps,
an origin off the allowlist, or a request to invent evidence.

## Preconditions

- The `admin-portal` credential set is configured on the tool-gateway
  (`GATEWAY_BROWSER_CREDENTIAL_SETS`). The admin password is
  platform-managed; never paste credentials into the chat.
- The target origin is on the gateway allowlist
  (`GATEWAY_BROWSER_ALLOW_ORIGINS`). An unbound write is admitted **only**
  on an allowlisted origin — the allowlist stays deny-by-default.
- The caller supplies the **target user** (email) and the **new temporary
  password** in the chat message. The new password is a chat-supplied
  value — never stored in this runbook, never committed.

## Procedure

**Do not bind a flow.** Call `web.navigate` with only the `url` — never
pass `skill_id`. This runbook declares no `web_target`, so there is no
flow to bind; passing `skill_id` fails with `SKILL_NOT_WEB_FLOW`. Because
no flow is bound, every write-tier interaction parks its own per-action
card. Read-tier steps (navigate, snapshot, credential fill) run ungated.

1. **Open the login page (unbound).** `web.navigate` to
   `http://browser-check-target:8080/admin/` with **no `skill_id`**. No
   flow binds; the session stays unbound for the whole procedure.

2. **Inspect the login form.** `web.snapshot` and verify the admin login
   form is present with empty username and password fields.

3. **Fill admin credentials by reference.** `web.fill_credential` (read
   tier) from set `admin-portal`: field `username` into the username
   element, then field `password` into the password element. This is the
   SPEC-054 R-2 relaxation that makes the ad-hoc login reachable at all —
   unbound `web.fill_credential` is admitted **by reference only**
   (`credential_set` + `field`), so the secret never enters the tool
   arguments, the parked payload, the card, or the audit trail. Never use
   `web.type` for a credential value.

4. **Let the login auto-submit.** The admin page auto-submits once both
   fields are filled (legacy SSO) and redirects to the user list. **Do not
   click "Sign in"** — authentication is read-tier and needs no write.
   `web.snapshot` after the redirect settles to confirm you are on the
   user list.

5. **Locate the target user.** In the user-list snapshot, find the target
   user in the table (columns: Name, Email, Role, Action). If the target
   user is not present, report it and stop.

6. **Open the reset form with the new password pre-filled.** `web.navigate`
   (still **no `skill_id`**) to
   `/admin/users/reset/?user=<target-email>&newpw=<new-password>` on the
   same origin. The panel pre-fills both password fields from the URL but
   does **not** submit. The `newpw` parameter is redacted from results,
   evidence, and audit — gateway-side in the result it returns and
   kernel-side in the tool-call arguments it records (SPEC-049 R-5) — and
   using the URL pre-fill
   keeps the secret out of any `web.type` argument.

7. **Confirm the reset — the per-action gate.** `web.click` the "Confirm
   reset" button. This is a **write-tier interaction with no bound flow**,
   so it parks a **per-action** confirmation card (`approval_kind:
   "action"`) carrying a **change-request projection** (R-3): a plain
   summary of the click plus the decision-relevant fields, secret-masked.
   The approver sees exactly what this one action changes and approves or
   denies it on its own merits. There is no flow-unlock: had this procedure
   performed N writes, it would park N cards.

8. **Verify and capture evidence.** `web.extract` `#reset-status` to read the
   target app's own "Password for <user> has been reset successfully." line.
   `web.snapshot` **cannot** show it: a snapshot enumerates interactive
   elements only (`a, button, input, select, textarea` and a few ARIA roles),
   and the status line is a plain `<p role="status">`, so a post-click snapshot
   legitimately contains no success text. If you follow the "View confirmation"
   link, extract `#confirmation-message` there for the same sentence. Then
   `web.screenshot` as final visual evidence — include it in your response to
   the caller.

## Interpretation

- `SKILL_NOT_WEB_FLOW` on `web.navigate` means you passed `skill_id` for
  this runbook. Retry the navigation **without** `skill_id` — this
  procedure is intentionally unbound.
- `BROWSER_ORIGIN_NOT_ALLOWED` means the origin is not on the allowlist;
  stop and report — an unbound write is never admitted off-allowlist.
- `BROWSER_FLOW_AUTHORITY_STALE` should not occur here (nothing binds a
  flow); if it does, a prior turn left a stale flow-provenance envelope —
  restart the procedure cleanly.
- An extract of `#reset-status` after step 7 reading "Error: passwords do not
  match" means the new password was not transmitted correctly; report it and
  ask the caller to retry. (`web.snapshot` cannot show that line either — same
  reason as step 8.)
- Each write-tier card is independent: approving one does **not** unlock the
  next. If you add more writes, expect one card per write.

## Tutorial notes (ad-hoc / per-action authoring guidance)

**Why does this runbook declare no `web_target`?**
`web_target` is what makes `web.navigate(skill_id=…)` bind a flow, and a
bound `write`-class flow collapses to one HITL gate (SPEC-051). This sample
wants the *opposite*: the unbound, per-action model SPEC-054 R-2 makes
reachable. Omitting `web_target` guarantees it — the gateway cannot bind a
flow that was never declared, so the platform enforces the per-action path
regardless of how the model sequences the steps.

**Why is credential entry "by reference"?**
Unbound login was previously blocked at the read tier: `web.fill_credential`
inherited the flow-binding precondition and was denied
(`BROWSER_FLOW_NOT_BOUND`), so the only way to enter a credential unbound was
`web.type` with the literal secret as an argument — which then landed in the
parked payload, the card, and the audit trail. SPEC-054 R-2 relaxes the
precondition for read-tier ref-addressed interactions, so `web.fill_credential`
(`credential_set` + `field`) works unbound and the secret never appears
anywhere. This is what makes "log in, then mutate" reachable ad hoc.

**What does the approver see on a per-action card?**
Not a bare tool name. The card leads with a **change request** (R-3): a
plain-language `summary` of the mutation plus the decision-relevant fields
promoted out of the collapsed "Technical details" expander, with secret values
masked to `***` by the same vocabulary the gateway redacts with. The projection
is display-only — it rides beside `parameters`, never inside it, so the signed
`args_digest` is byte-identical with or without it.

**How is this different from `password-reset`?**
Same task, same target, same single destructive mutation — but
`password-reset` binds a flow and renders a `flow`-kind card with the skill's
`flow_intent` headline under one gate, while this runbook stays unbound and
renders an `action`-kind card with a change request per write. Run both demos
to see the two approval models side by side.

**When do I graduate this to a flow?**
Once the ad-hoc procedure is stable and you want one-gate replay, author a
`web_target`-declaring `risk_class: write` skill (add `flow_intent` for the
gated step) and navigate with its `skill_id`. That is the SPEC-055 graduation
path: an observed per-action trace becomes a re-validated, replayable flow.
