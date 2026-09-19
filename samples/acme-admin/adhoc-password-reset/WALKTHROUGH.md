# Live Walkthrough: Ad-Hoc Password Reset with Per-Action Approval

This guide walks you through the ad-hoc demo step by step against your running
cluster. You'll see the agent log into a simulated admin panel and reset a
user's password **without binding a flow** — so the mutating browser action
parks a **per-action change-request card** (`approval_kind: action`) instead of
riding a single flow gate.

It is the counterpart to
[`acme-admin/password-reset/WALKTHROUGH.md`](../password-reset/WALKTHROUGH.md),
which performs the same reset as a **bound flow** with one HITL gate
(`approval_kind: flow`). Walk through both to see SPEC-054's two approval
models side by side.

## Prerequisites Check

Everything is already running in your cluster:

| Component | Status |
|---|---|
| Cluster (OrbStack) | ✅ Running |
| Browser connector | ✅ `GATEWAY_BROWSER_ENABLED=true` |
| Browser sidecar | ✅ 2/2 containers in tool-gateway pod |
| Admin pages (`acme-admin`) | ✅ `acme-admin` serving `/admin/` (stateful store) |
| Credential sets | ✅ `acme-admin` loaded |
| ResetPasswordAdHoc runbook | ✅ In skills-hub at `/skills/samples/` (installed by `make deploy-samples`) |

> **Note:** the runbook declares **no `web_target`** — that is deliberate. A
> skill without `web_target` cannot bind a browser flow, so the session stays
> unbound and every write parks its own card. If the runbook is missing, run
> `make deploy-samples` from the repository root.

## Step 1: Open the Operator Portal

Open **https://aiops.luban.metasync.cc** and sign in as **`luban-operator`**
(Keycloak, shared development password — see the dev-k8s README).

You will need a **second identity** at step 5: open a private window and sign in
as **`luban-approver`** now. Mutating execution carries a tier-2 approval and
`operator` is not a designated decider — step 5 explains what happens if you skip
this.

Use this canonical origin, not a `svc/web-ui` port-forward: the broker starts
every login at `OIDC_REDIRECT_URI`, so a localhost tab never receives the
authorization code and stays signed out (see `Runtime Wiring` in
`shared/platform-ops/gitops/dev-k8s/README.md`). The port-forwards this
walkthrough needs — `acme-admin` in step 2, plus identity-service and
platform-gateway for `demo.sh` — are set up where they are used.

## Step 2: Verify the Admin Target Pages

```sh
kubectl -n dev-luban-aiops port-forward svc/acme-admin 8080:8080 &
```

Open **http://localhost:8080/admin/** — the same stateful acme-admin console the
password-reset sample uses: a login form, a user table with "Reset password"
links, and a reset page that pre-fills from URL parameters and waits for a
"Confirm reset" click. Unlike a static mock, this console really mutates a store,
so step 6 can prove the reset landed.

## Step 3: Start a Chat Session

In the operator portal, click **Chat** in the sidebar. The composer is at the
bottom.

## Step 4: Ask the Agent to Reset a Password Ad Hoc

Type a message that asks for the reset **without a flow**, e.g.:

```
Ad-hoc, without binding a flow, reset the password for alice to
TempPass-2026! in the acme-admin console. Follow runbook
samples/adhoc-password-reset-resetpasswordadhoc but do not pass skill_id to
web.navigate — this session must stay unbound so each write parks its own
per-action card. Use the acme-admin credential set for login, and pass the new
password as the newpw URL parameter on the reset page.
```

Staying unbound is the point of the sample, not a warning sign — the runbook's
"Staying Unbound Is the Platform's Design" section and the kernel's default system
prompt both answer the objections a model may raise. An unbound write is the
**more** heavily gated path: one card per action rather than one gate per flow.

**Your password is masked in every human-readable projection.** The sidebar title
reads `Ad-hoc, without binding a flow, reset the password for alice
to ***` — masking runs *before* the 80-character cap, so this prompt's secret,
which sits right at the boundary, does not leak its leading characters (SPEC-049
R-5). The title is minted from your own message, the one credential carrier no
tool-side redactor sees, and it is the label an approver's inbox lists the session
by. The assistant's reply prose and your own turn on reload mask too — otherwise
the model could read `TempPass-2026!` in its prompt and echo it back. Two
boundaries, so this does not overclaim:

- **Your own bubble reads plaintext while the turn is live** — rendered from your
  composer, not a stream frame — and reads `***` once reloaded.
- **The value stays real in the agent's context at rest**, because the model needs
  it to perform the reset. Masking is a property of every human-readable
  projection (title, transcript, stream, cards, evidence), not of the machine
  input the reset runs from.

