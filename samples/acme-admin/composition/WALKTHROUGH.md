# Live Walkthrough: Recover a Locked-Out ACME Admin Account

Rung 5, and the top of the ladder. You will ask the agent, in **Chat**, to
follow **one** `kind: composition` skill — a runbook that names two skills this
suite already ships and adds nothing of its own but their order. The agent will
park **two** confirmation cards on **one** session:

1. a card of kind **`flow`** — the password reset, through the console's browser
   UI (rung 4's skill); then
2. a card of kind **`action`** — the unlock, over one `http.post` (rung 3's
   skill).

A **second identity** approves each. That two-card count is the whole claim a
composition has to earn: **ordering two mutating skills into a runbook does not
merge their gates.** Each sub-skill still parks its own card, decided by its own
approver, because a composition carries **no authority of its own** (ADR-0011) —
it mints no token, pre-binds no flow, and auto-approves nothing.

Rungs 3 and 4 each parked one card of a different `approval_kind`. This rung
puts both kinds on one session, in one runbook, and shows the gate count is the
**sum** of its parts (2) rather than one card that "covers" the other.

Everything below is also exercised unattended by
[`demo/demo.sh`](demo/demo.sh); the mapping is tabulated at the end. The five
**deterministic** legs are read-only against skills-hub and prove the catalog
facts (the composition resolves, derives `risk_class: write`, nests nothing);
only the opt-in chat leg exercises the two approvals.

**Portal surface: Chat** — for both identities. The operator asks in Chat; the
approver decides in **Approvals**, the decider-only inbox. Nothing here uses
**Studio** (SPEC-056); a composition is authored by hand or in Studio and merged
to Git like any other skill.

## Prerequisites

| Component | What must be true | Check it with |
|---|---|---|
| Cluster | dev-k8s deployed | `kubectl -n dev-luban-aiops get pods` |
| Browser surface | `GATEWAY_BROWSER_ENABLED=true`, origin on `GATEWAY_BROWSER_ALLOW_ORIGINS` — step 1 of the runbook resets through the console UI | `platform-runtime-config` |
| HTTP surface | `GATEWAY_HTTP_ENABLED=true`, origin on `GATEWAY_HTTP_ALLOW_ORIGINS` — step 2 unlocks over `http.post` | same ConfigMap |
| Mutating surface | `GATEWAY_MUTATING_TOOLS_ENABLED=true`, or neither `web.click` nor `http.post` is registered and no card can appear | same ConfigMap |
| Browser sidecar | 2/2 containers in the tool-gateway pod | `kubectl logs -n dev-luban-aiops deploy/tool-gateway -c browser` |
| HITL bridging | `AGENT_HITL_CONFIRM_TIMEOUT` not `0` **on agent-platform** — it is not a gateway ConfigMap key | `kubectl -n dev-luban-aiops exec deploy/agent-service -- printenv AGENT_HITL_CONFIRM_TIMEOUT`; empty output (exit 1) means unset, so the default `600` applies. An explicit `0` excludes write-tier tools from the toolkit entirely |
| Credential set | `acme-admin` present with a non-empty password | the demo's `require_credential_set` leg |
| `acme-admin` app | deployed and ready | `make deploy-sample-app` |
| All three skills installed | the composition **and both sub-skills** packed into the one `samples` source, so they resolve within a single sync cycle | `make deploy-samples` — check `/skills/samples/composition-RecoverAcmeAccount.md`, `password-reset-ResetAcmePassword.md` and `lock-unlock-user-LockUnlockUser.md` are all mounted |
| Two identities | `luban-operator` **and** `luban-approver` | step 2 |
| A one-time password | you generate it; you type it into the chat | step 4 |
| Portal | reachable at the canonical origin | open `https://aiops.luban.metasync.cc` |

Two mutating sub-skills means **two approvals**, and the same rule binds each:
the requester cannot decide their own call (SPEC-030 R-4). This is not a
formality you can skip by using one identity twice.

## Step 1: Note the starting state

```sh
kubectl -n dev-luban-aiops port-forward svc/acme-admin 8080:8080 &
```

Open **http://localhost:8080/admin/** and sign in (`admin`, plus the password
from `secret/acme-admin-credentials` — rung 2's Step 1 prints the command that
reads it). Find **`dave`**'s row and note two cells:

- **Status** — `locked` (the seed pre-locks him, which is exactly the
  locked-out account this runbook recovers)
- **Revision** — `0` on a fresh or reseeded store

