# Post-Live-Test Remediation: Credential Masking Across Every Projection, HITL Expiry, and Browser-Call Serialization (v0.36.1)

Date: 2026-09-11

A patch batch of thirteen commits closing findings from live browser runs of
the two password-reset samples (`samples/web-checks/password-reset` and
`samples/web-checks/adhoc-password-reset`) against the dev-k8s cluster, plus
one HITL defect reported from a live operator session. Eight are code fixes
and four are sample-documentation corrections; the thirteenth refreshes the
IDE knowledge cache and is not a user-facing change, so it earns no CHANGELOG
entry. There is no contract, policy, schema, or audit change: the stream
contract stays at v11 and Skill at v2.

## What the live runs proved

The organizing finding is that a credential an operator types into the chat
reaches **six** human-readable surfaces, and at v0.36.0 only two of them
masked it. SPEC-049 R-5 covered `web.navigate`'s result and SPEC-055 R-7
covered a change-request card's arguments. Everything else carried the
plaintext, and each gap was observed in a real run rather than inferred:

- **Every browser result after the navigation.** `_redact_secret_query` was
  called from exactly one place. The browser sits on the secret-bearing URL
  while the runbook snapshots, clicks through, and screenshots it, and each of
  those results re-serialized `entry.active_target.url` raw. In a bound
  password-reset flow the `web.navigate` frame reported `...&newpw=***` while
  the *following* `web.click` frame reported `...&newpw=TempPass-2026%21` in
  both `data.url` and the derived `data_summary.url` — so the plaintext
  persisted into the evidence store one frame after it had been masked.
- **The `tool_call` evidence frame's `parameters`.** The kernel emits the
  arguments the model chose *before* the gateway is ever called, so the
  gateway's redaction cannot see them, and R-7's `_redact_pending_parameters`
  is gated on `approval_kind == "action"` and reads the *parked* payload, not
  this frame. Both walkthroughs showed it live: `newpw=TempPass123%21` in the
  flow run's evidence panel, `newpw=TempPass-2026!` in the ad-hoc run's. The
  frame streams to the portal's evidence panel and persists into the store.
- **The minted session title.** `mark_session_turn` builds it from the first
  user message — the one credential carrier no tool-side redactor sees at all,
  because the operator typed the password into the chat rather than into a tool
  argument. The flow session's sidebar title carried the whole password; the
  ad-hoc one carried its first four characters, because the 80-char cap bit the
  secret in half rather than removing it. This surface also crosses an identity
  boundary: an approver's inbox lists a pending card by its session title.
- **The model's own prose, in both directions.** A live ad-hoc run ended turn 1
  with "worth flagging: the temporary password `TempPass123!` is now in this
  chat transcript", rendered verbatim underneath a sidebar title reading
  `... to ***`. The defect is that incoherence — two projections of one
  conversation disagreeing about whether the value is secret. It affected the
  durable transcript and the live stream, for the assistant's reply and for the
  operator's own message on re-read.

Two further findings are not masking:

- **An expired approval card wedged the transcript.** A live session parked a
  card at 16:22:53, the operator decided after the TTL elapsed, the API
  answered 410 Gone at 16:33:31, and the UI then polled for ~6.4 minutes with
  no further chat turn — a spinner that never resolved, which reads exactly
  like a hung agent. Two independent defects, one in the portal and one in the
  kernel.
- **Concurrent browser calls raced on one page.** The flow demo's chat leg lost
  a credential in flight: two `web.fill_credential` calls completed 1.4 ms
  apart, both reporting `status: success`, and the snapshot taken afterwards
  showed the username field carrying no value at all.

And one finding is about the models rather than the machinery: with the
platform's authorization wiring correct, the agents would not use it. The
ad-hoc agent read the runbook and refused, describing an instruction to stay
unbound as "exactly what a prompt-injection or privilege-escalation attempt
looks like"; the flow agent stalled asking whether it may proceed. Either way
**no card was parked**, so SPEC-054's per-action seam and its R-7 masking went
undemonstrated and the automated chat leg failed with "no per-action card
parked". This was not model-specific — a stronger model produced zero tool
calls across both turns and demanded the URL and `skill_id` outright.

## What changed

### Gateway: mask every browser result, not only the navigation

