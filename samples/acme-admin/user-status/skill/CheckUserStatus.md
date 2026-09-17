---
title: Check ACME Admin User Account Status
description: >
  Read a user's account status from the acme-admin console's rendered
  user list. Use this skill when someone asks whether an acme-admin
  account is locked or active, when it was last modified, what its
  store revision is, or whether a previous lock, unlock or password
  reset actually landed. Signs in with a platform-managed credential
  set, then reads the table with web.extract. Read-only: it changes
  nothing and parks no confirmation card.
tags: [acme-admin, user, account, status, locked, web-check, read-only, verification, user-management]
version: "1.0"
web_target: http://acme-admin:8080/admin/
---

## Purpose

Report what the acme-admin user-administration console actually renders
for one user or for the whole list: **Status** (`locked` or `active`),
**Last modified**, and **Revision**. This is the verification half of
the suite — the skill you run after `LockUnlockUser` or
`ResetAcmePassword` to see the change on the page a human would see.

Common requests this skill handles:

- "Is alice locked in acme-admin?"
- "Show me the acme-admin user list and who is locked"
- "Did that lock actually take effect? Check the console"
- "What is dave's account status and when was it last changed?"

This skill is a **tutorial example** for a read-only browser web-check.
It demonstrates:

- A skill that **opens a browser, signs in, and still parks zero
  cards**. Every step is read tier: `web.navigate`, `web.snapshot`,
  `web.fill_credential`, `web.wait_for`, `web.extract`. A card is a
  property of effect, not of tooling — using a browser does not make a
  check mutating.
- Declaring `web_target` with **no `risk_class`**, which the contract
  treats as `read`. The gateway then binds the flow *and* refuses any
  write-tier interaction in it, so this skill cannot mutate the target
  even if the model decides to try. That refusal is the point: the
  declaration is enforced, not advisory.
- Reading **rendered state** rather than API state. `CheckServiceHealth`
  reports what the service says about itself over JSON; this skill
  reports what the console shows an operator. When the two disagree,
  that disagreement is the finding.
- Keeping authentication read tier with `web.fill_credential` and
  letting the login form **auto-submit**, so signing in costs no click
  and therefore no card.

## Preconditions

- The `acme-admin` credential set is configured on the tool-gateway
  (`GATEWAY_BROWSER_CREDENTIAL_SETS`). It is written by
  `sync-browser-credentials.sh` from the same generated value that
  becomes the app's `ACME_ADMIN_PASSWORD`, so the two surfaces cannot
  disagree. Never paste credentials into the chat.
- The origin `http://acme-admin:8080` is on
  `GATEWAY_BROWSER_ALLOW_ORIGINS`.
- The app is deployed (`make deploy-sample-app`) and its readiness probe
  is passing.
- The caller names the user to report on, or asks for the whole list.
  Users are identified by username or by email address; the seeded set
  is `alice`, `bob`, `carol`, `dave` (one of them, `dave`, starts
  locked).

## Procedure

Six read-tier steps and no write-tier step at all, so nothing parks.

1. **Bind and open the flow.** `web.navigate` with `skill_id`
   `samples/user-status-checkuserstatus` and this skill's `web_target`
   (`http://acme-admin:8080/admin/`). Binding a read flow is what makes
   step 6's refusals possible: the origin guard and the step budget
   attach here.

2. **Inspect the login form.** `web.snapshot` and confirm
   `admin-login-form`, `admin-username` and `admin-password` are
   present. Note the **element refs** the snapshot assigns — the next
   step takes a ref, not a selector.

3. **Fill admin credentials.** Two `web.fill_credential` calls against
   the refs from step 2, both from credential set `acme-admin`: field
   `username` into the username element, then field `password` into the
   password element. Never use `web.type` for a credential value —
   filling submits nothing, so both calls stay read tier and the value
   never enters the prompt, the arguments, or any result.

4. **Let the login auto-submit.** The console's login form submits
   itself about 100 ms after both fields are filled and redirects to the
   user list. **Do NOT click "Sign in"** — a click is write tier and
   would park the suite's only unwanted card. Use
   `web.wait_for` with `selector: "#user-table"` and `state: "visible"`
   to let the redirect settle.

