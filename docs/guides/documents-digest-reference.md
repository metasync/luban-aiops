# Operations Documents and Digest Reference

A reader's companion to the portal's **Documents** view (see the
[Portal User Guide](portal-user-guide.md#documents-workspace)). This
reference explains, in plain operator language, every concept you meet
when you open a shift summary: what a document is, what the digest is,
what each digest section means, and the vocabulary — evidence frames,
coverage tiers, provenance, and the handover narrative.

## What an operations document is

An operations document is an **immutable snapshot** of what happened
on the platform — either across a set of chat sessions during a shift
(a **shift summary**) or around one incident (an **incident report**,
SPEC-043). Documents are created by
operators, stay private drafts until published, and are readable by
everyone with a document role (`platform-admin`, `approver`, or
`operator`) once published. A document is never edited after creation —
publishing only changes visibility, and deletion removes it for
everyone.

Every operations document has three layers:

1. **Metadata** — label, owner, state (draft/published), timestamps,
   and the one-line summary shown in the lists and atop the document.
2. **The digest** — the deterministic artifact of record (below).
3. **The narrative (prose)** — an optional AI-generated handover text,
   always labeled as derived from the digest facts; when present it
   also contributes the one-line AI blurb.

## What the digest is

The digest is the heart of the document. It is assembled
**mechanically at creation time** by copying facts from the platform's
durable stores — sessions, transcripts, the evidence store,
confirmation records, and execution records. **No model is involved**:
two documents created over the same records always carry byte-identical
digests. That determinism is why the digest is the artifact of record:
anything a reader can see in a document either rides the digest or is
explicitly labeled as generated from it.

The digest carries **counts and records, never content**: transcript
turn counts rather than conversation text, evidence frame counts rather
than tool outputs. This keeps documents safe to publish across
ownership boundaries.

### Digest sections, top to bottom

| Section | What it says |
|---|---|
| `generated_at`, `requester_user_id` | When the snapshot was taken and who requested it. |
| `session_count` / `sessions` | How many sessions are covered, and one entry per session (see below). |
| `handover` | The shift story: shift-level counts, decisions, executions, and still-open items (see [Handover](#the-handover-section)). |

### Session entries

Each covered session contributes one entry. What the entry contains
depends on the **coverage tier** (see [Vocabulary](#vocabulary)):

**Owner-covered sessions** (your own sessions) contribute:

- `title`, `created_at` — the session name and age.
- `transcript` — counts only: whether a transcript exists, total turn
  count, and user turn count. Conversation text never enters the
  digest.
- `evidence` — evidence **frame** counts: the total number of frames
  and the per-turn frame counts (see [Evidence frame](#evidence-frame)).
- `confirmations` — every confirmation record raised in the session:
  the action that needed approval, its status (`pending` or decided),
  the decision, who decided, and when.
- `executions` — every approved tool execution: the tool, its status,
  whether the execution matched the approved plan (`digest_match`), the
  receipt status, and completion time.
- `open_items` — how many confirmations are still pending and how many
  executions are still requested in this session.

**Foreign sessions** (another operator's sessions) contribute the
metadata tier only: confirmation decisions, execution receipts, and
record counts — never the title, transcript counts, or evidence counts.

When a source store is temporarily unreadable at creation time, the
affected section reports `unavailable` instead of failing the whole
document; the portal shows a *unavailable* tag on the session card.

### The handover section

The handover skeleton is the shift story in numbers, assembled from the
session entries so a relieving operator sees what happened before
reading any receipts:

- **Coverage counts** — covered sessions, split into own and foreign.
- **`decision_count` / `decisions`** — every decision made on your own
  sessions: action, decision, decider, and when.
- **`execution_count` / `executions`** — every execution from your own
  sessions: tool, receipt status, and completion time. Foreign sessions
  contribute to the count only.
- **`open_items`** — confirmations still pending and executions still
  requested across the whole shift.
- **`open_sessions`** — the session ids that still carry open items.
- **`quiet`** — the honest empty state: `true` when nothing was decided
  or executed anywhere in the shift. A quiet handover is not an error;
  it says the shift needed no interventions.

Documents created before the handover skeleton existed carry no
`handover` section; the portal degrades gracefully (no Handover tab,
the rest of the digest renders as usual).

### The incident report digest (SPEC-043)

An incident report's digest is assembled the same mechanical way, but
its facts come from the incident-service bundle plus the platform's
own stores for the incident's linked triage session. It carries four
deterministic sections:

| Section | What it says |
|---|---|
| `incident` | The incident envelope copied verbatim: id, severity, status, title, summary, source, labels, reporter, and timestamps. The raw alert payload (`triage_raw`) never enters the digest — only a `has_triage_raw` presence marker does. |
| `triage` | The validated triage report verbatim (severity assessment, evidence, hypotheses, next steps, cited skills), or the `not_triaged` marker when the incident has none. |
| `dispatches` | Every connector dispatch outcome (connector, status, reference, error) copied verbatim — possibly empty. |
| `session` | The incident's linked triage session under the same two-tier coverage: a full session entry when you own it, the metadata-only tier when it is foreign and your roles hold the approvals inbox, and the `foreign_denied`, `missing` (no linked session), or `unavailable` markers otherwise. |

Provenance adds the covered `incident_id` alongside the usual session
anchors, and the one-line summary is counts-only — e.g. *critical ·
triaged · triage report present · 1 dispatch · own session* — never
the incident title or summary text.

## The portal rendering: tabs

The document drawer renders the digest as tabs instead of one long
list. The tabs are a **rendering act only** — the stored document, the
audited fetch, and the Markdown export are unaffected:

| Tab | Shows |
|---|---|
| **Handover** | The shift-level counts, open items, and the quiet state (default tab when present). |
| **Sessions** | One card per covered session; foreign sessions are labeled *metadata only*. |
| **Confirmations** | Every confirmation as a row: action, status, decision, decider, decided time. |
| **Executions** | Every execution as a row: tool, status, receipt, completion time. |
| **Evidence & transcript** | Per-session transcript turn counts and evidence frame counts. |
| **Open items** | Still-pending confirmations and requested executions, with the affected sessions. |
| **Raw JSON** | The stored digest verbatim — the artifact of record, inspectable in place. |

Incident reports render their own tab set: **Incident**, **Triage**,
**Dispatches**, **Session**, and **Raw JSON**, with the session tab
showing the linked-session entry (or its marker) and — for
owner-covered sessions — the same confirmation and execution tables.

Both the digest and the narrative render in **bounded panes**: when
either block grows tall it scrolls inside a fixed-height region with an
*Expand to full height* affordance, so nothing is ever trapped off
screen.

## The list summary line

Document lists show a one-line **summary** under each label. Documents
created with a narrative carry an **AI one-liner (blurb)** — a single
sentence of at most a few dozen words, extracted from the narrative's
own summary line and anchored to the same digest facts. Documents
without a narrative fall back to the deterministic counts-only line,
e.g. *2 sessions · 3 decisions · 1 execution · 1 open item* or *Quiet
shift — no recorded decisions or executions.* Either way the line never
contains session titles, record ids, or decision outcomes — the blurb
inherits the digest's coverage scoping, and foreign sessions appear in
the digest as counts only. Documents created before summaries existed
show label-only rows — that is expected, not an error.

## Vocabulary

### Evidence frame

An **evidence frame** is one captured tool interaction from a chat
turn: a `tool_call` event and its `tool_result`, persisted by the
evidence store so a reopened session replays the same evidence cards
the operator saw live (SPEC-025). The digest reports **frame counts
only, never payloads** — counts are enough to see how much evidence a
session produced, and content is never smuggled across ownership tiers.

### Coverage tier: owner vs foreign

Coverage describes whose session a document entry comes from:

- **Owner coverage** — the session belongs to the document creator;
  the entry carries the full digest (title, transcript counts, evidence
  counts, confirmations, executions).
- **Foreign coverage** — the session belongs to another operator. It
  enters **metadata-only**: confirmation decisions, execution
  receipts, and record counts — never the title, transcript, or
  evidence. Foreign coverage is only possible when the creator holds
  the approvals inbox (`approvals:list`), and foreign entries are
  tagged as such everywhere they render.

### Provenance anchoring

Every document carries a **provenance** block naming each covered
session, its coverage tier, and the confirmation/execution record ids
the digest cites. Provenance lets a later reviewer anchor each digest
fact back to the durable record it was copied from — without any live
reference to the session itself.

### The narrative and the digest facts

The optional handover narrative is generated by a model **from the
digest alone**, after the digest is frozen. It is written as a short
operator briefing — plain and direct, at most three paragraphs plus a
one-sentence summary line — rather than a status report. It is always
labeled *AI-generated narrative — from this document's digest facts*;
when generation fails, a warning is shown and the digest stands alone.
The narrative is a reading aid — the digest remains the artifact of
record, and only the digest is guaranteed deterministic.

### Envelope-only lists

Document lists are deliberately **envelope-only**: they return ids,
labels, state, owner, timestamps, and the one-line summary (blurb or
counts-only) — never the digest or the prose. Full content is served
only by the single document fetch, which is the surface that carries
the cross-owner read audit. Browsing a list is cheap and un-audited;
opening someone else's document is one audited action.

## Reading a colleague's document

Published documents need no request or grant. Open it, and note:

- The row and the drawer both attribute the creator (*created by …*).
- Your reading a foreign-owner document is recorded on the audit trail
  (`document_read`) — that is by design and expected.
- Foreign sessions inside the document show the metadata tier; you see
  the decisions and receipts their owner granted visibility of, never
  titles or evidence.

## Export

**Export .md** downloads the open document as Markdown — metadata,
provenance, the full digest JSON, and the narrative when included. The
export runs entirely in your browser on the document already on screen:
no extra request, no new audit event. The export always serializes the
full digest, so offline copies stay faithful to the artifact of record.
