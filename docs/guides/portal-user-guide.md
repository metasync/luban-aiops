# Portal User Guide

Day-2 guide to the operator portal: signing in, chatting with the agent,
managing sessions, selecting models, reading tool evidence, approving tool
runs, and using the Control and Workspace views. Written for everyone who
uses the portal — operators, approvers, developers, observers, auditors.

For getting the portal running in the first place, see
[Getting Started](getting-started.md). For the approval model behind the
confirmation cards, see [Approval and HITL Governance](approval-and-hitl.md).

## Signing In and Out

- Click **Sign in** in the sidebar footer. The portal starts an OIDC flow
  through platform-gateway and returns you signed in; your user card shows
  an initials avatar and username.
- Click the user card to see the **roles** granted to your identity — these
  decide which views and actions you get (see
  [What your roles unlock](#what-your-roles-unlock)).
- Tokens refresh silently in the background about a minute before expiry.
  If a refresh fails, the session is cleared and you are prompted to sign
  in again — you will not be silently degraded.
- **Sign out** is the icon next to the user card.

The platform version renders as a muted chip in the logo row — quote it
when reporting issues.

## Finding Your Way Around

The portal is a two-column shell: a left sidebar with the function list and
a main column showing one view at a time. View state is preserved when you
switch — a half-typed chat draft survives a detour into the audit trail.

- **Chat** stands alone at the top.
- **Control** gathers Incidents, Audit trail, and Permissions.
- **Workspace** gathers Tools, Skills, and Settings.

Entries you lack the role for are hidden, and a section header disappears
when everything under it is hidden. On narrow screens the sidebar collapses
into a hamburger-triggered drawer.

## Chat

Type a prompt and send; the agent's reply streams in live. The agent may
invoke tools while answering — those show up as
[evidence cards](#reading-tool-evidence) attached to the reply.

### Voice input

The microphone button in the composer performs browser speech-to-text
(Web Speech API): no audio is captured, stored, or transmitted — only the
transcribed text enters your draft, exactly as if typed. A language
selector (`en-US` / `zh-CN`, defaulting from your browser locale) drives
the recognizer only. Voice-composed turns are tagged as voice **for the
audit trail only** — they pass through exactly the same permission and
approval layers as typed ones, and approvals always stay click-gated.
Browsers without the Web Speech API show the button disabled with an
explanation; typing always works.

### Selecting a model

The selection bar under the composer lists every model the deployment has
credentials for, grouped by provider, with the deploy-time default
pre-selected.

- Your selection rides with each turn and **pins to the session**:
  switching sessions re-seeds the selector from that session's pinned
  model.
- If exactly one model is configured, the bar renders as a fixed label.
- If the catalog cannot be fetched, the selector hides and chat continues
  on the default model — model choice is never a blocker.

Which models appear is an operator-side concern: see the
[Configuration Reference](configuration-reference.md) for provider
credentials and discovery knobs, and the
[Luban-Hosted Small Model Guide](luban-llm-guide.md) for self-hosted
entries.

## Sessions

The session panel lists your operator–agent sessions with titles and
relative last-active times.

- **Switching** loads the transcript of the selected session and repoints
  the live stream; persisted tool evidence is re-attached to the matching
  turns, so replayed evidence cards look exactly like they did live.
- An amber **awaiting approval** badge marks sessions with a parked
  confirmation card; confirmation cards stay anchored to the session that
  parked them.
- **Deleting** a session asks for an in-UI confirm. A session with a
  pending confirmation refuses deletion — decide the card first.
- **Renaming** (SPEC-039): each session entry carries an edit button that
  opens an inline rename dialog (1–80 characters). Renames apply to your
  own sessions only, update the panel instantly, and are deliberately not
  audited — titles are cosmetic, not operational state.
- **Copying the session id** (SPEC-039): every session entry shows its
  truncated id (full value on hover) with a one-click copy button — a
  check mark confirms the copy. The open session's header shows the same
  id + copy pair. This is how you hand a colleague a session id to cite
  in a shift summary (see below).
- **Draft as skill** (SPEC-044, preview per SPEC-045): the open
  session's header carries a **Draft as skill** action for
  `platform-admin`, `approver`, and `operator`. It generates a Skill
  Format v1 Markdown draft from the session's durable record (the
  validated triage report joins when the session is incident-linked),
  validates it against skills-hub before returning it, and opens it in
  a read-only **preview modal**: rendered view with a **Raw** toggle,
  a **generated** / facts-only **skeleton** mode badge, the validation
  status, and the suggested filename. **Download .md** hands over
  `<suggested-slug>.md`; **Discard** drops the draft. Generation may
  take a few seconds; if validation cannot run the action reports an
  error instead of handing out an unvalidated draft. Nothing is stored
  on the platform — see the
  [Skills and Guidance Guide](skills-guide.md) for merging the draft
  into a skill source.

## Reading Tool Evidence

When the agent invokes tools, the reply carries an evidence panel: one card
per tool call with a status badge, collapsible parameters, and a data
summary.

- **Show full output** expands the complete tool result when the full
  payload was streamed; multi-line text such as pod logs renders as a raw
  log block, not escaped JSON.
- Large payloads may carry truncation notes: an entry-capped payload shows
  its original size and a partial preview; a payload evicted by the
  session's evidence budget keeps its metadata but loses the data
  expander. The note tells you which happened.

## Approving Tool Runs (HITL Confirmations)

When the agent proposes a tool call that is not auto-approved, the chat
parks and renders a warning-toned confirmation card listing the pending
tools with collapsible parameters.

- A **mutating** badge appears when any parked call would change state
  (write/admin risk) — read it before approving.
- An approval-tier badge names who may decide: **operator confirmation**
  means the session operator confirms their own card; **approver
  required** names the designated approver roles (SPEC-030). If your roles
  do not match, the card renders read-only — no Approve/Deny buttons — and
  the gateway rejects non-decider approvals with a 403 regardless.
- **Approve** resumes the stream and executes; **Deny** feeds a refusal
  back to the agent. Nothing runs silently, and an expired card locks with
  a status badge (the agent is interrupted).
- Approve/Deny buttons render only for roles granted `chat:confirm`; the
  gateway re-enforces this server-side. Approving is not the same as
  executing — the run is still checked against `tools:mutate` and RBAC at
  the tool-gateway.
- Cards are durable (SPEC-031): they survive a re-login or page reload and
  stay in the transcript after a decision. Decided cards render read-only
  with who decided and when; pending cards stay actionable.
- External decisions sync live (SPEC-032): while a card is pending, the
  chat watches the session state and flips the card — with the decider's
  attribution and the agent's resumed reply — within seconds of an approval
  or denial made from the Approvals inbox or another window. No refresh is
  needed; the watch stops by itself once nothing is pending.

The full four-layer model (policy bundle, risk tiers, auto-allow, HITL) is
in [Approval and HITL Governance](approval-and-hitl.md).

## Approvals (Control)

The Approvals view is the designated approver's cross-session inbox
(SPEC-031). It appears in the Control section only for signed-in users
with a decider role (`approver` or `platform-admin`), and its nav entry
carries a badge with the number of pending items.

- **Pending** lists every parked confirmation across all sessions with
  Approve/Deny buttons; deciding resumes the owner's parked reply exactly
  like deciding from the chat.
- **History** lists decisions from the last 30 days (pending items plus
  approved/denied/expired outcomes), most recent first, each with decider
  attribution.
- Entries are metadata only — session, owner, parked calls, outcome — and
  never show the owner's conversation text.
- The inbox refreshes every 30 seconds and on window focus. If another
  approver decides first, your card flips to their outcome
  (`already_resolved`) instead of executing twice.

Inbox access is the `approvals:list` action; the gateway re-enforces it,
so non-deciders receive a 403 even if they call the API directly.

## Documents (Workspace)

The Documents view is the operations document repository (SPEC-039). It
appears in the Workspace section (since SPEC-040, shift handover is an
everyday workspace activity rather than oversight) only for signed-in
users with a document role (`platform-admin`, `approver`, or
`operator`) — access is by role, never by per-document permission
grants.

- **Mine** lists your drafts and published documents; **Published** lists
  every published document visible to your roles, each attributed with
  *created by …* when the owner is someone else. Rows carry a one-line
  summary: an AI one-liner when the document shipped with a narrative,
  otherwise a counts-only line (e.g. *2 sessions · 3 decisions · 1
  execution*) computed at creation — neither contains titles, record
  ids, or decision outcomes. The detail card repeats the same one-liner
  at the top of the document.
- The digest's vocabulary — digest, evidence frame, coverage tiers,
  handover, quiet, provenance — is explained in the
  [Documents and Digest Reference](documents-digest-reference.md); the
  drawer's **Learn more** link opens the same page.
- **New document** opens the creation dialog with a type choice
  (SPEC-043): **Shift summary** picks your own sessions from a
  selector (optionally plus foreign session ids copied from a
  colleague's session panel — see Sessions above); **Incident report**
  picks exactly one incident from a searchable picker. Both types take
  a label, and the AI narrative is generated by default — switch it
  off to ship a digest-only document. Shift summaries cover at most 20
  sessions; an incident report's coverage is the incident's own linked
  triage session, chosen server-side.
- **Coverage is two-tier**: your own sessions contribute full coverage;
  foreign sessions contribute metadata only — and only if your roles also
  hold the approvals inbox. The digest's provenance names every cited
  session and record id, and foreign entries are tagged as such. The
  same tiers apply to an incident report's linked session: full digest
  when you own it, metadata only when it is someone else's and your
  roles hold the approvals inbox, and an honest marker when it is out
  of reach — an incident report never fails because its session is.
- Every digest carries a deterministic **handover section** (SPEC-040):
  covered-session counts, the decisions made and execution outcomes of
  your own sessions, still-open items, and an honest *quiet* note when
  the shift recorded nothing — so the relieving operator reads what
  happened without a model in the loop.
- The document page is **digest-first**: the structured digest renders
  as tabs — shift summaries show Handover, Sessions, Confirmations,
  Executions, Evidence & transcript, Open items, Digest data; incident
  reports show Incident, Triage, Dispatches, Session, Digest data — and
  is the artifact of record; the
  digest and narrative panes are bounded: only their content region
  scrolls inside a fixed height while the tab bar and the narrative's
  collapse header stay pinned, with an expand affordance to release
  the bound. The generated narrative opens expanded under the
  label *AI-generated narrative — from this document's digest facts* —
  a short, plain-language shift briefing (at most three paragraphs)
  written for the relieving operator; it stays collapsible to the
  header alone; a failed generation shows a warning instead and the
  digest stands alone.
- **Export .md** in the document drawer downloads the open document as
  Markdown (metadata, provenance, digest, and the narrative when
  included) for offline handover. Export runs entirely in your browser
  on the document already on screen — it performs no extra request and
  adds no audit event.
- Drafts can be **Published** (one-way — publishing cannot be undone, and
  a published document refuses re-publish) or **Deleted** while they are
  yours. A document's content is never edited after creation; publishing
  only changes visibility, and owners may still delete their own
  published documents (they disappear for everyone).

Document creation and publishing are the `documents:create` action and
reading is `documents:read`; cross-owner reads are audited (`document_read`)
while reading your own documents is not. Incident reports additionally
require `incident:read` (the dual gate combines two existing actions —
no new policy action), so the document surface never bypasses the
incident visibility matrix. Creation failures surface the reason:
unknown incident id (404), incident reporting not configured on this
deployment (503), or the incident facts unreachable right now (502).

**Your first shift summary** — the typical end-of-shift workflow:

1. Open **Documents** in the Workspace section and click **New shift
   summary**.
2. Enter a label that names the shift (e.g. *Night shift 2026-08-28*).
3. Select your own sessions from the picker (up to 20). To fold in a
   colleague's session, ask them to copy its session id from their
   session panel (see Sessions above) and paste it into the foreign-id
   field — foreign sessions enter metadata-only, and only when your
   roles hold the approvals inbox.
4. Leave the narrative switch on (the default) or switch it off for a
   digest-only document; submit. The draft appears in **Mine**.
5. Review the handover section and the digest on the document page.
   When it reads right, click **Publish** — colleagues with a document
   role see it in **Published** immediately, and every cross-owner read
   lands on the audit trail.
6. Optionally click **Export .md** in the drawer to keep an offline copy
   of the handover.

**Capturing an incident report** — the post-triage workflow:

1. Open **Documents** and click **New document**, then choose
   **Incident report**.
2. Pick the incident from the searchable picker (title, id, severity,
   and status are shown) and enter a label (e.g. *Payment latency
   post-mortem*).
3. Submit. The digest copies the incident facts, the validated triage
   report (or a *not triaged* marker), and the connector dispatch
   outcomes verbatim, and covers the incident's linked triage session
   under your coverage tier. Publish or export as with any document.

Reading a colleague's published document needs no request or grant —
open it in the **Published** tab; the digest names its owner and anchors
every fact to its source records.

## Incidents (Control)

The Incidents view shows a filterable, auto-refreshing incident list.
Opening an incident shows its detail and, once triaged, the full triage
report: severity assessment, evidence, hypotheses, ranked advisory next
steps, and cited skills, plus any collaboration dispatch outcomes.

- **Run triage** starts an agent triage with a live *triaging* state; a
  failed run exposes the raw agent text so you can see what went wrong.
- **Draft as skill** (SPEC-045) turns the incident's validated triage
  into a Skill Format v1 draft for `platform-admin`, `approver`, and
  `operator` — regardless of who ran the triage session. The draft is
  built from the incident envelope and the validated triage report only
  (never from anyone's session), validated before it is returned, and
  opens in the same read-only preview modal as the chat action. An
  incident without a validated triage report answers 409 with a toast
  naming the precondition — run triage first, then draft the skill.
- **Continue in chat** drops you into the incident's dedicated session to
  investigate interactively. The button is enabled only while that
  session is one of your own live sessions; triage sessions expire
  after an idle TTL and are single-owner, so a stale or foreign
  session greys the button out (with an explanatory tooltip) instead
  of failing on click.
- **Report incident** files a new incident manually.

Viewing requires `incident:read`; reporting and triaging require
`incident:create` / `incident:triage`; drafting a skill from an incident
requires the combination of `incident:skill_draft` and `incident:read`.
Wiring Alertmanager and interpreting triage reports in depth is covered
in the [Incident Triage and Collaboration Guide](incident-guide.md).

## Audit Trail (Control)

A read-only view of the durable audit trail. The navigation entry
appears only for identities holding `audit:read` (auditors and platform
admins by default). A shared filter toolbar — username, event type,
emitter service, and a since/until window — drives both tabs and the
export:

- **Events** — the newest-first table with cursor pagination, a
  persistent **Load more** bar, and expandable event envelopes showing
  the full event payload.
- **Summary** — deterministic aggregates over the filtered window:
  the total event count, a decision-chain strip
  (`confirmation_decided → execution_requested → execution_completed →
  execution_rejected`, zeros shown as 0), and bucket tables by event
  type, outcome, and service plus the top actors. The summary
  refetches whenever the filters changed.
- **Export CSV** — downloads the filtered envelope columns as an
  RFC-4180 CSV under the server-chosen filename
  (`audit-export-<timestamp>.csv`). Exports are capped at
  `AUDIT_EXPORT_MAX_ROWS` rows; when the cap bites the response still
  downloads and the view shows a truncation notice so you know to
  narrow the filter window.

Typical uses: tracing who approved a confirmation
(`confirmation_decided`), what a tool run touched (`tool_invoked`), or
which model served a chat turn (`chat_started` details).

## Permissions (Control)

The live role × action matrix, evaluated from the policy bundle the
gateway actually enforces — not hand-maintained documentation. The header
shows the bundle version and source. Platform admins see all roles;
everyone else sees their own rows. Visible to every signed-in user under
`policy:read`. Cells under an approval requirement render a third state —
**self-approval** (`tier_1`) or **approver required** (`tier_2`, hovering
names the decider roles) — instead of plain allow/deny.

If a matrix cell surprises you, the bundle edit workflow is in
[Approval and HITL Governance](approval-and-hitl.md#policy-bundle-workflow).

## Tools and Skills Catalogs (Workspace)

- **Tools** — the read-only catalog of tools registered in the
  tool-gateway, as the agent sees them (name, risk level, description).
  Mutating tools appear only when the deployment enables them.
- **Skills** — the skills inventory with source and tag filters; what the
  agent can cite as grounded guidance. Content operations (adding,
  revising, removing skills) are in the
  [Skills and Guidance Guide](skills-guide.md).

## Settings (Workspace)

A read-only panel over the portal's own state, visible to everyone
(including signed-out visitors), with three tabs:

- **Identity** — sign-in state, username, roles, and the identity claims
  carried by the auth session. Signed out, the tab shows a sign-in prompt
  instead of stale data.
- **Session** — the currently selected session id and title, or an
  explicit *no session selected* state, plus the workspace session count.
- **Platform** — the platform version chip value, the API origin the
  portal talks to, and the most recent request id — quote these when
  reporting issues; they correlate directly with logs, traces, and audit
  events. Below sits the **Key platform components** table: every
  component follows the platform version above, so the table lists the
  tech stack underneath each one — framework/product (React · Ant
  Design, FastAPI · Python, AgentScope · FastAPI, the LLM provider API,
  PostgreSQL/Redis/In-memory store backends, JSON policy rules) and its
  live version where applicable — read from the gateway's health
  (`/health/ready`) and runtime (`/api/v1/runtime`) probes. Status uses
  one vocabulary — *ready*, *degraded*, *not ready* — with *unavailable*
  when a health probe fails and *checking…* while probes load.

The view carries no mutable controls; authorization decisions always come
from the gateway.

## What Your Roles Unlock

| Role | Chat | Approve cards | Approvals inbox | Documents | Skill drafts | Mutating tools | Incidents | Audit trail |
|---|---|---|---|---|---|---|---|---|
| `platform-admin` | yes | yes | yes | yes | yes | yes | full | yes |
| `operator` | yes | yes | no | yes | yes | yes | full | no |
| `approver` | yes | yes | yes | yes | yes | no | full | no |
| `developer` | yes | yes | no | no | no | no | full | no |
| `read-only-observer` | yes (read-only tools) | no | no | no | no | no | read | no |
| `auditor` | no | no | no | no | no | no | no | yes |

The authoritative answer is always the Permissions view — it reflects the
deployed bundle, including any local grants your administrators added. See
the [User and Role Administration Guide](user-and-role-administration.md)
for how roles are assigned.

## Related Documentation

- [Getting Started](getting-started.md) — deploy and first login
- [Approval and HITL Governance](approval-and-hitl.md) — the approval model
- [Incident Triage and Collaboration Guide](incident-guide.md) — incident depth
- [Skills and Guidance Guide](skills-guide.md) — skill content operations
- [Troubleshooting](troubleshooting.md) — when something misbehaves
