# Live Walkthrough: Develop-as-You-Go Skill Graduation

This guide walks you through the whole SPEC-055 story against your running
cluster: author a procedure **ad hoc** while every write parks its own
per-action card, **graduate** the approved mutations into an executable-flow
skill, **merge** it by hand, then **replay** the same work behind a single
HITL gate.

It is the third of three walkthroughs on the same admin panel. The other two
show the two approval models with a *hand-written* skill:
[`web-checks/password-reset/WALKTHROUGH.md`](../password-reset/WALKTHROUGH.md)
(one bound flow, one gate) and
[`web-checks/adhoc-password-reset/WALKTHROUGH.md`](../adhoc-password-reset/WALKTHROUGH.md)
(unbound, one card per write). This one shows where the bound flow comes from
when nobody wrote one.

## Prerequisites Check

Everything is already running in your cluster:

| Component | Status |
|---|---|
| Cluster (OrbStack) | ✅ Running |
| Browser connector | ✅ `GATEWAY_BROWSER_ENABLED=true` |
| Browser sidecar | ✅ 2/2 containers in the tool-gateway pod |
| Admin pages (nginx) | ✅ `browser-check-target` serving `/admin/` |
| Credential sets | ✅ `browser-check-target` + `admin-portal` loaded |
| `skills-samples` ConfigMap | ✅ present (created by `make deploy-samples`) — the merge target in step 7 |
| Authoring-trace capture | ✅ SPEC-055 R-2, on by default for approved write-tier executions |
| Graduation authorized | ✅ `session:skill_graduate` granted to `operator`, `approver`, `platform-admin` (not `read-only-observer`) |

> **Note:** there is no runbook to install for this sample — it ships no
> `skill/` directory, because the skill is what you are about to produce. You
> do still need `make deploy-samples` to have run once, so the ConfigMap
> exists for step 7 to merge into.

## Step 1: Open the Operator Portal

Open **https://aiops.luban.metasync.cc** — the canonical dev-k8s portal
entrypoint — and sign in (silent OIDC; click "Sign in" if prompted) as
**`luban-operator`**, the dev Keycloak user in `ops-operators`; all six dev
users share the development-only password `reconcile-luban-realm.sh` sets (see
`shared/platform-ops/gitops/dev-k8s/README.md`).

Do not try to reach the portal through a `svc/web-ui` port-forward instead. The
identity-broker starts every login at `OIDC_REDIRECT_URI`, which makes the
origin above *the only one where sign-in round-trips*: `OIDC_EXTRA_REDIRECT_URIS`
registers further callback URIs with Keycloak for reachability, but sign-in never
selects one, so a localhost tab stays signed out while its callback lands on the
public origin. Logout is the opposite — the portal passes its own origin, which
is what the separate `OIDC_EXTRA_POST_LOGOUT_REDIRECT_URIS` list is for. The
port-forwards this walkthrough does need — identity-service and platform-gateway,
for the API reads in step 7 and for the demo script — are set up where they are
used.

`operator` holds both `session:skill_graduate` (graduate) and `chat:confirm`
(answer a parked card), but it is **not** a tier-2 decider role — so you will
need a second identity to approve, in step 5. Sign in as **`luban-approver`**
in a private window or a second browser profile when you get there.

## Step 2: Verify the Admin Target Pages

```sh
kubectl port-forward -n dev-luban-aiops svc/browser-check-target 9090:8080 &
```

Open **http://localhost:9090/admin/** — the same legacy admin panel the other
two samples use: a login form, a user table with "Reset password" links, and a
reset page that pre-fills from URL parameters and waits for a "Confirm reset"
click.

## Step 3: Open a Skill-Development Session

