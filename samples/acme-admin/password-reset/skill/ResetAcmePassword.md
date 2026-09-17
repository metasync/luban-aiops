---
title: Reset a Password in the ACME Admin Console
description: >
  Reset a user's password in the acme-admin user-administration console
  by driving its browser UI. Use this skill when someone asks to reset,
  change or issue a new temporary password for an acme-admin account
  and wants it done through the console a human would use. Signs in
  with a platform-managed credential set, opens the reset form
  pre-filled from the URL, and gates the single "Confirm reset" click.
  Mutating: it parks exactly one confirmation card, of kind flow.
tags: [acme-admin, console, password, reset, browser-flow, web-check, mutation, temporary-password, user-management]
version: "1.0"
web_target: http://acme-admin:8080/admin/
risk_class: write
# flow_intent (SPEC-053 R-4): the operator-facing intent of the single gated
# mutation — the "Confirm reset" click in step 7. Rendered as the confirmation
# card's lead decision line, above the demoted DOM detail. Display-only: never
# a security input, and it carries no credential.
flow_intent: "Submit the password reset for the target acme-admin account, permanently replacing that user's console password."
---

## Purpose

Reset one acme-admin account's password through the console's own UI, and
prove the change landed in the store. This is the browser half of the
suite's mutating pair: `LockUnlockUser` makes the same class of change
over `http.post` and parks an `action` card; this skill binds a flow and
parks a `flow` card.

Common requests this skill handles:

- "Reset the acme-admin password for alice@example.com"
- "Issue bob a new temporary password in the acme-admin console"
- "Carol locked herself out of acme-admin — reset her password"
- "Change dave's password through the acme-admin UI"

This skill is a **tutorial example** for a `write`-class browser flow. It
demonstrates:

- **One write-tier interaction, one card.** The "Confirm reset" click in
  step 7 is the flow's only write-tier step, so the flow parks exactly
  one confirmation card — on the destructive mutation the operator
  actually means to approve, not on signing in.
- `approval_kind: "flow"`, and what that buys: the one approval covers
  the flow's remaining write-tier interactions (ADR-0007), so following
  the confirmation link afterwards does not park a second card.
- `flow_intent` as the card's lead decision line, above the demoted
  DOM/technical detail.
- **A one-time secret in a URL, masked everywhere.** The new password
  travels as `?newpw=`, and the gateway's shared URL redaction masks it
  in every result, evidence frame, card and durable record.
- Authentication kept **read tier**: `web.fill_credential` plus a login
  form that auto-submits, so signing in costs no click.
- **Cross-surface verification** at the end — the reset is confirmed from
  the JSON API, not only from the page that performed it.

## Preconditions

- The `acme-admin` credential set is configured on the tool-gateway
  (`GATEWAY_BROWSER_CREDENTIAL_SETS`), and the origin
  `http://acme-admin:8080` is on `GATEWAY_BROWSER_ALLOW_ORIGINS`.
- `GATEWAY_MUTATING_TOOLS_ENABLED=true`, or `web.click` is not
  registered and the flow cannot complete.
- A `tools:mutate` grant for the caller's role and, under the default
  bundle, a **designated approver** who is not the requesting operator.
- The caller supplies the **target user** (username or email) and the
  **new temporary password** in the chat message. That password is a
  chat-supplied one-time value: never stored in this skill, never
  committed, and never present in any tool output.
- The app is deployed (`make deploy-sample-app`). Unlike the static
  target this sample replaces, the reset really changes state — and the
  store is in memory, so a pod restart reverts it to the seed.

## Procedure

Exactly **one write-tier interaction**: the "Confirm reset" click in step
7. Every other step is read tier and runs without a gate.

1. **Bind and open the flow.** `web.navigate` with `skill_id`
   `samples/password-reset-resetacmepassword` and this skill's
   `web_target` (`http://acme-admin:8080/admin/`). Binding is what
   attaches the origin guard, the step budget and the flow's single
   approval.

2. **Inspect the login form.** `web.snapshot`; confirm `admin-login-form`,
   `admin-username` and `admin-password` are present and empty, and note
   the element **refs** — `web.fill_credential` takes a ref, not a
   selector.

3. **Fill admin credentials.** Two `web.fill_credential` calls from set
   `acme-admin`: field `username`, then field `password`. Never
   `web.type` a credential — filling submits nothing, so both calls stay
   read tier and the value never enters the prompt or any result.

4. **Let the login auto-submit.** The console submits the login about
   100 ms after both fields are filled and redirects to the user list.
   **Do NOT click "Sign in"** — that click would be write tier and would
   move the flow's single gate onto authentication, which is not what
   the operator is being asked to approve. Settle with `web.wait_for` on
   `#user-table`.

5. **Locate the target user.** In the table (columns: Name, Email, Role,
   **Status**, Last modified, **Revision**, Action) find the target and
   note their current Revision. If the user is not in the table, report
   that and stop — do not reset a similar-looking account.

6. **Open the reset form pre-filled.** `web.navigate` to
   `http://acme-admin:8080/admin/users/reset/?user=<target>&newpw=<new-password>`
   — read tier, because navigating is not interacting. The page's own
   script pre-fills `new-password` and `confirm-password` from the query
   string and sets `target-user`, and it deliberately does **not**
   submit. The `newpw` value is masked to `***` in the result and in the
   evidence, so the URL you get back is safe to read aloud.

