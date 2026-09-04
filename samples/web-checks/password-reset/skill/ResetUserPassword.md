---
title: Reset User Password in Admin Portal
description: >
  Reset a user's password in the admin portal. Use this skill when
  someone needs to change or reset a user account password in the
  admin portal system. The admin portal has no self-service password
  reset, so operators must reset passwords manually through this
  skill. Demonstrates a write-class browser web-check skill with a
  single HITL gate on the final "Confirm reset" click — the
  destructive mutation the operator actually approves.
tags: [admin, portal, password, reset, user, account, change-password, admin-portal, user-management]
version: "1.2"
web_target: http://browser-check-target:8080/
risk_class: write
---

## Purpose

Automate the password reset workflow for the admin portal. This is a
real-life scenario: a user cannot reset their own password (the admin
portal has no self-service flow), so they contact the operations team,
and an operator resets it through the admin portal UI.

Common requests this skill handles:
- "Reset the password for user alice@example.com"
- "Change bob's password in the admin portal"
- "I need to reset a user's password in the admin portal"
- "Reset password for carol@example.com to a new temporary password"

This skill is a **tutorial example** for writing a `write`-class
browser web-check skill. It demonstrates:

- Declaring `web_target` and `risk_class: write` in the skill
  frontmatter so the gateway binds a flow and enforces the HITL gate.
- Keeping exactly **one write-tier interaction** — the final "Confirm
  reset" click — so the flow parks a single HITL confirmation card on
  the destructive mutation the operator actually approves.
- Accepting the new password as a **chat-supplied parameter** (never
  stored in the skill body or committed anywhere).
- Using `web.fill_credential` for the admin login (read-tier —
  filling a field submits nothing) instead of `web.type`; the login
  form then auto-submits (legacy SSO), so authentication needs no
  write-tier click.
- Reaching the reset form through read-tier navigation
  (`web.navigate` to a URL that pre-fills the new password) so the
  "Confirm reset" click stays the flow's sole write-tier interaction.

## Preconditions

- The `admin-portal` credential set is configured on the tool-gateway
  (`GATEWAY_BROWSER_CREDENTIAL_SETS`). The admin password is
  platform-managed; never paste credentials into the chat.
- The target origin is on the gateway allowlist
  (`GATEWAY_BROWSER_ALLOW_ORIGINS`).
- The caller supplies the **target user** (email) and the **new
  temporary password** in the chat message. The new password is a
  chat-supplied value — it is never stored in this skill, never
  committed, and never appears in tool outputs.

## Procedure

The flow has exactly **one write-tier interaction**: the "Confirm
reset" click in step 7. Every other step is read-tier and runs without
a HITL gate. This is deliberate — the one gate lands on the destructive
mutation itself (the password reset), which is what the operator
actually means to approve, rather than on authentication.

1. **Bind and open the flow.** `web.navigate` with this skill's id
   and the `web_target` URL (`http://browser-check-target:8080/admin/`).
   This `write`-class flow parks exactly one confirmation card — at
   its single write-tier interaction, the "Confirm reset" click in
   step 7; the read-tier steps around it run without a gate.

2. **Inspect the login form.** Take a `web.snapshot` and verify the
   admin login form is present with empty username and password
   fields.

3. **Fill admin credentials.** Use `web.fill_credential` (read tier)
   from set `admin-portal`: field `username` into the username
   element, then field `password` into the password element. Never
   use `web.type` for credential values — filling a field submits
   nothing, so both fills stay read-tier.

4. **Let the login auto-submit.** The admin page auto-submits once
   both fields are filled (legacy SSO behaviour common in old internal
   tools) and redirects to the user list. **Do NOT click "Sign in"** —
   authentication is read-tier and needs no click, so it never parks a
   card. Take a `web.snapshot` after the redirect settles to confirm
   you are on the user list.

