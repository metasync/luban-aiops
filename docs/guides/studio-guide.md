# Studio Guide

Operator-facing guide to **Studio**, the portal's skill-development workspace
(SPEC-056, v0.37.0): what it is for, how it differs from **Chat**, how to run
your first development session end to end, and why a session's type can never
change. Written for the roles that hold authoring power — `operator`,
`approver`, `platform-admin`.

For the portal around Studio, see the
[Portal User Guide](portal-user-guide.md). For what a graduated skill is and
how skill content is managed afterwards, see the
[Skills and Guidance Guide](skills-guide.md). For the approval model that every
Studio session still runs under, see
[Approval and HITL Governance](approval-and-hitl.md).

## Which entry, and why there are two

The portal has two peer chat entries in the sidebar: **Chat** (a speech-bubble
icon) and **Studio** (a flask icon). They are the *same* chat surface — one
shared component, one stream, one secret-masking path, one approval path — and
they are driven by a single mode. Underneath, that mode fixes three things: the
`session_type` a new session is born with, the scope of the session list, and
which entry remembers the session you last had open. On top of those it swaps the
create affordance and the authoring controls, and decides who sees the entry at
all.

| | **Chat** | **Studio** |
|---|---|---|
| What it is for | operational work: incidents, triage, remediation | developing a skill: authoring a procedure you intend to keep |
| Session type | `operation` | `development` |
| Session list | your operational sessions only | your development sessions only |
| **New** button | one click, no dialog (plus icon) | opens a target dialog (flask icon) |
| Session-header controls | **Draft as skill** | **Declare target** + **Graduate as skill** |
| Feeds a shift summary | yes | no — never shift material |
| Visible to | every signed-in role | `operator`, `approver`, `platform-admin` only |

Use **Chat** for anything you would report on at the end of a shift. Use
**Studio** when the point of the session is to *produce a reusable skill* from
work you are about to do by hand — the develop-as-you-go path, where each
mutation parks its own approval card and the approved ones are then graduated
into an executable-flow draft.

If you do not see **Studio** in the sidebar, you are either signed out or your
role does not hold `session:skill_graduate`. That is the same grant that decides
whether the **Graduate as skill** control appears, so the entry and the power are
never out of step. `developer`, `read-only-observer` and `auditor` keep Chat
alone.

## Your first development session

### 1. Open Studio

Click **Studio** in the sidebar. Its session list is scoped server-side to your
own development sessions, so it starts empty for a new account and never mixes
in operational work — and the scope is applied in the query rather than in the
browser, so it cannot be coaxed into showing more.

### 2. Create the session

Click **New** (the flask icon). The dialog is titled **New skill-development
session** and asks one optional question: the web target the session will work
against.

Declaring the target here — before the session has mutated anything — is what
makes it the **scope the session acted under**. Every approved browser mutation
the session captures is then corroborated against that origin at graduation, and
a step that lands elsewhere refuses the flow. Graduation reports such a
declaration as having `preceded` every step.

You can leave it blank and open the session unscoped. Then use **Declare
target** in the session header later; the declaration still binds, but
graduation reports it as `postdated` — fitted to the trace rather than
authorizing it — and the preview says so in as many words. Declaring at birth is
the stronger artifact, so declare at birth unless you genuinely do not know the
target yet.

Two rules apply to any declaration, whenever you make it:

- **Only the origin and path are kept.** Any query string, fragment, or
  embedded `user:password@` is dropped before the value is stored.
- **The first declaration wins.** It cannot be widened afterwards; a second,
  different target is answered with the scope already in force rather than
  replacing it.

Click **Open session**.

> Declare the address the *platform's* browser will use, not the one in your own
> address bar. If you reach a target through a `localhost` port-forward but the
> connector resolves it by its in-cluster name, declaring the `localhost` form
> fails late rather than early: the session captures fine, and graduation then
> refuses every step as landing outside the declared origin.

### 3. Title it now

Rename the session with the pencil icon on its row. The title becomes the
graduated skill's `title` and its suggested filename slug, so it is worth
choosing before you graduate rather than after.

### 4. Do the work

Chat with the agent exactly as you would in Chat. Nothing about the trust path
changes: tool runs still park confirmation cards, secrets are still masked in
the card and in the transcript, tool evidence still renders the same way, and
you can still pick a model or use voice input.

While you work, the platform captures every **approved, signed, write-tier**
execution into the session's authoring trace, together with the origin the
connector observed it land on. Read-tier calls (navigate, snapshot, credential
fill) are deliberately not captured — the trace is a record of mutations a human
authorized, not of everything the agent touched.

### 5. Graduate

Click **Graduate as skill** (a bolt icon) in the session header. No model is
involved, so the answer is deterministic: either the artifact, or a refusal
naming every guard the trace failed and the step positions responsible.

A success opens the **Executable-flow draft preview**: a blue `graduated · no
model` badge, `validation: passed`, a suggested filename, the blast-radius facts
a prose draft cannot carry (the replay step count and the target it is bound to,
plus whether the declaration `preceded` the trace), and a **Rendered** / **Raw**
toggle. **Download .md** gives you the file. Nothing is published and the
platform keeps no copy — the response is ephemeral by construction, and merging
the draft into your skills repository stays a human act.

