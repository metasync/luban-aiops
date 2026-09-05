# Release Notes

This folder captures milestone-oriented release notes for the workspace.

During the current pre-release phase, release notes describe implementation
waves and validation outcomes rather than published product releases.

## Available Notes

- `2026-09-05-skill-transparency-and-approval-card-legibility.md`
  - release train (v0.34.0) closing the 2026-09-05 post-live-test feedback
    on the browser-flow approval experience: delivers SPEC-052 (a read-only
    rendered/raw skill content viewer in the portal Skills table via a new
    platform-gateway single-skill detail proxy reusing the `skills:read`
    action and skills-hub's existing `get_skill`; no shared-contract change,
    skills-hub unchanged) and SPEC-053 (one additive optional `flow_intent`
    frontmatter key — ≤ 200 chars, requires `web_target` — authoring the
    plain-language line the single HITL card leads with, carried card-level
    on the existing SPEC-051 R-6 `flow_summary` path from the gateway flow
    binding through the kernel confirmation frame + durable record to the
    portal card; display-only, never a security input; additive contract
    change, stream v9 → v10), plus two portal quick wins (the per-call block
    renders the parsed DOM label as prose with the raw args behind a
    "Technical details" expander, and the post-approval indicator becomes a
    labelled "Agent is working…" spinner row above the evidence). No new
    policy actions, no new audit event types
- `2026-09-05-post-live-check-confirmation-card-flow-headline.md`
  - next-day patch (v0.33.1) from a live test of v0.33.0: the operator's
    live HITL confirmation card rendered without its browser-flow
    description while the approver inbox card showed it, because the
    `confirmation_request` SSE frame is serialized through
    `AgentStreamEvent`, which had no `flow_summary` field — the kernel's
    headline was dropped at that boundary, while the durable record the
    inbox and the post-decision card read still carried it.
    `AgentStreamEvent` gains the optional field (stream schema v8 → v9),
    `_normalize_stream_event` passes it through a defensive coercion that
    keeps only the contract's five string fields, and
    `agent-session.schema.json` declares it on the durable card items (a
    latent gap); pinned by three contract tests — backend plus two shared
    contracts touched, the portal was already correct and is unchanged
- `2026-09-04-browser-flow-hitl-gate-enforcement.md`
  - delivers SPEC-051 (v0.33.0, thirteenth R5 slice): completes SPEC-049
    R-4 platform-side — one HITL gate per mutating browser flow. The
    agent-platform kernel now parks exactly one confirmation card for a
    `write`-class flow's first write-tier interaction, records a
    session-scoped flow authority keyed on the session **and** the flow
    identity (`skill_id` + `origin`), and auto-signs every subsequent
    unlocked `web.*` write under the approving card (still persisted,
    audited, receipted, and bounded by the gateway origin/risk_class/
    step-budget deviation guard). A `FlowContext` maintained from each
    `web.navigate` makes the authority flow-scoped, so a rebind re-parks
    (the ADR-0007 cross-flow trade-off eliminated);
    `AGENT_BROWSER_FLOW_APPROVAL_TTL` (default `900`, `0` disables) bounds
    it. Makes the card flow-semantic (R-6): the headline names the bound
    skill's title/description/target origin/risk class (e.g. "Reset User
    Password in Admin Portal") rather than a bare `web.click`, carried
    from the gateway flow binding through the kernel confirmation frame
    (and a new durable `flow_summary` JSONB column) to the portal card,
    with the tool action kept as secondary detail. Reconciles the
    password-reset sample to a single gate on the destructive "Confirm
    reset" click. Delivered under ADR-0008 (requirement-to-test
    traceability + exercised sample); tracked with ADR-0007. No new
    policy actions, no new audit event types, contracts unchanged
- `2026-09-04-spec-050-browser-tools-expansion-and-samples.md`
  - delivers SPEC-050 (v0.32.0, twelfth R5 slice): the browser tool
    surface grows from six to fifteen tools — nine new `web.*` tools
    (`web.select`, `web.press_key`, `web.upload_file`, `web.evaluate`
    write tier; `web.extract`, `web.wait_for`, `web.hover`,
    `web.scroll`, `web.switch_frame` read tier), each inheriting the
    SPEC-049 server-side guards (origin allowlist, flow binding,
    deviation guard, HITL gate, credential masking). `web.evaluate`
    is HITL-gated write tier with result bounding and a
    defense-in-depth mutation guard (never the security boundary);
    `web.upload_file` allowlists paths under the new
    `GATEWAY_BROWSER_UPLOAD_DIR`; `web.switch_frame` denies
    cross-origin frames and `web.navigate` resets to the main frame.
    Tutorial content moves into a self-contained top-level `samples/`
    tree under a strict tutorial → platform arrow: sample skills
    install out-of-band via `make deploy-samples` /
    `make undeploy-samples` into a generic `skills-samples` ConfigMap
    mounted at `/skills/samples` (skill id
    `samples/password-reset-resetuserpassword`), the base overlay
    names no specific sample, and the former `platform-runbooks`
    ResetUserPassword copy plus its base wiring are removed; no new
    policy actions, no new audit event types, contracts unchanged