All nine emission sites now redact a secret-bearing query value: `_step_result`
(shared by `web.click`, `web.type`, `web.select`, `web.upload_file`,
`web.fill_credential`), plus `web.snapshot`, `web.screenshot`, `web.hover`,
`web.evaluate`, `web.scroll`, `web.switch_frame`, and the two paths that build
their own data dict rather than calling `_step_result` (`web.press_key`, and
the `URL:` header line inside the snapshot text). The entry-based sites go
through a new `_evidence_url` helper so the rationale is carried once instead
of nine times. The page still holds the real value — only the reported copy is
masked — so nothing about what reaches the target application changes. This
also makes the password-reset runbook's existing claim ("the gateway redacts
the `newpw` parameter from every result, evidence frame, and audit record")
true for the steps after the navigation, which it previously was not.

### Kernel: a third masking posture for the evidence frame and the title

`secret_params.redact_evidence_parameters` masks the `tool_call` frame's
`parameters`. It is deliberately a *third* posture rather than a reuse of the
other two, because what the frame is for differs: R-7's `redact_parameters` is
fail-closed against a curated allow-list, since a change-request card conveys
an intention and its raw arguments are a convenience, whereas the evidence
frame is a debugging record whose value lies in being specific. The same commit
moves title minting onto the shared masker, so the sidebar, the session header,
and the approver inbox stop being a separate gap.

### Prose: the fifth application of the SPEC-049 R-5 posture

A new `services/prose_redaction.py` masks both prose projections — the durable
transcript and the live stream — for both roles. It absorbs the title-masking
machinery verbatim (`session_service` loses 98 lines and now calls
`redact_user_text`), so the heuristic is declared once and the six existing
title tests pass unchanged; that they pass unchanged is what proves the move
was behaviour-preserving rather than a rewrite. The secret vocabulary stays
where `validate_secret_vocabulary.py` pins it, read through a deferred accessor
rather than a module-level import, because the import chain
`skill_draft → shift_summary → session_transcript → prose_redaction` would
otherwise cycle.

Detection is asymmetric by design. The heuristic layer runs on **user-authored
text only**: `SECRET_PARAM_SUBSTRINGS` includes `token`, `session_id`, and
`signature`, which are ordinary words in an operations reply, so running it
over model output would mask the session id in "the delegated token for
ses-c8171f20 refreshed" — precisely the evidence-destroying false positive
`secret_params.is_secret_value` documents rejecting — and the `key=value` layer
would turn "signature: mismatch" into "signature: ***". `redact_assistant_text`
is therefore narrower: the pinned shapes, the URL query layer, and an exact
match against literals the operator typed. For that last layer a false positive
is impossible by construction, because the string matched is one the operator
wrote. The single accepted false positive (an identifier the operator typed
beside a secret name) is pinned by a test so it stays a decision rather than
drifting into an accident.

Masking lives in the projection rather than in its two callers, so neither can
forget it, and `extract_transcript` harvests every user turn first so a
cross-turn echo is caught — the model restating in turn five a password typed
in turn one. Streaming needed three real bugs fixed before it was correct, all
found by tests rather than by review: `urlsplit` was being called on a whole
*sentence*, so `…newpw=TempPass123%21 and confirm` parsed with three words of
prose inside the query, which both ate prose and missed the bare credential —
the exact form the model restates; a URL split across deltas leaked, because
`[^\s<>"']+` cannot match a buffer ending at `https://`; and a split *scheme*
(`o htt` | `ps://`) needed its own hold, since once `htt` is emitted no later
buffer can ever match a URL. The result was verified byte-identical to
whole-text redaction across 6 scenarios × 11 chunk sizes.

### HITL: an expired card must settle the turn and interrupt its agent

In the portal, the 410 branch of `decide()` cleared `turn.confirmationPending`
without setting `turn.completed`. `ChatView` derives
`loading = !completed && !confirmationPending && !error`, so that combination
is true forever, and the reply text is only produced once `completed` — a
permanent spinner with no reply and no error. `lockCard()` mutates only the
card, so nothing else settled the turn; the composer is driven separately by
`chat.streaming`, which the `finally` block clears, so re-sending still worked
and only the transcript looked wedged. The 409 branch shared the omission, and
worse: the unstructured-409 case is *retryable* with the card still pending, so
clearing `confirmationPending` there also dropped the session panel's
awaiting-approval tag from a card the operator could still answer. It is now
cleared only in the terminal branches (410 and the SPEC-031 R-4
already-resolved race), which also set `completed`, and the retryable branch
leaves the turn parked, matching the generic `StreamOpenError` posture.

