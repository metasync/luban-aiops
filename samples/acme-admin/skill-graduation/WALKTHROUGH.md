# Live Walkthrough: Develop-as-You-Go Skill Graduation

This guide walks you through the whole SPEC-055 story against your running
cluster: author a procedure **ad hoc** while every write parks its own
per-action card, **graduate** the approved mutations into an executable-flow
skill, **merge** it by hand, then **replay** the same work behind a single
HITL gate.

> **Since v0.37.0 (SPEC-056)** the portal has two peer chat entries — **Chat**
> for operational sessions and **Studio** for skill development — and a
> session's type is fixed when it is created, with no conversion in either
> direction. Steps 3 to 6 below happen in **Studio**; step 8's replay happens in
> **Chat**. For the entries themselves — what each is for, and why the authoring
> controls live where they do — see the
> [Studio Guide](../../../docs/guides/studio-guide.md).

It is the third of three walkthroughs on the same `acme-admin` console. The
other two show the two approval models with a *hand-written* skill:
[`acme-admin/password-reset/WALKTHROUGH.md`](../password-reset/WALKTHROUGH.md)
(one bound flow, one gate) and
[`acme-admin/adhoc-password-reset/WALKTHROUGH.md`](../adhoc-password-reset/WALKTHROUGH.md)
(unbound, one card per write). This one shows where the bound flow comes from
when nobody wrote one.

## Prerequisites Check

Everything is already running in your cluster:

| Component | Status |
|---|---|
| Cluster (OrbStack) | ✅ Running |
| Browser connector | ✅ `GATEWAY_BROWSER_ENABLED=true` |
| Browser sidecar | ✅ 2/2 containers in the tool-gateway pod |
| `acme-admin` app | ✅ deployed (`make deploy-sample-app`) serving `/admin/` + the JSON store |
| Credential sets | ✅ `acme-admin` loaded |
| `skills-samples` ConfigMap | ✅ present (created by `make deploy-samples`) — the merge target in step 7 |
| Authoring-trace capture | ✅ SPEC-055 R-2, on by default for approved write-tier executions |
| Graduation authorized | ✅ `session:skill_graduate` granted to `operator`, `approver`, `platform-admin` (not `read-only-observer`) |
| **Studio** entry visible | ✅ SPEC-056: the sidebar shows **Studio** to exactly those same three roles — steps 3 to 6 happen there |

> **Note:** there is no runbook to install for this sample — it ships no
> `skill/` directory, because the skill is what you are about to produce. You
> do still need `make deploy-samples` to have run once, so the ConfigMap
> exists for step 7 to merge into.

## Step 1: Open the Operator Portal

Open **https://aiops.luban.metasync.cc** and sign in (silent OIDC) as
**`luban-operator`** — the dev Keycloak user in `ops-operators`; all six dev users
share the password `reconcile-luban-realm.sh` sets (see
`shared/platform-ops/gitops/dev-k8s/README.md`).

Use this canonical origin, not a `svc/web-ui` port-forward: the broker starts
every login at `OIDC_REDIRECT_URI`, so a localhost tab never receives its
callback and stays signed out (see Troubleshooting). The identity-service and
platform-gateway port-forwards this walkthrough needs are set up where they are
used — step 7 and the demo script.

`operator` holds `session:skill_graduate` and `chat:confirm`, but is **not** a
tier-2 decider — so you will need a second identity to approve in step 5. Sign in
as **`luban-approver`** in a private window when you get there.

## Step 2: Verify the Admin Target Pages

```sh
kubectl port-forward -n dev-luban-aiops svc/acme-admin 8080:8080 &
```

Open **http://localhost:8080/admin/** — the same `acme-admin` console the other
two samples use: a login form, a user table with "Reset password" links, and a
reset page that pre-fills from URL parameters and waits for a "Confirm reset"
click. Unlike the static target these samples once drove, this console mutates a
real store — each reset bumps the user's **Revision** and records
`password_changed_at`, which is what lets step 8 prove the replayed work landed.

## Step 3: Open a Skill-Development Session in Studio

Click **Studio** in the sidebar — the skill-development workspace, visible only to
`operator`, `approver` and `platform-admin` (the roles holding
`session:skill_graduate`). Click **New** (flask icon).

