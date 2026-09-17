---
title: Lock or Unlock an ACME Admin User Account
description: >
  Lock or unlock a user account in the acme-admin user-administration
  console through its JSON API. Use this skill when someone asks to
  lock an acme-admin account, unlock one, suspend or re-enable a user,
  or reverse a lock that was applied in error. Performs one http.post
  to the lock or unlock endpoint with a platform-managed credential
  set, then reports the post-mutation revision. Mutating: it parks
  exactly one confirmation card, of kind action.
tags: [acme-admin, user, account, lock, unlock, suspend, http, mutation, user-management]
version: "1.0"
risk_class: write
---

## Purpose

Change one account's lock state in the acme-admin console and prove the
change landed. This is the HTTP half of the suite's mutating pair:
`ResetAcmePassword` performs the same class of change through a browser
flow and parks a `flow` card; this skill parks an `action` card. Reading
the two side by side is how SPEC-054's `approval_kind` discriminator
becomes visible without needing the ad-hoc sample.

Common requests this skill handles:

- "Lock the acme-admin account for alice"
- "Unlock dave in acme-admin, that lock was a mistake"
- "Suspend bob@example.com's acme-admin access"
- "Re-enable carol's acme-admin account"

This skill is a **tutorial example** for a write-tier, non-browser
mutation. It demonstrates:

- **Exactly one confirmation card, with `approval_kind: "action"`.** The
  card is parked by the gateway because `http.post` is write tier in the
  tool registry — not because this frontmatter says so. What the
  declaration does is keep the catalogue honest and keep the skill
  graduable under SPEC-055.
- A **legible card**. `change_request.summary` reads
  `POST to http://acme-admin:8080/api/users/alice/lock — 1 field:
  locked`, so an approver decides on the origin, the path and the field
  rather than on `url: *** body: ***`.
- **Credentials by reference.** `credential_set: "acme-admin"` resolves
  server-side into HTTP Basic auth. `http.post` ships no `headers`
  parameter at all, so a secret can never be a model-supplied literal —
  a structural control, not a convention.
- **Reading the post-mutation `revision`.** Every mutating response
  carries it, so you can prove *which* action changed the row rather
  than only that something did.
- **Treating a 409 as an answer.** Locking an already-locked user
  returns `409 NO_OP_MUTATION` and `mutation_confirmed: false`. Nothing
  broke and nothing changed; report that.

## Preconditions

- Both `GATEWAY_HTTP_ENABLED=true` and `GATEWAY_HTTP_ALLOW_ORIGINS`
  listing `http://acme-admin:8080`.
- `GATEWAY_MUTATING_TOOLS_ENABLED=true`, or `http.post` is not
  registered at all and the call fails with `TOOL_NOT_FOUND`. The dev
  cluster's `mutating-dev` runtime profile sets it.
- A `tools:mutate` grant for the caller's role, and — under the default
  policy bundle — a **designated approver** distinct from the operator
  who asked. An operator cannot approve their own mutation.
- `AGENT_HITL_CONFIRM_TIMEOUT` greater than `0` on agent-platform, else
  write-tier tools are excluded from the agent's toolkit entirely.
- The `acme-admin` credential set is configured on the tool-gateway.
  Never paste the admin password into the chat.
- The caller names the user (username or email) and the direction
  (lock or unlock). If they do not say which, ask — the two are not
  interchangeable and the card the approver sees differs.

## Procedure

One write-tier call, one card, then read-only verification.

1. **Resolve the target.** Accept a username (`alice`) or an email
   (`alice@example.com`); the API takes either, case-insensitively. Put
   it in the path exactly as given — do not URL-encode an email's `@`
   away and do not normalise the case.

2. **Make the mutation.** One `http.post`:

   - lock: `url: http://acme-admin:8080/api/users/<identifier>/lock`
     with `body: {"locked": true}`
   - unlock: `url: http://acme-admin:8080/api/users/<identifier>/unlock`
     with `body: {"locked": false}`
   - both with `credential_set: "acme-admin"`

   This call **parks the confirmation card**. Do not retry it, do not
   split it into two calls, and do not attempt the mutation over the
   browser surface as a workaround — the gate is the point.

3. **Wait for the decision.** The stream carries a
   `confirmation_request` frame with `approval_kind: "action"`, a
   `confirm_id`, and a `pending_calls` entry naming `http.post` with
   `risk_level: "write"`. A designated approver decides in the operator
   portal; on approval the same call executes and the stream resumes
   with a `confirmation_result` frame reporting `approved`.

