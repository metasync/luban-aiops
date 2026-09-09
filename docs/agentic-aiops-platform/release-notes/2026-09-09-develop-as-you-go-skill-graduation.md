# Develop-As-You-Go Skill Graduation (v0.36.0)

Date: 2026-09-09

A release train delivering SPEC-055, the seventeenth R5 slice and the **C**
phase of the operator-approved A→B→C HITL redesign (A = the v0.34.1 SPEC-051
R-6 headline-leak patch, landed; B = SPEC-054 action approval, landed at
v0.35.0; C = this spec, gated on B reaching `delivered`). It implements
**ADR-0009**: an operator who troubleshoots through chat, approving each
mutation as it parks, can **graduate that session** into a replayable
executable-flow skill — captured as a by-product of the approvals already
given, re-validated for blast radius, handed to a human as a draft to merge,
and replayed under **one** gate with every write still signed. Shared
contracts, agent-platform, skills-hub, platform-gateway, tool-gateway and the
portal touched; execution-runtime is verify-only. One new policy action, one
new audit event type, three new knobs.

## SPEC-055: develop-as-you-go skill graduation

### R-1 — a durable authoring-trace store

- `execution_records` is a receipt sweep, not a replay trace: it is ordered by
  `requested_at`, stores an `args_digest` (a hash for signature verification)
  rather than replayable arguments, and is swept at 30 days. "Develop now,
  graduate later" outlives that window and needs the arguments, so the
  operator chose a **dedicated authoring trace** over retention-bounded reuse.
- A new `AuthoringTraceStore` (`Protocol` + `InMemory` + `Postgres` + a
  `build_*_store` factory) mirrors `execution_records`/`confirmation_records`.
  Every schema field exists on **both** backends — the skills-hub
  `web_target`/`risk_class` lesson, where a field on one backend only is
  silently dropped in production.
- A step records the ordered position, the canonical tool name, the
  **secret-safe parameterized** arguments, and *references* to the originating
  `execution_id`/`confirm_id`. It never duplicates the signed receipt or the
  outcome; those stay where the tamper evidence belongs.
- The lifecycle is `draft → graduated | discarded`, **not** time-swept with
  the execution window. A per-session cap (`AGENT_AUTHORING_TRACE_MAX_STEPS`,
  default `100`) bounds an unbounded session, and an idle-GC
  (`AGENT_AUTHORING_TRACE_IDLE_DAYS`, default `180`, `0` disables) reclaims
  still-`draft` traces at startup and opportunistically on write. A terminal
  trace is never swept — but it does cascade when its owner deletes the
  session, because the lifecycle guard is against *time*, not against the
  owner removing their own data.

### R-2 — capture at the approval seam

- The trace is populated as a by-product of an **already-approved,
  already-signed** mutation, at the same resume/receipt seam that writes
  `execution_records`. No new trust surface, and no capture of anything
  un-approved.
- **Both** signing sites append — the per-action one (SPEC-054 R-2) and the
  flow-unlock one (SPEC-051) — so a mixed troubleshooting session yields one
  coherent ordered trace rather than two half-traces.
- *Being signed is not being a mutation.* `DEFAULT_AUTO_ALLOWED_TOOLS` is a
  curated subset, so an unvetted **read** tool (`elastic.search_logs`) parks,
  gets approved and gets signed exactly like a write. Capture is therefore
  gated on the platform's single risk→action mapping
  (`RISK_LEVEL_ACTIONS[tier] == "tools:mutate"`), so the seam and the policy
  bridge cannot disagree about what a mutation is — and it fails **closed** on
  an unclassified tier rather than open on `!= "read"`.
- Capture is best-effort: a trace-store failure degrades to "no graduation
  candidate" and never blocks the mutation's execution or its receipt path.
- Secrets are parameterized **at capture time**, so a literal never reaches a
  store that outlives every receipt. This deliberately diverges from R-7's
  fail-closed masking: masking every off-allow-list argument would placeholder
  `web.click.selector` and `web.navigate.url` alike and make every trace
  un-graduable, so the trace predicate targets *credential values*
  (vocabulary plus per-tool opaque fields, allow-list exempt). The residual
  gap is **bounded, not closed** — bounded at the other end by R-4, which
  refuses a trace still carrying a placeholder, and by the vocabulary, which
  is the only control over an off-vocabulary literal.

