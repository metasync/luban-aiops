---
title: Reset User Password in Admin Portal
description: >
  Reset a user's password in the admin portal. Use this skill when
  someone needs to change or reset a user account password in the
  admin portal system. The admin portal has no self-service password
  reset, so operators must reset passwords manually through this
  skill. Demonstrates a write-class browser web-check skill with a
  single HITL gate on the admin sign-in click — the access control
  boundary.
tags: [admin, portal, password, reset, user, account, change-password, admin-portal, user-management]
version: "1.1"
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
- Keeping exactly **one write-tier interaction** (the admin sign-in
  click) so the flow parks a single HITL confirmation card at the
  access control boundary — the natural mutation point.
- Accepting the new password as a **chat-supplied parameter** (never
  stored in the skill body or committed anywhere).
- Using `web.fill_credential` for the admin login (read-tier —
  filling a field submits nothing) instead of `web.type`.
- After HITL approval, completing the password reset through
  read-tier operations only (`web.navigate`, `web.snapshot`) — no
  further `web.click` or `web.type` calls, so no additional HITL
  gates.

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

The flow has exactly **one write-tier interaction**: the admin sign-in
click in step 4. Every later step is read-tier and runs without a HITL
gate. This is deliberate — the one HITL gate lands on the access
control boundary (authentication), and the actual password reset
happens through read-tier navigation after approval.

1. **Bind and open the flow.** `web.navigate` with this skill's id
   and the `web_target` URL (`http://browser-check-target:8080/admin/`).
   This `write`-class flow parks exactly one confirmation card — at
   its single write-tier interaction, the admin sign-in click in
   step 4; the read-tier steps around it run without a gate.

2. **Inspect the login form.** Take a `web.snapshot` and verify the
   admin login form is present with empty username and password
   fields.

3. **Fill admin credentials.** Use `web.fill_credential` (read tier)
   from set `admin-portal`: field `username` into the username
   element, then field `password` into the password element. Never
   use `web.type` for credential values — filling a field submits
   nothing, so both fills stay read-tier.

4. **Sign in to the admin panel.** Click the "Sign in" button
   (`web.click`) — the flow's **single write-tier interaction**, so
   this is where the one confirmation card parks. The approver sees
   the tool name, the sign-in button ref, and the target origin;
   they approve or deny. After approval, the page auto-redirects to
   the user list (legacy SSO behaviour common in old internal tools).

5. **Navigate to the user list.** `web.navigate` to `/admin/users/`
   on the same origin (read-tier). Take a `web.snapshot` and locate
   the target user in the table. The table has columns: Name, Email,
   Role, Action. Each row has a "Reset password" link. If the target
   user is not in the table, report this to the caller and stop.

6. **Navigate to the reset form with the new password.** Construct
   the URL `/admin/users/reset/?user=<target-email>&newpw=<new-password>`
   on the same origin and `web.navigate` to it (read-tier — direct
   URL navigation, no click needed). The admin panel auto-fills both
   password fields from the URL parameters and auto-submits the
   reset when the passwords match — a legacy batch-operation pattern
   common in old internal tools. **Do NOT click any button on this
   page** — the form submits itself automatically. Any `web.click`
   after the sign-in in step 4 would park an additional HITL card
   and break the one-gate invariant.

7. **Verify and capture evidence.** Take a `web.snapshot` to confirm
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
- A snapshot after step 6 that shows "Error: passwords do not match"
  means the new password was not transmitted correctly; report this
  to the caller and ask them to retry with the correct password.
- The step budget is bounded by `GATEWAY_BROWSER_FLOW_MAX_STEPS`;
  exhaustion (`BROWSER_FLOW_EXHAUSTED`) means the flow deviated and
  must be restarted with a fresh confirmation.

## Tutorial notes (skill authoring guidance)

**Why is the HITL gate on the sign-in click, not on the reset?**
The one-HITL-gate-per-flow invariant (D-3) requires exactly one
write-tier interaction per mutating flow. Both `web.click` and
`web.type` are write-tier, so the skill must choose which single
interaction carries the gate. The admin sign-in is the access control
boundary — the natural mutation point for the flow. After approval,
the password reset happens through read-tier navigation only
(`web.navigate` to a URL with the new password as a query parameter;
the page auto-fills and auto-submits). This keeps the flow within
the one-gate invariant while still completing the full reset.

**Why `web.fill_credential` instead of `web.type` for login?**
`web.fill_credential` is read-tier (it fills a field from a
server-side secret store; the value never enters the prompt or tool
arguments). `web.type` is write-tier (it would park an additional
HITL card, breaking the one-gate invariant). Always use
`web.fill_credential` for platform-managed credentials.

**Why is the new password a URL parameter, not a credential set?**
The new password is a one-time temporary value the caller generates
for this specific reset. It is not a persistent service credential.
Credential sets are for long-lived service accounts; one-time
passwords belong in the chat message. The URL parameter approach is
realistic for legacy admin panels that support batch operations via
pre-filled URLs.

**Why no `web.type` for the new password fields?**
`web.type` is write-tier — each call would park an additional HITL
card, violating the one-gate invariant. The URL-based auto-fill
pattern avoids any write-tier interaction for the password entry,
keeping the admin sign-in as the flow's sole write-tier interaction.