7. **Confirm the reset.** `web.click` on `#confirm-reset` — the flow's
   **single write-tier interaction**, so this is where the one
   confirmation card parks. The approver sees the `flow_intent` headline
   and the target origin, approves or denies, and on approval the click
   executes and the stream resumes.

8. **Read the console's own confirmation.** `web.extract` with
   `selector: "#reset-status"`. On success it reads
   `Password for <username> has been reset successfully.` A
   `web.snapshot` will **not** show it: a snapshot enumerates interactive
   elements only, and the status line is a plain `<p role="status">`.
   If the caller wants the confirmation page, `web.navigate` to the
   `View confirmation` link's href (read tier) and extract
   `#confirmation-message` and `#reset-timestamp`; navigating rather
   than clicking keeps the step read tier even though the flow's
   approval would have covered the click.

9. **Verify on the other surface.** One `http.get` with
   `credential_set: "acme-admin"` against
   `http://acme-admin:8080/api/users/<target>`, and report the bumped
   `revision` and `password_changed_at`. Then capture a `web.screenshot`
   as final visual evidence and include it in the response. The API
   check is what makes the console's success message a fact rather than
   a claim.

## Interpretation

- `#reset-status` reading `Error: passwords do not match.` — the two
  fields were not both pre-filled, so the new password did not arrive
  intact. Report it and ask the caller to retry; do not type into the
  fields directly.
- `#reset-status` reading `Error: <message>` where the message names
  `PASSWORD_MISMATCH`, `INVALID_PASSWORD` or `UNKNOWN_USER` — the app
  refused the reset. Report the app's own wording. The form stays
  usable, but the flow's gate has been spent; restart the flow rather
  than clicking again.
- A redirect back to `/admin/` at any point means the session cookie was
  not set or was dropped. Re-run from step 1.
- `BROWSER_ORIGIN_NOT_ALLOWED`, `BROWSER_FLOW_DENIED`,
  `BROWSER_FLOW_ORIGIN_DEVIATED` — the flow was refused by policy or by
  the guard. Stop and report the denial; never retry around it.
- `BROWSER_FLOW_EXHAUSTED` — the step budget
  (`GATEWAY_BROWSER_FLOW_MAX_STEPS`) ran out, which means the flow
  wandered. Restart it with a fresh confirmation.
- A **denial** on the confirmation result means an operator refused the
  reset. Report it and stop. Nothing was changed; the store's revision
  is unchanged, and step 9 will show that.
- `HTTP_URL_SECRET_NOT_ALLOWED` on step 9 — the verification URL carried a
  secret-bearing query parameter (`newpw`, `password`, `token`, …).
  `http.post` refuses such a URL outright and this skill's step-9 URL is a
  bare path, so the code means the call was constructed wrongly. Rebuild it
  from the path alone and read the new password from nowhere: it is a
  one-time value that belongs in the browser form and in no tool argument.

## Tutorial notes (skill authoring guidance)

**Why is the gate on "Confirm reset" and not on sign-in?**
The one-gate-per-flow invariant (SPEC-049 R-4/D-3, ADR-0007) requires
exactly one write-tier interaction per mutating flow, and it should land
on the action the operator means to approve. Resetting a password is the
mutation; signing in is not. An earlier revision of the shipped sample
gated the sign-in click and auto-submitted the reset, which asked an
approver to authorise a login and then changed a password they had never
seen mentioned. SPEC-051 moved the gate onto the mutation, and this app
preserves that asymmetry in code: the login form auto-submits, the reset
form does not.

**Why does the new password travel in a URL at all?**
Because legacy admin panels that accept pre-filled batch URLs are real,
and a tutorial that only shows the safe shape teaches nothing about the
unsafe one. The value is a one-time temporary password the caller
generates for this reset — not a long-lived service credential, so it
does not belong in a credential set. It is masked at every seam: by the
gateway in the results it returns, and by the kernel in the tool-call
arguments it streams and persists, which no gateway-side redactor ever
sees. This app additionally keeps the pre-fill client-side, so the value
never appears in served HTML and a `web.snapshot` cannot leak it.

**Why not reset through `http.post` instead?**
The app does expose `POST /api/users/{username}/password`, and
`LockUnlockUser` proves that surface works — so the honest answer is not
that `http.post` cannot do this. It is that this skill exists to show the
other half: a **bound browser flow**, which is what an operator's `flow`
card means, and a one-time value that only ever travels as a masked URL
parameter rather than as a tool argument. Two constraints shape it. The
pre-filled-URL form is the shape a legacy console actually has, and
driving it needs a browser. And `http.post` refuses a URL carrying a
secret-bearing query parameter (`HTTP_URL_SECRET_NOT_ALLOWED`) and ships
no `headers` parameter, so the `?newpw=` route — the one this app's own
reset page reads — is not reachable over HTTP at all. Use the browser for
the form, use `http.get` for the verification, and read `LockUnlockUser`
for the mutation that genuinely belongs on the JSON surface.

**Why is the card `flow` and not `action`?**
Because a browser flow binds an origin, a step budget and an approval
that covers its subsequent write-tier interactions. `LockUnlockUser`
makes one call and needs one decision, so it parks an `action` card.
Run the two back to back and SPEC-054's discriminator stops being a field
in a schema and becomes something you have seen twice.

**What does this skill prove that the static target could not?**
That the reset happened. The previous target reported success for any
user, including users that did not exist, so its own walkthrough had to
warn the reader that the URL they had just been shown was a lie. This one
mutates a store, bumps a revision, records `password_changed_at`, and
answers step 9 from that store — so the confirmation is evidence rather
than a sentence the page always printed.