### R-3 — an executable-flow skill class

- The skill contract advances **Skill v1 → v2** additively: an optional `kind`
  (`knowledge | executable_flow`, absent = `knowledge`) and an optional ordered
  `steps` list of `{tool, args, expect?}` whose `args` carry credential-set
  **references**, never literals. A knowledge skill with neither validates
  exactly as before, so no existing skill breaks.
- `risk_class: read|write` is now accepted **without** a `web_target` — the
  ingestion rule "risk_class requires a web_target declaration" is relaxed, so
  a non-browser mutating skill (one that runs `k8s.*`) can declare that it
  mutates. This is the explicit mechanism the operator asked for, mirroring a
  tool's risk attribute rather than inferring mutating-ness from a browser
  declaration.
- skills-hub validates the class on the existing `validate_document` path
  SPEC-044 drafts against, and `skill_store` carries `kind TEXT` + `steps
  JSONB` on **both** backends. Two deliberate tightenings beyond the spec
  text: `risk_class: write` is required **unconditionally** for
  `kind: executable_flow` (skills-hub holds no per-tool risk vocabulary to
  check a `read` claim against — the authoritative `risk_level` lives in the
  gateway's tool definitions — while declaring `write` costs only that the
  flow replays under one gate), and a `web.*` step **still** requires a
  `web_target` (R-3 decouples the two fields; it does not license a browser
  flow with no origin to bind to).
- `shared/shared-contracts/skill-format.md` advances v1 → v2 alongside the
  schema. It is the human-readable half of the same contract and still
  documented the exact rule R-3 removes, so shipping the validator without it
  would have left the doc authors lint against contradicting the code.

### R-4 — graduation with blast-radius re-validation

- `POST /api/v1/sessions/{session_id}/skill-graduate` assembles the draft
  **deterministically** from the trace. Contrast SPEC-044's `skill-draft`
  beside it: that endpoint asks a model to synthesize knowledge prose and
  falls back to a facts-only skeleton, so it always returns something. This
  one renders what the session actually did, or it refuses — no model call, no
  skeleton, and no step that was not approved by a human and signed before it
  ran.
- `revalidate_blast_radius` runs **before** the draft exists, re-applying at
  graduation the guards the tool-gateway applies at replay: the step budget
  (`AGENT_SKILL_GRADUATION_MAX_STEPS`, default `20`), every observed origin
  inside the declared target's origin, a write-class declaration with no
  read-tier step in it, and no unresolved credential placeholder — plus a
  **fifth** guard that is graduation-only rather than a replay guard, refusing
  an argument *shaped* like a secret literal. It is the one guard whose
  inference is a guess (the other four read a fact the trace records), it
  exists because R-2's capture-time parameterization is name-based and
  deliberately fails open, and it over-catches on purpose: a `web.select`
  option reading `Basic Authentication` is refused too, because a false refusal
  costs an operator a re-author while a false accept publishes a credential
  into the one artifact a human merges into a repository. A trace that
  fails answers `409` naming every guard it failed and the steps responsible —
  the refusal text *is* the operator's remedy.
- "Target/origin" turned out to be **two** things, and both are recorded
  rather than inferred (a stage-6a refinement):
  - the **declared target** (`authoring_trace_target`, one row per session) is
    the web target the operator names when opening a develop-as-you-go
    session. Declared *before* mutating, it is an **authorization scope** the
    session acted under — strictly stronger than scraping a target out of the
    trace afterwards, which would be an untrusted post-hoc claim fitted to
    whatever happened. Graduation emits it as the draft's `web_target`, the
    security parameter a replayed flow binds its origin guard and step budget
    to.
  - the **observed origin** (`authoring_trace.flow_origin`, one column per
    step) is what the gateway reported each captured mutation actually landed
    on. Re-validation checks every observed origin against the declared
    target, so "every origin allowlisted" is substantiated by evidence rather
    than asserted about a trace that never carried any. A step with no
    observed origin is *unverified*, not drifted, and refuses.
