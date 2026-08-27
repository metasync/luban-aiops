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

## Documents (Control)

The Documents view is the operations document repository (SPEC-039). It
appears in the Control section only for signed-in users with a document
role (`platform-admin`, `approver`, or `operator`) — access is by role,
never by per-document permission grants.

- **Mine** lists your drafts and published documents; **Published** lists
  every published document visible to your roles, each attributed with
  *created by …* when the owner is someone else.
- **New shift summary** opens the creation dialog: pick your own sessions
  from a selector, optionally add foreign session ids (copied from a
  colleague's session panel — see Sessions above), set a label, and
  optionally request an AI-written prose summary. The digest covers at
  most 20 sessions.
- **Coverage is two-tier**: your own sessions contribute full coverage;
  foreign sessions contribute metadata only — and only if your roles also
  hold the approvals inbox. The digest's provenance names every cited
  session and record id, and foreign entries are tagged as such.
- The document page is **digest-first**: the structured digest (sessions,
  confirmations, executions, evidence counts) is the artifact of record.
  When prose was requested it renders collapsed under the label *AI-
  generated prose (digest-only, may omit facts)*; a failed generation
  shows a warning instead and the digest stands alone.
- Drafts can be **Published** (one-way — publishing cannot be undone, and
  a published document refuses re-publish) or **Deleted** while they are
  yours. A document's content is never edited after creation; publishing
  only changes visibility, and owners may still delete their own
  published documents (they disappear for everyone).

Document creation and publishing are the `documents:create` action and
reading is `documents:read`; cross-owner reads are audited (`document_read`)
while reading your own documents is not.

**Your first shift summary** — the typical end-of-shift workflow:

1. Open **Documents** and click **New shift summary**.
2. Enter a label that names the shift (e.g. *Night shift 2026-08-27*).
3. Select your own sessions from the picker (up to 20). To fold in a
   colleague's session, ask them to copy its session id from their
   session panel (see Sessions above) and paste it into the foreign-id
   field — foreign sessions enter metadata-only, and only when your
   roles hold the approvals inbox.
4. Optionally switch on the prose summary; submit. The draft appears in
   **Mine**.
5. Review the digest on the document page. When it reads right, click
   **Publish** — colleagues with a document role see it in
   **Published** immediately, and every cross-owner read lands on the
   audit trail.

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
- **Continue in chat** drops you into the incident's dedicated session to
  investigate interactively.
- **Report incident** files a new incident manually.

Viewing requires `incident:read`; reporting and triaging require
`incident:create` / `incident:triage`. Wiring Alertmanager and
interpreting triage reports in depth is covered in the
[Incident Triage and Collaboration Guide](incident-guide.md).

## Audit Trail (Control)

A read-only view of the durable audit trail: filter bar, newest-first
table, cursor pagination with a persistent **Load more** bar, and
expandable event envelopes showing the full event payload. The navigation
entry appears only for identities holding `audit:read` (auditors and
platform admins by default).

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
  events.

The view carries no mutable controls; authorization decisions always come
from the gateway.

## What Your Roles Unlock

| Role | Chat | Approve cards | Approvals inbox | Documents | Mutating tools | Incidents | Audit trail |
|---|---|---|---|---|---|---|---|
| `platform-admin` | yes | yes | yes | yes | yes | full | yes |
| `operator` | yes | yes | no | yes | yes | full | no |
| `approver` | yes | yes | yes | yes | no | full | no |
| `developer` | yes | yes | no | no | no | full | no |
| `read-only-observer` | yes (read-only tools) | no | no | no | no | read | no |
| `auditor` | no | no | no | no | no | no | yes |

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
