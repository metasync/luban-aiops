# SPEC-055 Tasks: Develop-As-You-Go Skill Graduation

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
Ordering follows `plan.md`'s Sequencing And Dependencies — stage 2 (R-7 masking) and
stage 3 (the trace store) are independent; stage 4 (capture) depends on stage 3 and
reads the seam stage 2 hardened; stage 6 (graduation) depends on stages 3 + 5; stage 7
(replay) depends on stages 5 + 6. Contracts (stage 1) come first — everything validates
against them.

## Stage 1: Contracts

> **Lockstep refinement (found at implementation):** a shared schema is never edited
> alone — bidirectional parity tests pin each schema to its consumers, so the schema
> and its bound declarations ship as **one atomic unit** or `make verify` fails. Three
> bindings fold into this stage: skills-hub `schemas/skill.py` (`Skill`/`SkillStep`,
> pulled forward from stage 5), audit-service `schemas/audit.py` (`EventType`), and the
> portal `views/audit/constants.ts` `EVENT_TYPES` (SPEC-046 vitest drift guard — set
> **and order** equality, so `skill_graduated` lands last, matching the enum).

- [x] `shared/shared-contracts/schemas/skill.schema.json`: advance **Skill v1 → v2** — add optional `kind` (`enum: ["knowledge", "executable_flow"]`, absent = `knowledge`) and `steps` (ordered array of `{tool, args, expect?}`; `args` credential values are credential-set **references**, never literals) (R-3)
- [x] `skill.schema.json`: drop the "requires web_target" clause from the `risk_class` description so `risk_class: write` is valid without a `web_target`; leave the `enum: ["read","write"]` unchanged (R-3)
- [x] **lockstep** skills-hub `schemas/skill.py`: declare `SkillStep` + optional `kind`/`steps` on `Skill` (`test_model_properties_match_contract_properties` asserts property-set equality); add `test_executable_flow_skill_validates_against_contract` (R-3)
- [x] `shared/shared-contracts/schemas/audit-event.schema.json`: add `skill_graduated` to the `event_type` enum and document its `details` payload (session_id, mode, validation, step_count) in the description ledger (R-4)
- [x] **lockstep** audit-service `schemas/audit.py`: add `skill_graduated` to the `EventType` Literal (`test_model_enum_values_match_contract` asserts enum equality); add `test_skill_graduated_event_validates` (R-4)
- [x] **lockstep** portal `views/audit/constants.ts`: append `skill_graduated` to `EVENT_TYPES` (last, matching the schema enum order the drift guard pins) (R-4)
- [x] `shared/shared-contracts/policies/policy-default.yaml`: add one `session:skill_graduate` action granted to `roles_any: [platform-admin, approver, operator]` (observer excluded), mirroring the `session:skill_draft` grant (R-4 / OQ-3)
- [x] `policy-scenarios.yaml`: cover `session:skill_graduate` in the operator allow block + the auditor/observer/developer deny blocks (the harness fails verify if a granted pair is uncovered) (R-4)
- [x] `make sync-policy` propagates the new action to all bundle copies; the bundle content-hash (SPEC-048) updates (R-4)
- [x] verify `execution-request.schema.json` needs **no** change (a browser replay envelope is byte-identical to a hand-authored flow envelope, `approval_kind: "flow"`) (R-5 / plan §6)

## Stage 2: agent-platform + portal — R-7 approval-seam secret masking

