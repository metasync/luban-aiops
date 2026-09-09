# Develop-as-You-Go Skill Graduation: Author Ad Hoc, Replay Behind One Gate

This sample demonstrates SPEC-055's **graduation** path end to end: an operator
works ad hoc against a declared target with no skill bound, and the platform
turns the mutations a human already approved into an **executable-flow skill**
— no model call, no step nobody signed — which then replays the same work
behind **one** HITL gate instead of one per write.

It is the third of three web-check samples that drive the *same* legacy admin
portal, and the only one that ships no skill:

| Sample | Skill | Approval shape |
|---|---|---|
| [`web-checks/password-reset`](../password-reset/) | hand-written **bound flow** (`web_target` declared) | 1 `flow` card for N writes |
| [`web-checks/adhoc-password-reset`](../adhoc-password-reset/) | hand-written runbook, **no `web_target`** | N `action` cards for N writes |
| `web-checks/skill-graduation` (this one) | **none** — the skill is the artifact the demo produces | N `action` cards to author, then 1 `flow` card to replay |

That last column is the value proposition: N approvals to do the work the first
time, one approval every time after — and the artifact that earns the discount
is a record of what a human actually approved, not a summary a model wrote.

## What this sample contains

| Path | Purpose |
|---|---|
| `demo/demo.sh` | Standalone demo script: six deterministic legs (always run) plus four opt-in acts — author → graduate → merge → replay (`RUN_CHAT_LEG=true`) |
| `WALKTHROUGH.md` | Live, click-by-click walkthrough against your running cluster, including the human half of the merge the script deliberately does not do |

