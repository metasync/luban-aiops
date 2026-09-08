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

- [ ] `runtime_kernel.py`: a `_capture_authoring_step(...)` helper called beside `_persist_execution_request` at the per-action signing site (`_prepare_executions`) (R-2)
- [ ] `runtime_kernel.py`: the same helper called at the flow-unlock signing site (`_sign_flow_execution`), so both approval kinds append to one coherent ordered trace (R-2)
- [ ] secret-safe parameterization **at capture**: credential values replaced by credential-set references / placeholders (reuse `secret_params` vocabulary + the `web.fill_credential` indirection) before the write — no literal secret reaches the store (R-2)
- [ ] the step stores `execution_id` / `confirm_id` references and does **not** duplicate the signed receipt or outcome (those stay in `execution_records`) (R-2)
- [ ] best-effort + fail-safe: wrapped like `_persist_execution_request` — a trace failure degrades to "no graduation candidate", never blocks the mutation's execution or its `execution_records`/receipt path (R-2)
- [ ] tests: a step is captured only for a signed mutation at **both** sites; a read-tier call is never captured (R-2)
- [ ] tests: a mixed session (per-action + flow-unlock writes) yields one ordered trace (R-2)
- [ ] tests: secret values are parameterized at capture — no literal in the stored `args` (R-2)
- [ ] tests: a trace-store failure never blocks execution or the `execution_records`/receipt write (R-2)

## Stage 5: skills-hub — R-3 executable-flow skill class

- [x] `schemas/skill.py`: `kind` + `steps` on the `Skill` model — **done in stage 1** (the contract parity test binds the model to the schema atomically, so it cannot wait for stage 5); stage 5 keeps only ingestion + store (R-3)
- [ ] `services/ingestion.py`: add `kind`, `steps` to `ALLOWED_KEYS`; relax the `risk_class`-requires-`web_target` rule so `risk_class: write` ingests without a `web_target` (R-3)
- [ ] `services/ingestion.py`: validate the executable-flow class — step-list shape, `risk_class: write` when any step mutates, credential references resolve to named credential sets — and reject a malformed one on the existing `validate_document` path (R-3)
- [ ] `services/skill_store.py`: add `kind TEXT` + `steps JSONB` on **both** backends (in-memory + Postgres), idempotent `ALTER TABLE … ADD COLUMN IF NOT EXISTS`, INSERT + row-map (the `flow_intent` precedent) (R-3)
- [ ] confirm a `read`-class skill still never executes mutating tools; only a `write`-class executable flow can replay, and only under R-5's one gate (R-3)
- [ ] tests: `risk_class: write` **without** `web_target` ingests (the relaxed rule) (R-3)
- [ ] tests: a `kind: executable_flow` skill with a valid step list ingests and round-trips on **both** store backends (R-3)
- [ ] tests: a malformed step list / a missing `risk_class: write` on a mutating flow / an unresolvable credential reference is rejected (R-3)
- [ ] tests: a knowledge skill (no `kind`/`steps`) validates exactly as today — no existing skill breaks (R-3)

## Stage 6: agent-platform + portal — R-4 graduation

- [ ] `services/skill_graduation.py` (new): `build_executable_flow_draft(trace)` renders the ordered trace into an executable-flow skill Markdown (frontmatter `kind: executable_flow`, `risk_class: write`, `web_target` for a browser flow, `steps`; body = a human-readable replay runbook) with **no LLM call** (contrast SPEC-044's `generate_skill_draft`) (R-4)
- [ ] `services/skill_graduation.py`: `revalidate_blast_radius(trace)` runs **before** the draft is produced — bounded step count, every origin/target allowlisted, consistent `risk_class: write`, all credentials resolved to credential-set references (the SPEC-051 guards); a failing trace is a deterministic refusal surfaced to the operator (R-4)
- [ ] `api/v2/routes.py`: `POST /api/v2/sessions/{session_id}/skill-graduate` mirroring `create_skill_draft` — gateway-enforced `session:skill_graduate`, server-side ownership re-check (foreign/unknown → the structural 404), validate through skills-hub's ingestion path (`_validate_skill_markdown`), ephemeral (nothing persisted but the lifecycle flip) (R-4)
- [ ] `api/v2/routes.py`: emit the `skill_graduated` audit event and flip the trace lifecycle to `graduated` (R-4)
- [ ] the graduated draft is validated against Skill v2 on skills-hub's own ingestion path before it reaches the operator (never auto-published) (R-4)
- [ ] portal: a "Graduate as skill" entry point on the session (role-gated — visible to operator/approver, not observer) (R-4)
- [ ] portal: the executable-flow draft preview (rendered + raw toggle, mode badge, Download .md / Discard) reusing the SPEC-045 pattern (R-4)
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
  - R-4 → stage 6 deterministic draft, blast-radius refusal + happy path, `skill_graduated` + lifecycle flip + draft-not-published, observer-denied
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