`dave` is the right target here, where rung 3 told you to avoid him: a recovery
is a *reset then an unlock*, and both are real transitions against a locked
account. Recovering an already-active user would make step 2 a `409
NO_OP_MUTATION` that proves nothing. Write the revision down; step 7 is only
meaningful if you can compare.

Choose a **one-time** password, e.g. `TempPass-2026!`. It is a throwaway value
for a store that discards it: the app records *when* the reset happened and which
revision it produced, and never stores the password.

## Step 2: Sign in twice

Open **https://aiops.luban.metasync.cc** and sign in as **`luban-operator`**.
Then open a **private window or a second browser profile** and sign in there as
**`luban-approver`**.

You will need both at steps 5 and 6 — once for each card. Do not reach the portal
through a `svc/web-ui` port-forward: the broker builds every authorization URL
from `OIDC_REDIRECT_URI` (the canonical origin), so a localhost tab never
receives the code and stays signed out. See `Runtime Wiring` in
`shared/platform-ops/gitops/dev-k8s/README.md`.

## Step 3: Open a Chat session as the operator

In the `luban-operator` window, click **Chat** and start a new session. **One**
session carries both cards — that is the point of the count in step 7.

## Step 4: Ask for the recovery

Paste this into the composer as one block — **Enter sends**, so typing it line by
line submits the first line on its own (Shift+Enter makes a newline):

```
Recover the locked-out acme-admin account for 'dave' by following the runbook
skill samples/composition-recoveracmeaccount: first reset the password to
'TempPass-2026!' through the console UI, then unlock the account over the API.
Admin credentials are in the acme-admin credential set — do not ask me for a
password.
```

Naming the **runbook** skill, the credential set, the target, the one-time value
and the direction is what `demo.sh`'s chat leg sends. The runbook is grounded
guidance, not a program: you have told the model the order you want (reset then
unlock), and it will follow it — but the platform enforces nothing about that
order. What makes either order safe is that each mutating sub-skill still gates
on its own.

The one-time value must be in the message: it is a chat-supplied secret, never
stored in the skill, never committed, and — as rung 4's walkthrough shows — every
human-readable projection (title, transcript, live stream, cards, tool evidence)
masks it. The value stays real only in the agent's own context, because the reset
needs it.

## Step 5: The FIRST card — `flow` (the password reset)

The agent begins step 1 of the runbook: it follows
`samples/password-reset-resetacmepassword`, binds the browser flow (`web.navigate`
with that `skill_id`), signs in, opens the pre-filled reset form, and makes its
**single write-tier click** on `#confirm-reset`. That is where the first card
parks. It shows:

- `approval_kind` = **`flow`** — one approval covers the flow's remaining
  write-tier interactions (ADR-0007), because a bound browser flow was armed.
- The **`flow_intent` headline** from the reset skill's frontmatter (SPEC-053
  R-4), above the demoted DOM detail: *"Submit the password reset for the target
  acme-admin account…"*. Display-only, never a security input, and it carries no
  credential.
- The bound target origin and the write-tier interaction being authorised.
- **No plaintext one-time value** in any confirmation frame.

**The operator cannot approve it.** On an `operator`'s screen the card renders
**no Approve or Deny button**, only the note "This request needs a designated
approver — your current role cannot approve or deny it." That note is a display
hint (SPEC-030 R-5); the gateway stays authoritative and answers a self-posted
decision with `403 not_a_designated_approver`, `approval_tier: tier_2`.

Switch to the **`luban-approver`** window, open **Approvals** (badged with the
pending count), and approve the card there. It renders identically to the
operator's copy (same component), under a provenance header naming the session
and its owner. The operator's stream resumes, the click executes, and the reset
skill verifies from a **second surface** — one `http.get` against
`/api/users/dave` reporting the bumped `revision` and a set `password_changed_at`.
**Wait for that verification before the runbook continues**; step 2 is only
meaningful once the account has a usable password.

## Step 6: The SECOND card — `action` (the unlock)

The agent continues to step 2 of the runbook: it follows
`samples/lock-unlock-user-lockunlockuser` in the **unlock** direction against the
same user, and makes **one** `http.post`. That call parks the second card — on the
**same session**. It shows:

- `approval_kind` = **`action`** — one approval for exactly one call. Nothing was
  bound here, so unlike the `flow` card this decision covers only this `http.post`.
- The pending call **`http.post`**, `risk_level` = **`write`**, and a legible
  `change_request.summary`:

  ```
  POST to http://acme-admin:8080/api/users/dave/unlock — 1 field: locked
  ```