- `2026-09-02-spec-049-browser-web-check-tools.md`
  - delivers SPEC-049 (v0.31.0, eleventh R5 slice): a bounded,
    deny-by-default `web.*` tool surface lets the agent verify
    internal web applications — navigate, read pages via ref-minted
    snapshots, bounded JPEG screenshots, and (behind the existing
    HITL gate + signed execution) sign in and click. tool-gateway
    gains a stateful Playwright-over-CDP `BrowserConnector` (library
    only, no browser binary in the image; sessions pooled per chat
    session id so an owner-bound flow survives the approver's HITL
    resume), a server-side origin allowlist
    (`BROWSER_ORIGIN_NOT_ALLOWED` denial), flow binding with a
    deviation guard and one HITL approval per mutating flow, named
    credential sets whose secrets never enter prompts or snapshots
    (leak-asserted tests), skills-hub `web_target`/`risk_class`
    frontmatter, a committed `browser-dev` runtime profile
    (`chromedp/headless-shell` sidecar + `browser-check-target`
    sample app + credential-secret sync + `browser-check-demo.sh`),
    and agent-platform invariant tests pinning that the write-class
    web tools can never auto-allow; the base deployment stays
    byte-identical
- `2026-09-02-spec-048-policy-testing-rollout-controls.md`
  - delivers SPEC-048 (v0.30.0, tenth R5 slice): the policy bundle
    change workflow gains rehearsal, regression, and verification
    controls around the existing engines without touching evaluation
    semantics — a load-time SHA-256 bundle fingerprint on both
    gateways' readiness surfaces and the policy matrix (unchanged
    `policy:read` gate), a scenario-expectation harness pinned into
    `make verify` (131 api / 19 tools expectations over the exact
    engine path, mechanical full-grant coverage so a new grant with
    no recorded intent fails the gate), a `make policy-diff`
    per-(role, action) outcome-transition impact report sharing the
    harness evaluator, the rollout runbook in the configuration
    reference (edit → sync → verify → diff → commit → deploy →
    confirm hash, ConfigMap+restart posture), and copy-parity
    coverage extended to the GitOps overlay copy; no new policy
    actions, no new audit event types, bundle schema and semantics
    unchanged; live check confirmed readiness hashes matching the
    canonical file byte-for-byte on both gateways
- `2026-09-01-post-live-check-audit-events-initial-load-recovery.md`
  - remediation batch (v0.29.3) from the post-v0.29.2 live-check
    observation (Events tab stuck in its initial empty posture next
    to a populated Summary until a manual Refresh): server logs
    proved every gateway 200 served a full page, and the gateway log
    exposed the trigger — a stale expired stored session booting the
    shell signed-in until the silent refresh cleared it, so the
    first audit auto-load 401'd and the initial-load effect latched
    (`!error` guard plus `[allowed]`-only deps). The effect is now
    keyed on the session object as well, clearing latched errors and
    retrying once on identity-lifecycle moves, pinned by a
    stale-session 401 → fresh sign-in → auto-recovery test — one
    component touched, no API / contract / route changes
- `2026-09-01-post-review-remediation-audit-view-hooks.md`
  - review remediation batch (v0.29.2) from the post-v0.29.1 code &
    doc review of the SPEC-047 delivery: the drill-down `useCallback`
    that had landed after the role-gate early return in `AuditView`
    (a Rules-of-Hooks violation that unmounted the whole portal when
    the gate flipped on sign-out or token refresh) moved beside the
    other hooks and is typed to the panel's exported `DrilldownPatch`
    contract, pinned by a role-flip regression test; the SPEC-047
    index line, spec changelog, and delivery roadmap annotate the
    v0.29.1 share-bar retirement — one component touched, no API /
    contract / route changes
- `2026-09-01-post-spec-047-hardening-audit-summary-tables.md`
  - patch hardening batch (v0.29.1) from the operator review of the
    live v0.29.0 Summary tab: the SPEC-047 share cell's progress bar
    is retired (R-4 keeps the one-decimal percentage via the same
    shared formatter) and the bucket tables gain a fixed layout with
    narrow right-aligned count/share tracks so the `name` column
    absorbs the width evenly and the percentage can never wrap; one
    component touched (`AuditSummaryPanel.tsx`), no API / contract /
    route changes, all 259 portal tests green unchanged; the
    pie-chart alternative raised in the same review was adjudicated
    and withdrawn in favor of the compact table
