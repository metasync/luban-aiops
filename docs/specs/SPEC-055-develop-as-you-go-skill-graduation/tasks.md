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
>   other end by R-4's blast-radius re-validation (**landed in stage 6** as
>   `skill_graduation.revalidate_blast_radius`), which refuses a trace still carrying a
>   `TRACE_CREDENTIAL_PLACEHOLDER` — see the "bounded, not closed" bullet below for what that does
>   and does not detect.
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
>   **Resolved in stage 6b: R-4 refuses rather than renders the hole into the draft** — see the
>   stage-6b refinement note for why, and for the second half of this finding (the remedy has to be a
>   re-author, because `web.fill_credential` is never captured in the first place).
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
>   **Resolved in stage 5: kept bare** — see the stage-5 refinement note. The parenthetical guess did
>   *not* survive stage 6b: a placeholder is a pre-draft refusal, not a hole rendered into the draft.
>   Bare is still the right call, now for a better reason — a self-describing marker would have bought
>   nothing, because no stage can name the credential set that was never recorded. See the stage-6b
>   note.
> - `is_secret_value`'s residual fail-open gap is **bounded, not closed**: R-4's planned re-validation
>   detects *placeholders*, so a literal under a name the vocabulary does not know produces no
>   placeholder and is not detectable by that check. Until stage 6 lands the vocabulary is the only
>   control. The vocabulary + the per-tool opaque fields are the boundary.
>   **Landed in stage 6**, which makes the two controls separable rather than one: the vocabulary +
>   the per-tool opaque fields bound what a trace *stores*, R-4 bounds what may *graduate* out of it,
>   and an off-vocabulary literal is invisible to both. The boundary is unchanged, it is just now a
>   boundary with a second gate behind it.
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
>   **Landed in stage 6b** as `AGENT_SKILL_GRADUATION_MAX_STEPS` (default 20, `>= 1`), a deliberate
>   twin of the gateway's flow budget and tunable *because* that one is — so all three counts move
>   together and the coupling above is the whole of it. Both this knob and the two R-1 knobs are now
>   documented in `docs/guides/configuration-reference.md`, which plan.md asked for at stage 1 and
>   which stage 6b found had not happened.
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