- A `credential_set` row naming the reference **`acme-admin`** — never a value.
- **No `flow_summary`.** This is the assertion the demo makes explicitly: the
  action card carries none of the browser flow's authority, so the infra write
  does **not** inherit the reset's blanket approval. ADR-0007 covers one bound
  flow, not the runbook. No card claims authority over a sub-skill it does not
  name.

> **If no second card appears on its own:** the model may finish the reset and
> stop, waiting for you to confirm the next step. That is fine — the runbook is
> guidance, not a sequencer. Send a short follow-up naming step 2 (`unlock 'dave'
> over the API with skill samples/lock-unlock-user-lockunlockuser`); the card
> lands on the same session either way, and the durable count in step 7 is what
> matters. `demo.sh` sends exactly this nudge when the resumed turn carries no
> card.

**The operator cannot approve it either** — same note, same `403`. Approve it in
the **`luban-approver`** window's **Approvals** inbox. The unlock executes and
the response reports `locked: false` and a further bumped `revision`.

## Step 7: Read the outcome — two cards, one account recovered

The resumed turn reports **each sub-skill's own evidence** rather than a single
blended "done":

| From | Field | What it tells you |
|---|---|---|
| step 1 (reset) | `password_changed_at` | the reset really ran, from the JSON API |
| step 1 (reset) | `revision` | the bump the reset produced |
| step 2 (unlock) | `locked` | `false` — the account is active |
| step 2 (unlock) | `revision` | a further bump, on the same store |

Quote both so the operator can see which step produced which fact — the runbook
never becomes the place a reader has to trust.

Now count the cards on this session: **two** — one `flow`, one `action`. That is
the multi-binding gate count. Rung 3 parked one, rung 4 parked one; composing
them parks **two**, because a composition's gate count is the **sum** of its
sub-skills' gates and the platform has no mechanism to produce a single card that
authorises both.

Reload **http://localhost:8080/admin/users/** in your own browser: `dave`'s Status
reads `active`, his Revision moved by two (one per mutation), `password_changed_at`
is set, and the footer's store revision matches. The strongest cross-check is to
ask the agent for it in a **new Chat session** using rung 2's skill:

```
Read the current status of the acme-admin user 'dave' from the admin console and
tell me whether the account is active or locked, plus its revision. Use skill
samples/user-status-checkuserstatus. Admin credentials are in the acme-admin
credential set.
```

That is the suite's cross-skill verification: a recovery made over **two
surfaces** (a browser flow and an HTTP call), observed over **HTML**, against
**one store**. `demo-suite.sh` asserts this agreement after all five rungs.

## Honest caveats

- **Two cards is the correct count, not a stuck flow.** If you see one card for
  the reset and, after approving it, a second for the unlock, that is the runbook
  working. A single card claiming to authorise both would be the bug — and there
  is no mechanism to produce one, because the composition carries no authority.
- **It is not a transaction.** There is no rollback and no compensation. If step 1
  is denied or errors, do not attempt step 2 — the account still has its old
  password and its lock. If step 1 succeeds and step 2 is denied or errors, **the
  password is already changed** and the account is still locked; say exactly that,
  name the sub-skill that stopped, and do not retry around the denial. A denial is
  an answer.
- **`409 NO_OP_MUTATION` on step 2** means the account was already active. Nothing
  changed and the revision did not move; report "already unlocked" and treat the
  runbook as complete for that step. It is an answer, not a failure, and not a
  reason to re-run step 1.
- **The order is guidance, not enforced.** The platform never pre-binds a
  sub-skill, never issues `web.navigate` on the model's behalf, and never enforces
  the declared sequence. The model may run the two in either order, skip one, or
  stop — and the gates are what make each choice safe.
- **A cross-source sub-skill resolves eventually.** Both sub-skills here ship in
  the same `samples` source, so they resolve in one cycle. A composition whose
  sub-skill lives in a *different* source is rejected on the sync cycle before
  that source has synced, and accepted on a later one — eventual consistency,
  documented rather than papered over. This runbook deliberately does not depend
  on it.
- **The deterministic legs prove the catalog, not the gate.** Legs 1–5 are
  read-only against skills-hub: they show the composition resolves, derives
  `risk_class: write`, and nests nothing. Only the chat leg — steps 4 to 7 —
  exercises an approval. Conflating the two is how a demo ends up claiming a gate
  it never ran.
- **Re-entry is bounded.** The completed prefix is recoverable from the platform's
  signed execution receipts, swept at **30 days** (`execution_records.py:31`).
  Inside that window an operator resuming the runbook can see step 1 already ran;
  outside it, restart from the beginning. Either way each sub-skill **re-gates** on
  re-entry — a receipt is a record, not a standing approval.