> **Note:** there is no `skill/` directory, and that is the point. See
> [Why this sample ships no skill](#why-this-sample-ships-no-skill) below — the
> absence has one practical consequence worth knowing up front: install the
> ConfigMap act 3 merges into with plain `make deploy-samples`, **not**
> `SAMPLE=web-checks/skill-graduation` (which refuses, correctly, because there
> is no `skill/` to pack).

## Prerequisites

- A running dev-k8s cluster with the `browser-dev` runtime profile deployed
- The browser sidecar reachable (chromium-headless-shell in the tool-gateway pod)
- The `browser-check-target` nginx serving the admin pages
- The `admin-portal` credential set loaded via `sync-browser-credentials.sh`
- `make deploy-samples` already run once, so the `skills-samples` ConfigMap
  exists for act 3 to merge into (this sample contributes no file to it)
- Port-forwards for the identity broker and the platform-gateway:

  ```sh
  kubectl -n dev-luban-aiops port-forward svc/identity-service 18081:8000 &
  kubectl -n dev-luban-aiops port-forward svc/platform-gateway 18083:8000 &
  ```

  Unlike the other two web-check samples, the gateway forward is **not**
  chat-leg-only: legs 5 and 6 declare targets and attempt graduations, so the
  deterministic run needs it too.

## How it works

The four acts run against one admin portal and two throwaway users
(`alice@example.com`, `bob@example.com`):

1. **Author.** Open a develop-as-you-go session that declares its target at
   birth (`skill_target` on `POST /api/v1/sessions`), bind nothing, and reset
   both passwords ad hoc. Because no skill exists, nothing can bind: every
   write parks its own **per-action** card (`approval_kind: action` with a
   change-request projection, SPEC-054 R-2/R-3), and each approved, signed
   mutation is captured into the session's authoring trace (SPEC-055 R-2). Two
   users, two "Confirm reset" clicks, two cards.
2. **Graduate.** `POST /api/v1/sessions/{id}/skill-graduate` re-validates the
   trace against the declared target — which steps were browser steps, whether
   each corroborates the declared origin, whether the declaration *preceded*
   the first capture — and renders an executable-flow draft (R-4). The response
   carries the markdown, `mode: graduated`, `validation: passed`, the suggested
   filename, the step count, the `web_target`, and the `declaration` verdict.
   The frontmatter holds the authoritative replay copy (`kind:
   executable_flow`, `risk_class: write`, `web_target`, `tags:
   [executable-flow, graduated]`, and the `steps:` list); the body holds
   provenance and a merge advisory.
3. **Merge.** The script does the *mechanical* half: patch the draft into the
   `skills-samples` ConfigMap under `skill-graduation-<file>.md`, restart
   skills-hub, and assert the ingested skill carries the v2 `kind` / `steps`
   columns (R-3) under the predicted id
   `samples/skill-graduation-batch-password-reset-graduation-demo`. The
   *human* half — reviewing the runbook, replacing snapshot-relative element
   refs, adding the login step, writing a `flow_intent` decision line — is what
   `WALKTHROUGH.md` covers, and the draft's own advisory lists it.
4. **Replay.** A fresh session binds the graduated skill with
   `web.navigate(skill_id=…)` and does the same work. **Exactly one**
   `approval_kind: flow` card parks, headed by the graduated skill's
   `flow_summary`, with no per-call change-request projection — and every
   write-tier execution carries a signed receipt under that one card (R-5).
   The script prints the contrast and leaves both sessions in the portal so you
   can read them.

## Key design decisions

### Why this sample ships no skill

`deploy-samples.sh` discovers samples with `find -type d -name skill`, so this
one is invisible to it. That is deliberate: a hand-written skill would beg the
question, since the artifact under test is the skill graduation *produces*.
Act 3 therefore patches the ConfigMap directly, under the same
`<sample-leaf>-<file>.md` key convention `deploy-samples.sh` uses, and the
script's `cleanup()` trap removes that key on exit — a write-class executable
flow left in a cluster would outlive the run that produced it and be
indistinguishable from a properly merged one. Set `KEEP_GRADUATED_SKILL=true`
to keep it. Note that re-running `make deploy-samples` at any point also drops
it: the ConfigMap is declarative and always ends up holding exactly the
selected set.

### Why the target is declared at birth and never moves

Graduation corroborates each captured step against the declared origin, so the
declaration is only evidence if it *preceded* the capture. The later
`POST /{id}/skill-target` route is therefore **first-wins**: a second,
different target answers `200` with `already_declared: true` and reports the
scope already in force rather than moving it. Were it movable, a session that
drifted could always be re-scoped to wherever it ended up and the corroboration
would attest to nothing. The draft states which side of the first capture the
declaration fell on (`declaration: preceded`), so a late declaration stays
visible in the artifact instead of being silently laundered.

Leg 5 also asserts an address-bar paste is scoped *before* it is stored —
query, fragment, and embedded `user:password@` userinfo all stripped — because
the declaration lands in a table that outlives every receipt.

### Why the renderer composes nothing

`flow_intent` is the decision line a replay card headlines; `expect:` is a
post-condition. Neither is derivable from a trace of what ran, so the renderer
emits neither, and the demo asserts their absence. Everything in a draft is
either a recorded fact (a signed step, the declared target, the session id) or
a standing advisory. The platform supplies the record; the judgment a merge
adds is a human's.

### Why act 1 forbids `web.type` and `web.evaluate`

Capture withholds a value argument by name (R-2), and a withheld value is an
unresolved credential hole that graduation **refuses** to export — correctly,
since a step whose argument nobody can read is a step nobody can review. The
act-1 prompt therefore routes the login through `web.fill_credential` (read
tier, by reference, never captured) and the new password through a read-tier
`web.navigate` URL parameter, so the only captured writes are the two clicks.
That is a property of *this* procedure rather than a limit on graduation: a
session that legitimately typed a value graduates once the merge author
replaces the hole with a credential reference.

### Who may graduate, and who may only declare

`session:skill_graduate` gates both `POST /{id}/skill-graduate` and the
mid-session `POST /{id}/skill-target` — declaring late is part of graduating,
not a second capability. Declaring at *birth* rides `session:create` instead,
so any authenticated role may scope their own session; scoping your own session
authorizes nothing. An observer can open a develop-as-you-go session but can
never graduate one. Leg 6 asserts both denials (`403`) and that graduation
refuses an untouched session (`409`, naming the missing-trace guard) rather
than exporting an empty or synthesized flow.

### Why the graduation budget must not exceed the replay budget

`AGENT_SKILL_GRADUATION_MAX_STEPS` bounds the step list a draft may carry;
`GATEWAY_BROWSER_FLOW_MAX_STEPS` bounds what the gateway will replay. A
graduation bound above the replay bound exports a flow that dies part-way
through mutating, so leg 1 asserts the relationship. dev-k8s leaves all four
SPEC-055/SPEC-051 knobs unset today, which means the leg reads the code's own
defaults (100-step trace cap, 180-day idle GC, 20 and 20) — what it earns is
the relationship check and a nonsense-value check, not the numbers.

## Running the demo

```sh
# Create the ConfigMap act 3 merges into (this sample contributes no file):
make deploy-samples

# Deterministic legs only (no model interaction):
bash samples/web-checks/skill-graduation/demo/demo.sh

# The full author -> graduate -> merge -> replay story (needs a running agent):
RUN_CHAT_LEG=true bash samples/web-checks/skill-graduation/demo/demo.sh
```

> **Note:** the chat legs are opt-in because they depend on the model choosing
> tools, exactly like the other two demos' chat legs. Their assertions are
> **count-agnostic and tool-agnostic**: act 1 accepts however many cards park
> (bounded at 8) and requires every one to be `action`-kind with a
> change-request projection, and every execution to have *succeeded* and carry
> a signed receipt; act 4 requires exactly one `flow`-kind card, no second card
> after the approval, and the same of every replayed execution. Neither names a
> specific first tool or a specific number of writes, because the model may
> batch both resets into one card or park two, and the count act 2 asserts
> against is read from the durable session detail rather than predicted.
>
> Tool-agnosticism is **not** tolerance of `web.type` or `web.evaluate`, which
> is where this demo differs from `adhoc-password-reset`: there, which write
> tool the model picks changes nothing, but here either one is captured with its
> value withheld, and a withheld value is an unresolved credential hole that act
> 2 refuses to export. See
> [Why act 1 forbids `web.type` and `web.evaluate`](#why-act-1-forbids-webtype-and-webevaluate).

## Adapting for your own target

1. Copy this directory to `samples/web-checks/<your-sample>/` and update
   `SAMPLE_LEAF` in `demo.sh` — it is both the ConfigMap key prefix and the
   skill-id prefix act 3 predicts
2. Point `ADMIN_TARGET` at your own allowlisted origin. Declare it at birth;
   it is first-wins, so get it right the first time
3. Rewrite the act-1 prompt for your procedure, keeping the captured writes to
   interactions whose arguments carry no secret — `web.fill_credential` for
   credentials, URL parameters for values your target accepts — so the trace
   graduates cleanly instead of carrying a credential hole
4. Remember `SESSION_TITLE` is load-bearing: its slug becomes the merged
   ConfigMap key and the skill id. The demo derives both from the graduation
   response rather than hard-coding them, so changing the title is safe
5. If you want the graduated skill to survive the run, set
   `KEEP_GRADUATED_SKILL=true` — but merge it into your team's skills repo
   properly rather than leaving a demo artifact in a ConfigMap

## Infrastructure wiring

This sample is self-contained: its demo and docs live entirely under
`samples/`, and the only cluster state it creates is two throwaway sessions
(deleted on exit), the authoring and replay sessions (kept so you can read them
in the portal), and act 3's ConfigMap key (removed on exit). The platform base
overlay provides only a *generic* `samples` skill source — it never names this
sample, so the dependency arrow stays tutorial → platform.

The sample *drives* shared browser infrastructure that intentionally lives
outside `samples/` (the same infra the other two web-check samples and the
SPEC-049 `browser-check-demo.sh` smoke test use):

- **Admin pages**: `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-check-target-pages.yaml`
- **Credential sync**: `shared/platform-ops/gitops/sync-browser-credentials.sh` (the `admin-portal` set)
- **Network policy**: `shared/platform-ops/gitops/runtime-profiles/browser-dev/browser-sidecar-network-policy.yaml`
- **Generic skill-source hook**: the `samples` entry in `SKILLS_SOURCES` (`.../dev-k8s/base/skills-hub/runtime-config.env`) and the optional `/skills/samples` mount (`.../skills-hub/skills-hub-deployment.yaml`)