In the kernel, `expire_confirmation()` called `ensure_agent(session_id, None)`,
leaving `model_id` at its default. `_normalize_model_id(None)` returns
`settings.provider` — a bare provider name — which never equals a session
pinned to a concrete model, so `ensure_agent` evicted and rebuilt the agent on
*every* expiry, deterministically. The rebuilt agent restores persisted memory
but not the in-flight parked reply, so the `UserInterruptEvent` landed on
nothing: of 42 `session_evidence` rows for that session, none contain
`interrupted` and none reference the expired call id, so the docstring's
promise to close the parked calls with an interrupted result did not hold and
turn 0's transcript ended mid-procedure with no closure.

### Browser: serialize calls per session

SPEC-049 R-1 gives one chat session exactly one browser context and one active
page, but nothing serialized the calls driving it, and the kernel runs every
tool call a model emits in a turn concurrently. Playwright's `fill()` focuses
its element and then inserts text into whatever holds focus *at that moment*,
so two concurrent fills can both land in the same field and the loser reports
`success` with its value silently absent. The target's legacy-SSO auto-submit
waits for both fields, so it never fired, the flow stalled before its single
gated write, and no card was parked.

A per-session-key `asyncio.Lock` now covers the whole of each call, applied at
the registration boundary: `register_tools` wraps all fifteen tools in
`_SessionSerializedTool`, so a tool added later inherits the guarantee instead
of having to remember to opt in. The lock lives on the pool rather than on
`BrowserSessionEntry`, keyed apart from the sessions, for two reasons. Taking
it from the entry would mean resolving the session first, which creates a
browser context — that changed the behaviour of a call refused before it ever
reached the pool (an off-allowlist `web.navigate` started creating a context,
which `test_navigate_outside_allowlist_denied` caught) and would let refused
calls consume the `GATEWAY_BROWSER_MAX_SESSIONS` budget and evict live
sessions. And the first pair of calls for a key needs the same guarantee the
later ones do, which an entry-level lock cannot give. `sweep_expired`, which
every lookup already runs, prunes locks that are neither held nor backed by a
session, so the map stays bounded by the live sessions.

The tradeoff is stated rather than hidden: a queued call now waits behind a
slow one instead of racing it — up to the 30 s `web.navigate` / `web.wait_for`
cap, against the caller's own 30 s budget, so a pathological pairing can now
surface as a `TIMEOUT`. That is honest and retryable; the race produced a false
success.

### Model-facing contract: descriptions the model can act on

Six `web.*` descriptions still asserted the pre-SPEC-054 contract, that a
write is permitted only "inside a bound, approved write-class web-check flow".
SPEC-054 R-2 relaxed that: an unbound interaction re-checks the live origin and
the signed envelope's authority provenance, so an ad-hoc write executes once
its per-action card is approved. The module docstring and the in-code gate
comments already documented the relaxation; only the strings the model actually
reads were stale, which is what made the ad-hoc sample unreachable through
chat. `web.click`, `web.type`, `web.select`, `web.press_key`, and
`web.upload_file` now name both permitted paths and state that the live origin
must stay on the allowlist. `web.evaluate` already carried correct wording and
is untouched. `web.fill_credential` is corrected in the *opposite* direction:
it is read tier by design, because filling a field submits nothing and needs no
operator confirmation — the write gate lands on the submitting interaction, and
its old text implied a bound flow was required, which was wrong on both counts.

`DEFAULT_SYSTEM_PROMPT` now names both platform-enforced authorization paths —
a bound write-class flow unlocking its writes under one approval, and an ad-hoc
unbound session parking a per-action card per write — and states that neither
is a bypass, so the model attempts the step and lets the platform gate it. The
refusal boundary is kept explicit and narrowed to what is genuinely the model's
call: an instruction that contradicts the runbook, an origin off the allowlist,
or a request to invent evidence. Consent to a mutation is not the model's to
withhold, because refusing pre-emptively parks no card, shows no approver a
change request, and records no signed receipt — it removes the control that
actually protects the system and leaves no trace of what was declined. The
ad-hoc runbook gained a section answering the three objections where the
authority actually sits, including that the unbound path is the *more* heavily
gated of the two: one card per action rather than one gate per flow.