- **The store is in memory.** A pod restart reverts it to the seed, and the
  Deployment pins `replicas: 1` because two replicas would be two consoles that
  disagree.

## What just happened

```
Operator          Agent        kernel HITL       Approver        acme-admin
   │                │               │               │               │
   │ "recover dave" │               │               │               │
   │  (runbook)     │               │               │               │
   │───────────────>│               │               │               │
   │                │  STEP 1 · password-reset (bound browser flow)  │
   │                │ web.navigate (bind) … web.click #confirm-reset │
   │                │──────────────>│  PARK         │               │
   │  ┌───────────┐ │               │  ┌──────────┐ │               │
   │  │ flow card │ │               │  │Approvals │ │               │
   │  │ + intent  │ │               │  │  inbox   │ │               │
   │  └───────────┘ │               │  └──────────┘ │               │
   │                │               │<──────────────│ approve       │
   │                │               │───────────────────────────────>│
   │                │  200 revision=N password_changed_at            │
   │                │<──────────────│<───────────────────────────────│
   │                │  STEP 2 · lock-unlock-user (one http.post)     │
   │                │ http.post /api/users/dave/unlock (write)       │
   │                │──────────────>│  PARK         │               │
   │  ┌───────────┐ │               │  ┌──────────┐ │               │
   │  │action card│ │               │  │Approvals │ │               │
   │  │ no flow   │ │               │  │  inbox   │ │               │
   │  └───────────┘ │               │  └──────────┘ │               │
   │                │               │<──────────────│ approve       │
   │                │               │───────────────────────────────>│
   │                │  200 locked=false revision=N+1                 │
   │                │<──────────────│<───────────────────────────────│
   │ "dave active,  │               │               │               │
   │  new password" │               │               │               │
   │<───────────────│               │               │               │
```

Two PARKs, two approvals, one session. The composition never appears as an actor
in this diagram — it named the two sub-skills and their order, and the platform
gated each on its own.

## Step ↔ demo mapping

| Walkthrough step | Demo leg |
|---|---|
| Step 1 — the composition and both sub-skills are mounted | leg 1: `require_skill composition RecoverAcmeAccount.md` matches the title, `kind: composition` and both sub-skill ids |
| Step 1 — the runbook declares no authority of its own | leg 1: `require_no_frontmatter_key` for `web_target`, `steps` and `risk_class` |
| Step 4 — the runbook resolves to two ordered sub-skills | leg 2: `get_skill` returns `kind: composition`, the two ids **in order**, each enriched with `resolved_title`; the browser sub-skill also carries `resolved_web_target`, the infra one does not |
| Step 4 — the derived `risk_class` is `write` | leg 2: `risk_class == "write"`, computed at sync because a resolved sub-skill is `write` — the document declares none |
| Step 5/6 — no nesting: both sub-skills are leaves | leg 3: `get_skill` on each sub-skill asserts `kind != "composition"`, and the `samples` source synced with zero rejections naming the runbook |
| Step 4 — the structural pre-flight fails closed | leg 4: an over-cap list, a self-declared `risk_class` and a smuggled `on_fail` sequencing key are each rejected by `/skills/validate` (R-3: no control flow) |
| The two-layer split (why nesting is a resolution rejection) | leg 5: the catalog-blind pre-flight **passes** a nested reference — leg 3 asserts the rule holds live, and skills-hub's `test_sync.py` asserts the negative |
| Step 5 — one card, kind `flow`, for the reset | chat leg: `require_card_shape … flow` against the write-tier web tool set |
| Step 6 — one card, kind `action`, for the unlock | chat leg: `require_card_shape … action http.post` |
| Step 6 — the action card claims no flow authority | chat leg: `first_card_field … flow_summary.skill_id` must be empty |
| Step 5/6 — a second identity decides both | chat leg: `chat_confirm` posts as `luban-approver`, asserting `"status": "approved"` for each card |
| Step 7 — exactly two cards, not one | chat leg: `require_card_count "$CHAT_SESSION" 2` on the **durable** session |
| Step 7 — the store moved and the console agrees | `../demo-suite.sh`'s cross-skill leg after all five rungs |

```sh
make deploy-samples   # packs the composition + both sub-skills into `samples`

sh samples/acme-admin/composition/demo/demo.sh                       # deterministic legs only
RUN_CHAT_LEG=true sh samples/acme-admin/composition/demo/demo.sh      # + the two cards and approvals
TARGET_USER=dave NEW_PASSWORD='Another-Temp-1!' \
  RUN_CHAT_LEG=true sh samples/acme-admin/composition/demo/demo.sh
```