4. **Read the outcome from the response.** On success the body carries
   `action` (`lock` or `unlock`), the user's `username`, `locked`,
   `last_modified`, `revision` and `password_changed_at`. Report the
   `action`, the resulting `locked` value, and the `revision`. Quote
   `last_modified` as the timestamp it is (microsecond precision, UTC) —
   two mutations in the same second must still be distinguishable.

5. **Verify on the other surface.** Tell the caller that
   `CheckUserStatus` will now report the new Status cell for this user
   from the rendered console. This is the suite's cross-skill check: a
   mutation made over HTTP, observed over HTML, against one store.

## Interpretation

- `mutation_confirmed: false` with `status: 409` and
  `error: NO_OP_MUTATION` — the user is already in the requested state.
  Nothing changed and the revision did not move. Report it as
  "already locked"/"already active", not as a failure.
- `status: 404` with `error: UNKNOWN_USER` — no such username or email
  in the store. Report the identifier you used and stop; do not try a
  similar name.
- `status: 401` — the credential set did not authenticate. The response
  carries `WWW-Authenticate: Basic realm="acme-admin"` and
  `error: UNAUTHORIZED` or `INVALID_CREDENTIALS`. Report that the
  platform-managed credential is wrong or missing; never ask the caller
  for a password.
- `TOOL_NOT_FOUND` — `http.post` is not registered: either
  `GATEWAY_HTTP_ENABLED` is false or `GATEWAY_MUTATING_TOOLS_ENABLED` is
  false. Report which, from the live runtime config.
- `HTTP_ORIGIN_NOT_ALLOWED` — refused before any socket was opened.
  Nothing reached the app, so no state changed and no card was needed.
- `HTTP_URL_SECRET_NOT_ALLOWED` — the URL carried a secret-bearing query
  parameter. This skill's URLs never do; if one appeared, the call was
  constructed wrongly. Rebuild it from the path only.
- `HTTP_BODY_TOO_LARGE` / `INVALID_PARAMETERS` — the body exceeded the
  depth, key-count or byte bounds. `{"locked": true}` is one scalar and
  cannot trip them; anything larger means the call was not this skill's.
- A **denial** (`decision: deny` on the confirmation result) means an
  operator refused the mutation. Report the refusal and stop. Never
  re-ask, never re-phrase the request to route around it, and never
  attempt the same change through the browser surface.

## Tutorial notes (skill authoring guidance)

**Why is the card `action` and not `flow`?**
`approval_kind: "flow"` is reserved for a *bound browser flow*, where one
approval unlocks the rest of the flow's write-tier interactions (ADR-0007,
SPEC-054). This skill opens no browser and binds no flow, so its single
gated call is an `action` card: one approval for exactly one call. If a
reader sees both kinds in one afternoon, the discriminator stops being
abstract.

**Why send a body the endpoint ignores?**
`/api/users/{identifier}/lock` and `/unlock` take no request body — the
action is in the path. `{"locked": true}` is sent anyway, and the app
ignores it, because the body is what the confirmation card projects: with
it the approver reads `1 field: locked`, and without it the card names
only a URL. This is worth stating out loud in a tutorial precisely
because it is a choice, not a requirement — an endpoint that *did* read
its body would need no such note.

**Why is the credential a set name and not a header?**
SPEC-058 R-4 deliberately ships no `headers` parameter on either verb.
The only way to authenticate is `credential_set`, which the gateway
resolves from platform-managed configuration at call time. A model cannot
therefore put a literal secret into an `http.post` argument, and the
graduation pipeline has no credential hole to fill:
`parameterize_for_trace` finds a non-secret scalar body and leaves no
`<credential-reference>` marker behind, which is what keeps this skill
graduable under SPEC-055 R-4.

**Why does `risk_class: write` appear without a `web_target`?**
Since SPEC-055 R-3 the two are decoupled: `risk_class` declares a skill's
effect, `web_target` declares where a browser flow starts. A mutating
skill that never opens a browser declares the first and not the second.
The key does not create the gate — `http.post`'s registry tier does — but
a catalogue that cannot distinguish read skills from write skills is a
catalogue an operator cannot triage.

**Why is verification a separate skill?**
So the two halves can be run by different people at different times, and
so a composition (SPEC-057) can put them in either order. A skill that
mutates *and* verifies hides which of the two produced the evidence; here
the mutation reports the API's revision and `CheckUserStatus` reports what
the console renders, and agreement between them is the proof.