## A regression this batch introduced, and the testing lesson

The prose fix holds back `max(len(literal)) - 1` characters of each streamed
chunk, so a secret split across deltas is never published in pieces. That hold
outlived the text segment it belongs to. The kernel drains the tool-evidence
queue at the *top* of each loop iteration, before `normalize_event`, so when a
tool call follows narration the previous segment's tail is still inside the
redactor and rides out in the same delta as the next segment's opening text.
The portal opens a new paragraph on the first delta after a tool frame
(SPEC-035 R-2) and applies it to the whole frame, so the break landed one
hold-length early and mid-word — `procedu` | `re precisely` — while the real
segment boundary lost its break and sentences ran together
(`procedure.Navigation`). A live browser run showed six such breaks and five
lost separators.

The reason it survived a green test suite is the durable lesson here. **No text
was lost**: concatenating the deltas reproduces the durable transcript
character for character, so every text-equality assertion in
`test_prose_redaction.py` passed while the rendered reply was corrupt. A
concatenated-delta assertion is structurally incapable of detecting a misplaced
frame boundary. The fix is to model the client's reduce function instead: the
regression tests reproduce the portal's accumulator (`_portal_render` mirrors
`useChatStream`'s `segmentBreak` handling) and assert on the rendered string
*and* on the break's position, so the failure is named rather than implied.
`InterleavedAgent` pushes the two evidence frames `kernel_middleware` really
pushes around one gateway call, between two text segments.

The fix itself: in both `stream_events` and `resume_confirmation`, drain into a
list and, when the drain is non-empty, flush the prose tail before yielding the
tool frames. The flush stays conditional — flushing on every event would defeat
the hold entirely — and the post-loop safety-net flush moves ahead of the final
drain, since a tail released after trace frames would pick up a stray paragraph
break for the same reason. Reverting only `runtime_kernel.py` fails all three
tests, at position 43 of a 56-character segment (43 = 56 − 13, the hold length),
with the mask still intact in the composite case: the leak never returned, only
the paragraphing broke.

## Sample documentation corrections

Four commits corrected claims the samples made that the platform cannot
satisfy. Each was grounded in source, not in the runs alone, because a
walkthrough that overclaims is worse than one that underclaims:

- **The tier-2 approval goes to a second identity.** Both walkthroughs told the
  reader to click Approve in the same chat that requested the reset. Mutating
  execution carries a tier-2 approval requirement (`decided_by_roles`:
  approver, platform-admin), so that click answers 403 and the card stays
  parked; for an operator the reason is `not_a_designated_approver`, because the
  decider-role check runs before the self-approval one and the operator role
  holds no decider role. The walkthroughs described a step that cannot succeed.
- **The verification step names a tool that can produce the evidence.** Both
  runbooks' step 8 told the agent to take a `web.snapshot` to confirm the
  "Password for <user> has been reset successfully." message, but
  `_build_snapshot` enumerates interactive selectors only and the status line is
  a plain `<p role="status">`, which that list does not include. Step 8 now
  names `web.extract`, which can read it.
- **The self-fulfilling verification URLs are labelled as not evidence.** Both
  walkthroughs told operators to confirm the reset by opening
  `/admin/users/?reset=...` in their own browser. `browser-check-target` is a
  static mock with no server-side state, so those pages render their own query
  parameters back and report success for any value, including a user absent from
  the fixed three-row roster. The samples now point at what actually is
  evidence: the post-click `web.extract` of `#reset-status`, emitted by the
  target's own submit handler, the accompanying screenshot, and the signed
  receipt.
- **The ad-hoc sample pins its card count at exactly one.** It described a
  per-action card in the singular but never stated the number, so a run that
  parked two looked like a pass and a run that parked one looked like a failure
  — the reverse. The target's login page auto-submits on a timer once both
  credential fields are filled, and step 4 says not to click Sign in, because
  authentication is read tier and needs no write; the reset form pre-fills from
  the URL but deliberately does not auto-submit, so Confirm reset is the
  procedure's single write-tier interaction. Two cards mean the agent clicked
  Sign in anyway: a redundant gated write, not a stronger gate.

