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

The full four-layer model (policy bundle, risk tiers, auto-allow, HITL) is
in [Approval and HITL Governance](approval-and-hitl.md).

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

| Role | Chat | Approve cards | Mutating tools | Incidents | Audit trail |
|---|---|---|---|---|---|
| `platform-admin` | yes | yes | yes | full | yes |
| `operator` | yes | yes | yes | full | no |
| `approver` | yes | yes | no | full | no |
| `developer` | yes | yes | no | full | no |
| `read-only-observer` | yes (read-only tools) | no | no | read | no |
| `auditor` | no | no | no | no | yes |

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