The agent should:
1. Read the `ResetPasswordAdHoc` runbook via `skills.get`/`skills.search`
2. Navigate to the admin login page via `web.navigate` **without `skill_id`**
   — nothing binds; the session stays unbound
3. Snapshot the login form via `web.snapshot`
4. Fill username + password via `web.fill_credential` (read tier, **by
   reference** — admitted unbound by SPEC-054 R-2; the secret never enters the
   arguments). The login form auto-submits (legacy SSO) and redirects
5. Navigate to the reset page with the new password as the `newpw` URL
   parameter (read tier; the value is masked in the result the gateway returns
   *and* in the tool-call arguments the kernel streams and persists, so it
   reads `newpw=***` in the evidence panel with the rest of the URL intact)
6. **Click "Confirm reset"** ← an unbound write-tier interaction, so it parks a
   **per-action** confirmation card

Expect **exactly one** card from this sample. The target's login page
auto-submits on a timer once both credential fields are filled (legacy SSO), and
step 4 of the runbook says **"Do not click 'Sign in'"** — authentication is
read-tier and needs no write. The reset form likewise pre-fills from the URL but
deliberately does not auto-submit, so "Confirm reset" is the procedure's one
write-tier interaction. Two cards mean the agent clicked "Sign in" anyway: a
redundant gated write, not a stronger gate.

## Step 5: Approve the Per-Action Card

When the agent clicks "Confirm reset", a **change-request card** appears. Unlike
the password-reset flow card, it shows **no flow headline**; each call leads with
the **change request** (SPEC-054 R-3):

- a bold plain-language **summary** — here `Click "<button type=submit> "Confirm
  reset""`, the element description the gateway parsed from the snapshot, wrapped
  in the projection's own quotes (so the inner pair reads doubled — cosmetic, but
  that is the string you see)
- a **decision-relevant fields** table, *only when the projection has fields*.
  `web.click` promotes none — its single argument is the snapshot `ref`, so the
  summary carries the element instead. A `web.type` card does promote its `text`
  field, with a `masked` tag beside the `***`
- the element **hint** line, `<button type=submit> "Confirm reset"`

An action card does *not* show the per-call tool name and risk tag — that header
(`web.click` + `write`) is the flow branch of the same component; an action card
conveys risk through card-level `mutating` / `approver required` tags instead. Its
"Technical details" args arrive **pre-redacted** from the kernel (SPEC-055 R-7,
fail-closed) — `{ "ref": "***" }`, not the raw ref the flow card shows. Under the
hood it carries `approval_kind: "action"` and **no** `flow_summary`, the
discriminator SPEC-054 R-1 adds so the card states its own kind.

**Someone else approves it.** Mutating execution carries a tier-2 approval
decided by `approver` or `platform-admin`, and the requester cannot decide their
own call. On an `operator`'s screen the card renders **no Approve/Deny button**,
only the note "This request needs a designated approver — your current role
cannot approve or deny it." That is a display hint (SPEC-030 R-5); the gateway
stays authoritative — posting the decision to `/api/v1/chat/confirm` as the
operator returns `403 not_a_designated_approver` (tier 2), because `operator`
holds no decider role. Either way the card stays parked. This is SPEC-030 R-4
working, not a bug.

Switch to the window signed in as **`luban-approver`** and open **Approvals** —
the decider-only inbox, badged with the pending count. The card renders there
identically (same component) under a provenance header naming the session and
owner. Approve it; the operator's stream resumes and the agent clicks, extracts
the success message, and captures a screenshot. Because there is no flow-unlock
for unbound writes, **had the agent performed more than one write, each would park
its own card** — approving one never unlocks the next.

## Step 6: Verify the Result

The agent's final message confirms the reset. Because `acme-admin` really
mutates a store, this is now **verifiable** — not the self-echoing query string a
static mock would give you. The console surfaces the change in three places you
can open yourself:

```
http://localhost:8080/admin/users/            # the roster row now shows a bumped revision + "Last modified"
http://localhost:8080/api/users/alice         # the JSON store: revision + password_changed_at
```

The chat transcript carries the in-band evidence first: a `web.extract` of
`#reset-status` (or `#confirmation-message` on the confirmation page) reading
`Password for alice has been reset successfully.`, emitted by the target app's own
submit handler, so it shows the approved click landed; plus the `web.screenshot`
beside it. Do not look for that sentence in a `web.snapshot`: a snapshot
enumerates interactive elements only (`a, button, input, select, textarea` and a
few ARIA roles) and the status line is a plain `<p role="status">`, so it is
legitimately absent.

Then the runbook's step 9 corroborates it **on the other surface**: one read-tier
`http.get` with `credential_set: "acme-admin"` against `/api/users/alice`, which
returns the bumped `revision` and the recorded `password_changed_at`. That is the
difference this migration buys — the static target this sample used to drive could
only re-render its own query parameters (reporting success for *any* user, even one
absent from the roster), so its success sentence was a claim; here the store is the
surface that turns it into a fact. `http.get` is read tier, so it parks no card and
leaves the per-action count unchanged.