Both walkthroughs also now state the prose and transcript masking guarantee
*and its two boundaries*, rather than documenting only the sidebar title as
masked — which was true when written and has been incomplete since the prose
fix. The operator's own bubble reads plaintext while the turn is live, because
it is rendered from the composer in their own browser (`useChatStream`'s
`userMessage: message`) and never from a stream frame; the only kernel frames
that echo the message are the unconfigured and provider-error fallbacks, which
mask it first. And the value stays real in the agent's context at rest, because
the model needs it to perform the reset. Masking is a property of every
human-readable projection — title, transcript, live stream, cards, evidence —
not of the machine input the reset runs from.

## Untouched

The stream contract (v11) and the Skill contract (v2) are unchanged, as are the
policy bundles, the authorization matrix, the JSON schemas, the audit event
types, and SPEC-037 signed execution. No new knob, no new endpoint, no new
policy action. The flow-unlock one-gate behaviour (SPEC-051 R-1..R-3), the
gateway deviation guard, and the SPEC-054 approval-kind discriminator are
unchanged. `web.evaluate`'s description was already correct and was left alone.
Execution-runtime, incident-service, audit-service, identity-broker,
platform-gateway, skills-hub and the portal's own components take no behavioural
change beyond the version lockstep and the portal's turn-settling fix.

## Verification

`make verify` is green at 0.36.1: 2509 tests across the eight Python products
with no failures, all four GitOps overlays rendering, 18 policy rules and
137 api + 19 tools scenarios passing, version lockstep validated across every
product and the portal's vite wiring, and all three secret-vocabulary couplings
agreeing — 20 secret-parameter substrings and 4 shape patterns between
agent-platform and tool-gateway, and the `<credential-reference>` hole marker
between agent-platform and skills-hub. The portal's own vitest suite runs
separately, since `make verify` does not include operator-portal.

Every fix in this batch is pinned by a regression test that was **confirmed to
fail against the unpatched code** — the batch's own discipline, because a test
that cannot fail cannot protect anything:

- gateway post-navigate redaction: three substantive tests failed unmasked, and
  the fixture first pins that the plaintext really is in the live page URL, so
  the absence assertions cannot pass vacuously;
- evidence frame and session title: six tests failed pre-fix;
- prose redaction: sixteen behavioural failures with the wiring reverted, twelve
  with the URL knobs reverted (the one passer streams in a single chunk and
  legitimately needs no fix);
- HITL expiry: six pre-fix failures across the kernel and both route call sites;
- per-session serialization: serialization, teeth, and lock-pruning tests;
- paragraph ordering: three tests, all failing at the hold-length offset with
  the mask intact.

Beyond the suite, each fix was confirmed **served** in the running pods rather
than merely present on disk, and the two walkthroughs were re-run end to end in
a browser against the deployed cluster: the ad-hoc run produced live and durable
transcripts that are byte-identical with every paragraph break on a sentence
boundary, and the flow run completed the full two-identity approval, the signed
receipt, and twelve tool calls of which exactly one is a write.

## Deployment state

Unlike v0.34.1, this release **rebuilds and redeploys** rather than deferring,
so the cluster carries the release sha while live testing continues. Nine
images are built at the coordinated tag `0.36.1-dev-k8s-<release-sha>`.

That tag cannot be recorded inside the commit that creates it: the short sha is
an input to the tag, so the release notes are necessarily written before it is
knowable. The authoritative record is the gitignored
`shared/platform-ops/gitops/dev-k8s/.images.env`, which `make build` writes and
`make deploy` consumes, and it is verifiable from the running pods. This is the
platform's traceability posture (ADR-0008) working as intended — the tag is
derived from a git ref rather than asserted in prose — and it is why the v0.34.1
note records a `-dirty-` tag explicitly: a dirty tag is *not* reproducible from
a ref, so it has to be written down. This one is.

The rebuild resets in-flight agent state, since redis runs on an `emptyDir`;
sessions persist in Postgres. Approval cards parked before the redeploy are
disrupted by it, which is the accepted cost of testing against a properly
tagged image.