In **Chat**, the session panel header has two buttons: **New** and, beside it,
**Skill** (a flask icon — "Open a skill-development session against a declared
web target"). Click **Skill**.

The dialog is titled **New skill-development session** and asks for one thing
before the session exists: the web target it will work against. Enter:

```
http://browser-check-target:8080/admin/
```

> **Important:** that is the address the *connector's* browser uses, not the
> `localhost:9090` you are looking at. Declaring the localhost form is the
> classic mistake here, and it fails late rather than early: the session
> captures fine, but at graduation every step is refused with *"step(s) landed
> outside the declared target's origin"*, because the observed origin is
> `http://browser-check-target:8080`.

Click **Open session**. Only the origin and path are kept — any query,
fragment or `user:password@` you paste is dropped before it is stored, and the
first declaration wins for the life of the session.

Declaring at birth is what makes the target an **authorization scope** rather
than a claim fitted to the trace afterwards: nothing has been captured yet, so
graduation can report the declaration as `preceded` every step. (If a session
*becomes* a development session later, the chat header's **Declare target**
button does the same job — but the ordering verdict then reads `postdated`,
and the preview says so in as many words.)

Give the session a title with the pencil icon on its row — e.g. **Batch
Password Reset (Graduation Demo)**. The title becomes the graduated skill's
`title` and its suggested filename slug, so it is worth choosing now.

## Step 4: Author the Procedure Ad Hoc

Type a message that asks for the work **without binding a flow**, e.g.:

```
Working ad hoc in the legacy admin panel, reset the password for BOTH
alice@example.com and bob@example.com to TempPass-2026!. There is no skill for
this yet: do NOT pass skill_id to web.navigate, so this session stays UNBOUND
and each write parks its own per-action card. Navigate to
http://browser-check-target:8080/admin/ and fill BOTH admin credentials with
web.fill_credential from the admin-portal credential set — never web.type. Do
NOT click "Sign in": that page submits itself as soon as both fields are filled
and replaces the form, so the click would land on a detached element and fail.
Then, for each user, navigate to /admin/users/reset/ with the user and newpw
query parameters so the form pre-fills, snapshot, and click "Confirm reset".
```

Three constraints in that prompt are load-bearing for graduation:

- **Sign in by reference.** `web.fill_credential` is read tier, so it is never
  captured — the secret stays out of the trace and out of the artifact. It is
  also why the fill is not one of the two writes: a read-tier call parks no card
  and enters no trace, even though it touches the page.
- **Do not click "Sign in".** The admin login page carries a legacy-SSO
  auto-login timer that fires within 100 ms of *both* credential fields holding
  a value: it hides the form and navigates to `/admin/users/` by itself. A click
  on that button after two fills therefore cannot land — the dev-k8s live check
  of this sample failed with exactly that, `ElementHandle.click: Element is not
  attached to the DOM`. The model recovered and finished both resets, but the
  failed write stayed in the trace with **no observed origin**, and graduation
  refuses an unverified step: fabricating an origin would corroborate a mutation
  that never happened, and dropping the step would graduate a flow the operator
  never approved. Wait for the redirect instead.
- **Do not `web.type` or `web.evaluate` a value.** Capture withholds a value
  argument by name, and a withheld value is an unresolved credential hole that
  graduation **refuses** to export. Passing the new password as a read-tier URL
  parameter is what keeps it out of the step list.

## Step 5: Approve Each Per-Action Card

Nothing is bound, so each "Confirm reset" click parks its own **change-request
card** (`approval_kind: action`): a plain-language summary, the
decision-relevant fields with secrets masked, and the tool and risk level
beneath — exactly what the ad-hoc walkthrough shows. Two users, two cards.

**Someone else approves them.** Mutating execution carries a tier-2 approval
requirement decided by `approver` or `platform-admin`, and the requester cannot
decide their own call. The portal pre-empts the click instead of letting you
make it: on an `operator`'s screen each card renders **no Approve or Deny button
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

Switch to the window signed in as **`luban-approver`** and open **Approvals**
in the sidebar — the decider-only inbox, badged with the pending count. Each
parked card renders there identically to the one in the operator's transcript
(same component), under a provenance header naming the session and its owner.
Approve each in turn; the operator's stream resumes and the agent performs the
click. Approving the first never unlocks the second: that is the cost of
authoring, and the thing graduation is about to remove.

While the approvals land, the platform is doing the part nobody sees: every
approved, signed, write-tier execution is captured into the session's
**authoring trace**, together with the origin the connector observed it land
on. Read-tier calls (navigate, snapshot, fill_credential) are deliberately not
captured — the trace is a record of mutations a human authorized.

## Step 6: Graduate the Session

Click **Graduate as skill** (a bolt icon) in the chat header. The platform
re-validates the trace against the declared target and renders the draft. No
model is involved, so the answer is either the artifact or a refusal naming
every guard the trace failed.

The preview that opens is titled **Executable-flow draft preview**:

- a blue **`graduated · no model`** badge — blue, not green, because this is a
  different artifact class rather than a happier draft
- `validation: passed` and the suggested filename
  (`batch-password-reset-graduation-demo.md`)
- the blast-radius facts a prose draft cannot carry: **`2 replay steps · bound
  to http://browser-check-target:8080/admin/`**, and beneath it **`target
  declared before the first captured step`**. The step count is whatever this run
  actually captured — two is the expected shape for one approved reset per user,
  but the platform does not promise a number, and a run that batched or repeated
  a click reports its own
- **Rendered** / **Raw** toggle. The rendered view strips the frontmatter fence
  and the provenance comment for reading; **Raw** shows the file you are about
  to merge, frontmatter and all

Click **Download .md**. Nothing is published and the platform keeps no copy —
the response is ephemeral by construction.

A refusal arrives as a modal, not a toast, because it lists step positions and
is your only remedy. The ones worth knowing: *"the session has no captured
authoring trace"* (nothing was approved, or the writes were read tier),
*"step(s) landed outside the declared target's origin"* (step 3's address),
*"step(s) still carry an unresolved credential hole"* (step 4's `web.type`),
*"step(s) … have no observed origin"* (a result that did not succeed, a payload
over the evidence frame's size guard, or a gateway that reported no URL — all
three read as *unverified* rather than as a drift), and *"N captured steps exceed
the 20-step budget a bound flow replays under"* (raise
`GATEWAY_BROWSER_FLOW_MAX_STEPS` and its `AGENT_SKILL_GRADUATION_MAX_STEPS`
twin together, or author a shorter procedure).

## Step 7: Merge It by Hand

Read the draft's own **"Before you merge this"** advisory — it is the honest
list of what a machine cannot do. For this procedure there are four edits:

1. **Add the binding step.** The step list holds only *mutating* steps, so it
   carries no `web.navigate` — and `web.navigate(skill_id=…)` is the only call
   that binds a flow, which is what arms the origin guard and the step budget.
   Add it as step 1, pointing at the declared target and carrying the skill id
   the merge assigns.
2. **Add the login step.** `web.fill_credential` is read tier and was never
   captured, so the flow as rendered does not authenticate. Add the reference
   step naming the credential set and field.
3. **Replace the element refs.** A captured `web.click` carries the
   snapshot-relative ref that was live at the time (`args: {"ref": 12}`). Those
   are not durable. Give each step a selector or description a later snapshot
   will still resolve.
4. **Write the `flow_intent`.** The renderer composes no decision line and no
   `expect:` post-condition, because neither is derivable from a trace of what
   ran. The one-gate card headlines whatever you write here, so write the
   sentence an approver should decide on.

Step 8 works with the draft merged **as downloaded**: binding reads the skill's
`web_target` and `risk_class`, not its step list, so the flow still binds and
still collapses to one gate. The four edits are what make it a skill worth
*keeping* — without them the writes a replay performs are the model's
improvisation inside a bound flow rather than the record a human approved.

Then merge it where your team's skills live. In a real deployment that is a
Git skills repository whose ingestion validates the document against the skill
contract. For this walkthrough, the mechanical equivalent is the `samples`
ConfigMap:

```sh
kubectl -n dev-luban-aiops patch configmap skills-samples --type=merge \
  --patch "{\"data\":{\"skill-graduation-batch-password-reset-graduation-demo.md\":$(python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' ~/Downloads/batch-password-reset-graduation-demo.md)}}"
kubectl -n dev-luban-aiops rollout restart deployment/skills-hub
kubectl -n dev-luban-aiops rollout status deployment/skills-hub --timeout=180s
```

The id it ingests under is `samples/<mounted file name lowercased,
non-alphanumerics collapsed>` — here
`samples/skill-graduation-batch-password-reset-graduation-demo`. Confirm it in
the portal's **Skills** view (sidebar → Skills): set `source` to `samples` and
`tag` to `graduated`, press **Apply**, then open the row's **View**. The viewer
shows the `executable-flow` / `graduated` tags, the declared target, and the
runbook body with the step list restated for reading.

> If **View** answers *"skills hub unavailable"* in the second or two after
> `rollout status` returns, that is the gateway reporting a connection it could
> not complete while the Service endpoints finish propagating — not a verdict
> about your skill. Open the row again. The demo's act 3 retries that same call
> on that status code for exactly this reason, and only on it: a `404` there
> means the id really is unknown.

The *machine-readable* halves — `kind: executable_flow`, `risk_class: write`
and the `steps` array — are on the API record but deliberately not in the
viewer's shape, so read them off the inventory proxy instead (this is exactly
what the demo's act 3 asserts). `$TOKEN` is a platform token from the dev
broker endpoint the demo script uses, so this needs the identity port-forward
too:

```sh
kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000 &
TOKEN=$(curl -fsS -X POST http://localhost:18081/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"luban-operator","email":"luban-operator@luban-aiops.local","roles":["operator"],"groups":["ops-operators"]}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000 &
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:18083/api/v1/skills/samples/skill-graduation-batch-password-reset-graduation-demo" \
  | python3 -m json.tool | head -30
```

> **Note:** `make deploy-samples` recreates that ConfigMap declaratively, so
> re-running it drops the key. That is the right behaviour for a demo artifact
> and the wrong one for a real skill — which is exactly why the platform hands
> you a file instead of publishing it.

## Step 8: Replay Under One Gate

Open a fresh session with the plain **New** button — no target needed now; the
skill declares one. Ask for the same work by skill id:

```
Use skill samples/skill-graduation-batch-password-reset-graduation-demo to
reset the password for BOTH alice@example.com and bob@example.com to
TempPass-2026! in the legacy admin panel. Bind the flow by passing skill_id to
web.navigate. Fill both admin credentials with web.fill_credential from the
admin-portal credential set and do NOT click "Sign in" — the page signs itself
in once both fields are filled. Then pass the new password as the newpw URL
parameter on each reset page so the form pre-fills.
```

The no-sign-in-click instruction carries over from step 4 for the same reason,
and it is worth twice as much here: the flow card you are about to approve
covers *every* write in the replay, so a click that fails on the auto-login's
already-replaced form is a write the graduated flow never declared.

This time `web.navigate` binds, and the card that parks is a **flow** card: one
decision for the whole workflow, headed by the skill's title, the target origin
and the risk class — plus the `flow_intent` decision line if you wrote one in
step 7 (as downloaded there is none, and the card honestly shows no intent
line rather than inventing one). There is no per-call change-request
projection: this is a decision about a workflow, not about a DOM action.

Have **`luban-approver`** approve it once from the **Approvals** inbox, exactly
as in step 5 — tier 2 still applies, and one gate is still one decision by
someone other than the requester. Both resets then run behind that single
approval, each individually signed and gateway-guarded, and **no second card
parks**. Compare the two sessions side by side: however many cards the
authoring transcript holds — one per approved reset, so two for the prompt
above, but the model may batch or repeat — the replay session's holds exactly
one, and collapsing that count is the whole point of graduation.

To see the result in your own browser (the connector uses a separate headless
one):

```
http://localhost:9090/admin/users/?reset=bob@example.com
```

## What Just Happened

```
AUTHORING — no skill bound, so every write parks its own card

  Operator             Agent                     Approver
     │  "reset both"     │                           │
     │──────────────────>│                           │
     │                   │ navigate (no skill_id)    │  nothing binds
     │                   │ fill_credential ×2        │  read tier, uncaptured
     │                   │ navigate(reset?newpw=…)   │
     │                   │ click "Confirm reset"     │
     │                   │────── ACTION card ───────>│
     │                   │                      ┌────┴─────┐
     │                   │                      │ Approve  │  decision 1 of 2
     │                   │<── signed write ─────┴──────────┘
     │                   │ navigate(reset?newpw=…)   │
     │                   │ click "Confirm reset"     │
     │                   │────── ACTION card ───────>│
     │                   │                      ┌────┴─────┐
     │                   │                      │ Approve  │  decision 2 of 2
     │                   │<── signed write ─────┴──────────┘
     │                   │
     │  Graduate as skill (bolt icon)
     │──────────────────>│  re-validate the trace against the declared
     │<─── draft .md ────│  target, render the flow — no model call
     │
     │  human merge: binding step, login step, durable refs, flow_intent
     │──────────────────────────────────────────>  skills-hub ingests it


REPLAY — the graduated skill binds, so the same work costs one decision

  Operator             Agent                     Approver
     │  "use skill …"    │                           │
     │──────────────────>│                           │
     │                   │ navigate(skill_id=…)      │  FLOW BINDS
     │                   │ fill_credential ×2        │  read tier
     │                   │ navigate(reset?newpw=…)   │
     │                   │ click "Confirm reset"     │
     │                   │─────── FLOW card ────────>│
     │                   │                      ┌────┴─────┐
     │                   │                      │ Approve  │  the ONLY decision
     │                   │<─────────────────────┴──────────┘
     │                   │ write 1 runs, signed      │
     │                   │ write 2 runs, signed      │  no second card parks
```

## Key Observations

1. **N became 1, and nothing got weaker.** Every replayed write still carries
   its own signed receipt and still runs inside the gateway's origin guard and
   step budget — and the one decision is still made by an approver other than
   the requester, because tier 2 does not relax just because a flow is bound.
   What collapsed was the *number of human decisions*, not the number of
   controls.
2. **The draft is a record, not a summary.** Every step in it was approved and
   signed before it ran; a step the session did not run cannot appear. That is
   why the renderer refuses to compose a `flow_intent` or an `expect:` — the
   judgment is yours to add at merge.
3. **The declaration is evidence only because it came first.** The preview
   reports `preceded` / `postdated` rather than silently trusting the target,
   and the target cannot be widened after the fact: a second, different
   declaration reports the scope already in force.
4. **Graduation refuses rather than guesses.** An untouched session, an
   off-origin step, a withheld value, a trace over the replay budget — each
   answers `409` naming the guard. Nothing is exported as an empty or
   synthesized flow.
5. **Merging stays a human act.** The platform validates the draft against the
   skill contract before handing it over and publishes nothing, because the
   artifact declares `risk_class: write` and a machine-readable replay list:
   once it is a skill, a replay runs the whole flow under one gate.

## Running the Demo Script

For the automated version, after `make deploy` and `make deploy-samples`, with
the identity-broker and platform-gateway port-forwards up:

```sh
kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000 &
kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000 &

# Deterministic legs only (no model interaction):
bash samples/web-checks/skill-graduation/demo/demo.sh

# The full author -> graduate -> merge -> replay story:
RUN_CHAT_LEG=true bash samples/web-checks/skill-graduation/demo/demo.sh
```

The six deterministic legs verify:
1. Browser connector enabled, HITL bridging active, and the SPEC-055 knobs sane
   — including that the graduation budget does not exceed the replay budget
2. The admin pages are served (login, user list, reset form)
3. The `admin-portal` credential set is loaded
4. All fifteen `web.*` tools are registered with the correct risk tiers
5. A declared target is first-wins, is reported as the scope in force rather
   than echoed, and is stripped of any query, fragment or embedded credential
6. Graduation posture: an observer is denied both routes (`403`), and a session
   with no captured mutation is refused (`409`) rather than exported

Note the gateway forward is **not** chat-leg-only here: legs 5 and 6 declare
targets and attempt graduations, so the deterministic run needs it too.

With `RUN_CHAT_LEG=true` the script then runs all four acts, asserts act 2's
draft against the trace it just captured (step count equal to the signed
write-tier executions, `declaration: preceded`, no synthesized `flow_intent`,
no secret anywhere in the artifact), merges and re-ingests it, and asserts act
4 parks exactly one `flow` card with every execution signed. It removes the
merged ConfigMap key on exit; set `KEEP_GRADUATED_SKILL=true` to keep it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| The portal tab stays signed out after an OIDC round-trip | You opened it on a localhost port-forward. The broker starts every login at `OIDC_REDIRECT_URI`, so sign-in only round-trips on `https://aiops.luban.metasync.cc` (step 1) |
| **Graduate as skill** button missing | Your role lacks `session:skill_graduate` — sign in as an operator, approver or platform-admin |
| "step(s) landed outside the declared target's origin" | You declared `localhost:9090` instead of the connector's `http://browser-check-target:8080/admin/`; the declaration is first-wins, so open a new skill-development session |
| "step(s) … have no observed origin" | A captured write **failed** — most often the model clicked "Sign in" after two `web.fill_credential` calls and hit the auto-login's already-replaced form (step 4). An unverified step is never treated as a corroborated one, so re-author in a fresh session and let the page redirect itself |
| "the session has no captured authoring trace" | No write was approved yet, or the model only performed read-tier calls — approve at least one write-tier interaction first |
| "step(s) still carry an unresolved credential hole" | The model used `web.type`/`web.evaluate` with a value; re-author routing the secret through `web.fill_credential` or a URL parameter |
| Graduation answered `503` | The validation leg is not configured — agent-service needs both `AGENT_SKILLS_SERVICE_URL` and `AGENT_SKILLS_CLIENT_SECRET` (`sync-skills-secrets.sh`) |
| `SKILL_NOT_WEB_FLOW` on replay | Binding reads the skill's `web_target` alone (`kind`/`steps` play no part), so the merged document lost it — re-check the frontmatter survived |
| `BROWSER_FLOW_TARGET_MISMATCH` on replay | Binding requires the navigated URL to be on the declared origin **and** on-or-under its path — navigate to `/admin/`, not to `/` |
| A second card parks during replay | The flow never bound — the model navigated without `skill_id`, usually because the merged step list carries no binding `web.navigate` to follow (step 7, edit 1) |
| The graduated skill is not in the **Skills** view | skills-hub was not restarted after the ConfigMap patch, or `make deploy-samples` was re-run and dropped the key |
| "skills hub unavailable" on the skill detail | The gateway could not complete the connection. In the second or two after `rollout restart deployment/skills-hub` the Service endpoints are still propagating — retry. If it persists, check `kubectl -n dev-luban-aiops get pods -l app=skills-hub` |
| Admin pages 404 | Check the `browser-check-target` port-forward is still running |