- [x] `services/skill_graduation.py` (new): `build_executable_flow_draft(trace)` renders the ordered trace into an executable-flow skill Markdown (frontmatter `kind: executable_flow`, `risk_class: write`, `web_target` for a browser flow, `steps`; body = a human-readable replay runbook) with **no LLM call** (contrast SPEC-044's `generate_skill_draft`) (R-4)
- [x] `services/skill_graduation.py`: `revalidate_blast_radius(trace)` runs **before** the draft is produced — bounded step count, every step's observed `flow_origin` inside the declared target's origin, a **NULL `flow_origin` refuses** (unverified is never fabricated), consistent `risk_class: write`, all credentials resolved to credential-set references (the SPEC-051 guards); a failing trace is a deterministic refusal surfaced to the operator (R-4)
- [x] `services/skill_graduation.py`: report whether the declaration preceded the first captured step, on one comparison basis across both backends (see the stage-6a refinement note) — a late declaration is a scope fitted to the trace, and the operator is told so rather than silently trusted (R-4)
- [x] `api/v2/routes.py`: `POST /api/v2/sessions/{session_id}/skill-graduate` mirroring `create_skill_draft` — gateway-enforced `session:skill_graduate`, server-side ownership re-check (foreign/unknown → the structural 404), validate through skills-hub's ingestion path (`_validate_skill_markdown`), ephemeral (nothing persisted but the lifecycle flip) (R-4)
- [x] `api/v2/routes.py`: emit the `skill_graduated` audit event — `details` carrying `session_id, mode, validation, step_count, web_target`, the payload the contract's description ledger already pins (stage 6a) — and flip the trace lifecycle to `graduated` (R-4)
- [x] the graduated draft is validated against Skill v2 on skills-hub's own ingestion path before it reaches the operator (never auto-published) (R-4)
- [x] portal: a "Graduate as skill" entry point on the session (role-gated — visible to operator/approver, not observer), and the develop-as-you-go session opener that collects the target at birth (R-4)
- [x] portal: the executable-flow draft preview (rendered + raw toggle, mode badge, Download .md / Discard) reusing the SPEC-045 pattern (R-4)
- [x] `platform-gateway`: proxy `POST /api/v1/sessions/{session_id}/skill-graduate` behind `ACTION_SESSION_SKILL_GRADUATE` (the action constant and its grant landed in stage 6a), with the draft proxy's 502/503 passthrough — a graduation *does* have a validation leg, unlike the declaration (R-4)
- [x] tests: `build_executable_flow_draft` is deterministic over a fixed trace (no LLM synthesis of steps) (R-4)
- [x] tests: blast-radius re-validation refuses an over-budget / off-allowlist / inconsistent-`risk_class` / unresolved-credential trace and passes a clean one (R-4)
- [x] tests: the endpoint emits `skill_graduated`, flips the lifecycle to `graduated`, and produces a draft that is **not** published (R-4)
- [x] tests: observer is denied `session:skill_graduate`; operator/approver are allowed (R-4)
- [x] portal tests: the entry point appears for an authorized role and not for an observer; the preview renders (rendered + raw) and downloads (R-4)
- [x] `runtime_settings.py`: register `AGENT_SKILL_GRADUATION_MAX_STEPS` (default 20, `>= 1`) and have the route pass it — *not in plan.md*; found by stage 6b when a comment claimed the knob existed (see the refinement note) (R-4)
- [x] tests: the route's step bound comes from settings, not the module default — both directions pinned, so the wiring cannot regress silently (R-4)
- [x] real-PostgreSQL sqlcheck re-run for 6b (`.sqlcheck-spec055-s6a.sql`): the collapsed `_TARGET_DECLARATION` projection resolves, and `to_char`/`date_part` over the live columns prove the second-precision canonicalization is doing work rather than passing a value through (R-4)
- [x] review fix: a **fifth** blast-radius guard — no step argument shaped like a secret literal. The frontmatter is the authoritative replay copy and is never scrubbed, while `postprocess` redacts only the body, so a literal under a name R-2's vocabulary does not know showed as `[REDACTED]` to the reviewer and rode verbatim into the artifact they merge. Refuses rather than scrubs; `skill_draft._VALUE_PATTERNS` became public `REDACTION_VALUE_PATTERNS` so detection and redaction read one vocabulary (R-4)
- [x] review fix: the step-list size guard measured per-step UTF-8 bytes with `ensure_ascii=False` while skills-hub's ingestion ceiling is `len(json.dumps(steps))` on the whole list with `ensure_ascii=True` — a ~2× divergence window that passed graduation and then surfaced as a 502 blamed on the renderer. Now measured on ingestion's exact basis (R-4)
- [x] review fix: the runbook names the `web.navigate` binding step a trace can never contain — `bind_flow` is reachable only from that read-tier call, so without it a merged flow never binds and every write parks its own card (R-4, and an R-5 input)
- [x] review fix: a third cross-product coupling in `validate_secret_vocabulary.py` — the secret-*shape* vocabulary compared as **ordered** lists, proven to fire on a gateway-only shape, a re-ordering and a rename (R-4)
- [x] review fix: the shape guard's refusal no longer asserts the value *is* a credential; it names the over-catch (`web.select` option `Basic Authentication`) and why that error direction is the safe one, with a test pinning the wording (R-4)

> **Refinement (stage 6b) — the draft takes the report, so the ordering is structural.** plan.md wrote
> `revalidate_blast_radius(trace)` and `build_executable_flow_draft(trace)` as two calls over one
> input. Shipped as a *sequence*: `revalidate_blast_radius(steps, *, target, declared_at, max_steps)
> -> BlastRadius`, then `build_executable_flow_draft(steps, *, report, session_id, title,
> declared_target) -> (markdown, slug)`. Two reasons. The draft **requires** the report, so a document
> cannot be rendered from a trace that was never re-validated — the ordering the plan asked for is a
> signature fact rather than a caller discipline. And the draft needs the session's own id and title
> (the provenance block and the runbook's `Session:` line, and a title the operator chose rather than
> one the endpoint invented), which no trace row carries.
>
> - **A credential hole is a refusal, not a hole rendered into the draft.** Stage 4 predicted the
>   opposite ("R-4 … must surface each placeholder as a hole in the draft for the human to fill",
>   above). Stage 6b refuses pre-draft (409) for three reasons that turned out to agree. spec.md R-4
>   lists "all credentials resolved to credential-set references" as a *graduality* condition and the
>   checklist above ticks it as a re-validation guard, so refusing is what was asked for. Rendering
>   `<credential-reference>` into `steps` would fail skills-hub's own `CREDENTIAL_HOLE` rule (R-3), so
>   the platform would hand the operator a document its own validator rejects — breaking the invariant
>   that a graduation draft always validates. And inventing a set name to fill it would fabricate a
>   reference to a credential set that may not exist, in the one artifact a human merges into a repo.
>   The refusal therefore names each step and argument path and says what to do instead.
> - **The remedy has to be a re-author, because `web.fill_credential` is never captured.** Writing the
>   test that a named credential-set reference is *not* a hole failed: `web.fill_credential` was
>   refused as read-tier. The guard was right and the premise was wrong — `web.fill_credential` is on
>   `kernel_middleware.DEFAULT_AUTO_ALLOWED_TOOLS` and absent from `BROWSER_WRITE_TOOLS`, so R-2's
>   `tools:mutate` gate never captures it (recorded at stage 4 and in `skill-format.md`). What *was*
>   wrong is the refusal's stated remedy: it told the operator to add the reference step, but nothing
>   resolves a hole already stored and no reference ever reaches a trace, so the instruction was
>   unactionable. It now says **re-author these steps filling the credential through
>   `web.fill_credential`** rather than typing it, and the draft's runbook says the reference step must
>   be added by hand at merge time. **R-5 input:** a graduated browser flow therefore always needs a
>   human-added credential step, so replay verification must not treat a missing `web.fill_credential`
>   as an anomaly.
> - **read-tier is derived, not listed.** The guard is `tool_name.startswith("web.") and tool_name not
>   in BROWSER_WRITE_TOOLS` — `web.*` is the whole browser surface and that set is its complete write
>   subset, so a `web.*` tool outside it is read-tier by construction. One vocabulary, no second list
>   to drift, and `runtime_kernel.py`'s capture gate now says so at the seam.
> - **`web_target` is emitted iff the flow has a browser step.** It is what `bind_flow` binds an origin
>   guard and a step budget from, so declaring one on a pure-infra flow would advertise a binding that
>   does not exist. A NULL `flow_origin` refuses for a step `BROWSER_WRITE_TOOLS` covers (stage 6a's
>   "unverified is never drifted"); for a non-browser step it is *not applicable*, and those positions
>   are reported as `unguarded_positions` in the draft rather than counted as drift.
> - **One comparison basis, and it is load-bearing.** `captured_at` (`_iso`) and `declared_at`
>   (`_canonical_timestamp`) are both rendered to second precision on **both** backends, so the
>   declaration-ordering comparison is made on one basis and equal stamps answer `indeterminate`
>   rather than picking a winner. The re-run real-PostgreSQL check proves the canonicalization does
>   work rather than passing a value through: the column holds `2026-09-09 02:57:09.178661+00`
>   (`date_part('microsecond', …) % 1000000 = 178661`) while both canonical renders read
>   `2026-09-09T02:57:09Z`. Cross-backend parity is asserted in `test_authoring_trace.py`, not assumed.
> - **One projection of `authoring_trace_target`.** Stage 6a shipped `_TRACE_TARGET` (target only)
>   beside `_TARGET_DECLARATION` (target + `declared_at`); 6b needs the stamp, so they were collapsed
>   into `_TARGET_DECLARATION` and `declare_target`'s same-transaction read-back now runs it and drops
>   the column it does not use. Two statements over one table is two places for the column set to drift
>   from the DDL — and this drift was found the hard way: a 6a Postgres test's single-column fake row
>   raised `IndexError` once `target_declaration` began reading `row[1]`. Only the **full-suite** run
>   caught it; every targeted file passed. Lesson carried to R-5: a change to a shared store's
>   read shape needs the whole suite, not the files that mention it.
> - **`AGENT_SKILL_GRADUATION_MAX_STEPS` exists because a comment claimed it did.**
>   `skill_graduation.py` documented the bound as operator-tunable under that name while no such
>   setting existed and the route used the module default — an overclaim that would have shipped.
>   Rather than delete the claim, 6b made it true: the knob joins `RuntimeSettings` beside the two R-1
>   ones (default 20, `>= 1`, read in `from_env`, passed by the route) with a route-level test pinning
>   **both** directions, because the service already honoured `max_steps` and only the wiring could
>   regress silently. Finding it also exposed that the two R-1 knobs had never been added to
>   `docs/guides/configuration-reference.md` as plan.md required; all three rows are there now.
> - **The lifecycle flip is ordered validate → `close_trace(TRACE_GRADUATED)` → audit, and is not
>   best-effort.** A trace that fails validation is never marked graduated, and the audit event never
>   describes a flip that did not happen. Re-graduating an already-graduated trace is an idempotent
>   re-export: `close_trace` returns `False`, `graduated_now` is logged as such, and the event is
>   emitted again — a second export is a second consequential act and gets its own audit line.
> - **The gateway's status mapping is the *draft's*, not the declaration's, deliberately.** Stage 6a's
>   declaration proxy collapses 503→502 because a declaration reaches no downstream validation leg, so
>   a 503 there is only an unhealthy upstream. A graduation validates on skills-hub's own ingestion
>   path, so 503 ("not configured") and 502 ("unreachable") are domain outcomes meaning no validated
>   artifact exists; both ride through unchanged, as does the multi-guard 409 refusal verbatim.
> - **Hand-rolled YAML with JSON-quoted scalars.** agent-platform has no PyYAML, and JSON is a subset
>   of YAML, so frontmatter is rendered by hand with every scalar JSON-quoted and `sort_keys=True` for
>   byte-determinism — which is what keeps a selector like `#submit-1` or a target URL from being
>   re-interpreted on the way back in. No model call, no skeleton and no bounded regeneration, unlike
>   SPEC-044's `generate_skill_draft`: every step in the document was human-approved and signed before
>   it ran, so there is nothing to synthesize and nothing a session did not run can appear in it.
> - **Review finding (Critical): a secret literal reached the frontmatter while the runbook showed
>   `[REDACTED]`.** R-2's capture-time parameterization is *name*-based and deliberately fails open on
>   an unknown name — failing closed would placeholder `web.click.selector` and make every trace
>   un-graduable — and `KNOWN_SAFE_FIELDS` positively exempts some names from placeholdering at all
>   (`web.select.value`). So a literal under a name the vocabulary does not know is stored verbatim.
>   The draft's `postprocess` redacts the *body* only, because the frontmatter is the authoritative
>   replay copy and a redacted argument would replay the wrong value. The asymmetry therefore hid the
>   leak from the reviewer while the value itself rode into the artifact they merge. Fixed by refusing
>   (a fifth guard, naming each position, beside the credential hole) rather than scrubbing — the
>   posture the credential hole already takes. `skill_draft._VALUE_PATTERNS` became public
>   `REDACTION_VALUE_PATTERNS` so the refusal and the redaction read one vocabulary, not two that can
>   drift; the four shapes are parametrized in tests against `parameterize_for_trace` to prove R-2
>   really does store them verbatim. `skill-format.md` now states the residual as the intersection
>   (neither the name vocabulary nor a recognized shape) instead of overclaiming a detection neither
>   side performs, and the draft no longer says it "carries no literal secret".
> - **Review finding (High): the size guard measured on a different basis than the validator it guards
>   against.** skills-hub's ingestion ceiling is `len(json.dumps(steps))` — the whole list, default
>   `ensure_ascii=True`, where one BMP character costs 6 `\uXXXX` characters. Graduation summed
>   per-step UTF-8 bytes with `ensure_ascii=False`, where the same character costs 3. A step list above
>   roughly half the ceiling could pass graduation and then be rejected by ingestion, surfacing as a
>   502 blamed on the renderer when the real cause was the bound disagreeing with itself. Now measured
>   on ingestion's exact basis, with the UTF-8 premise **asserted** in the test rather than assumed so
>   the test is a real discriminator. Same class of bug as the `captured_at` basis above: two places
>   measuring one thing on different scales.
> - **Review finding (Warning): the `web.navigate` binding hole was unnamed — an R-5 input.**
>   `bind_flow` is reachable *only* from the `web.navigate` handler, and `web.navigate` is read-tier, so
>   a graduated step list can never contain the call that binds the flow. Without it the flow never
>   binds, the origin guard and the step budget never arm, and every write parks its own confirmation
>   card instead of the single one the `risk_class` bullet promises. The runbook now says to add it as
>   step 1, naming the `skill_id` the binding is keyed on — which does not exist until the merge
>   assigns it, so the guidance has to say that too. Emitting the step instead was rejected: it would
>   synthesize a step the session never ran, which is the one thing the deterministic-rendering
>   invariant exists to prevent. **R-5 input:** a graduated browser flow therefore always needs *two*
>   human-added steps at merge time — the binding `web.navigate` and the credential
>   `web.fill_credential` — so replay verification must not treat either absence as an anomaly, and a
>   replay of an unmerged draft is expected to park per-action rather than one-gate.
> - **Re-review of the fixes: the shape guard over-catches, and that is the accepted direction.**
>   A second review of the delta above found that `web.select` with `value: "Basic Authentication"` —
>   a plausible dropdown option on an admin portal's auth-settings page, stored verbatim because
>   `web.select.value` is in `KNOWN_SAFE_FIELDS` — matches the Bearer/Basic shape and is refused with no
>   in-platform remedy. Verified reachable. Kept, because the over-catch is **pre-existing and already
>   shipped twice**: the same pattern redacts that string out of tool-gateway evidence and out of a
>   SPEC-044 draft body, so R-4 changes the *consequence* (cosmetic redaction → refusal), not the
>   trade. Narrowing the pattern to buy back this false positive opens a false *negative*, and only one
>   of the two publishes a credential into a repository. What changed is the honesty: the refusal no
>   longer asserts the value *is* a credential, names the over-catch and its direction, and offers the
>   `web.fill_credential` remedy conditionally; the function docstring went from "four guards" to five
>   and says plainly that this is the only guard whose inference is a guess. A test pins the wording so
>   the narrowing cannot happen quietly.
> - **A third cross-product coupling is now pinned in `make verify`.** Making
>   `skill_draft._VALUE_PATTERNS` public turned an unpinned second copy of the gateway's
>   `tools/redaction._VALUE_PATTERNS` into a **consequential** one: before, divergence only changed
>   cosmetic body redaction; now it decides whether a secret-shaped literal is refused or rides into the
>   merged frontmatter — failing *open* in the graduation guard, exactly like the credential-hole marker
>   already did. `validate_secret_vocabulary.py` therefore grew a third check, comparing the two tuples
>   textually as **ordered** lists (both copies document "most specific first" as meaningful, so a
>   re-ordering is a divergence a set comparison would pass silently). The existing `_tuple_pattern`
>   could not be reused: it captures to the first `)` and these bodies are regex source texts full of
>   their own groups. Proven to fire rather than assumed — a throwaway tree was perturbed three ways
>   (a gateway-only fifth shape, a re-ordering, a rename) and each failed the build with a message naming
>   the coupling. Same class as the two basis bugs above: one thing measured in two places.

## Stage 7: agent-platform + tool-gateway + portal — R-5 replay

- [x] verify a graduated **browser** executable flow binds and one-gates through the existing SPEC-051 path (`_observe_flow_binding` → `_record_flow_approval` → `_sign_flow_execution` → `build_flow_request`) with no new executor (R-5)
- [x] verify the gateway deviation guard (origin allowlist, declared `risk_class`, step budget) bounds a replayed executable-flow write identically to a hand-authored flow; executable-flow writes join **no** auto-allow list (R-5)
- [x] verify credentials resolve at replay from the named credential sets via `web.fill_credential` references — never literals (R-5)
- [x] confirm execution-runtime is **verify only** — a browser replay envelope (`approval_kind: "flow"`) verifies and forwards unchanged (R-5 / plan §6)
- [x] the infra (non-browser) executable-flow binding is **deferred** to its own 0.36.0-era slice (OQ-2) — not delivered here (R-5)
- [x] tests: a graduated browser executable flow collapses to **one** `flow`-kind gate; each subsequent write is individually signed (`build_flow_request`) + receipted (R-5)
- [x] tests: an infra executable-flow write parks **per-action** (SPEC-054 R-2) and joins no auto-allow list — the OQ-2 safe fallback asserted (R-5)
- [x] tests: a replay past step budget or off-allowlist fails closed (R-5)
- [x] portal tests: replay surfacing renders the flow headline + change-request framing (R-5)

> **Refinement notes (stage 7, R-5 replay verification).**
> - **R-5's claim is one of *indistinguishability*, and it is guaranteed structurally twice over.**
>   Once ingested, a graduated executable flow is an ordinary `web_target` + `risk_class: write` skill;
>   its `steps` list is the replay contract the *agent* follows under the single gate, never an input
>   *to* the gate — were it an input, a skill author could widen their own blast radius by writing a
>   longer step list. Verified by tracing all five seams rather than by assertion: `bind_flow` reads
>   only `web_target`/`risk_class`/`title`/`description`/`flow_intent` and takes `max_steps` from the
>   gateway knob; `FlowState` declares no `kind`/`steps` field at all, so `to_dict()` emits a fixed
>   9-key envelope; `_observe_flow_binding` passes that dict on unchanged; `FlowContextStore.record`
>   reads 8 named keys and drops everything else; `build_flow_request` emits a fixed 10-key signed
>   payload plus its signature, with nothing step-derived. **Either half alone would leave a way
>   in**, so both are pinned by test — at the gateway (it strips) and at the kernel (it would strip
>   anyway, proved by injecting `kind` and
>   `steps` into the flow dict and asserting `not hasattr`). The budget test is the discriminating one:
>   a 5-step flow bound with `flow_max_steps=2` gets `max_steps == 2`, two writes land, the third is
>   `BROWSER_FLOW_EXHAUSTED`.
> - **Review finding (High): `_sign_flow_execution` enforced its own stated scope only by call-site
>   discipline — and a direct test drove an infra mutation straight through it.** The function's
>   contract is "auto-sign one unlocked ***browser*** write", but what made that true was its single
>   caller: `GatewayPermissionMiddleware.on_check_permission` checks `gateway_tool_name in
>   BROWSER_WRITE_TOOLS` before consulting the signer. Calling the signer directly with
>   `k8s.scale_deployment` under a live browser flow authority returned a **full signed envelope** —
>   `approval_kind: "flow"`, a durable `EXECUTION_RECORD_STORE` row, an `execution_requested` audit
>   event — for a mutation no operator decision of theirs covers. Not reachable in production today
>   (one call site, gated), which is precisely the problem: the invariant rested on a call site staying
>   the only one, one refactor or middleware reordering from a hole. This is the OQ-2 fallback's worst
>   case — an executable flow self-admitting a step nobody approved — so it was closed at the seam
>   rather than left at the caller: a first-position, unconditional `BROWSER_WRITE_TOOLS` guard
>   returning `None`, placed ahead of the function's four *side effects* — the `EXECUTION_REQUESTS`
>   injection, the durable execution record, the authoring-trace step and the `execution_requested`
>   audit — so a refused name leaves no trace of a request never made. The position buys nothing
>   against the pure reads it also precedes (every other `None` path takes those too), and the code
>   comment now says exactly that rather than claiming more. `None` parks the call exactly as an
>   absent authority would, so the guard is fail-safe and is zero behavior change for every current
>   caller (full agent-platform suite: 1142 passed). It cannot reject a legitimate browser write
>   either: the middleware passes `tool.gateway_tool_name`, the dotted canonical form
>   `BROWSER_WRITE_TOOLS` holds, so the sanitized `web_click` form never reaches the guard. Both
>   checks now name each other in comments so neither gets deleted as redundant, and the test carries
>   a control asserting the same authority still signs `web.click` — so the refusal is the tool scope
>   and not a broken signer, and the control also proves the empty-audit assertion above it is a real
>   observation rather than a capture that never fired. Review confirmed the test discriminates by
>   mutation: widening `BROWSER_WRITE_TOOLS` to admit `k8s.scale_deployment` reproduces the exact
>   signed-envelope failure the finding describes. Precedent for fixing
>   in-stage rather than deferring: 6a's userinfo credential vector, 6b's leak guard.
> - **`web.fill_credential` is read-tier for *approval* but shares the write tier's step accounting.**
>   Found by a credential-reference replay test, not by reading. It is one of the five
>   `_WebInteractionTool` subclasses and the only read-tier one, so it increments `steps_used` and sets
>   `flow.approved = True` while being auto-allowed with no operator decision. Dispositioned as two
>   separate consequences rather than one bug. **`steps_used` is observable** (surfaced beside
>   `steps_budget` on every interaction result) and **conservative**: the credential-reference step
>   R-4's refusal names as the remedy comes out of the same `GATEWAY_BROWSER_FLOW_MAX_STEPS` the
>   mutations do, so a flow lands *fewer* writes than its budget advertises, never more — it fails
>   safe. What it costs is honesty in `steps_budget`, and a tight budget can be exhausted by reference
>   steps rather than mutations; pinned by test with a comment saying it is pinned because it is a
>   surprise, not because it is wanted. **`flow.approved` is unobservable**, but not for the reason
>   first written here: a review caught that "`to_dict()` runs once, at bind time, before any
>   interaction" is **false**. Its one call site is gated on `entry.flow is not None`, not on this
>   navigate being the one that bound the flow, so a plain in-flow `web.navigate` re-publishes the
>   envelope *after* interactions have set `approved: true` and advanced `steps_used` — and
>   `_observe_flow_binding` re-records it. The conclusion survives on a different fact: the key is
>   dropped at both ends. The gateway's `gate_interaction` reads `denied`/origin/`risk_class`/
>   `steps_used` but never `approved`; the kernel's `FlowContext` declares no `approved` field and
>   `FlowContextStore.record` reads 8 named keys. Because that second half is now load-bearing rather
>   than incidental, it is pinned by test — `approved: True` injected into the flow dict beside
>   `kind`/`steps`, then `not hasattr(context, "approved")` — instead of left as a doc claim.
>   Worth recording because the false premise was
>   load-bearing for a deliberate no-op, and a future reader relying on "only ever pre-interaction"
>   would be wrong. So the flip is documentation-grade
>   and was **not** changed: altering shipped SPEC-051/054 guard behavior inside an R-5 replay-
>   verification commit is out of scope, and there is no observable behavior to fix. What changed is
>   the claim (below). Flagged here per plan §6's precedent rather than silently absorbed.
> - **Three false documentation claims in tool-gateway that the tests exposed, and would have
>   shipped.** The `browser_connector` module docstring's read tier listed 4 of 9 tools and its write
>   tier listed `web.click, web.type` where the real set is the six names in agent-platform's
>   `flow_approvals.BROWSER_WRITE_TOOLS` — directly contradicting 6b's own "the complete write subset"
>   claim; its "Interactions only execute inside a bound, approved, unexhausted flow" was stale
>   post-SPEC-054 R-2, which made an *unbound* browser write park for a decision rather than be
>   refused; and `FlowState.approved`'s docstring asserted the flag universally (the finding above).
>   All three rewritten — and the `approved` rewrite needed a second pass, because "recorded when an
>   interaction of a `write`-class flow executes" over-generalized in the other direction: the set
>   that *accounts* and the set that is write-tier differ by one member each way,
>   `web.fill_credential` (read-tier, accounts) in place of `web.evaluate` (write-tier, rides
>   `gate_capture`, accounts neither). The docstring now names both sets instead of implying they
>   coincide. The docstring also names the cross-product coupling explicitly — a
>   seventh write tool added to the gateway without being added to `BROWSER_WRITE_TOOLS` degrades
>   **safe but not silent** in both consumers: graduation re-validation refuses the draft as an
>   unexplained read-tier `web.*` step, and upstream it loses flow-unlock so its writes park
>   per-action. It can never be auto-allowed by drifting, because the allow-list branch is gated on
>   `is_read_only` (the SPEC-021 R-3 invariant) — a first draft of this note claimed it "would be
>   read-tier to both", which is true of graduation and false of flow-unlock. Same
>   one-thing-measured-in-two-places class as the three basis bugs
>   recorded in stage 6.
> - **The graduation renderer emits no `flow_intent`, so a replayed graduated card has no lead
>   decision line.** `_yaml_frontmatter` writes `title`, `description`, `tags?`, `web_target?`,
>   `risk_class`, `kind`, `steps` — no `flow_intent` — so on replay `FlowContext.flow_intent` is `""`
>   and the portal's SPEC-053 R-3 `.confirm-flow-intent` node never renders. Deliberate and not a gap
>   to close: synthesizing a decision line would be a sentence the captured trace never said, the exact
>   composition R-4 forbids. The card headlines instead with the derived `title`
>   (`"<origin> executable flow"`) and the step-count `description`; a human may add a `flow_intent` at
>   merge time, beside the two steps 6b's runbook already asks for. The portal's frame guard admits on
>   `title || origin || flowIntent`, so the headline survives the absence — pinned by test, because the
>   pre-existing coverage had a hand-authored `flowIntent` and a single-call flow card separately but
>   never the graduated combination. What the new tests assert is the portal-visible half of the
>   one-gate claim, and a review narrowed it to what the renderer can actually discriminate:
>   `ConfirmationCardView` **never reads `card.approvalKind`** (it appears in `decoder.ts`,
>   `models.ts`, `useChatStream.ts` and `transcript.ts` and nowhere in `ChatView.tsx`), so the portal
>   cannot tell a flow card from an action one. A first draft asserted zero `.confirm-call-summary`
>   nodes on a multi-call flow card; that was fixture-determined rather than discriminating — the
>   change-request nodes are gated solely on `call.changeRequest`, which the fixture never sets, so
>   the assertion passed identically for `approvalKind: "action"` and a pre-existing test already
>   asserted the same two properties for exactly that. Dropped. The wire-level invariant is real and
>   stays pinned where the shape is parsed: `hitl_confirmations` emits `change_request` only when
>   `approval_kind == "action"`, and `decoder.test.ts` asserts a `"flow"` frame decodes with
>   `changeRequest: undefined`. What the renderer *does* contribute, and what the test now pins, is
>   that a **multi-call** batch yields two `.confirm-call` audit rows but exactly one Approve/Deny
>   pair — a per-call-button renderer would fail it — plus the sibling test's `.confirm-flow` truthy
>   with `.confirm-flow-intent` null, which does exercise the `title || origin || flowIntent`
>   admission guard against an empty `flowIntent`. Together: an operator replaying a graduated flow
>   sees "one decision about this workflow" and not "N decisions about N DOM actions".
> - **Box 4 needed no new test, and is recorded as verified rather than ticked silently.**
>   execution-runtime's `approval_kind` forwarding is already pinned both ways
>   (`test_executor.py::test_approval_kind_forwarded_in_payload`,
>   `::test_approval_kind_absent_when_envelope_predates_it`) and its provenance handling is covered
>   (`test_handoff.py::test_flow_provenance_reaches_the_executor`,
>   `::test_forged_provenance_rejected_before_execution`, plus the receipt-omits-provenance case).
>   Since `build_flow_request` emits a fixed 10-key signed payload plus its signature, with nothing
>   step-derived, a graduated
>   flow's replay envelope is byte-shaped like a declared one and there is nothing for R-5 to add —
>   which is the point of plan §6 naming this leg verify-only.
> - **OQ-2's fallback is asserted, not delivered.** `web.navigate` is the only binding seam and
>   requires a `web_target`, so `kind: executable_flow` alone binds nothing: an infra executable flow
>   gets `SKILL_NOT_WEB_FLOW`, `pool[...].flow` stays `None`, and every `k8s.*` write parks its own
>   per-action card under SPEC-054 R-2 with no flow authority armed. Two tests pin this — the gateway
>   side (nothing binds) and the kernel side (an infra step parks, and the signer refuses the name per
>   the High finding above). The generalized non-browser binding remains deferred to its own
>   0.36.0-era slice.

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