5. **Locate the target user.** In the user-list snapshot, find the
   target user in the table. The table has columns: Name, Email, Role,
   Action. Each row has a "Reset password" link. If the target user is
   not in the table, report this to the caller and stop.

6. **Navigate to the reset form with the new password.** Construct the
   URL `/admin/users/reset/?user=<target-email>&newpw=<new-password>`
   on the same origin and `web.navigate` to it (read-tier — direct URL
   navigation, no click needed). The admin panel pre-fills both
   password fields from the URL parameters but does **not** submit
   automatically; it waits for the operator's confirmation.

7. **Confirm the reset.** Click the "Confirm reset" button
   (`web.click`) — the flow's **single write-tier interaction**, so
   this is where the one confirmation card parks. The approver sees
   the flow headline (this skill's intent and the target origin) plus
   the confirm-reset action, and approves or denies. This is the
   destructive mutation, so gating it here is the whole point of the
   flow.

8. **Verify and capture evidence.** Take a `web.snapshot` to confirm
   the "Password for <user> has been reset successfully." message is
   visible. Then capture a `web.screenshot` as final visual evidence
   of the successful reset — include the screenshot in your final
   response to the caller.

## Interpretation

- Any denial (`BROWSER_ORIGIN_NOT_ALLOWED`, `BROWSER_FLOW_DENIED`,
  `BROWSER_FLOW_ORIGIN_DEVIATED`) means the flow was refused by
  policy or the operator — stop and report the denial, never retry
  around it.
- A snapshot that does not show the target user in the table means
  the user was not found; report this to the caller without
  attempting the reset.
- A snapshot after step 7 that shows "Error: passwords do not match"
  means the new password was not transmitted correctly; report this
  to the caller and ask them to retry with the correct password.
- The step budget is bounded by `GATEWAY_BROWSER_FLOW_MAX_STEPS`;
  exhaustion (`BROWSER_FLOW_EXHAUSTED`) means the flow deviated and
  must be restarted with a fresh confirmation.

## Tutorial notes (skill authoring guidance)

**Why is the HITL gate on the "Confirm reset" click, not on sign-in?**
The one-HITL-gate-per-flow invariant (SPEC-049 R-4/D-3) requires
exactly one write-tier interaction per mutating flow, and that gate
should land on the action the operator actually means to approve — the
destructive mutation. Resetting a password is the mutation; signing in
is not. So the skill makes the "Confirm reset" click the sole
write-tier interaction and keeps authentication read-tier. The
confirmation card then reads as "reset a user's password on <origin>"
(the flow headline), which is far clearer than approving a bare sign-in
click whose intent is ambiguous.

**Why is authentication read-tier (no sign-in click)?**
`web.fill_credential` is read-tier — it fills a field from a
server-side secret store and submits nothing; the value never enters
the prompt or tool arguments. The admin page auto-submits once both
fields are filled (legacy SSO), so the agent reaches the user list
without any write-tier click. Using `web.type` or clicking "Sign in"
would add a write-tier interaction and a second card, breaking the
one-gate invariant.

**Why is the new password a URL parameter, not a credential set?**
The new password is a one-time temporary value the caller generates
for this specific reset. It is not a persistent service credential.
Credential sets are for long-lived service accounts; one-time
passwords belong in the chat message. The URL parameter approach is
realistic for legacy admin panels that support batch operations via
pre-filled URLs, and the gateway redacts the `newpw` query parameter
from every result, evidence frame, and audit record (SPEC-049 R-5).

**Why does the reset form pre-fill but not auto-submit?**
The form pre-fills both password fields from the URL so the operator
sees exactly what will be committed, but it waits for the "Confirm
reset" click. That click is the flow's single write-tier interaction —
the one HITL gate — so the destructive reset never runs without an
explicit approval. (An earlier revision auto-submitted the reset and
gated the sign-in click instead; SPEC-051 moved the gate onto the
mutation where it belongs, and the platform now enforces one gate per
flow kernel-side regardless of how the model sequences the steps.)