> **Chat's New cannot substitute.** Chat mints `operation` sessions only, so
> nothing in Chat can create a session that later graduates a captured flow.
> Chat's header offers **Draft as skill**; Studio's offers **Declare target** and
> **Graduate as skill**. A session's type is fixed at birth — there is no
> conversion either way, so start the work in the right entry.

In the **New skill-development session** dialog, declare the web target — the one
field, optional but used here:

```
http://acme-admin:8080/admin/
```

> **Important:** that is the address the *connector's* browser uses, not the
> `localhost:8080` you view in step 2. Declaring the localhost form is the
> classic mistake: capture succeeds, but graduation refuses every step with
> *"step(s) landed outside the declared target's origin."*

Click **Open session**. Only origin and path are kept (any query, fragment or
`user:password@` is dropped), and the first declaration wins for the session's
life. Declaring at birth makes the target an **authorization scope** rather than
a claim fitted to the trace afterwards, so graduation reports it as `preceded`
every step; leaving it blank and using **Declare target** later reads `postdated`
instead. Finally, give the session a title (pencil icon) — e.g. **Batch Password
Reset (Graduation Demo)** — since it becomes the graduated skill's `title` and
filename slug.

## Step 4: Author the Procedure Ad Hoc

Drive it one message at a time so you can watch each tool call and each card
land. Send these in order, waiting for the agent between them.

**1. Open the panel, unbound.**

```
Navigate to http://acme-admin:8080/admin/. Do NOT pass skill_id to
web.navigate — there is no skill yet, so this session must stay UNBOUND and each
write parks its own per-action card.
```

**2. Sign in by reference.**

```
Fill BOTH admin credential fields with web.fill_credential from the acme-admin
credential set — never web.type. Then do NOT click "Sign in": the page
auto-submits once both fields are filled, so wait for it to redirect to
/admin/users/ by itself.
```

**3. Reset alice.**

```
For alice, navigate to /admin/users/reset/ with the user and
newpw=TempPass-2026! query parameters so the form pre-fills, snapshot, then
click "Confirm reset".
```

A per-action card parks — approve it in step 5.

**4. Reset bob.** Repeat message 3 for `bob`; a second card parks.

Three constraints above are load-bearing for graduation, and each fails silently
if you drop it on the step where it matters:

- **Sign in by reference.** `web.fill_credential` is read tier, so it parks no
  card and is never captured — the secret stays out of the trace.
- **Do not click "Sign in".** The auto-login fires ~100 ms after both fields are
  filled and replaces the form; a late click lands on a detached element, the
  failed write stays in the trace with **no observed origin**, and graduation
  refuses an unverified step.
- **Do not `web.type`/`web.evaluate` a value.** Capture withholds a value
  argument by name, and a withheld value is an unresolved credential hole that
  graduation **refuses** to export. Passing the new password as a read-tier URL
  parameter keeps it out of the step list.

> Prefer one shot? Send all four actions in a single message carrying the same
> three constraints — that is what the demo script does. The step-by-step route is
> just easier to follow the first time.

## Step 5: Approve Each Per-Action Card

Nothing is bound, so each "Confirm reset" click parks its own **change-request
card** (`approval_kind: action`): a plain-language summary, the decision-relevant
fields with secrets masked, and the tool and risk level beneath. Two users, two
cards.

**Someone else approves them.** Mutating execution carries a tier-2 approval
decided by `approver` or `platform-admin`, and the requester cannot decide their
own call. On an `operator`'s screen each card renders **no Approve/Deny button**,
only the note "This request needs a designated approver — your current role
cannot approve or deny it." That note is a display hint (SPEC-030 R-5); the
gateway stays authoritative — posting the decision to `/api/v1/chat/confirm` as
the operator returns `403 not_a_designated_approver` (tier 2), because
`operator` holds no decider role. Either way the card stays parked. This is
SPEC-030 R-4 working, not a bug.

Switch to the window signed in as **`luban-approver`** and open **Approvals** in
the sidebar — the decider-only inbox, badged with the pending count. Each card
renders there identically (same component) under a provenance header naming the
session and owner. Approve each in turn; the operator's stream resumes and the
agent performs the click. Approving the first never unlocks the second — that is
the cost of authoring, and the thing graduation removes.