- The origin is captured at the **receipt seam**, the only place it is legible:
  `build_receipt` stores an `outcome_digest` alone, and `data["url"]` survives
  for exactly one moment. `_observe_step_origin` runs right after
  `save_receipt` (receipt first, so the tamper evidence is durable before a
  derived trace amendment is attempted), is scoped to `BROWSER_WRITE_TOOLS`,
  and takes the `status` already written into the receipt — only a `succeeded`
  result is observed, because a failed or timed-out write can still report the
  URL it was *attempting*, and corroborating that as "landed on target" would
  let a mutation that never happened count toward graduation.
- A declaration is stored as origin **and path**, never as a bare origin:
  `bind_flow` requires origin equality *and* path containment, so collapsing
  the path would silently widen the graduated skill to every path on the host.
  Query, fragment and `user:password@` userinfo go the other way
  (`skill_target_scope`): `bind_flow` reads none of them, so storing one would
  advertise a narrowing that does not exist — and a target pasted from an
  address bar is exactly where a session token rides, into a table that
  outlives every receipt, into a structured log field, and into an audit
  payload. Userinfo is worse than a leak: it normalizes to an origin no
  browser will ever report, so graduation would refuse a trace that ran
  perfectly. It is stripped at declaration, where the input is still the
  operator's own, rather than deeper in a path that has already stored it.
- Graduation produces a **draft for human review and merge**, previewed
  (rendered + raw) and downloadable in the SPEC-045 pattern. The draft *is*
  the ephemeral response — nothing is persisted server-side, and the platform
  never auto-publishes an executable mutating skill.
- Gated by one new policy action and one new audit event type.
  `session:skill_graduate` is deliberately **not** folded into
  `session:skill_draft` (OQ-3): the artifact declares `risk_class: write` and
  a machine-readable replay step list rather than knowledge prose, so it is a
  higher trust level and is separately authorized. It follows the
  operational-role grant pattern of its authoring siblings —
  `platform-admin`, `approver`, `operator` — with `developer`,
  `read-only-observer` and `auditor` receiving the standard audited policy
  403. One grant covers both graduated-session entry points (the chat header's
  **Graduate as skill** and the mid-session **Declare target** route).
  Declaring at session *birth* rides `session:create` alone: it is inert,
  granting nothing and only narrowing what a later graduation may emit, so
  dual-gating it would refuse session creation over an inert field.
- Each export is recorded once as a `skill_graduated` event whose `details`
  carry the session, the mode, the step count, the `web_target` scope in force
  and the declaration-ordering verdict. The declare-target route is
  deliberately unaudited at the gateway — a declaration is a scope, not an
  operational act against an external system — and `session_created` records
  only a boolean `skill_target_declared` flag rather than the URL, so
  `skill_graduated` is where a reviewer learns which origin a graduated flow
  is bound to. The trace's lifecycle flips to `graduated`.

### R-5 — replay under one gate

- Replay needed **no new executor**. Once ingested, a graduated executable
  flow is an ordinary `web_target` + `risk_class: write` skill and binds
  through the existing SPEC-051 path (`_observe_flow_binding` →
  `_record_flow_approval` → `_sign_flow_execution` → `build_flow_request`),
  parking **one** `flow`-kind card whose subsequent writes are each
  individually signed, persisted, audited and receipted.
- The requirement is one of **indistinguishability**, and it is guaranteed
  structurally twice over. A flow's `steps` list is the replay contract the
  *agent* follows under the single gate, never an input *to* the gate — were
  it one, a skill author could widen their own blast radius by writing a
  longer step list. So `bind_flow` reads only
  `web_target`/`risk_class`/`title`/`description`/`flow_intent` and takes its
  budget from the gateway's `GATEWAY_BROWSER_FLOW_MAX_STEPS` knob rather than
  from `len(steps)`, **and** `FlowState` declares no `kind`/`steps` field at
  all, so `to_dict()` emits a fixed envelope that `FlowContextStore.record`
  reads by named key and `build_flow_request` signs as a fixed payload. Either
  half alone would leave a way in, so both are pinned by test — the gateway
  strips, and the kernel would strip anyway. The discriminating test is the
  budget: a five-step flow bound with `flow_max_steps=2` gets `max_steps ==
  2`, two writes land, the third is `BROWSER_FLOW_EXHAUSTED`.