The chat leg needs the identity-service port-forward on `18081` **and** the
platform-gateway port-forward on `18083`, because it issues tokens for both
identities itself.

## Key observations

1. **Two mutating sub-skills, two cards — the sum, never one.** A composition's
   gate count is the sum of its sub-skills' gates. The platform has no mechanism
   to merge them, because the composition carries no authority to merge with.
2. **Two kinds on one session.** The `flow` card (a bound browser flow, one
   approval covering its remaining writes) and the `action` card (one `http.post`,
   one decision) are the pair you saw separately in rungs 3 and 4 — now in one
   runbook, which is the clearest live demonstration that the discriminator is
   per-binding, not per-runbook.
3. **No card claims authority it does not have.** The action card carries no
   `flow_summary`: the infra write does not inherit the browser flow's blanket
   approval. ADR-0007 covers one bound flow, not the runbook that named it.
4. **The derived `risk_class` is display-only.** skills-hub derives `write` for
   the catalogue badge; it is read by the Skills viewer and by nothing in the
   deviation guard, the identity guard or the policy engine. A composition can
   never talk its way into a scope its sub-skills do not already have.
5. **Guidance, not sequencing.** The platform delivered an ordered reference list
   and grounded each item with its own title and target. It pre-bound nothing,
   enforced no order, and verified nothing on the sub-skills' behalf — each
   sub-skill kept its own gate and its own evidence.

## Where to go next

- This is the top of the ladder. Run [`../demo-suite.sh`](../demo-suite.sh) for
  all five rungs in order plus the cross-skill verification, or `make e2e` for the
  whole verification path.
- The two rungs this runbook composes, each on its own:
  - [`../password-reset/WALKTHROUGH.md`](../password-reset/WALKTHROUGH.md) — rung
    4, the **flow** model: a bound browser flow, one gate.
  - [`../lock-unlock-user/WALKTHROUGH.md`](../lock-unlock-user/WALKTHROUGH.md) —
    rung 3, the **action** model: one `http.post`, one gate.
- To author your own runbook, see [`README.md`](README.md)'s "Adapting for your
  own runbook" — reference existing published single-target skills by id, declare
  no `web_target` / `steps` / `risk_class`, do not nest, and keep the list within
  `SKILLS_COMPOSITION_MAX_SUB_SKILLS` (default `8`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| The runbook skill is not found | `make deploy-samples` (`SAMPLE=<one>` drops the others) — the composition **and both sub-skills** must be in the one `samples` source |
| Only one card appears, then the turn ends | the model finished step 1 and is waiting. Send the step-2 nudge (see step 6); the second card lands on the same session |
| No card appears and a call just runs | `AGENT_HITL_CONFIRM_TIMEOUT=0` excludes write-tier tools from the toolkit, or you invoked the gateway directly rather than through the agent — see the caveat above |
| The card shows no Approve button | correct: you are signed in as `luban-operator`, who holds no decider role. Decide it in the `luban-approver` window's **Approvals** inbox |
| `403 not_a_designated_approver` / `403 self_approval` | you posted the decision as the operator, or a designated decider tried to decide a session they own. Use the second identity |
| `TOOL_NOT_FOUND` for `http.post` | `GATEWAY_HTTP_ENABLED` or `GATEWAY_MUTATING_TOOLS_ENABLED` is false. Check both and report which |
| No `web.*` tools / `web.click` `TOOL_NOT_FOUND` | `GATEWAY_BROWSER_ENABLED` or `GATEWAY_MUTATING_TOOLS_ENABLED` is false, or the sidecar is not ready |
| `409 NO_OP_MUTATION` on the unlock | the target was already active. `dave` starts locked; if you re-ran, the first recovery already unlocked him |
| `404 UNKNOWN_USER` | no such username. Report the identifier you used and stop; do not try a similar name |
| `BROWSER_FLOW_DENIED` / `BROWSER_FLOW_ORIGIN_DEVIATED` / `BROWSER_FLOW_EXHAUSTED` | the reset flow left its binding, wandered past the step budget, or tried an ungated write. Restart step 1 from `web.navigate` |
| The composition was rejected at sync (get_skill 404s) | a sub-skill did not resolve, or is itself a composition. Check `GET /api/v1/skills/status` for the `samples` source's rejection reasons — no nesting in Phase 1 |
| The agent tries the other surface after a denial | it must not. A denial is final: report which sub-skill stopped and stop |