Behind the scenes, every approved, signed, write-tier execution is captured into
the session's **authoring trace** with the origin the connector observed it land
on. Read-tier calls (navigate, snapshot, fill_credential) are deliberately not
captured — the trace records only mutations a human authorized.

## Step 6: Graduate the Session

Click **Graduate as skill** (bolt icon) in Studio's session header. The platform
re-validates the trace against the declared target and renders the draft — no
model is involved, so the answer is either the artifact or a refusal naming every
guard the trace failed.

The **Executable-flow draft preview** shows:

- a blue **`graduated · no model`** badge (blue, not green — a different artifact
  class, not a happier draft)
- `validation: passed` and the suggested filename
  (`batch-password-reset-graduation-demo.md`)
- the blast-radius facts a prose draft cannot carry: **`2 replay steps · bound to
  http://acme-admin:8080/admin/`** and **`target declared before the
  first captured step`**. The step count is whatever this run captured — two is
  the expected shape, but the platform promises no number
- a **Rendered** / **Raw** toggle — rendered strips the frontmatter fence and
  provenance comment for reading; **Raw** is the file you will merge

Click **Download .md**. Nothing is published and the platform keeps no copy.

A refusal arrives as a modal listing step positions. The ones worth knowing:
*"no captured authoring trace"* (nothing approved, or the writes were read tier),
*"landed outside the declared target's origin"* (step 3's address), *"unresolved
credential hole"* (step 4's `web.type`), *"no observed origin"* (a failed or
oversized result, or a gateway that reported no URL — read as unverified, not
drift), and *"N captured steps exceed the 20-step budget"* (raise
`GATEWAY_BROWSER_FLOW_MAX_STEPS` and its `AGENT_SKILL_GRADUATION_MAX_STEPS` twin
together, or author a shorter procedure).

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

Step 8 works with the draft merged **as downloaded** — binding reads the skill's
`web_target` and `risk_class`, not its step list — but the four edits are what
make it a skill worth *keeping*: without them a replay's writes are the model's
improvisation inside a bound flow, not the record a human approved.

Merge it where your team's skills live — in production a Git skills repository
whose ingestion validates the document against the skill contract. Here, the
mechanical equivalent is the `samples` ConfigMap:

```sh
kubectl -n dev-luban-aiops patch configmap skills-samples --type=merge \
  --patch "{\"data\":{\"skill-graduation-batch-password-reset-graduation-demo.md\":$(python3 -c 'import json,sys; print(json.dumps(open(sys.argv[1]).read()))' ~/Downloads/batch-password-reset-graduation-demo.md)}}"
kubectl -n dev-luban-aiops rollout restart deployment/skills-hub
kubectl -n dev-luban-aiops rollout status deployment/skills-hub --timeout=180s
```

It ingests under `samples/<file name lowercased, non-alphanumerics collapsed>` —
here `samples/skill-graduation-batch-password-reset-graduation-demo`. Confirm it
in the portal's **Skills** view: set `source` to `samples` and `tag` to
`graduated`, **Apply**, then open the row's **View** (shows the
`executable-flow` / `graduated` tags, declared target, and runbook body).

> If **View** answers *"skills hub unavailable"* right after `rollout status`
> returns, the Service endpoints are still propagating — open the row again. A
> `404`, by contrast, means the id really is unknown.