- `2026-08-31-audit-summary-drilldown-and-readability.md`
  - delivers SPEC-047 (v0.29.0): the audit Summary tab becomes a page
    you can act on — a headline statistic row (total + decision chain,
    zeros as 0), collapsible bucket sections (expanded by default,
    section total in the header), a share column per bucket row
    (one-decimal percentage + neutral bar), and drill-down from every
    aggregate value into the Events tab under merged filters; backed
    by the additive **`outcome`** filter dimension on the three audit
    read routes (events / summary / export, four contract enum values,
    422 otherwise) forwarded by the gateway under the unchanged
    **`audit:read`** gate, and `OUTCOMES` joining the portal's pinned
    filter vocabulary behind the existing drift guard; no new routes,
    no new policy actions, no new event types, both contract schemas
    unchanged
- `2026-08-31-audit-reporting-and-export.md`
  - delivers SPEC-046 (v0.28.0): the audit trail gains two read-only
    reporting surfaces that ride the existing **`audit:read`** grant —
    a deterministic summary aggregate over any filter window (bucket
    tables by event type / outcome / service, top actors, and the
    decision-chain counters, zeros included) and a bounded RFC-4180
    CSV export of the filtered envelopes under the new
    **`AUDIT_EXPORT_MAX_ROWS`** cap (default 10000) with honest
    `X-Audit-Export-Truncated` / `X-Audit-Export-Rows` headers; new
    **`audit-summary.schema.json`** contract, gateway pass-through
    (30 s export leg, allowlisted headers), and the portal Audit view
    becomes tabbed (**Events** / **Summary**) with a shared filter
    toolbar, **Export CSV** under the SPEC-040 Blob posture, and a
    vitest drift guard re-syncing the filter vocabulary to the
    contract (20 event types / 7 emitter services); no new policy
    action, no new event type, envelope columns only
- `2026-08-31-post-review-hardening-tool-name-rewrite.md`
  - review-remediation patch (v0.27.6) closing the v0.27.4/v0.27.5
    code review (approve-with-minor): the rewrite's match boundary
    now excludes a leading dot so an already-dotted mention can never
    re-match a pathological suffix key (trailing boundary stays
    word-only so sentence-final names still rewrite), plus four new
    boundary/collision tests; doc review found no findings; portal-
    only, no backend changes
- `2026-08-31-dotted-tool-names-everywhere.md`
  - same-day patch (v0.27.5) broadening v0.27.4: the sanitized →
    dotted tool-name rewrite now covers every rendered surface,
    including inline code spans and fenced blocks — the v0.27.4
    shield assumed configuration surfaces need the sanitized form,
    but the sanitized form has no external consumer and
    `AGENT_GATEWAY_TOOL_AUTO_ALLOW` normalizes dots on input; tool
    lists (which the model backticks) now render dotted too;
    transcripts still keep the model's original words; portal-only,
    no backend changes
- `2026-08-31-dotted-canonical-tool-names-in-chat-prose.md`
  - same-day patch (v0.27.4) in the v0.27 train: chat reply prose and
    incident triage-report summaries now show the registry's dotted
    canonical tool names (`k8s.get_pods`) instead of the sanitized
    form the model writes (`k8s_get_pods`) — a presentation-only,
    render-time rewrite keyed off the `/api/v1/tools` catalog; code
    spans and fenced blocks keep the sanitized form that
    configuration surfaces expect, durable transcripts stay
    untouched, and a failed catalog fetch degrades to no mapping;
    portal-only, no backend changes
- `2026-08-31-chat-markdown-tool-identifier-rendering.md`
  - same-day patch (v0.27.3) from a live test of v0.27.2: the chat
    markdown renderer no longer strips underscores from tool
    identifiers (`k8s_delete_pod` used to render "k8sdeletepod") —
    code fences and inline code spans are fenced from every block/
    inline pass, and the underscore emphasis passes require non-word
    context (CommonMark flanking); escape-first contract and the
    http(s)-only link allow-list untouched; portal-only, no backend
    changes
- `2026-08-30-session-availability-gate-and-gateway-postures.md`
  - same-day patch (v0.27.2) from a live test of v0.27.1: the
    incident-detail **Continue in chat** button now renders disabled
    with an explanatory tooltip whenever the incident's triage session
    is expired, not yet visible, or owned by another operator (gated
    at render time on the caller's own session list; the chat
    **Draft as skill** keeps a 404 toast as a race-window safety net);
    `GET /api/v1/runtime` now carries the platform `version`; the
    identity-service sign-in legs ride the house proxy error model
    (4xx passthrough, 5xx/transport → structured 502) — no routes,
    actions, or event types change
