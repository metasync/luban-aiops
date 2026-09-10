# Live Walkthrough: Ad-Hoc Password Reset with Per-Action Approval

This guide walks you through the ad-hoc demo step by step against your running
cluster. You'll see the agent log into a simulated admin panel and reset a
user's password **without binding a flow** — so the mutating browser action
parks a **per-action change-request card** (`approval_kind: action`) instead of
riding a single flow gate.

It is the counterpart to
[`web-checks/password-reset/WALKTHROUGH.md`](../password-reset/WALKTHROUGH.md),
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
| Admin pages (nginx) | ✅ `browser-check-target` serving `/admin/` |
| Credential sets | ✅ `browser-check-target` + `admin-portal` loaded |
| ResetPasswordAdHoc runbook | ✅ In skills-hub at `/skills/samples/` (installed by `make deploy-samples`) |

> **Note:** the runbook declares **no `web_target`** — that is deliberate. A
> skill without `web_target` cannot bind a browser flow, so the session stays
> unbound and every write parks its own card. If the runbook is missing, run
> `make deploy-samples` from the repository root.

## Step 1: Open the Operator Portal

Open **https://aiops.luban.metasync.cc** — the canonical dev-k8s portal
entrypoint — in your browser and sign in as **`luban-operator`** (Keycloak, with
the shared development password the dev-k8s README documents).

You will need a **second identity** at step 5, so open a private window or a
second browser profile and sign in there as **`luban-approver`** now. Mutating
execution carries a tier-2 approval requirement and `operator` is not a
designated decider — step 5 explains what happens if you skip this.

Do not reach the portal through a `svc/web-ui` port-forward instead. The broker
starts every login at `OIDC_REDIRECT_URI`, which is the canonical origin above,
so a localhost tab never receives the authorization code and stays signed out
however correctly the port-forward serves the shell. See the `Runtime Wiring`
section of `shared/platform-ops/gitops/dev-k8s/README.md` for the mechanism and
for what the extra registered origins are actually for.

The port-forwards this walkthrough and its demo do need — `browser-check-target`
in step 2, plus identity-service and platform-gateway for `demo.sh`, whose header
lists them — are set up where they are used.

## Step 2: Verify the Admin Target Pages

```sh
kubectl port-forward -n dev-luban-aiops svc/browser-check-target 9090:8080 &
```

Open **http://localhost:9090/admin/** — the same legacy admin panel the
password-reset sample uses: a login form, a user table with "Reset password"
links, and a reset page that pre-fills from URL parameters and waits for a
"Confirm reset" click.

## Step 3: Start a Chat Session

In the operator portal, click **Chat** in the sidebar. The composer is at the
bottom.

## Step 4: Ask the Agent to Reset a Password Ad Hoc

Type a message that asks for the reset **without a flow**, e.g.:

```
Ad-hoc, without binding a flow, reset the password for alice@example.com to
TempPass-2026! in the admin portal. Follow runbook
samples/adhoc-password-reset-resetpasswordadhoc but do not pass skill_id to
web.navigate — this session must stay unbound so each write parks its own
per-action card. Use the admin-portal credential set for login, and pass the new
password as the newpw URL parameter on the reset page.
```

Staying unbound is the point of the sample, not a warning sign — the runbook's
"Staying Unbound Is the Platform's Design, Not a Red Flag" section answers the
objections a model may raise, and the kernel's default system prompt states the
same. An unbound write is the **more** heavily gated of the two paths: one card
per action rather than one gate for the whole flow.

The agent should:
1. Read the `ResetPasswordAdHoc` runbook via `skills.get`/`skills.search`
2. Navigate to the admin login page via `web.navigate` **without `skill_id`**
   — nothing binds; the session stays unbound
3. Snapshot the login form via `web.snapshot`
4. Fill username + password via `web.fill_credential` (read tier, **by
   reference** — admitted unbound by SPEC-054 R-2; the secret never enters the
   arguments). The login form auto-submits (legacy SSO) and redirects
5. Navigate to the reset page with the new password as the `newpw` URL
   parameter (read tier; the gateway redacts it)
6. **Click "Confirm reset"** ← an unbound write-tier interaction, so it parks a
   **per-action** confirmation card

## Step 5: Approve the Per-Action Card

When the agent clicks "Confirm reset", a **change-request card** appears. Unlike
the password-reset flow card, it does **not** show a flow headline. Instead each
call leads with the **change request** (SPEC-054 R-3):

- A plain-language **summary** of the effect, rendered bold. For this click it
  reads `Click "<button type=submit> "Confirm reset""` — the element description
  the gateway parsed out of the snapshot, wrapped in the projection's own quotes,
  so the inner pair reads as doubled. Cosmetic, but that is the string you see.