A refusal arrives as a **modal rather than a toast**, because it lists step
positions and is your only remedy — it is the answer, not a transient error. The
ones worth knowing:

| Refusal | What it means |
|---|---|
| *the session has no captured authoring trace* | nothing was approved, or every call was read tier |
| *step(s) landed outside the declared target's origin* | the declared address and the observed origin disagree |
| *step(s) still carry an unresolved credential hole* | a secret was passed as a value rather than by reference |
| *step(s) … have no observed origin* | a captured write failed, or its landing could not be verified |
| *N captured steps exceed the 20-step budget* | raise the graduation and replay budgets together, or author a shorter procedure |

## What Studio deliberately does not change

Studio is a *scoping* change, not a trust change. The following are identical in
both entries, and are asserted identical rather than assumed so:

- the streaming transcript and its frame vocabulary
- secret masking, in cards and in prose
- the HITL confirmation path, including who may decide
- tool evidence rendering
- model selection and voice input

The mode that distinguishes the two entries is never threaded into any of those
paths. If something behaves differently between Chat and Studio, that is a bug
worth reporting, not a setting to find.

Likewise, opening Studio adds no new policy action, no new audit event type, and
no new configuration knob. Creating a development session is dual-gated at the
gateway — ordinary `session:create` **plus** the existing
`session:skill_graduate` — so a role that cannot graduate cannot mint a
development session either, and a `403` names the grant it lacks.

## Why there is no "Move to Studio"

A session's type is **fixed when it is created and never changes**. There is no
conversion in either direction and the portal offers no control for one.

The reason is not tidiness. An operational session's steps were approved as
incident remediation, across whatever targets the incident happened to touch.
Graduation corroborates every captured step against **one** declared origin, so a
multi-target operational trace would deterministically refuse — offering the
button would only manufacture a refusal. Conversely, a development session is
authoring work and is never operational shift material.

Start the work in the right entry. If you authored something in Chat and then
decided it was worth keeping, redo it in Studio: the second run is cheap, and the
artifact you get is one a reviewer can trust.

> **What the split does and does not enforce.** The restriction above is on the
> *affordance* and on the session record, not a type check inside graduation
> itself: the graduation route re-validates the captured trace against the
> declared target, and that is what decides the outcome. An `operation` session
> holding a genuinely single-target, on-origin trace can therefore still be
> graduated through the API — which is exactly what the
> `samples/web-checks/skill-graduation/` demo script does. The portal does not
> offer it, because in real operational use that shape is the exception and the
> multi-origin refusal is the rule.

## Development sessions and documents

Development sessions are never shift-summary material, and two independent
things keep it that way:

- **The picker cannot offer one.** The session picker in the Documents create
  dialog reads the operation-scoped workspace, so Studio sessions simply are not
  in the list.
- **Naming one is refused.** The dialog also accepts session ids typed by hand.
  A development id there is rejected whole — never silently dropped, which would
  hide the mistake — with a `400` reading `development sessions are not
  shift-summary material: […]`, raised before any fact is read for the request.

Incident reports are unaffected: that path anchors to an incident, not to a
session list. And an operational session that carries a declared target is still
perfectly valid shift material — declaring a target does not make a session
Studio's.

## Sessions, reloads, and switching entries

Each entry remembers its own last-open session separately, under its own
namespaced key. A detour from Studio into Chat and back restores your place in
both, and a reload lands you on the session you were last reading in whichever
entry you open.

Underneath there are two workspace instances rather than one per view: the
operation instance backs Chat and is reused by Incidents, Documents and Settings,
and the development instance backs Studio. Everything except Studio therefore
deals in operation sessions.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| **Studio** is missing from the sidebar | You are signed out, or your role lacks `session:skill_graduate`. Sign in as `operator`, `approver` or `platform-admin` |
| **Graduate as skill** is missing | You are in **Chat**, whose header offers only **Draft as skill**. The authoring controls live in Studio |
| **Declare target** says the scope is already in force | The first declaration wins and cannot be widened. Open a new development session if you need a different target |
| Creating a session returns `403` | The dual gate: creating a development session needs `session:create` **and** `session:skill_graduate`. The response names the missing grant |
| Graduation returns `409` | A refusal, not a failure — read the modal. It names every guard the trace failed and the steps responsible |
| A Studio session is missing from the Documents picker | Correct behaviour. Development sessions are never shift-summary material |
| `400 development sessions are not shift-summary material` | A development id was typed into the picker's manual-id field. Remove it and pick operational sessions |
| Studio's session list looks empty | It lists only your development sessions. Operational work is in Chat |

## Where to go next

- To run the whole author → graduate → merge → replay story against a live
  cluster, follow `samples/web-checks/skill-graduation/WALKTHROUGH.md`. It is
  click-by-click, uses the same admin panel as the two password-reset samples,
  and covers the human half of the merge that no script can do.
- To understand what happens to the draft afterwards, see the
  [Skills and Guidance Guide](skills-guide.md).
- For the portal around Studio, see the
  [Portal User Guide](portal-user-guide.md).