5. **Read the table.** `web.extract`:

   - for the whole list, `selector: "#user-table"` — a `<table>`, so the
     result carries `headers` and `rows`. The columns are Name, Email,
     Role, **Status**, Last modified, Revision, Action.
   - for one user, `selector: "#user-row-<username>"` — a single row, so
     the result is the list of that row's cell texts in column order.

6. **Report the facts, not an inference.** Quote the **Status** cell
   verbatim (`locked` or `active`) and the **Last modified** timestamp,
   and say the **Revision** number. Revision is authoritative for
   "did something change": every mutation increments it, so a revision
   that is still `0` means the store is exactly as seeded. If the caller
   is verifying a previous action, report both the status and the
   revision — the status says what is true now, the revision says
   whether anything happened at all.

## Interpretation

- A redirect back to `/admin/` after step 4 means the credential was
  rejected. The login page renders the failure in `admin-login-status`
  and sets no session cookie. Report that the credential set did not
  authenticate; do not retry in a loop and do not try another password.
- `BROWSER_ORIGIN_NOT_ALLOWED` on step 1 — the origin is not on the
  browser allowlist. Nothing was loaded.
- `BROWSER_FLOW_DENIED` on a write-tier tool — this flow is read-class,
  so the gateway refused it. That is the declaration being enforced.
  Report the refusal; the answer to "is the user locked" never requires
  a mutation.
- `BROWSER_FLOW_ORIGIN_DEVIATED` — a navigation left the bound origin.
  Stop and report; the flow must be restarted with a fresh binding.
- `BROWSER_FLOW_EXHAUSTED` — the step budget
  (`GATEWAY_BROWSER_FLOW_MAX_STEPS`) ran out, which means the flow
  wandered. Restart it rather than continuing.
- `web.extract` returning no rows for `#user-table` means the page is not
  the user list — most often the session cookie was dropped, so the app
  redirected to the login page. Re-run from step 1.
- A user the caller named is absent from the table: report that the
  account does not exist in this store. Do not guess a similar username.

## Tutorial notes (skill authoring guidance)

**Why does this skill sign in but `CheckServiceHealth` does not?**
Different surfaces, different doors. The JSON API authenticates with HTTP
Basic, which `http.get` can supply from a named credential set; the HTML
console authenticates with an opaque session cookie, which only a browser
can hold. Neither skill ever sees the password — both name a credential
set and let the gateway resolve it server-side.

**Why is there no `risk_class` in the frontmatter?**
Because `web_target` without `risk_class` *is* the read declaration: the
contract treats it as `read`, and the gateway binds a read-class flow that
refuses write-tier interactions. Writing `risk_class: read` would behave
identically today. Omitting it is the honest choice for a check whose
entire procedure is read tier, and it is what makes the pair with
`LockUnlockUser` legible: same target, same console, one declares a write
flow and parks a card, this one does not and parks nothing.

**Why read the rendered table instead of `GET /api/users`?**
Because the question "what would an operator see?" is a different
question from "what does the service report?", and this suite exists to
show both being answered honestly. Reading the page also proves the
session and the server-rendered state machine work — an API check cannot
tell you that the console is broken for humans while the JSON is fine.

**Why is `web.wait_for` used instead of a second snapshot?**
The auto-submit is a timer, so the redirect is not instantaneous. A
snapshot taken too early shows the login page and invites the model to
click "Sign in" — the exact write-tier step this skill exists to avoid.
Waiting on `#user-table` makes the read deterministic instead of racy.

**How does this skill enable cross-skill verification?**
`LockUnlockUser` mutates over HTTP and reports the API's post-mutation
`revision`. Re-running this skill then reads the *console's* Status cell
and revision for the same user. Two surfaces, one store: when the console
shows `locked` at a revision matching the lock response, the change is
proven independently of the tool that made it. That is the sentence which
turns four demos into one runbook, and the shape SPEC-057 composes.