- `2026-08-30-post-release-review-remediation.md`
  - same-day patch (v0.27.1) closing the one High finding from the
    v0.27.0 code & doc review: the incident skill-draft assembler now
    strips the triage `session_id` from the envelope alongside
    `triage_raw`, restoring the "never anyone's session" invariant on
    the incident anchor; the purity fixture carries a session id and
    the assertion pins the strip; spec-trio and release-note wording
    corrected to match — no routes, actions, or event types change
- `2026-08-30-incident-skill-draft-and-preview.md`
  - delivers SPEC-045 (v0.27.0), the seventh R5 slice: a triaged
    incident becomes team-authored guidance — any caller holding the
    new deny-by-default **`incident:skill_draft`** action (dual-gated
    with `incident:read` per the SPEC-043 pattern, granted to the
    operational roles) drafts a validated Skill Format v1 Markdown from
    the incident envelope (minus `triage_raw` and the triage
    `session_id`) plus the validated triage report — never anyone's
    session, never connector dispatches — with a deterministic **409**
    when no validated report
    exists; both entry points (the new incident toolbar action and the
    existing chat session action) now open the validated draft in a
    read-only preview modal (rendered + raw toggle, mode badge,
    Download .md / Discard) before any client-side download; audited
    as **`incident_skill_draft_generated`**; ephemeral by construction
    — nothing about a draft is persisted
- `2026-08-30-skill-authoring-export.md`
  - delivers SPEC-044 (v0.26.0), the sixth R5 slice: one route turns
    the durable record of a session into a validated Skill Format v1
    Markdown draft — digest-only generation input, deterministic
    redaction + cap guardrails, provenance block, and a facts-only
    skeleton degradation that keeps generation 500-free — validated on
    skills-hub's own ingestion code path (new read-only
    `POST /api/v1/skills/validate`) before it reaches the operator,
    then downloaded client-side from the portal's **Draft as skill**
    session action; gated by the new deny-by-default
    **`session:skill_draft`** action (documents-create grant pattern)
    and audited as **`skill_draft_generated`**; ephemeral by
    construction — nothing about a draft is persisted
- `2026-08-29-bounded-pane-review-follow-ups.md`
  - same-day patch (v0.25.2) closing the two minor follow-ups from
    the v0.25.1 code review: the bounded-pane height is single-sourced
    via a `--bounded-pane-max-height` custom property (the CSS rules
    and the overflow comparison can no longer drift apart), and the
    v0.25.1 post-motion re-measure race fix gains a fake-timer
    regression test — portal rendering and tests only, no backend
    runtime change
- `2026-08-29-portal-live-check-polish.md`
  - same-day patch (v0.25.1) remediating the v0.25.0 live-check
    feedback: bounded panes pin their structural chrome (the digest
    tab bar and the narrative collapse header stay visible while only
    the content region scrolls), the **Raw JSON** tab is renamed
    **Digest data** to say what it shows, and the digest reference
    codifies the house layout rule (tables for repeated records,
    description lists for single objects, bullets for long text,
    chips for identifiers) — applied to the incident report Triage
    tab; portal rendering and documentation only, no backend runtime
    change
- `2026-08-29-incident-report-document-type.md`
  - delivers SPEC-043 (v0.25.0), the fifth R5 slice: the operations
    document repository gains its second type — **`incident_report`** —
    a durable, attributed report assembled verbatim from
    incident-service facts (incident envelope, validated triage
    report, connector dispatches) plus the linked triage session's
    digest under the existing two-tier own/foreign posture, with the
    inherited digest-only narrative, draft→publish lifecycle, and
    role-based access matrix; gated by the combination of the existing
    **`documents:create` + `incident:read`** actions — no new policy
    actions, no new audit event types, read-only with respect to
    incident state
