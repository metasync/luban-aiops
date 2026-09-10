# Live Walkthrough: Password Reset via Browser Web-Check Tools

This guide walks you through the password-reset demo step by step against
your running cluster. You'll see the agent use browser tools to log into
a simulated admin panel and reset a user's password — with a single HITL
approval gate.

## Prerequisites Check

Everything is already running in your cluster:

| Component | Status |
|---|---|
| Cluster (OrbStack) | ✅ Running |
| Browser connector | ✅ `GATEWAY_BROWSER_ENABLED=true` |
| Browser sidecar | ✅ 2/2 containers in tool-gateway pod |
| Admin pages (nginx) | ✅ `browser-check-target` serving `/admin/` |
| Credential sets | ✅ `browser-check-target` + `admin-portal` loaded |
| ResetUserPassword skill | ✅ In skills-hub at `/skills/samples/` (installed by `make deploy-samples`) |

> **Note:** Unlike the shared browser infrastructure that `make deploy`
> provisions, this sample's skill is installed out-of-band so the platform
> never hard-wires a tutorial. If the ResetUserPassword skill is missing, run
> `make deploy-samples` from the repository root to pack it into the
> skills-hub `samples` source.

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
# Port-forward the admin target to see what the agent will interact with:
kubectl port-forward -n dev-luban-aiops svc/browser-check-target 9090:8080 &
```

Open **http://localhost:9090/admin/** in your browser. You'll see:
- A login form with username/password fields and a "Sign In" button
- After login: a user table with "Reset Password" links
- The reset page pre-fills from URL parameters and waits for a "Confirm reset" click

This is the "legacy admin panel" the agent will automate.

## Step 3: Start a Chat Session

In the operator portal:
1. Click **Chat** in the sidebar
2. You'll see the chat composer at the bottom

## Step 4: Ask the Agent to Reset a Password

Type a message in the chat composer, like:

```
Reset the password for user alice@example.com to TempPass123! in the admin portal.
Use skill samples/password-reset-resetuserpassword. Admin credentials are in the
admin-portal credential set.
```

Naming the skill and the credential set is what `demo.sh` sends, and it is the
reliable form: it closes the two ambiguities that make models stall before they
reach the gate — which runbook to follow, and where the admin password comes
from. You can try the bare one-line request instead and watch the agent discover
the skill itself (`skills.search` → `skills.get`), but if it stops to ask whether
it may proceed rather than navigating, re-send the message above. The skill's
title (`ResetUserPassword`) works in place of its id.

The agent should:
1. Search for the `ResetUserPassword` skill via `skills.search`
2. Navigate to the admin login page via `web.navigate` (binding the flow)
3. Take a snapshot via `web.snapshot` to see the login form
4. Fill the username via `web.fill_credential` (from `admin-portal` set)
5. Fill the password via `web.fill_credential` (from `admin-portal` set) —
   the login form auto-submits (legacy SSO) and redirects, no click needed
6. Navigate to the reset page via `web.navigate` with the new password as a
   URL parameter (the form pre-fills but does not submit)
7. **Click "Confirm reset"** ← this parks the single HITL confirmation card

## Step 5: Approve the HITL Gate

When the agent reaches step 7 (clicking "Confirm reset"), a **confirmation
card** appears in the chat. It shows:
- The **flow headline**: the workflow intent ("Reset User Password in Admin
  Portal") and the target origin — so you approve the reset, not a bare click
- The **decision line** (SPEC-053): the skill's authored `flow_intent` —
  "Submit the password reset for the target user, permanently changing their
  admin-portal credentials." — what approving this gate actually does
- The tool being called: `web.click` on the "Confirm reset" button
- The risk level: **write**

Its "Technical details" expander shows the call arguments **raw** — for this card
that is `{ "ref": 4 }`, the snapshot ref of the button. That is deliberate: the
SPEC-055 R-7 fail-closed redaction is gated on the *action* kind, and a flow card
renders the tool-level header instead of a change-request projection. The ad-hoc
sample's card masks the same field to `***`. Neither card carries a secret here,
because the only secret in this procedure travels as a `newpw` URL parameter on a
read-tier `web.navigate`, never as a write-tier argument.

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

After approval, the agent:
- Clicks "Confirm reset" (the admin panel performs the password reset)
- Reads the target's own status line with `web.extract`, expecting
  `Password for alice@example.com has been reset successfully.`
- Captures a screenshot as visual evidence

## Step 6: Verify the Result

The agent's final message should confirm the password was reset. You'll see:
- The tool evidence chain (all `web.*` calls with their results)
- The HITL approval record (signed receipt)
- The final snapshot showing the success page

### The Admin Portal URLs Are Not Verification

The connector drives a headless browser separate from your own, and the sample
admin panel is a **static mock with no server-side state** — every
"confirmation" page renders its own query parameters back at you. These URLs
therefore show a success banner for *any* value you pass, including a user who
is not in the roster:

```
http://localhost:9090/admin/users/?reset=alice@example.com
http://localhost:9090/admin/users/reset/done/?user=alice@example.com
```

Open them to read the mock's output in your own browser, but do not treat them
as evidence that the reset happened — they would say so regardless.

**The real evidence is in the chat transcript:**

- a `web.extract` of `#reset-status` — or of `#confirmation-message` on the
  confirmation page — reading
  `Password for alice@example.com has been reset successfully.`, emitted by the
  target app's own submit handler, so it shows the approved click landed. Do not
  go looking for that sentence in a `web.snapshot`: a snapshot enumerates
  interactive elements only (`a, button, input, select, textarea` and a few ARIA
  roles) and the status line is a plain `<p role="status">`, so it is
  legitimately absent from every snapshot in the transcript