- Credentials resolve **at replay time** from the named credential sets a step
  references. A graduated skill is shareable and replayable precisely because
  it carries no literal secret. Executable-flow writes join **no** auto-allow
  list, and the gateway deviation guard (origin allowlist, declared
  `risk_class`, step budget) bounds a replayed write identically to a
  hand-authored one.
- **Non-browser replay stays deferred (OQ-2).** Today's flow binding
  (`FlowContext`/`web.navigate(skill_id=…)`) is browser-specific, so an infra
  (`k8s.*`) executable flow's steps park **per-action** under SPEC-054 R-2.
  That is the asserted safe fallback rather than a gap — it fails safe, joins
  no auto-allow list, and the generalized binding is anchored to its own
  follow-up train.

### R-7 — approval-seam secret-masking hardening

R-7 closes the two change-request secret-masking gaps SPEC-054 **recorded and
deferred** (its Non-Goal "No masking of the raw parameters already persisted
on the durable record" and OQ-5, re-confirmed by its delivery review). They
are not regressions SPEC-054 introduced, and they are the source-side
complement of R-1/R-2: those keep a literal secret out of the **derived**
trace, R-7 keeps it out of the **approval-seam record and projection** the
trace is captured from.

- **Fail-closed projection masking.** `secret_params.should_mask` is flipped
  to *mask unless positively known safe*, with a new curated per-tool
  `KNOWN_SAFE_FIELDS` allow-list for the fields that may render verbatim
  (`k8s.delete_pod` name/namespace, `web.select` value,
  `web.fill_credential` credential_set/field, `web.press_key` key,
  `web.upload_file` filename), and `_generic_fields` inherits the posture. A
  generically-named secret under an off-vocabulary key now masks instead of
  projecting as plaintext.
- **No literal secret at rest, on the stream, or in the expander.** For an
  `action`-kind card the raw `parameters` values are redacted **in place**
  (keys preserved, secret-bearing values → `***`) beside the `change_request`
  projection, so nothing plaintext persists in
  `confirmation_records.pending_calls`, rides the `confirmation_request`
  frame, or renders in the portal's "Technical details" expander — which now
  presents the masked projection. `flow` and legacy cards are unchanged.
- This ships with **no contract change** and a byte-identical signed
  `args_digest`, which is what made the deferral reconcilable: the digest is
  computed at resume from the in-memory `PendingConfirmation` (`build_requests`
  re-parses `tool_calls`), never from the persisted JSONB or the frame, and a
  parked confirmation never survives a restart. Masking is therefore a pure
  display + persistence projection.
- `web.evaluate.expression` joins `OPAQUE_VALUE_FIELDS`. Arbitrary JS can read
  a masked secret off the page and can *be* the mutation
  (`document.querySelector('#pw').value = '<literal>'`); it is write-tier, in
  `BROWSER_WRITE_TOOLS`, and the change-request projection already refused to
  render it — so without this entry the trace projection was the one place a
  JS-embedded literal survived, into a store that outlives every receipt. The
  nesting walker now takes the tool name, so per-tool opaque fields hold below
  the top level too.

## The skill-graduation sample

- A new `samples/web-checks/skill-graduation/` tutorial (`README.md` +
  `WALKTHROUGH.md` + `demo/demo.sh`) drives the whole loop against the same
  admin portal as its two siblings: author a session of individually-approved
  mutations, graduate it, merge the draft by hand, then replay the merged flow
  and compare the two sessions side by side. However many cards the authoring
  transcript holds, the replay session holds exactly one — collapsing that
  count is the whole point of graduation.
- It is the only web-check sample that ships **no `skill/` directory**,
  deliberately: the skill is the artifact the demo *produces*, and a
  hand-written one would beg the question. Consequently `deploy-samples.sh`
  (which discovers samples by `find -type d -name skill`) cannot see it, so
  act 3 patches the `skills-samples` ConfigMap directly under the same
  `<sample-leaf>-<file>.md` key convention, and the `cleanup()` trap removes
  that key on exit — a write-class executable flow left behind would be
  indistinguishable from a properly merged one — unless
  `KEEP_GRADUATED_SKILL=true`.
- `demo.sh` runs six deterministic legs (connector and HITL bridging and the
  four relevant knobs including the `graduation budget <= replay budget`
  relationship; admin pages served; the `admin-portal` credential set loaded;
  fifteen `web.*` tools with risk tiers; declared-target first-wins, reported
  scope, and query/fragment/userinfo stripping; graduation posture — an
  observer denied **both** the graduate and the declare route with `403`, an
  untouched session refused `409` naming the missing-trace guard) plus four
  opt-in acts under `RUN_CHAT_LEG=true`, per ADR-0008. The two sibling demos'
  chat legs stay byte-identical and green.

## Untouched / guarantees

Graduation never auto-publishes and persists nothing server-side; the draft is
the response. A flow's `steps` list is never an input to its own gate, so a
skill author cannot widen their blast radius by writing a longer one.
Executable-flow writes join no auto-allow list. Capture happens only for an
approved, signed, **mutating** call, and a trace-store failure can never block
a mutation or its receipt. The signed `args_digest` is byte-identical with and
without R-7's redaction. ADR-0007 is extended, not reversed: a graduated flow
replays under exactly the one gate a hand-authored flow gets. **ADR-0009 is
implemented by this delivery and stays `accepted`.** skills-hub never reads
the trace — it ingests the drafted Markdown like any other skill, preserving
the no-cross-product-import invariant.

## Verification

Version lockstep 0.36.0 validated across all products and the portal
(`VERSION` + 8 `pyproject.toml` + 8 `metadata.py` + 2 `__init__.py` + 8
`uv.lock` re-locks). `make verify` green: 2424 python tests across the eight
products (agent-platform 1142, platform-gateway 354, tool-gateway 336,
skills-hub 184, audit-service 138, incident-service 137, execution-runtime 73,
identity-broker 60), four kustomize overlays, 18 policy rules, 137 api + 19
tools scenarios with every granted pair covered, version lockstep, and all
three secret-vocabulary agreements — including the new
`session:skill_graduate` grants and denials.
The R-1..R-7 → asserting-test mapping is recorded in the spec's `tasks.md`
delivery gate, per ADR-0008, including the `postgres` backend for the trace
store (the dev-k8s backend) checked against a real database rather than only
the in-memory one.

Portal: 342 vitest tests across 29 files green and `npm run build`
(`tsc --noEmit` + vite) clean. Landing that took one test-harness fix worth
recording: React 19's scheduler defers root work to a macrotask (`setImmediate`
under jsdom, there being no MessageChannel) and antd's rc-motion advances an
animated dialog's enter step over several animation frames, so a test that
opens one — the shared skill-draft preview, any Modal, an imperative toast —
can leave a scheduler task queued when it finishes. Vitest destroys the file's
jsdom environment on worker hand-off, the task then fires against a deleted
`window`, and React throws `ReferenceError: window is not defined`, which
vitest reports as an uncaught exception attributed to whichever file the
*worker* runs next. Every test passed and the suite still exited non-zero,
blaming an unrelated file. `src/test/setup.ts` now drains the scheduled work
after each test, while the environment is alive and `act` is still legal, and
scopes `IS_REACT_ACT_ENVIRONMENT` to that drain — leaving it set globally
would turn on React's dev-mode act warning for every async mock that resolves
after a test's `act` block, against tests that are correct as written. The
drain interleaves an animation frame and a scheduler immediate per iteration
rather than batching the frames, because work drained by the immediate — a
React commit — can itself queue the next frame, and its iteration count is
documented as a ceiling with the symptom that means it was exceeded, so a
future longer transition is a one-line raise here rather than a mystery
failure blamed on an unrelated file. No product behavior is involved, and
`make verify` does not run the portal suite, which is why this is recorded
here rather than in `CHANGELOG.md`.