- `2026-08-28-post-release-review-remediation.md`
  - same-day patch (v0.24.1) remediating the v0.24.0 review findings:
    the zero-tolerance vitest deprecation guard broadens to cover
    antd's aggregated emission mode (`ConfigProvider warning={{ strict:
    false }}`), plus release-note and tasks.md accuracy polish — test
    and documentation only; no runtime behavior, actions, event
    types, or dependency versions change
- `2026-08-28-dependency-hygiene.md`
  - delivers SPEC-042 (v0.24.0), the fourth R5 slice: the portal
    migrates off every deprecated antd v6 API (**Drawer `width` →
    `size`**, **Alert `message` → `title`**) behind a zero-tolerance
    vitest deprecation guard, applies the managed refresh adopt set
    (**TypeScript 5.9, vite 8 + plugin-react 6, vitest 4, jsdom 30**,
    `engines.node >=22.22.2`) and the **React 19** migration with a
    behavioral gate, and all eight backend products re-lock inside
    their declared ranges (**agentscope 2.0.7.post1**, fastapi 0.141.1,
    uvicorn 0.52.4, cryptography caps raised to 50.x after the
    signing call-site review) — latest stable only, no beta/RC; no new
    routes, actions, event types, or audit changes
- `2026-08-28-components-tech-stack-and-status.md`
  - same-day follow-up polish (v0.23.4) on the Settings component
    table: rows now list the **tech stack underneath** each component
    (React · Ant Design, FastAPI · Python, AgentScope · FastAPI, the
    LLM provider and model, store backends with their server versions,
    policy rules) instead of the redundant component version, and the
    status column adopts one vocabulary — *ready / degraded / not
    ready / unavailable*; informational backend fields only, no new
    actions or event types
- `2026-08-28-platform-components-blurb-prose-voice.md`
  - same-day operator polish patch (v0.23.3): a live **Key platform
    components** table in Settings → Platform (versions and readiness
    from the gateway's health and runtime probes), the AI one-liner
    **blurb** surfaced on Documents list rows, the detail card, and the
    Markdown export, and a prose prompt retuned to a concise,
    human-oriented operator briefing — additive and presentational; no
    new actions, event types, or approval-path change
- `2026-08-28-shift-summary-narrative-expanded.md`
  - same-day portal polish patch (v0.23.2): the AI-generated handover
    narrative in the Documents drawer now opens expanded by default and
    stays collapsible to its header — presentation only; digest, export,
    and audit posture unchanged
- `2026-08-28-mutating-tool-name-regression.md`
  - same-day patch on the SPEC-037/038 signed-execution path (v0.23.1):
    parked mutating calls carried the sanitized model-visible tool name
    into the signed envelope, so the execution worker invoked the
    gateway with `k8s_delete_pod` and every approved `k8s.delete_pod`
    run failed closed with `TOOL_NOT_FOUND`; the park now emits the
    dotted canonical name end-to-end — no new actions or event types
- `2026-08-28-documents-readability-and-digest-reference.md`
  - delivers SPEC-041 (v0.23.0), the third R5 slice: an operator-facing
    digest reference guide, tabbed table-shaped digest rendering in the
    document drawer (tier-aware, Raw JSON retained), bounded scrollable
    digest and prose panes with an expand affordance, and a
    deterministic counts-only summary line computed at creation and
    shown with each document in the lists — no new policy actions or
    audit event types
- `2026-08-28-shift-summary-handover-narrative-export.md`
  - delivers SPEC-040 (v0.22.0), the second R5 slice: a deterministic
    `handover` digest section (decisions, execution outcomes, open
    items, quiet flag), the generated narrative flipped to default
    under a digest-anchoring prompt contract, Documents moved from
    Control to Workspace, and client-side Markdown export for offline
    handover — no new policy actions or audit event types
- `2026-08-27-document-read-audit-integrity.md`
  - same-day patch on the SPEC-039 document repository (v0.21.1):
    document listings are envelope-only (digest/prose omitted) and the
    portal drawer loads full documents through the audited single
    fetch, so cross-owner reads of published documents always emit
    `document_read`; also corrects the guide's deletion wording and
    adds the "Your first shift summary" get-started walkthrough
- `2026-08-27-operations-document-repository.md`
  - delivers SPEC-039 (v0.21.0), the first R5 slice: a platform-owned
    operations document repository — typed substrate with a role-based
    access matrix (draft→publish replaces per-document grants), cap 20
    per owner, 30-day TTL, provenance anchoring, and document audit
    (`document_created` / `document_published` / cross-owner
    `document_read`) behind new deny-by-default `documents:create` /
    `documents:read` actions; Phase 1 ships the shift-summary type
    (deterministic digest with two-tier own/metadata-only foreign
    coverage gated on `approvals:list`, fail-soft digest-only prose
    layer) plus the session-rename (`session:update`) and session-id
    copy add-ons, and the portal Documents control view
- `2026-08-27-isolated-execution-worker.md`
  - delivers SPEC-038 (v0.20.0) and closes R4: approved mutating calls
    leave agent-service via an authenticated internal handoff to the
    new `execution-runtime` worker, which independently re-verifies the
    SPEC-037 envelope signature and parked-arguments digest, executes
    through the tool-gateway under the forwarded confirmer token,
    authors the signed receipt (first-write-wins), and emits the
    correlated execution audit events; blocking bounded-timeout resume
    await, `execution_id`-keyed single-flight idempotency on a pinned
    single replica, fail-closed `worker_unavailable` posture with no
    in-process fallback, and infrastructure-enforced isolation
    (ClusterIP-only, no HTTPRoute, `execution-handoff-secret`)
- `2026-08-27-signed-execution-requests.md`
  - delivers SPEC-037 (v0.19.0): approved mutating calls gain a
    tamper-evident execution chain — HMAC-signed execution requests
    bound to the parked arguments' digest at approval resume (missing
    signing key fails closed), argument-digest verification at the
    invocation boundary, durable execution records and signed receipts
    on the SPEC-031 Postgres posture, `execution_requested` /
    `execution_completed` / `execution_rejected` audit events
    correlated with the decision chain, a read-only receipt badge on
    decided confirmation cards, and the `execution-signing-secret`
    deploy wiring; the isolated execution worker stays Phase 2
- `2026-08-26-live-check-patch.md`
  - v0.18.1 patch from the v0.18.0 live check: the chat markdown
    renderer gains nesting-aware list handling (indented sub-bullets
    nest instead of rendering as literal "- text"; ordered items get
    their `<ol>` back), the SPEC-036 seeded-transcript typewriter is
    reverted (the reveal applies to live arrivals only), and pod-log
    excerpts in replies move to fenced code blocks rendered in a
    fixed-height scrollable box
- `2026-08-26-server-inbox-pagination-and-seeded-reveal.md`
  - delivers SPEC-036 (v0.18.0): the approvals History tab moves to
    server-side pagination (split store queries with a windowed total,
    paginated inbox API, gateway pass-through, server-driven portal
    tab) so decisions past the old 100-row payload cap stay reachable,
    and the typewriter reveal cascades across every reply of a
    cold-seeded transcript instead of only the most recent one
- `2026-08-26-decision-sync-arrival-polish.md`
  - delivers SPEC-035 (v0.17.0): the four v0.16.0 live-test findings —
    transcript segment boundaries (agent-service block join +
    live-stream paragraph break) so resumed headings render, a
    time-based settle window with a visibility kick so slow resumed
    turns land without refresh, progressive arrival reveal with a
    stronger flash and scroll-into-view, session-tag park timing with a
    stale-response guard, plus the approvals banner line and
    History-tab pagination
- `2026-08-26-approval-owner-ux-polish.md`
  - delivers SPEC-034 (v0.16.0): five portal usability enhancements from
    the v0.15.0 live approval test — arrival highlight for post-decision
    content in the owner window, instant session-panel refresh on applied
    decisions, Pending/History tabs in the Approvals view, separated
    inbox entries with structured provenance headers, and a banner note
    on unanswered-request expiry
- `2026-08-26-confirmation-card-turn-anchoring.md`
  - delivers SPEC-033 (v0.15.0): the v0.14.1 live validation found a
    multi-park session stacking every confirmation card under the
    newest turn — parked records now persist their parking turn
    ordinal (additive column with in-place migration), the session
    detail carries it additively, and transcript seeding anchors each
    card under the exchange that parked it, with the legacy
    newest-turn anchoring kept as the fallback for pre-delivery
    records
- `2026-08-25-owner-decision-sync-reseed-patch.md`
  - closes v0.14.1: the SPEC-032 poll applied through `setSession`,
    whose stash-then-restore hands back the stale cached turns for the
    session already on screen — the owner window stayed deaf after an
    external decision; the new `reseedTurns` path replaces live turns
    and the cache entry authoritatively, with regression tests
- `2026-08-25-owner-side-live-decision-sync.md`
  - delivers SPEC-032 (v0.14.0): the owner's open chat window syncs
    externally made decisions live — a bounded, change-gated
    poll-while-pending on the session-detail surface (5s, torn down
    when no card is pending or any stream is active, settle window for
    the trailing resumed-turn content) flips the card with decider
    attribution and surfaces the resumed turn without a refresh;
    portal-only, no backend/contract/policy changes
- `2026-08-25-confirmation-race-and-restart-sweep-patch.md`
  - closes v0.13.1: SPEC-031 review remediations — the confirm route
    persists the durable outcome at claim time (racing approvers get
    `409 already_resolved` even mid-stream of the winner's resume,
    never a bare 404), and the Postgres startup sweep only expires
    pending rows older than the HITL confirmation TTL so a sibling
    replica's restart never kills a live park
- `2026-08-25-approval-inbox-persistent-confirmation.md`
  - delivers SPEC-031 (v0.13.0): durable confirmation lifecycle records
    on the shared Postgres posture (cap 50 per session, cascade delete,
    TTL-scoped startup expiry, registry rehydration), an additive owner-transcript
    `confirmations` session-detail surface so cards survive re-login and
    pod restarts, a decider-scoped approvals inbox
    (`GET /api/v1/approvals/inbox` behind the new `approvals:list`
    action — metadata-only, pending + 30-day history incl. expired),
    structured `409 already_resolved` race semantics, and the portal
    Approvals view with pending-count badge and persistent owner-side
    cards
- `2026-08-25-require-approval-policy-semantics.md`
  - delivers SPEC-030 (v0.12.0): `require_approval` as a first-class,
    enforced policy outcome with approval tiers (`tier_1` operator
    self-confirmation, `tier_2` designated approver with self-approval
    blocked), evaluated in both gateway engines and bridged onto
    `chat:confirm` with structured 403s and blocked-attempt audit;
    default `tier_2` rule on `tools:mutate`, matrix third state
    (`approval_requirements`), portal tier badges + read-only cards,
    and the Settings view restored as a read-only Session & Identity
    panel (add-on R-6)
- `2026-08-25-skills-secret-sync-patch.md`
  - closes v0.11.1: `sync-skills-secrets.sh` preserves
    `SKILLS_AUDIT_CLIENT_SECRET` across its rewrite of the shared
    skills-hub `runtime-secrets.env` (same pattern as the OTLP-header
    preservation), fixing the wipe that 401'd every skills-hub audit
    emission after a plain `make deploy`; version lockstep and
    lockfiles refreshed for the patch
- `2026-08-25-skills-usage-audit-trail.md`
  - delivers SPEC-029 (v0.11.0): skills-hub emits `skill_searched` /
    `skill_retrieved` per authenticated query and one `skills_synced`
    per source per sync cycle via the canonical fire-and-forget emitter
    (fourth parity-guard member), correlated with caller `tool_invoked`
    events through forwarded `x-request-id`; plus the pre-milestone
    review remediation (three operator guides, drift-guard parity
    suite, audit-service 95% / incident-service 92% coverage) and the
    audit-secret rollout-race fix in `sync-audit-secrets.sh`
- `2026-08-24-multimodel-runtime-and-live-discovery.md`
  - closes v0.10.0, the multi-model runtime train: SPEC-024 per-turn
    model selection with session pinning and audit attribution, SPEC-025
    evidence persistence with replayed prop-identical evidence cards,
    SPEC-026 per-provider curated model series with `<PROVIDER>_MODELS`
    override and consolidated `default` runtime profile, SPEC-027
    live `/models` discovery behind a fail-soft ladder (live → memory →
    Postgres → curated), and SPEC-028 the `luban` provider for
    team-hosted OpenAI-compatible servers (Ollama/vLLM/llama.cpp) with
    token auth, an operator hosting guide, and reference Ollama K8s
    manifests; plus four review remediations (confirm-route
    stale-pin degradation, fallback-response provider attribution,
    discovery-cache bootstrap connection leak, Ollama readiness probe
    under token auth)
- `2026-08-22-portal-framework-rebuild.md`
  - delivers SPEC-023 (v0.9.0): the operator portal rebuilt as a
    Vite + React 18 + TypeScript SPA on antd / Ant Design X — a
    platform-owned SSE contract adapter (schema v6, unit-tested), the
    SPEC-022 multi-session workspace UI (session panel, switch/resume
    with transcripts, anchored confirmation cards, parked-delete 409
    posture, incident deep links), browser voice composition with a
    recognition-language selector (`input_modality=voice` metadata only,
    HITL stays click-gated), full view-migration parity (audit,
    permissions, tools, skills, incidents) with role-scoped navigation,
    immutable-cache hashed assets with a no-store SPA shell, and the
    vanilla trio removed at delivery
- `2026-08-22-post-release-hardening.md`
  - closes v0.8.1: post-v0.8.0 code-review hardening — atomic set-once
    Redis session titles (dedicated NX title key), gateway session-list
    proxy 4xx passthrough parity, twelve new store/proxy tests,
    `is_parked`/`has_pending` dedupe, `select-runtime-profile.sh`
    guard against `mutating-dev`, and the documented
    delete-vs-in-flight-turn limitation; no API or contract changes
- `2026-08-22-multi-session-operator-workspace.md`
  - delivers SPEC-022 (v0.8.0), backend-first: session workspace
    lifecycle API (list cap-50 / title + transcript detail /
    owner-only delete with 404 anti-enumeration and 409 parked) under
    the new deny-by-default `session:list` / `session:delete` actions
    with a durable `session_deleted` audit event; voice-readiness
    `input_modality` contract (metadata only, HITL stays click-gated);
    the SPEC-021 dev opt-in promoted to the committed `mutating-dev`
    kustomize profile; plus two walkthrough fixes closed in-release
    (session-detail proxy 4xx passthrough, audit `EventType` enum
    sync)
- `2026-08-22-bounded-mutating-actions.md`
  - delivers SPEC-021 (v0.7.0): the platform's first write capability
    (`k8s.delete_pod`), triple-gated — tool-gateway risk-tier admission
    behind `GATEWAY_MUTATING_TOOLS_ENABLED`, read-only-by-construction
    agent auto-allow, and SPEC-020 HITL confirmation with `mutating`
    badges on stream schema v6 — under the deny-by-default
    `tools:mutate` action; disabled by default in dev-k8s with opt-in
    RBAC, the Approval & HITL Governance Guide, and a deterministic
    `mutating-demo.sh`
- `2026-08-21-durable-otlp-secret-provisioning.md`
  - closes 0.6.1: fixes the OTLP ingest 401 regression where sibling
    secret-sync scripts wiped `OTEL_EXPORTER_OTLP_HEADERS` from five
    service Secrets; provisioning now merges the header cluster-side
    and file rewrites preserve it, restoring authenticated telemetry
    push to OpenObserve for all seven services
- `2026-08-21-hitl-confirmation-bridging.md`
  - delivers SPEC-020: kernel ASK decisions surface as inline approval
    cards (park/resume bridging via `confirmation_request` /
    `confirmation_result` frames and `POST /api/v1/chat/confirm` under
    the new deny-by-default `chat:confirm` action), platform-owned
    permission gating (the allow-list is the only auto-approval
    surface), TTL-safe expiry, `confirmation_decided` audit events, and
    stream schema v5 full-output evidence transparency
- `2026-08-20-portal-transparency-and-navigation.md`
  - delivers SPEC-019: sectioned portal navigation (Chat / Control /
    Workspace) with auto-hiding sections and a logo-row version chip,
    live permission matrix endpoint (`GET /api/v1/policy/matrix`)
    evaluated from the enforced bundle with server-side role scoping and
    a Permissions view, read-only Tools and Skills inventory views behind
    new platform-gateway proxies, new `policy:read` / `skills:read`
    policy actions for all operational roles, and dev-k8s skills-query
    wiring for the platform-gateway client
- `2026-08-17-r3-incident-triage-and-collaboration.md`
  - delivers Release 3 with SPEC-015: new `incident-service` product
    (Alertmanager webhook + manual intake, fingerprint dedupe, dual-backend
    store), operator-initiated agent triage with validated triage reports,
    pluggable connector framework with the built-in audit sink, read-only
    `incidents.list` / `incidents.get` tools, the portal Incidents panel,
    dev-k8s wiring, and a deterministic e2e demo smoke test
- `2026-08-15-skills-and-grounded-guidance.md`
  - opens Release 2 with SPEC-014: canonical skill contract, new
    `skills-hub` product (federated multi-source ingestion, deterministic
    ranked retrieval, dedicated query-credential registry), read-only
    `skills.search` / `skills.get` / `skills.list` tools in tool-gateway,
    skills discipline in the agent prompt, two adapted open-source sample
    sources, dev-k8s wiring, and a deterministic e2e demo smoke test
- `2026-08-12-durable-audit-trail.md`
  - delivers SPEC-013: canonical audit-event contract, new `audit-service`
    product (in-memory + PostgreSQL stores, retention), authenticated
    fire-and-forget ingestion from three services, `audit:read`-gated query
    API proxied via platform-gateway, and the operator portal audit view
  - ships the operator portal shell redesign alongside: two-column
    sidebar/drawer layout, sidebar-footer user and version cards, and
    accessibility polish
- `2026-08-11-r1-close-operator-guide.md`
  - closes Release 1 with SPEC-012: operator guide suite (getting started,
    configuration reference, troubleshooting, tool configuration, architecture
    overview), policy management tooling (`sync-policy`, `validate-policy`),
    and the completion of all 12 Release 1 specs
- `2026-08-10-r1-hardening-grounded-responses-and-evidence-ux.md`
  - summarizes the Release 1 hardening wave: SPEC-011 completion (grounded
    responses with v3 evidence frames), audit log visibility, cluster-wide
    read-only access, permission allow-list and token-rotation fixes, and
    the portal's inline per-turn evidence/audit UX
- `2026-07-30-release-1-tool-execution-and-service-identity.md`
  - summarizes Release 1 (read-only operations copilot): the SPEC-007 tool
    execution framework and the SPEC-008 broker-mediated token delegation
    that completes the authenticated end-to-end tool path
- `2026-07-26-release-0-runtime-and-dev-k8s-overlays.md`
  - summarizes the current Release 0 runtime/provider refactor and the
    GitOps-oriented development Kubernetes overlay and rollout improvements