- the `web.screenshot` captured as visual evidence
- the HITL approval record and its signed receipt (SPEC-037), stamped with
  `flow` authority provenance (ADR-0010)

## What Just Happened

```
Operator                  Agent                     Admin Panel
   │                        │                           │
   │  "reset alice's pw"    │                           │
   │───────────────────────>│                           │
   │                        │  web.navigate (bind flow) │
   │                        │──────────────────────────>│
   │                        │  web.snapshot             │
   │                        │──────────────────────────>│
   │                        │  web.fill_credential (×2) │
   │                        │──────────────────────────>│
   │                        │       (login auto-submits)│
   │                        │  web.navigate (reset URL) │
   │                        │──────────────────────────>│
   │                        │  web.click → HITL card    │
   │  ┌──────────────────┐  │      (Confirm reset)      │
   │  │ Approve reset    │  │                           │
   │  └──────────────────┘  │                           │
   │───────────────────────>│                           │
   │                        │  web.click (approved)     │
   │                        │──────────────────────────>│
   │                        │  web.snapshot (verify)    │
   │                        │──────────────────────────>│
   │  "Password reset OK"   │                           │
   │<───────────────────────│                           │
```

## Key Observations

1. **Single HITL gate**: Only the "Confirm reset" click required approval —
   the destructive mutation itself. Login and the reset-form navigation were
   read-tier (credential fill + SSO auto-submit, then a URL-based pre-fill).

2. **Credential masking**: The admin password never appeared in any tool
   output, snapshot, or screenshot — it was filled directly from the
   `admin-portal` credential set.

3. **Flow binding**: The `web.navigate` call bound the flow to the admin
   panel's origin. All subsequent operations were checked against this
   binding — the agent couldn't navigate to a different site.

4. **Evidence chain**: Every `web.*` call produced a structured evidence
   record with risk level, duration, and URL.

## Running the Demo Script

For a fully automated run (deterministic legs only — no model interaction),
after `make deploy` and `make deploy-samples`:

```sh
bash samples/web-checks/password-reset/demo/demo.sh
```

This verifies:
1. Prerequisites (cluster, pods, services)
2. Admin pages are served
3. Credential sets are loaded
4. Skill is ingested in skills-hub
5. All 15 `web.*` tools are registered with correct risk tiers

## Troubleshooting

| Symptom | Fix |
|---|---|
| Agent asks "do you want me to proceed?" and never navigates | It stalled before reaching the gate. Re-send the step-4 message naming the skill and the credential set — that is the form `demo.sh` sends and the one that reaches the card. The platform gates the write itself; the flow card *is* the gate, so the agent does not need your permission first. |
| "No web.* tools available" | Check `GATEWAY_BROWSER_ENABLED=true` on tool-gateway |
| "Credential set not found" | Run `sync-browser-credentials.sh` to refresh the secret |
| "Skill not found" | Run `make deploy-samples` to pack the skill into the `skills-samples` ConfigMap |
| Browser sidecar not ready | Check `kubectl logs -n dev-luban-aiops deploy/tool-gateway -c browser` |
| Admin pages 404 | Check `kubectl port-forward` is still running |