The evidence chain masks the secret on both sides of the gateway boundary: the
`web.navigate` **result** reports `newpw=***` (the gateway masks every
representation of a call it executed), and its **`tool_call` arguments** read the
same way (the kernel masks the arguments the model chose). What survives is the
URL's shape — a `tool_call` frame records what was invoked, so it keeps its
evidence and loses only the secret.

In the session detail (or approvals inbox), the durable record carries the **same**
`approval_kind: "action"`, the persisted top-line `message` (SPEC-054 R-4), and
the per-call `change_request` — so a re-login and the approver inbox render exactly
the card the live stream showed. Every execution row carries a signed receipt
(SPEC-037), stamped with `action` authority provenance (ADR-0010).

## What Just Happened

```
Operator                  Agent                     Admin Panel
   │                        │                           │
   │ "reset alice ad hoc"   │                           │
   │───────────────────────>│                           │
   │                        │ web.navigate (NO skill_id)│
   │                        │──────────────────────────>│  (nothing binds)
   │                        │ web.snapshot              │
   │                        │ web.fill_credential (×2)  │  read tier, by
   │                        │──────────────────────────>│  reference (R-2)
   │                        │      (login auto-submits) │
   │                        │ web.navigate (reset URL)  │
   │                        │──────────────────────────>│
   │                        │ web.click → ACTION card   │
   │  ┌──────────────────┐  │  (change request, no flow)│
   │  │ Approve action   │  │                           │
   │  └──────────────────┘  │                           │
   │───────────────────────>│                           │
   │                        │ web.click (approved,      │
   │                        │   action-provenance signed)
   │                        │──────────────────────────>│
   │                        │ web.snapshot (verify)     │
   │  "Password reset OK"   │                           │
   │<───────────────────────│                           │
```

## Key Observations

1. **Per-action, not per-flow**: with no `web_target` declared, nothing binds,
   so the write parked an `action`-kind card. N writes would park N cards —
   there is no flow-unlock on the unbound path (SPEC-054 R-2).
2. **Unbound login is reachable**: `web.fill_credential` worked **by reference**
   with no bound flow — previously this was denied `BROWSER_FLOW_NOT_BOUND`,
   blocking interactive login at the read tier (SPEC-054 gap 3).
3. **The card is a change request**: the approver saw a plain summary and the
   decision-relevant fields, secret-masked — not a bare tool name (R-3). The
   projection is display-only; the signed `args_digest` is unchanged.
4. **Kind is explicit**: `approval_kind: "action"` rode both the live frame and
   the durable record, with no `flow_summary` — the same branch computes both,
   so they cannot disagree (R-1, subsuming the v0.34.1 headline-leak class).

## Running the Demo Script

For a fully automated run (deterministic legs only — no model interaction),
after `make deploy` and `make deploy-samples`:

```sh
bash samples/acme-admin/adhoc-password-reset/demo/demo.sh
```

This verifies:
1. Prerequisites (runtime config, allowlisted origin, credential set, HITL bridging)
2. The ad-hoc runbook is ingested **and declares no `web_target` and no
   `risk_class`** (the unbound guarantee)
3. All 15 `web.*` tools are registered with correct risk tiers
4. The target really mutates: a reset through the console bumps the store
   (`revision` + `password_changed_at`), corroborated by `GET /api/users/alice`

Add the opt-in chat leg (requires a running agent + the platform-gateway
port-forward) to drive the live unbound reset, assert every parked card is
`action`-kind with a change request and every execution signed, then confirm the
reset landed in the store:

```sh
RUN_CHAT_LEG=true bash samples/acme-admin/adhoc-password-reset/demo/demo.sh
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agent refuses, or asks "do you want me to proceed?" and parks no card | The model substituted its own refusal for the operator's decision, so there is no card, no change request, and no signed receipt. Re-send the step-4 message — it names the runbook, the credential set, and the reason for staying unbound. The gate is the platform's to apply, not the model's. |
| Card shows a flow headline / `approval_kind: flow` | The model bound a flow — re-ask ad hoc and ensure no `web_target` skill was navigated with `skill_id` |
| `SKILL_NOT_WEB_FLOW` on navigate | Expected if `skill_id` was passed for this runbook; retry navigate **without** `skill_id` |
| "No web.* tools available" | Check `GATEWAY_BROWSER_ENABLED=true` on tool-gateway |
| "Credential set not found" | Run `sync-browser-credentials.sh` to refresh the secret |
| "Runbook not found" | Run `make deploy-samples` to pack it into the `skills-samples` ConfigMap |
| Admin pages 404 | Check `kubectl port-forward` is still running |