The *machine-readable* halves — `kind: executable_flow`, `risk_class: write` and
the `steps` array — are on the API record but deliberately not in the viewer's
shape, so read them off the inventory proxy (what the demo's act 3 asserts).
`$TOKEN` is a platform token from the dev broker endpoint, so this needs the
identity port-forward too:

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

Replay is operational work, so go back to **Chat** and open a fresh session with
its plain **New** button (plus icon, no dialog) — no target needed; the skill
declares one. Ask for the same work by skill id:

```
Use skill samples/skill-graduation-batch-password-reset-graduation-demo to
reset the password for BOTH alice and bob to
TempPass-2026! in the acme-admin console. Bind the flow by passing skill_id to
web.navigate. Fill both admin credentials with web.fill_credential from the
acme-admin credential set and do NOT click "Sign in" — the page signs itself
in once both fields are filled. Then pass the new password as the newpw URL
parameter on each reset page so the form pre-fills.
```

This time `web.navigate` binds, so the card that parks is a **flow** card: one
decision for the whole workflow, headed by the skill's title, target origin and
risk class — plus the `flow_intent` line if you wrote one in step 7 (as
downloaded there is none, and the card shows no intent line rather than inventing
one). No per-call projection: this is a decision about a workflow, not a DOM
action. The no-sign-in-click instruction matters even more here — the one card
covers *every* write, so a click that fails on the auto-login's replaced form is
a write the graduated flow never declared.

Have **`luban-approver`** approve it once from the **Approvals** inbox, as in
step 5 — tier 2 still applies, and one gate is still one decision by someone
other than the requester. Both resets then run behind that single approval, each
individually signed and gateway-guarded, and **no second card parks**. Compare
the sessions: the authoring transcript held one card per approved reset (two
above, though the model may batch or repeat), the replay holds exactly one —
collapsing that count is the whole point of graduation.

To see the result in your own browser (the connector uses a separate headless
one), open the user list — it renders from the store, so both rows now show a
moved **Revision** and a `password_changed_at`:

```
http://localhost:8080/admin/users/
```

Then prove it against the JSON store the way the demo's act 4 does. The
`/api/users/{id}` record is auth-gated, so sign the call with the `acme-admin`
credential (`admin`, plus the password from `secret/acme-admin-credentials`):

```sh
curl -s -u admin:"$(kubectl -n dev-luban-aiops get secret acme-admin-credentials \
  -o go-template='{{index .data "ACME_ADMIN_PASSWORD" | base64decode}}')" \
  localhost:8080/api/users/bob | python3 -m json.tool
```

Both `revision` (≥ 1) and `password_changed_at` are set — the reset landed in the
store, not merely in a URL. This is the check the static target these samples
once drove could never pass: its confirmation page echoed whatever user you asked
it about, so a URL that *looked* like success proved nothing. Here the store is
authoritative. `demo.sh` asserts it for acts 1 and 4 alike — and that act 4's
revision *advanced past* act 1's, so a genuine replay is distinguished from
leftover authoring state.

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
   its own signed receipt and runs inside the gateway's origin guard and step
   budget, and the one decision is still made by an approver other than the
   requester — tier 2 does not relax just because a flow is bound. What collapsed
   was the *number of human decisions*, not the number of controls.
2. **The draft is a record, not a summary.** Every step was approved and signed
   before it ran; a step the session did not run cannot appear. That is why the
   renderer composes no `flow_intent` or `expect:` — the judgment is yours at
   merge.
3. **The declaration is evidence only because it came first.** The preview reports
   `preceded` / `postdated` rather than silently trusting the target, and the
   target cannot be widened after the fact.
4. **Graduation refuses rather than guesses.** An untouched session, an off-origin
   step, a withheld value, a trace over the replay budget — each answers `409`
   naming the guard. Nothing is exported as an empty or synthesized flow.
5. **Merging stays a human act.** The platform validates the draft against the
   skill contract and publishes nothing, because the artifact declares
   `risk_class: write` and a machine-readable replay list — once it is a skill, a
   replay runs the whole flow under one gate.

## Running the Demo Script

For the automated version, after `make deploy` and `make deploy-samples`, with
the identity-broker and platform-gateway port-forwards up:

```sh
kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000 &
kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000 &

# Deterministic legs only (no model interaction):
bash samples/acme-admin/skill-graduation/demo/demo.sh

# The full author -> graduate -> merge -> replay story:
RUN_CHAT_LEG=true bash samples/acme-admin/skill-graduation/demo/demo.sh
```

The six deterministic legs verify:
1. Browser connector enabled, HITL bridging active, and the SPEC-055 knobs sane
   — including that the graduation budget does not exceed the replay budget
2. The `acme-admin` console is served — the login page, and (after signing in
   for a session cookie) the session-gated user list and reset form
3. The `acme-admin` credential set is loaded
4. All fifteen `web.*` tools are registered with the correct risk tiers
5. A declared target is first-wins, is reported as the scope in force rather
   than echoed, and is stripped of any query, fragment or embedded credential
6. Graduation posture: an observer is denied both routes (`403`), and a session
   with no captured mutation is refused (`409`) rather than exported

Note the gateway forward is **not** chat-leg-only here: legs 5 and 6 declare
targets and attempt graduations, so the deterministic run needs it too.

With `RUN_CHAT_LEG=true` the script first reseeds the store to revision 0, then
runs all four acts. It asserts act 1's two ad-hoc resets really landed
(`/api/users/{alice,bob}` each carrying a bumped `revision` and a
`password_changed_at`), asserts act 2's draft against the trace it just captured
(step count equal to the signed write-tier executions, `declaration: preceded`,
no synthesized `flow_intent`, no secret anywhere in the artifact), merges and
re-ingests it, and asserts act 4 parks exactly one `flow` card with every
execution signed **and** that the replayed resets landed again — with the store
revision *higher* than act 1 left it, so a genuine replay is told apart from
leftover authoring state. It removes the merged ConfigMap key on exit; set
`KEEP_GRADUATED_SKILL=true` to keep it.

## Troubleshooting

| Symptom | Fix |
|---|---|
| The portal tab stays signed out after an OIDC round-trip | You opened it on a localhost port-forward. The broker starts every login at `OIDC_REDIRECT_URI`, so sign-in only round-trips on `https://aiops.luban.metasync.cc` (step 1) |
| **Graduate as skill** button missing | Two causes. You are in **Chat**, whose session header offers only **Draft as skill** — the authoring controls live in **Studio** (step 3). Or your role lacks `session:skill_graduate`, and so never sees Studio at all — sign in as an operator, approver or platform-admin |
| **Studio** missing from the sidebar | The same grant decides it: Studio is visible exactly to `operator`, `approver` and `platform-admin`. `developer`, `read-only-observer` and `auditor` keep Chat alone |
| "step(s) landed outside the declared target's origin" | You declared `localhost:8080` instead of the connector's `http://acme-admin:8080/admin/`; the declaration is first-wins and cannot be widened, so open a new skill-development session in **Studio** |
| "step(s) … have no observed origin" | A captured write **failed** — most often the model clicked "Sign in" after two `web.fill_credential` calls and hit the auto-login's already-replaced form (step 4). An unverified step is never treated as a corroborated one, so re-author in a fresh **Studio** session and let the page redirect itself |
| "the session has no captured authoring trace" | No write was approved yet, or the model only performed read-tier calls — approve at least one write-tier interaction first |
| "step(s) still carry an unresolved credential hole" | The model used `web.type`/`web.evaluate` with a value; re-author routing the secret through `web.fill_credential` or a URL parameter |
| Graduation answered `503` | The validation leg is not configured — agent-service needs both `AGENT_SKILLS_SERVICE_URL` and `AGENT_SKILLS_CLIENT_SECRET` (`sync-skills-secrets.sh`) |
| `SKILL_NOT_WEB_FLOW` on replay | Binding reads the skill's `web_target` alone (`kind`/`steps` play no part), so the merged document lost it — re-check the frontmatter survived |
| `BROWSER_FLOW_TARGET_MISMATCH` on replay | Binding requires the navigated URL to be on the declared origin **and** on-or-under its path — navigate to `/admin/`, not to `/` |
| A second card parks during replay | The flow never bound — the model navigated without `skill_id`, usually because the merged step list carries no binding `web.navigate` to follow (step 7, edit 1) |
| The graduated skill is not in the **Skills** view | skills-hub was not restarted after the ConfigMap patch, or `make deploy-samples` was re-run and dropped the key |
| "skills hub unavailable" on the skill detail | The gateway could not complete the connection. In the second or two after `rollout restart deployment/skills-hub` the Service endpoints are still propagating — retry. If it persists, check `kubectl -n dev-luban-aiops get pods -l app=skills-hub` |
| Admin pages 404 | Check the `acme-admin` port-forward is still running, and that the app is deployed (`make deploy-sample-app`) |