- [x] `services/secret_params.py`: add a per-tool `KNOWN_SAFE_FIELDS` allow-list (curated non-secret fields that may render verbatim: `k8s.delete_pod` name/namespace, `web.select` value, `web.fill_credential` credential_set/field, `web.press_key` key, `web.upload_file` filename) (R-7)
- [x] `services/secret_params.py`: flip `should_mask` to **mask-unless-known-safe** (fail-closed) — a field not positively on the allow-list masks; the curated `_cr_*` formatters keep deciding their own fields (R-7 finding #2)
- [x] `services/hitl_confirmations.py`: `_generic_fields` inherits the fail-closed posture; an off-vocabulary secret value masks, never projects as plaintext (R-7 finding #2)
- [x] `services/hitl_confirmations.py`: for an `action`-card entry, redact the raw `parameters` **values in place** (keys preserved, secret-bearing values → `***`) beside the `change_request` projection — the `pending_calls.items` shape is unchanged, so no contract change (R-7 finding #1, stream leg)
- [x] `runtime_kernel.py` park site + `services/confirmation_records.py`: the persisted `pending_calls` for an action card carries the redacted entry (no plaintext secret at rest); `flow`/legacy cards unchanged (R-7 finding #1, persistence leg)
- [x] confirm `build_requests` / `canonical_digest(parameters)` are untouched — the signed `args_digest` is computed from the in-memory parked call, never the redacted frame/record (R-7 invariant; plan §1)
- [x] portal `chat/ChatView.tsx`: the action-card "Technical details" expander presents the `change_request` projection (masked values `***`), not raw secret-bearing `parameters`; a `flow`/legacy card renders unchanged (R-7 finding #1, render leg)
- [x] tests: an off-vocabulary secret value is masked in the projection (fail-closed) (R-7a)
- [x] tests: a secret-bearing parameter does not stream/render/persist as plaintext for an action card (R-7b)
- [x] tests: `args_digest` verification still passes after masking — byte-identical with and without redaction (R-7c, invariant)
- [x] tests: a `flow`/legacy card and its persisted record are unchanged by R-7 (R-7 no-regression)

## Stage 3: agent-platform — R-1 durable authoring-trace store

- [x] `services/authoring_trace.py` (new): `AuthoringTraceStore` `Protocol` + `InMemoryAuthoringTraceStore` + `PostgresAuthoringTraceStore` + `build_authoring_trace_store()` factory + module-level `AUTHORING_TRACE_STORE` singleton, mirroring `execution_records.py` (reuse `AGENT_STATE_STORE_BACKEND` / `AGENT_STATE_DB_URL`, fail-open-to-memory) (R-1)
- [x] trace step shape: `session_id`, `position` (per-session ordinal), `tool_name` (canonical dotted), `args` (JSONB, secret-safe parameterized), `execution_id` + `confirm_id` (**references**, not the receipt), `status`, `captured_at` — every field on **both** backends (R-1)
- [x] `authoring_trace` table: idempotent DDL created in place on first use, sharing the SPEC-016 `sessions` database; ordered by `(session_id, position)` (R-1)
- [x] lifecycle `draft → graduated | discarded` (terminal); **not** time-swept with the 30-day `execution_records` window (R-1 / OQ-1)
- [x] per-session step cap `AGENT_AUTHORING_TRACE_MAX_STEPS` (default 100) enforced at append — capture beyond the cap drops best-effort (R-1)
- [x] idle-GC `AGENT_AUTHORING_TRACE_IDLE_DAYS` (default 180) reclaims `draft` traces idle beyond the window at startup + opportunistically on write; terminal rows are never swept (R-1 / OQ-1)
- [x] `core/config.py` / `runtime_settings.py`: register the two knobs with defaults (R-1)
- [x] tests: dual-backend round-trip incl. the `postgres` backend — every field survives on both (R-1)
- [x] tests: the per-session step cap drops capture beyond the bound (R-1)
- [x] tests: lifecycle transitions `draft → graduated` and `draft → discarded`; the idle-GC reclaims a `draft` row and never a terminal row (R-1)
- [x] tests: a store failure degrades without raising (best-effort) (R-1)

## Stage 4: agent-platform — R-2 capture at the approval seam

- [x] `runtime_kernel.py`: a `_capture_authoring_step(...)` helper called beside `_persist_execution_request` at the per-action signing site (`_prepare_executions`) (R-2)
- [x] `runtime_kernel.py`: the same helper called at the flow-unlock signing site (`_sign_flow_execution`), so both approval kinds append to one coherent ordered trace (R-2)
- [x] secret-safe parameterization **at capture**: credential values replaced by credential-set references / placeholders (reuse `secret_params` vocabulary + the `web.fill_credential` indirection) before the write — no literal secret reaches the store (R-2)
- [x] the step stores `execution_id` / `confirm_id` references and does **not** duplicate the signed receipt or outcome (those stay in `execution_records`) (R-2)
- [x] best-effort + fail-safe: wrapped like `_persist_execution_request` — a trace failure degrades to "no graduation candidate", never blocks the mutation's execution or its `execution_records`/receipt path (R-2)
- [x] tests: a step is captured only for a signed **mutating** call at both sites; a read-tier call is signed and recorded but never captured, and a call with no classified tier is not captured either (R-2)
- [x] tests: a mixed session (per-action + flow-unlock writes) yields one ordered trace (R-2)
- [x] tests: secret values are parameterized at capture — no literal in the stored `args` (R-2)
- [x] tests: a trace-store failure never blocks execution or the `execution_records`/receipt write (R-2)

> Implementation-found refinements (stage 4):
> - `services/secret_params.py` gained `TRACE_CREDENTIAL_PLACEHOLDER`, `is_secret_value()`
>   and `parameterize_for_trace()` rather than reusing R-7's `should_mask`/`redact_parameters`.
>   Fail-closed masking would placeholder every off-allow-list argument (`web.click.selector`,
>   `web.navigate.url`, `k8s.restart_service.namespace`), making every trace un-graduable —
>   R-2 would ship non-functional. The trace predicate targets *credential values* (vocabulary
>   + opaque fields, allow-list exempt); the residual fail-open-on-capture gap is **bounded** at the
>   other end by R-4's planned blast-radius re-validation (stage 6, not yet implemented), which is to
>   refuse a trace still carrying a `TRACE_CREDENTIAL_PLACEHOLDER` — see the "bounded, not closed"
>   bullet below for what that does and does not detect.
> - `services/session_service.py`: `delete_session` now cascades `AUTHORING_TRACE_STORE.delete_session`
>   (absent from plan §R-2's affected-file list, but every sibling per-session store is wired there
>   and omitting it would leak durable argument copies for a deleted session). A terminal trace
>   cascades too — the lifecycle guard is against *time*, not against its owner deleting the session.
> - the signed envelope carries `args_digest` but **not** the raw parameters, so `_prepare_executions`
>   reads `pending.pending_calls_payload()` once for both the arguments and the park-time risk tier
>   (`redact_parameters` is a display/at-rest projection applied to copies, never a signing input, so
>   the payload is raw at resume); `_sign_flow_execution` already has them in scope.
> - **being signed is not being a mutation.** `DEFAULT_AUTO_ALLOWED_TOOLS` is a *curated subset* —
>   auto-allow needs `is_read_only` **AND** membership — so an unvetted read tool (`elastic.search_logs`)
>   parks, gets approved and gets signed like any write. The per-action capture is therefore gated on
>   `RISK_LEVEL_ACTIONS.get(risk_level) == "tools:mutate"`, reusing the platform's single risk→action
>   mapping so the seam and the policy bridge cannot disagree about what a mutation is. It fails
>   **closed** on an unclassified tier rather than open on `!= "read"`: the flow site is already
>   positively gated by `BROWSER_WRITE_TOOLS`, the trace store outlives every receipt, and the
>   degradation (no graduation candidate) is the one R-2 already accepts for a store failure.
> - `web.evaluate.expression` joined `OPAQUE_VALUE_FIELDS`. Arbitrary JS can read a masked secret off
>   the page and can *be* the mutation (`document.querySelector('#pw').value = '<literal>'`), it is
>   write-tier and in `BROWSER_WRITE_TOOLS`, and `_cr_web_evaluate` already refuses to project it on a
>   card — without the entry the trace projection was the one place a JS-embedded literal survived,
>   into a store that outlives every receipt. The nesting walker now takes the tool name so the
>   per-tool opaque fields hold below the top level too; `KNOWN_SAFE_FIELDS` deliberately does **not**
>   descend (at depth, failing closed costs only replayability).
> - **R-4/R-5 input:** `web.fill_credential` is read-tier *and* on the default auto-allow list *and*
>   absent from `BROWSER_WRITE_TOOLS`, so under the default configuration a credential-set reference
>   step never enters a trace at all. A graduated browser flow therefore replays its mutations with no
>   recorded way to authenticate, and the credential reference is what the human completing the draft
>   supplies at merge time — consistent with spec.md R-4 (graduation produces a draft for human review
>   and merge, never an auto-published skill). Consequence: a trace carries **no** reference to resolve
>   a placeholder *against*, so R-4 cannot "resolve" one — it must surface each placeholder as a hole
>   in the draft for the human to fill, and R-5 must refuse to replay a flow with one still unresolved.
> - **R-4/R-5 input:** `TRACE_CREDENTIAL_PLACEHOLDER` is a bare string. It records that a hole exists
>   but not *which* credential set fills it, nor which tool/field it came from once the step is read
>   back. Two related costs land on stage 6/7: (a) the per-tool opaque fields (`web.type.text`,
>   `web.evaluate.expression`) placeholder **unconditionally, by name, regardless of value**, so a
>   non-secret value typed through them is lost too — and since R-4 refuses a trace carrying a
>   placeholder, one `web.type` of a search string would refuse the *whole* trace, the same
>   "un-graduable" outcome `is_secret_value` exists to avoid; (b) the draft preview cannot name the
>   hole. Open decision for stage 5/6: keep the bare string (R-4 treats a placeholder as a hole the
>   human fills in the draft, not a pre-draft refusal) or make it self-describing, e.g.
>   `{"__credential_ref__": {"tool": …, "field": …}}` — which stage 5's step schema and stage 7's
>   replay substitution would both have to absorb, so it is cheaper to decide before stage 5 lands.
>   **Resolved in stage 5: kept bare** — see the stage-5 refinement note.
> - `is_secret_value`'s residual fail-open gap is **bounded, not closed**: R-4's planned re-validation
>   detects *placeholders*, so a literal under a name the vocabulary does not know produces no
>   placeholder and is not detectable by that check. Until stage 6 lands the vocabulary is the only
>   control. The vocabulary + the per-tool opaque fields are the boundary.
> - new `tests/test_secret_params.py`: the R-2 projection is a pure function with no confirmation
>   frame to ride, and most of what it pins is the *deliberate divergence* from R-7's fail-closed
>   posture (R-7's own predicates stay asserted through the frame in `test_hitl_confirmations.py`).

## Stage 5: skills-hub — R-3 executable-flow skill class

- [x] `schemas/skill.py`: `kind` + `steps` on the `Skill` model — **done in stage 1** (the contract parity test binds the model to the schema atomically, so it cannot wait for stage 5); stage 5 keeps only ingestion + store (R-3)
- [x] `services/ingestion.py`: add `kind`, `steps` to `ALLOWED_KEYS`; relax the `risk_class`-requires-`web_target` rule so `risk_class: write` ingests without a `web_target` (R-3)
- [x] `services/ingestion.py`: validate the executable-flow class — step-list shape, `risk_class: write` when any step mutates, credential references resolve to named credential sets — and reject a malformed one on the existing `validate_document` path (R-3)
- [x] `services/skill_store.py`: add `kind TEXT` + `steps JSONB` on **both** backends (in-memory + Postgres), idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, INSERT + row-map (the `flow_intent` precedent) (R-3)
- [x] confirm a `read`-class skill still never executes mutating tools; only a `write`-class executable flow can replay, and only under R-5's one gate (R-3)
- [x] tests: `risk_class: write` **without** `web_target` ingests (the relaxed rule) (R-3)
- [x] tests: a `kind: executable_flow` skill with a valid step list ingests and round-trips on **both** store backends (R-3)
- [x] tests: a malformed step list / a missing `risk_class: write` on a mutating flow / an unresolvable credential reference is rejected (R-3)
- [x] tests: a knowledge skill (no `kind`/`steps`) validates exactly as today — no existing skill breaks (R-3)

> Implementation-found refinements (stage 5):
> - `shared/shared-contracts/skill-format.md` advances **v1 → v2** (absent from plan §R-3's
>   affected-file list, which named only `skill.schema.json`). It is the human-readable half of the
>   same contract and still read "`risk_class` … requires `web_target`" — the exact rule R-3 removes —
>   so shipping the code without it would leave the doc authors lint against contradicting the
>   validator. Adds the `kind`/`steps` key rows, an "Executable-flow skills (v2)" section with the
>   step table and the class rules, and the step size caps. Four further files beyond plan §R-3's
>   list are touched, each for a reason recorded in its own bullet below:
>   `shared/shared-contracts/scripts/validate_secret_vocabulary.py` (the twin-literal drift guard),
>   `services/sync.py` (the rejection-metrics bucket), agent-platform's
>   `tests/test_secret_vocabulary.py` (that script's self-test, extended to cover the second coupling
>   in both directions — it materializes a synthetic tree, so it fails closed on a new required
>   literal until the tree carries it), and — comment only — agent-platform's
>   `services/secret_params.py` (the back-reference that makes the guard discoverable from the side a
>   rename would start on).
> - **`risk_class: write` is required unconditionally for `kind: executable_flow`**, which is the
>   fail-closed reading of "`write` when any step mutates". A step list is a replay of *approved
>   mutations* — R-2's tier gate makes a read-tier call structurally incapable of entering a trace —
>   so for every flow the platform produces the conditional and unconditional rules coincide; for a
>   hand-authored one, skills-hub holds no per-tool risk vocabulary to check a `read` claim against
>   (the authoritative `risk_level` lives in the gateway's tool definitions), while declaring `write`
>   costs only that the flow replays under R-5's one gate and the gateway's write-class guard. A
>   read-only browser flow needs no step list: the SPEC-049 `web_target` + `risk_class: read` class
>   already serves it.
> - **A `web.*` step still requires a `web_target`.** R-3 decouples `risk_class` from `web_target`,
>   not browser *replay* from it: the gateway binds the flow — and with it the origin guard and the
>   step budget — from the declared target (`bind_flow` fails closed with `SKILL_NOT_WEB_FLOW`
>   without one), so a browser step list with no target declares a flow that cannot be bound or
>   bounded. Non-browser (`k8s.*`) flows need none, which is what the decoupling buys. Relaxing the
>   `risk_class`/`web_target` pairing is safe for the same reason — the consuming side already fails
>   closed.
> - **"credential references resolve to named credential sets" is structural at this boundary.**
>   skills-hub cannot see the gateway's platform-managed credential store (a secret-mounted JSON file
>   resolved at call time), so what ingestion can and does require is that a `web.fill_credential`
>   step *names* the set and the field, and that no step argument still carries R-2's unresolved-hole
>   marker `<credential-reference>` — a hole names no set, so such a flow could never authenticate at
>   replay. This **resolves the stage-4 open decision: the placeholder stays a bare string.** A
>   self-describing marker would only ever have carried `{tool, field}` (the trace records no set to
>   resolve against — see the stage-4 `web.fill_credential` note), and R-4 can name the hole at
>   draft-render time from the step's own position, so the extra shape would buy nothing and stage 7's
>   substitution stays a string comparison. The literal is a declared cross-product twin
>   (`ingestion.CREDENTIAL_HOLE` ↔ `secret_params.TRACE_CREDENTIAL_PLACEHOLDER`, products do not
>   import each other) and is documented in `skill-format.md` — and, because documentation alone left
>   the coupling **one-directional** (renaming the marker on the agent-platform side would have
>   silently disabled the ingestion check rather than failing anything), it is now *enforced*:
>   `shared/shared-contracts/scripts/validate_secret_vocabulary.py` extracts both literals and fails
>   the `validate-secret-vocabulary` leg of `make verify` on divergence. That script already pinned
>   the SPEC-054 vocabulary twin the same textual way, so this reuses the mechanism rather than
>   inventing plumbing. Verified in both directions by that leg's own self-test, which was extended
>   to materialize the skills-hub twin in its synthetic tree (agree / each side renamed / each side
>   missing the literal / a prose mention of the name not mistaken for the assignment / a
>   triple-quoted or f-string assignment not mistaken for a literal). The extractor treats an empty
>   extraction as **absent**: the pattern stops at the first quote, so a triple-quoted assignment on
>   *both* sides would otherwise compare equal and pass vacuously — and an empty marker is
>   independently a bug, since the empty string is a substring of every string and the ingestion
>   check would then reject every document.
> - **The rejection-metrics bucket is pinned end to end, not just by transcription.** Deriving the
>   reason strings from ingestion's constants tracks a *cap* change but not a *wording* change, so
>   `test_ingestion.py` also asserts `_rejection_category(...) == "size"` on the reason a real
>   oversize document actually produced. The two strings ingestion renders as literals (rather than
>   from a constant) stay literal in the derived test too — "deriving" them would pin strings
>   ingestion never emits.
> - **Step `args` are validated with `json.dumps`** — the exact encoding the `steps` JSONB column
>   applies, so "accepted at validation" and "storable in Postgres" cannot diverge. Not a formality:
>   YAML parses an unquoted date into `datetime.date`, which no JSON encoder accepts, so without the
>   check such a document would ingest and then break the sync write. `steps` is also the first
>   frontmatter key the per-key char caps do not bound, so it gets a resource ceiling (≤ 200 steps,
>   ≤ 64 KiB serialized) deliberately *above* the two step counts that exist today — the R-1 trace
>   cap (default 100) and the gateway's flow budget (default 20) — so the ceiling is never the thing
>   that decides graduality. R-4's policy bound (stage 6, **not yet implemented**) is planned to sit
>   below it too. Both existing counts are operator-tunable and `MAX_STEPS` is not, so the ordering is
>   a coupling to preserve rather than an invariant: raising `AGENT_AUTHORING_TRACE_MAX_STEPS` past
>   200 would make a long trace un-graduable here (failing safe — rejected, never truncated).
> - **A new size ceiling needs a metrics bucket.** `sync._rejection_category` mapped only
>   `"body exceeds"` to `size`, so `"steps exceed 64 KiB"` and `"more than 200 steps"` fell through to
>   `frontmatter` and the rejection counter under-counted size rejections. Broadened, gated on
>   `steps` so the neighbouring `"more than 10 tags"` bound — which shares the `more than` prefix —
>   stays where it always was. The label set remains bounded (the counter's cardinality guard).
> - `steps` persists as SQL `NULL` (never JSON `null`) when absent, and the row-map guards with
>   `isinstance(steps, list)`, so a pre-R-3 row reads back as exactly the v1 envelope shape and
>   `summary()`/detail `exclude_none` keep the served payload byte-identical for knowledge skills.
>   The column stores the envelope's own dump, so a step that omits `expect` materializes it as JSON
>   null — both backends read it back as `expect=None`.
> - **read-class confirmation:** R-3 adds a *declaration*, not an execution path. The guards that keep
>   a read-class skill from mutating are unchanged and already asserted in their own suites — the
>   gateway's `BROWSER_FLOW_READ_ONLY` denial on a write-tier interaction in a read-class flow
>   (`browser_connector.py`, `test_browser_connector.py`) and the kernel's write-class-only flow
>   signing (`runtime_kernel.py`, `test_runtime_kernel.py` / `test_flow_approvals.py`). Ingestion adds
>   the third: it cannot produce a read-class executable flow at all.
> - stage 6 inherits R-3's validation for free: `_validate_skill_markdown` →
>   `POST /skills/validate` → `validate_document` → the same `_validate_frontmatter` these rules live
>   in, so a graduation draft is refused by the rules it will be ingested under.

## Stage 6: agent-platform + platform-gateway + portal — R-4 graduation

> **Refinement (stage 6a) — R-4 needs *two* forms of target, not one.** The plan as written asks
> `revalidate_blast_radius` to check that "every origin/target is allowlisted", but before stage 6a
> nothing in the trace recorded an origin at all, and nothing recorded a target. Both are now
> captured, and they are different things:
>
> - **declared target** (`authoring_trace_target`, one row per session) — the web target the operator
>   names when opening a develop-as-you-go session. Declared *before* mutating, it is an
>   **authorization scope**: the session acted under it. Graduation emits it as the draft's
>   `web_target`, the security parameter a replayed flow binds its origin guard and step budget to.
> - **observed origin** (`authoring_trace.flow_origin`, one column per step) — the origin the gateway
>   reported that captured mutation actually landed on. Graduation uses these to *prove* every step
>   landed inside the declared scope, so "every origin/target allowlisted" is substantiated by
>   evidence rather than asserted about a trace that never carried any.
>
> This is the operator's model, and it is strictly stronger than scraping a target out of the trace
> after the fact: a target supplied *at graduation* is an untrusted post-hoc claim, while one
> declared before the first mutation is a scope the session can be held to — and it is still
> corroborable, because the gateway reports `data["url"]` on every successful browser write result.
>
> - **the receipt seam is the only place the origin can be captured.** `build_receipt` stores
>   `outcome_digest` alone — the outcome is digested, never stored — and `execution_records` are swept
>   at 30 days while a trace must outlive them (ADR-0009). `data["url"]` is legible for exactly one
>   moment, so `_observe_step_origin` runs in `_observe_tool_result` right after `save_receipt` (the
>   receipt first, so the tamper evidence is durable before a derived trace amendment is attempted —
>   the same ordering R-2 uses). Scoped to `BROWSER_WRITE_TOOLS`, the set that gates the flow-unlock
>   capture site.
> - **only a `succeeded` result is observed.** `_observe_step_origin` takes the `status` already written
>   into the receipt rather than re-reading the frame, so the trace and the receipt cannot disagree about
>   which mutations landed. A failed or timed-out write can still report the URL it was *attempting*, and
>   corroborating that as "landed on target" would let a mutation that never happened count toward
>   graduation.
> - **`web.navigate` cannot supply it:** R-2's tier gate captures write-tier only, and navigate is
>   read-tier, so it never enters a trace.
> - **the declaration is stored as origin and path — never as a bare origin, and never with anything a
>   replay is not bound by.** `bind_flow` requires origin equality *and* `_path_under(url_path,
>   target_path)`, so a path narrowing is part of the scope and must survive into the draft; collapsing
>   it to a bare origin would silently widen the graduated skill to every path on the host. Query,
>   fragment and `user:password@` userinfo go the other way (`skill_target_scope`): `bind_flow` reads
>   none of them, so storing one would advertise a narrowing that does not exist — and a target pasted
>   from an address bar is exactly where a session token rides, into a table that outlives every receipt
>   (ADR-0009), into the structured log's `target_origin`, and into the `skill_graduated` audit payload.
>   A declaration reaches the store from the operator's own input, not through the gateway's result
>   redaction, so nothing upstream has masked it. Userinfo is worse than a leak: `origin_of_url` keeps
>   the netloc verbatim, so `https://u:p@host` normalizes to an origin no browser will ever report, and
>   graduation would refuse a trace that ran perfectly. It is stripped at declaration rather than inside
>   `origin_of_url`, which must stay byte-identical to the gateway's `origin_of` twin. Scoping therefore
>   runs *before* the shape check, so the check judges the value that will be stored rather than the
>   paste — `https://u:p@/path` has an origin as typed and none at all once scoped, and is refused
>   (a `urlparse` `ValueError` on the way answers the same 422, never a 500). Corroboration is
>   at origin granularity only — a bounded residual, because the gateway's live deviation guard already
>   enforces origin *and* path at write time.
> - **NULL `flow_origin` means *unverified*, never *drifted*.** It is produced by a result that did not
>   succeed, by `_make_full_data`'s size guard omitting `data` entirely over 128KB, by a gateway that
>   reported no URL, and by every row written before R-4. Stage 6b must refuse such a trace rather than
>   fabricate an origin.
>
> **Plan gap: R-4 needs a `platform-gateway` leg that neither plan.md nor this file mentioned.** The
> portal reaches the agent layer only through the gateway, so a route the gateway does not proxy is a
> route the operator cannot call. Stage 6a delivers it: the `session:skill_graduate` action constant
> and its `PROTECTED_ACTIONS` entry, the request schema, the client + proxy pair, the route,
> `EXPECTED_ROUTES`, and the policy-engine/matrix literals.
>
> **Two declaration paths, deliberately different authorization postures.**
>
> - `skill_target` on `POST /sessions` is the **birth** declaration and the primary path: the session
>   does not exist to mutate until the create returns, so no captured step can predate it. It rides
>   `session:create` and is *not* dual-gated with `session:skill_graduate` — declaring a scope is
>   inert (it grants nothing and only narrows what a later graduation may emit), and dual-gating would
>   refuse *session creation itself* over an inert field, which is worse than an observer scoping their
>   own session. Graduation, the consequential act, stays gated.
> - `POST /sessions/{id}/skill-target` is for a session that *becomes* a development session later, so
>   a declaration made through it can postdate the first captured step. It rides
>   `session:skill_graduate` on the `documents:create` precedent — one action gating the several
>   operations that constitute one capability — which avoids a second action's bundle, scenario, matrix
>   and content-hash churn.
>
> **Stage 6b input: the ordering datum is expressible and discriminating.** The real-PostgreSQL check
> (`.sqlcheck-spec055-s6a.sql`) proves `declared_at <= min(captured_at)` over the stored columns
> returns true for a birth-declared session and **false** for one declared an hour after its first
> step, so 6b can tell an authorization scope from a claim fitted to the trace. Two hazards for 6b:
> `now()` is the *transaction* timestamp in PostgreSQL, so declaration and capture only differ across
> separate requests (they always are); and `_canonical_timestamp` renders second precision while the
> columns hold microseconds, so the comparison must be made on **one** basis across both backends or
> they will disagree inside a sub-second window.

### Stage 6a: the durable substrate and the two write paths that populate it

- [x] `services/authoring_trace.py`: `flow_origin TEXT` on `authoring_trace` and a new `authoring_trace_target (session_id PK, target, declared_at)` table, on **both** backends — DDL, the idempotent `ALTER … ADD COLUMN IF NOT EXISTS` that migrates a 0.35.0 cluster in place, the INSERT/LOAD column lists, and `_row_to_step` (R-4)
- [x] `services/authoring_trace.py`: `record_step_origin` (first observation wins — `AND flow_origin IS NULL` in SQL, an `is not None` guard in memory), `declare_target` (first declaration wins — `ON CONFLICT DO NOTHING` plus a same-transaction read-back so the caller learns which target is in force), `trace_target`; `sweep_idle` also reclaims declarations that never produced a step and still returns a **step** count so both backends report one unit; `delete_session` reclaims both key spaces (R-4)
- [x] `services/authoring_trace.py`: `origin_of_url`, the deliberate twin of the tool-gateway's `origin_of` — agreement is what stops a coherent trace looking like a drift (R-4)
- [x] `runtime_kernel.py`: `_observe_step_origin` amends the captured step from the receipt seam, after `save_receipt`, best-effort, scoped to `BROWSER_WRITE_TOOLS` and to a `succeeded` result (R-4)
- [x] `api/v2/routes.py`: `POST /api/v2/sessions/{session_id}/skill-target` — ownership re-checked server-side (structural 404), shape-checked and scoped by `_validated_skill_target`, first-wins, responding with the target **in force** rather than an echo of the request (R-4)
- [x] `api/v2/routes.py` + `schemas/v2.py`: `skill_target` on session create — validated *before* the session exists, so a refused target leaves no half-created session behind (R-4)
- [x] `platform-gateway`: `ACTION_SESSION_SKILL_GRADUATE` + its `PROTECTED_ACTIONS` entry, `SkillTargetDeclareRequest`, `agent_client`/`gateway_service` `declare_skill_target`, `POST /api/v1/sessions/{session_id}/skill-target`, and `skill_target` forwarded through create-session (R-4)
- [x] `platform-gateway`: `create_session` gains the house 4xx/5xx mapping it previously lacked — without it the agent's 422 on an unnormalizable target would have reached the operator as a 500 (R-4)
- [x] `services/authoring_trace.py`: `skill_target_scope`, the shared normalization both declaration paths go through — origin and path kept; query, fragment and `user:password@` userinfo dropped (R-4)
- [x] `shared/shared-contracts/schemas/audit-event.schema.json`: `web_target` added to the `skill_graduated` `details` ledger — the declaration is deliberately unaudited at the gateway, so this event is where a reviewer learns which scope was in force (`details` is `additionalProperties: true`, so no emitter or model moves in lockstep) (R-4)
- [x] tests: both backends' first-wins guards, the 9-column round-trip, origin normalization, a `k8s.*` frame carrying a URL left unobserved, a store failure degrading the trace and never the execution or its audit, a second observation never rewriting the first, and both declaration paths' posture (R-4)
- [x] tests: a target declared with a query, a fragment or embedded credentials persists as origin and path only on **both** declaration paths, and a **failed** browser write carrying `data["url"]` leaves `flow_origin` NULL rather than corroborating a mutation that did not land (R-4)
- [x] real-PostgreSQL sqlcheck (`.sqlcheck-spec055-s6a.sql`, Postgres 16): pre-R-4 migration leaves the existing row NULL and the 9-column list resolvable; DDL and ALTER idempotent on a second run; `UPDATE 0` on a repeat observation and on a second declaration; the ordering predicate discriminating; the target sweep keeping a declaration whose session has steps; zero footprint after ROLLBACK (R-4)

### Stage 6b: graduation itself

- [ ] `services/skill_graduation.py` (new): `build_executable_flow_draft(trace)` renders the ordered trace into an executable-flow skill Markdown (frontmatter `kind: executable_flow`, `risk_class: write`, `web_target` for a browser flow, `steps`; body = a human-readable replay runbook) with **no LLM call** (contrast SPEC-044's `generate_skill_draft`) (R-4)
- [ ] `services/skill_graduation.py`: `revalidate_blast_radius(trace)` runs **before** the draft is produced — bounded step count, every step's observed `flow_origin` inside the declared target's origin, a **NULL `flow_origin` refuses** (unverified is never fabricated), consistent `risk_class: write`, all credentials resolved to credential-set references (the SPEC-051 guards); a failing trace is a deterministic refusal surfaced to the operator (R-4)
- [ ] `services/skill_graduation.py`: report whether the declaration preceded the first captured step, on one comparison basis across both backends (see the stage-6a refinement note) — a late declaration is a scope fitted to the trace, and the operator is told so rather than silently trusted (R-4)
- [ ] `api/v2/routes.py`: `POST /api/v2/sessions/{session_id}/skill-graduate` mirroring `create_skill_draft` — gateway-enforced `session:skill_graduate`, server-side ownership re-check (foreign/unknown → the structural 404), validate through skills-hub's ingestion path (`_validate_skill_markdown`), ephemeral (nothing persisted but the lifecycle flip) (R-4)
- [ ] `api/v2/routes.py`: emit the `skill_graduated` audit event — `details` carrying `session_id, mode, validation, step_count, web_target`, the payload the contract's description ledger already pins (stage 6a) — and flip the trace lifecycle to `graduated` (R-4)
- [ ] the graduated draft is validated against Skill v2 on skills-hub's own ingestion path before it reaches the operator (never auto-published) (R-4)
- [ ] portal: a "Graduate as skill" entry point on the session (role-gated — visible to operator/approver, not observer), and the develop-as-you-go session opener that collects the target at birth (R-4)
- [ ] portal: the executable-flow draft preview (rendered + raw toggle, mode badge, Download .md / Discard) reusing the SPEC-045 pattern (R-4)
- [ ] `platform-gateway`: proxy `POST /api/v1/sessions/{session_id}/skill-graduate` behind `ACTION_SESSION_SKILL_GRADUATE` (the action constant and its grant landed in stage 6a), with the draft proxy's 502/503 passthrough — a graduation *does* have a validation leg, unlike the declaration (R-4)
- [ ] tests: `build_executable_flow_draft` is deterministic over a fixed trace (no LLM synthesis of steps) (R-4)
- [ ] tests: blast-radius re-validation refuses an over-budget / off-allowlist / inconsistent-`risk_class` / unresolved-credential trace and passes a clean one (R-4)
- [ ] tests: the endpoint emits `skill_graduated`, flips the lifecycle to `graduated`, and produces a draft that is **not** published (R-4)
- [ ] tests: observer is denied `session:skill_graduate`; operator/approver are allowed (R-4)
- [ ] portal tests: the entry point appears for an authorized role and not for an observer; the preview renders (rendered + raw) and downloads (R-4)

## Stage 7: agent-platform + tool-gateway + portal — R-5 replay

- [ ] verify a graduated **browser** executable flow binds and one-gates through the existing SPEC-051 path (`_observe_flow_binding` → `_record_flow_approval` → `_sign_flow_execution` → `build_flow_request`) with no new executor (R-5)
- [ ] verify the gateway deviation guard (origin allowlist, declared `risk_class`, step budget) bounds a replayed executable-flow write identically to a hand-authored flow; executable-flow writes join **no** auto-allow list (R-5)
- [ ] verify credentials resolve at replay from the named credential sets via `web.fill_credential` references — never literals (R-5)
- [ ] confirm execution-runtime is **verify only** — a browser replay envelope (`approval_kind: "flow"`) verifies and forwards unchanged (R-5 / plan §6)
- [ ] the infra (non-browser) executable-flow binding is **deferred** to its own 0.36.0-era slice (OQ-2) — not delivered here (R-5)
- [ ] tests: a graduated browser executable flow collapses to **one** `flow`-kind gate; each subsequent write is individually signed (`build_flow_request`) + receipted (R-5)
- [ ] tests: an infra executable-flow write parks **per-action** (SPEC-054 R-2) and joins no auto-allow list — the OQ-2 safe fallback asserted (R-5)
- [ ] tests: a replay past step budget or off-allowlist fails closed (R-5)
- [ ] portal tests: replay surfacing renders the flow headline + change-request framing (R-5)

## Stage 8: Samples

- [ ] new interactive graduation demo under `samples/` — author a session of approved mutations → graduate → human-merge → replay under one gate (R-6)
- [ ] the sample's own demo script exercises it in the verification path (ADR-0008 exercised-sample rule) (R-6)
- [ ] the password-reset + adhoc-password-reset `demo.sh` chat legs stay green **unchanged** (the one-gate and per-action paths do not regress) (R-6)

## Delivery Gate

- [ ] all acceptance criteria in `spec.md` verified (R-1…R-7), each mapped to an asserting test above (ADR-0008):
  - R-1 → stage 3 dual-backend round-trip (incl. `postgres`), step cap, lifecycle, idle-GC, best-effort failure
  - R-2 → stage 4 capture-only-on-signed-mutation (both sites), ordered mixed trace, secret parameterization, fail-safe
  - R-3 → stage 5 `risk_class`-without-`web_target`, executable-flow schema validation (both backends), malformed rejection, knowledge-skill no-regression
  - R-4 → stage 6a declared-target + observed-origin substrate (both backends, both declaration paths, real-PG migration) and stage 6b deterministic draft, blast-radius refusal + happy path, `skill_graduated` + lifecycle flip + draft-not-published, observer-denied
  - R-5 → stage 7 one-gate browser replay with per-write signing, infra per-action fallback asserted, deviation-guard fail-closed
  - R-6 → this mapping + the exercised `samples/` graduation demo
  - R-7 → stage 2 fail-closed projection (off-vocabulary masked), no-plaintext-secret on stream/render/at-rest for an action card, `args_digest` invariant preserved
- [ ] `make verify` green (all product pytest; kustomize overlays; policy rules + the new `session:skill_graduate` scenario; api + tools scenarios; version lockstep; the secret-vocabulary leg — extended if `KNOWN_SAFE_FIELDS` needs a twin check)
- [ ] portal `npm test` and `npm run build` green (`tsc --noEmit` + vite)
- [ ] version lockstep bumped **0.35.0 → 0.36.0** (MINOR): `VERSION` + every `pyproject.toml` + `metadata.py` + `__init__.py` literal + per-product `uv.lock` re-locks; `make validate-version` reports OK
- [ ] `make build` produces the clean image; `make deploy` rolls it onto dev-k8s
- [ ] living state docs updated (see spec `Impact`): `CHANGELOG.md` (a `## 0.36.0` section), a dated release note + the notes README index, `docs/guides/configuration-reference.md` (the two new trace knobs), `docs/agentic-aiops-platform/authorization-matrix.md` (the new `session:skill_graduate` action), affected RepoWiki pages
- [ ] `docs/specs/README.md` SPEC-055 row → `delivered`
- [ ] `docs/adr/README.md` ADR-0009 stays `accepted` (implemented by this delivery)
- [ ] `docs/agentic-aiops-platform/delivery-roadmap.md` SPEC-055 backlog row → `delivered` with the shipping version; the deferred OQ-2 infra-binding slice anchored to its own follow-up train
- [ ] spec.md Status block → `delivered`, release slice fixed to the shipping train, delivery changelog entry appended
- [ ] browser live check on the canonical dev-k8s deployment: a session of approved mutations captures an ordered trace; graduating it produces a validated executable-flow draft (not published); a merged+ingested browser executable flow replays under **one** gate with every write signed + receipted; an action card shows no plaintext secret at rest, on the stream, or in the expander