- A **decision-relevant fields** table beneath it — *only when the projection has
  fields*. `web.click` promotes none: its single argument is the snapshot `ref`,
  so there is nothing decision-relevant to lift and the summary carries the
  element instead. A `web.type` card does promote its `text` field, with a
  `masked` tag beside the `***`.
- The element **hint** line, `<button type=submit> "Confirm reset"`.

Note what an action card does *not* show: the per-call tool name and risk tag.
That header (`web.click` + `write`) is the flow branch of the same component — an
action card replaces it with the change request, and conveys risk through the
card-level `mutating` / `approver required` tags instead.

The collapsed "Technical details" expander holds the call arguments, and on an
action card they arrive **pre-redacted** from the kernel (SPEC-055 R-7,
fail-closed), so it reads `{ "ref": "***" }` rather than the raw ref. The flow
sample's card shows the raw value in the same expander: R-7's redaction is gated
on the action kind.

Under the hood the card carries `approval_kind: "action"` and **no**
`flow_summary` — the discriminator SPEC-054 R-1 adds so the card states its own
kind rather than inferring it from ambient session state.

**Someone else approves it.** Mutating execution carries a tier-2 approval
requirement decided by `approver` or `platform-admin`, and the requester cannot
decide their own call. The portal pre-empts the click instead of letting you
make it: on an `operator`'s screen the card renders **no Approve or Deny button
at all**, only the note "This request needs a designated approver — your
current role cannot approve or deny it."

That note is a display hint (SPEC-030 R-5) and the gateway stays authoritative.
Post the decision straight to `/api/v1/chat/confirm` as the operator and it
answers `403` with `reason: not_a_designated_approver` and
`approval_tier: tier_2` — the decider-role check runs before the self-approval
one, and `operator` holds no decider role at all. `self_approval` is the reason
a *designated decider* gets on a session they own, because tier 2 blocks
self-approval even for an approver. Either way the card stays parked. That is
SPEC-030 R-4 working, not a bug in the sample.

Switch to the window signed in as **`luban-approver`** and open **Approvals** in
the sidebar — the decider-only inbox, badged with the pending count. The parked
card renders there identically to the one in the operator's transcript (same
component), under a provenance header naming the session and its owner. Approve
it; the operator's stream resumes and the agent performs the click.

Because there is no flow-unlock for unbound writes, **had the agent performed
more than one write, each would park its own card** — approving one never
unlocks the next.

After approval the agent clicks "Confirm reset", extracts the success message,
and captures a screenshot.

## Step 6: Verify the Result

The agent's final message confirms the reset. The sample admin panel is a
**static mock with no server-side state**, so these URLs only re-render their
own query parameters back at you — they report success for *any* user, including
one absent from the roster, and are not evidence that the reset happened:

```
http://localhost:9090/admin/users/?reset=alice@example.com
http://localhost:9090/admin/users/reset/done/?user=alice@example.com
```

The real evidence is in the chat transcript: a `web.extract` of `#reset-status`
— or of `#confirmation-message` on the confirmation page — reading `Password for
alice@example.com has been reset successfully.`, emitted by the target app's own
submit handler, so it shows the approved click landed; plus the `web.screenshot`
captured beside it. Do not go looking for that sentence in a `web.snapshot`: a
snapshot enumerates interactive elements only (`a, button, input, select,
textarea` and a few ARIA roles) and the status line is a plain `<p
role="status">`, so it is legitimately absent from every snapshot in the
transcript.

In the session detail (or the approvals inbox), the durable confirmation record
carries the **same** `approval_kind: "action"`, the persisted top-line `message`
(SPEC-054 R-4), and the per-call `change_request` — so a re-login and the
approver inbox render exactly the card the live stream showed. Every execution
row carries a signed receipt (SPEC-037), stamped with `action` authority
provenance (ADR-0010).

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
bash samples/web-checks/adhoc-password-reset/demo/demo.sh
```

This verifies:
1. Prerequisites (browser connector, HITL bridging)
2. Admin pages are served
3. Credential sets are loaded
4. The ad-hoc runbook is ingested **and declares no `web_target`** (the unbound
   guarantee)
5. All 15 `web.*` tools are registered with correct risk tiers

Add the opt-in chat leg (requires a running agent + the platform-gateway
port-forward) to drive the live unbound reset and assert every parked card is
`action`-kind with a change request and every execution signed:

```sh
RUN_CHAT_LEG=true bash samples/web-checks/adhoc-password-reset/demo/demo.sh
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
