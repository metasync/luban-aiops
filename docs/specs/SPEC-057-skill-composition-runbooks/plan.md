# SPEC-057 Plan: Skill Composition — Validated Runbooks of Single-Target Skills

## Approach

SPEC-057 adds a third skill class, `composition`: an ordered, validated list of
single-target sub-skill references (`sub_skills[]`) that carries **no authority
of its own** (ADR-0011). The load-bearing fact this plan is built on is that the
trust model is *already enforced by shipped code* — `FlowContext.identity()` is
`(skill_id, origin)` (`flow_approvals.py:102-104`), `FLOW_CONTEXTS` holds one
context per session and `record` overwrites it unconditionally
(`flow_approvals.py:124-155`), and ADR-0007 already re-parks the next write when
a session rebinds to a different flow (the module docstring states it verbatim at
`flow_approvals.py:18-21`). So SPEC-057 is **authoring + validation + grounding +
display**, not new enforcement machinery. Nothing here adds a gate, a kernel
trust store, a policy action, an audit event type, or a contract change to the
confirmation frames.

The work groups into six moves that each stay as close to existing machinery as
possible:

1. **Extend the contract additively** (R-1, R-3) — Skill v2 → v3: a third `kind`
   value (`composition`) and one new optional top-level `sub_skills` array, landed
   in **lockstep** across every mirror (shared schema, skills-hub pydantic,
   ingestion, portal types) with the drift guard extended to pin the new property
   and enum value on each. `additionalProperties: false` on the item is what makes
   R-3 (no control flow) true by construction rather than by detection.
2. **Validate ingestion in two layers** (R-2) — because `ingest_directory` is
   *pure per-document parsing with no store access* (`ingestion.py:476-558`, run
   via `asyncio.to_thread` at `sync.py:201-203`) and sync is *per-source and
   independent* (`sync.py:181-281`), the structural facts a single document can
   prove alone go in a new pure `_validate_composition` (so `validate_document`
   and the `python -m skills_hub.validate` CLI cover them too), and the
   cross-skill facts that need the catalog go in a new store-consulting
   `_resolve_compositions` pass in `sync_once`, between `ingest_directory` and
   `replace_source`, where `self._store` is reachable.
3. **Ground the runbook for the model** (R-6) — the resolved sub-skill view
   (title + declared target per item) is produced by **skills-hub's** `get_skill`
   read path, because that is the retrieval path the model actually rides
   (Resolved At Plan Time 1). Both gateways stay pure passthrough.
4. **Assert the authority purity, do not build it** (R-4, R-5) — no
   `flow_approvals.py` / `runtime_kernel.py` / deviation-guard / policy change.
   R-4 and R-5 are realized as *tests* (a grep/AST purity assertion that
   `sub_skills` never reaches trust state; a rebind re-park assertion extending
   the shipped `test_record_overwrites_previous_identity` precedent; a no-new-store
   assertion) plus the report-and-stop guidance the authored `body` carries.
5. **Render the read side** (R-7) — the portal Skills viewer renders `sub_skills`
   as an ordered list reusing the SPEC-052 rendered/raw pattern, and the Skills
   list shows the derived `risk_class` badge. No new policy action, no new audit
   event; `make policy-diff` reports zero transitions.
6. **Ship the required demo** (R-8) — `samples/acme-admin/composition/` composes
   two existing published single-target acme-admin skills and asserts
   ingestion/validation deterministically plus a live opt-in multi-binding
   gate-count leg, wired into the `make e2e` path via `demo-suite.sh`.

Three invariants are load-bearing and pinned by test rather than by review:

- **A composition carries no authority.** `sub_skills` is a *reference list for
  grounding and display*; it never reaches `FlowContext`, `FLOW_APPROVALS`, the
  gateway deviation guard, or the policy engine. A purity test asserts the absence
  (R-4), so a future change that wires a composition into the trust path fails the
  suite rather than silently widening authority.
- **Validation fails closed; it never degrades to knowledge.** A composition whose
  sub-skill is unresolved, is itself a composition, is over the cap, carries a
  sequencing key, or declares its own `web_target`/`steps`/`risk_class` is
  **rejected** (dropped + a `Rejection`), not silently re-classified
  (`ingestion.py` rejection vocabulary; R-2).
- **A field on one store backend only is silently dropped in production.** The
  `web_target`/`risk_class`/`flow_intent`/`kind`/`steps` lesson
  (`skill_store.py:177-190`) applies again: `sub_skills` lands on **both** the
  in-memory and Postgres backends (a `sub_skills JSONB` column with the idempotent
  `ALTER TABLE … ADD COLUMN IF NOT EXISTS` migration, the `Jsonb(...)` wrapper at
  insert, and the `isinstance(..., list)` read guard), and the **derived**
  `risk_class` is persisted at sync so `summary()` carries it to the list badge.
  Verification targets `postgres` (the dev-k8s backend).

## Resolved At Plan Time

The spec resolved OQ-1..OQ-5 at approval; their concrete shape is worked here.
The pre-implementation code read also surfaced **two refinements of the spec's
tentative `Impact` attributions** and **two interpretations** that change no
`R-x` acceptance criterion — only which product implements, and how a demo is
constructed. They are recorded here for explicit operator sign-off, since an
`approved` spec's requirements change only by agreement (the changelog rule).

### 1. R-6 is resolved in skills-hub, not agent-platform (Impact refinement #1)

The spec's `Impact` tentatively attributes "grounded-guidance rendering of
`sub_skills` (R-6)" to **agent-platform**. The retrieval-path code read refines
this. The model reaches skills through **tool-gateway** `skills.get` /
`skills.search` / `skills.list` (`tools/skills_connector.py`), which return
skills-hub's record **verbatim** (`ToolResult(data=response.json())`); the portal
reaches a single skill through **platform-gateway**'s `{skill_id:path}` proxy →
skills-hub `get_skill` (`api/routes/skills.py:184-214`). agent-platform's
`services/skills_client.py` is **validation-only** (`POST /api/v1/skills/validate`,
the SPEC-044 draft path) and is *not* in the retrieval path.

**Resolution:** the resolved sub-skill view (each item's own `title` + declared
`web_target`) is projected by **skills-hub's `get_skill`** read path, exactly as
`search_skills` already projects `{**summary(), "score", "excerpt"}` beside the
stored envelope (`api/routes/skills.py:134-146`). Both gateways stay **unchanged**
(pure passthrough), matching the spec's "tool-gateway unchanged / platform-gateway
unchanged". This changes no R-6 acceptance criterion — the model still receives
the `body` plus a rendered `sub_skills` view in declared order with each note and
each sub-skill's title and target — only *which product renders it*. **agent-platform's
only SPEC-057 change is the R-4 purity test** (no src change), which is a strictly
smaller footprint than the spec's tentative Impact implied.

### 2. R-7 ships the viewer/read side, not a bespoke composition editor (Impact refinement #2 + assumption)

The spec's `Impact` names "Studio authoring surface and Skills viewer rendering
(R-7)". R-7's acceptance criteria require: **no new policy action and no new audit
event type** (`make policy-diff` zero transitions); Studio is the authoring home
under the **existing** `session:skill_graduate` posture (SPEC-056); the portal
Skills viewer renders `sub_skills` as an ordered list reusing the SPEC-052
rendered/raw pattern; read-only observers gain no authoring power. **None of these
require new machinery.** A composition is a hand-authored `.md` merged to Git like
every other skill — Non-Goals exclude multi-target graduation, so there is no
graduation trace to assemble one from — and Studio already exists (SPEC-056).

**Resolution:** Phase 1 ships the **read side** (the Skills viewer `sub_skills`
list + the list `risk_class` badge) and the **authoring posture** (a composition is
created in a `development` session / by hand and merged, never in Chat, under the
existing posture), and does **not** build a bespoke composition-editor UI.
**Assumption flagged for operator confirmation:** if the operator wants a dedicated
composition editor, that is a Phase 2 authoring-ergonomics slice — row 346's (a)
spawn bridge and (c) assisted trace-extraction are already deferred there, and a
composition editor belongs beside them. This keeps R-7 inside the spec's own "no
new machinery" spirit.

### 3. "Published" = present in the served catalog (interpretation)

skills-hub has **no draft/publish lifecycle**: the store is present-or-absent
(`skill_store.py`), and `replace_source` is an atomic per-source delete+insert
(`skill_store.py:318-362`). A graduated skill is "published" once it is merged to
Git and synced into the served catalog.

**Resolution:** R-2's "resolves to a published skill" is implemented as "resolves
to a skill **present in the catalog at resolution time**" — a sub-skill id that
`_resolve_compositions` can look up in this source's fresh records or in
`store.get()`. This is recorded as an explicit interpretation because the spec uses
"published" without a lifecycle to hang it on.

### 4. Cross-source compositions are eventually consistent (documented property)

`sync_once` is per-source and independent (`sync.py:181-281`), so a composition in
source A whose sub-skill lives in source B can only resolve B's id from
`store.get()` **after** B has synced at least once.

**Resolution:** `_resolve_compositions` builds its index as *this source's fresh
records overlaid on `store.get()` for cross-source ids*. A composition whose
sub-skill is not yet present is **rejected on this cycle and accepted on a later
one** (sync repeats every `SKILLS_SYNC_INTERVAL_SECONDS`, `sync.py:186`). This is
the correct fail-closed behavior — an unresolvable reference is never served — and
is documented rather than papered over. The R-8 demo keeps a composition and its
sub-skills in **one source** (the `samples` ConfigMap) so its assertions are
deterministic within a single cycle.

### 5. R-8's demo composes password-reset + lock-unlock-user (mixed browser+infra), given the shipped repertoire

R-8 says the demo "composes the **existing** single-target web-check skills —
password-reset and one other — and asserts multi-binding re-park end to end". The
shipped acme-admin repertoire (`samples/acme-admin/*/skill/*.md`) has exactly **one
browser write flow** (`password-reset/ResetAcmePassword.md`: `web_target` +
`risk_class: write` + `flow_intent`) and **one browser read flow**
(`user-status/CheckUserStatus.md`: `web_target`, read). A *live browser→browser
rebind re-park* needs two browser **write** flows, which the repertoire does not
contain, and authoring a new single-target product skill just to demo the composite
would be net-new surface beyond "compose the existing skills".

**Resolution:** the live leg composes **password-reset** (browser write flow → 1
`flow` card) + **lock-unlock-user** (`LockUnlockUser.md`: `http.post` infra write →
1 `action` card) — the **mixed browser+infra** composition R-4 *explicitly permits*
("its gate count is the sum of its browser bindings and its infra writes"). Its gate
count (**2**) exceeds any single sub-skill run (**1** each), and each card names only
its own sub-skill (the flow card carries password-reset's `flow_intent`/target; the
action card carries lock-unlock-user's `http.post`), so "no card claims authority
over a sub-skill it does not name" is asserted live. The **pure browser→browser
rebind re-park** (the identity guard) is asserted at the **unit** level in
agent-platform (R-4), extending the shipped `test_record_overwrites_previous_identity`
precedent — which needs no second live browser skill. This meets both R-8 acceptance
criteria (multi-binding asserted end to end; R-4's gate-count assertion gets a live
leg) with no new single-target product skill.

## Design Per Requirement

### R-1: A `composition` skill class, additive on the existing contract

- **affected files:** `shared/shared-contracts/schemas/skill.schema.json` (title
  "Skill (v2)" → "Skill (v3)"; `kind` enum `["knowledge","executable_flow"]` →
  `+ "composition"`; a new optional top-level `sub_skills` array; extended
  description); `products/skills-hub/src/skills_hub/schemas/skill.py` (a new
  `SubSkillRef` model + `sub_skills: list[SubSkillRef] | None`; widen the `kind`
  pattern to `^(knowledge|executable_flow|composition)$`);
  `products/skills-hub/src/skills_hub/services/ingestion.py` (`ALLOWED_KEYS +=
  {"sub_skills"}`, `VALID_KINDS += ("composition",)`);
  `products/skills-hub/src/skills_hub/services/skill_store.py` (a `sub_skills
  JSONB` column on **both** backends + the idempotent `ALTER`, INSERT column/value
  + `ON CONFLICT DO UPDATE`, `_ROW_COLUMNS`, the `_row_to_skill` read guard, and the
  `Jsonb(...)` insert wrapper — the `steps` precedent verbatim);
  `products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx`
  (`SkillDetail`) + `views/control/SkillsView.tsx` (`SkillRecord`);
  `shared/shared-contracts/skill-format.md` (v2 → v3: a `sub_skills` + `kind:
  composition` frontmatter row and a "Composition skills (v3)" section).
- **chosen approach:** a `sub_skills` item is `{ skill_id (required, same id
  pattern as the top-level `skill_id`), note (optional string ≤ 200) }` with
  `additionalProperties: false`. Order in the array **is** the declared runbook
  sequence. `note` is display-only and never a security input — the same standing
  `flow_intent` (SPEC-053) and `steps[].expect` (SPEC-055) have. The composition's
  own `risk_class` is **derived for display only** and **reuses the existing
  top-level `risk_class` field** (no new field): `write` when any resolved
  sub-skill declares `risk_class: write`, else `read`. It is computed and persisted
  server-side at sync (R-2's resolution pass) so `summary()`
  (`schemas/skill.py:63-65`) carries it to the Skills-list badge; the deviation
  guard, identity guard and policy engine never read it. Skill Format bumps v2 → v3
  additively — a v2 consumer that ignores `kind`/`sub_skills` still ingests the
  `body` as grounded guidance, and a knowledge/executable_flow skill validates
  exactly as today.
- **alternatives rejected:** a **separate document kind** beside `shift_summary` /
  `incident_report` — rejected at approval (OQ-1): sub-skills are referenced by
  `skill_id`, so the composition belongs in the same namespace and rides the same
  ingestion/publication/grounding paths; a document kind would duplicate all three
  and could not be referenced as a skill. A **new `derived_risk_class` field** —
  rejected: the existing `risk_class` field already means "declared effect" and
  already flows to the badge via `summary()`; a second field would drift and
  double-render. Author-declared `risk_class` on a composition — rejected (R-2):
  it would falsely imply the composite is itself a gated target.

### R-2: Ingestion validation fails closed

- **affected files:** `services/ingestion.py` (a new pure `_validate_composition`,
  called from `_validate_frontmatter` beside `_validate_steps` at
  `ingestion.py:268-270`; a `MAX_SUB_SKILLS` module default; the cap threaded as an
  optional parameter through `_validate_frontmatter` / `ingest_directory` /
  `validate_document`); `services/sync.py` (a new `_resolve_compositions` pass in
  `sync_once` between `ingest_directory` and `replace_source` at `sync.py:201-204`;
  a `composition` bucket in `_rejection_category` for the resolution-layer
  rejections); `core/config.py` (a new `composition_max_sub_skills: int = 8`
  field + `from_env` read of `SKILLS_COMPOSITION_MAX_SUB_SKILLS`, with a
  `SettingsError` guard for a value < 1, consistent with the fail-fast posture at
  `config.py:19-20`); `dev-k8s/base/skills-hub/runtime-config.env` (the knob);
  `docs/guides/configuration-reference.md` (a Feature Activation Matrix row beside
  `SKILLS_SYNC_INTERVAL_SECONDS`).
- **chosen approach — two layers.**
  - **Structural (pure, `_validate_composition`):** `sub_skills` is a non-empty
    list; each item is a mapping with a required `skill_id` (matching the id
    pattern) + an optional `note ≤ 200`; **no unknown item key** (this is what
    rejects a sequencing key — R-3); **no duplicate** `skill_id`; count ≤ the
    configured cap; `kind: composition` **requires** `sub_skills`; and a composition
    declares **no** `web_target`, **no** `steps`, **no** `risk_class` (all three
    rejected). Living in `_validate_frontmatter` means `validate_document`
    (`ingestion.py:463-473`, the `POST /skills/validate` draft path) and the
    `python -m skills_hub.validate` CLI (`validate.py:37-39`, which calls
    `ingest_directory`) cover it for free.
  - **Resolution (store-consulting, `_resolve_compositions`):** for each
    composition record, resolve every `sub_skills[].skill_id` against *this source's
    fresh records overlaid on `store.get()`* (Resolved At Plan Time 4); **reject**
    (drop the record + append a `Rejection`) any composition whose sub-skill is
    **unresolved**, resolves to another **`composition`** (no nesting — removes
    cycles/unbounded depth by construction), or is **not single-target** (a scalar
    `web_target` or none — structurally guaranteed by the scalar field, asserted
    defensively). The same pass **derives and persists** the composition's display
    `risk_class` (R-1) via `model_copy(update=...)` before `replace_source`.
  - Ingestion re-checks **only** the two structural facts OQ-2 named (still
    present, still single-target); it does **not** re-run SPEC-055 R-4 blast-radius
    validation, which re-litigated a decision already made at each sub-skill's
    graduation. A rejection rides the **existing** `skills_synced` rejected count +
    per-source status (`sync.py:216-234`) — **no new audit event type** (R-2).
- **cap arithmetic:** `SKILLS_COMPOSITION_MAX_SUB_SKILLS` (default **8**, OQ-4) ×
  `GATEWAY_BROWSER_FLOW_MAX_STEPS` (default **20**, `tool-gateway/core/config.py:21`)
  = **160** worst-case unlocked browser writes per run, each still individually
  signed, audited and receipted, and each sub-skill still gated once. The value is
  revisited on the first real operator-authored composition.
- **alternatives rejected:** resolving sub-skills **inside `ingest_directory`** —
  rejected: it is pure per-document parsing with no store handle, and giving it one
  would break the `asyncio.to_thread` purity and the per-source independence. A
  **single-layer** validator — rejected: the structural facts must fail in the draft
  CLI (no catalog), the cross-skill facts must consult it, and conflating them would
  either make the draft path lie or make sync re-parse. **Nesting with cycle
  detection** — rejected at approval (R-2/Non-Goals): forbidding a composition
  sub-skill removes cycles by construction rather than by detection.

### R-3: No control flow

- **affected files:** `skill.schema.json` (the `sub_skills` item's
  `additionalProperties: false` + a description recording the rationale);
  `services/ingestion.py` (`_validate_composition`'s unknown-item-key rejection);
  `skill-format.md` (the v3 section states there is no branch/loop/conditional/
  retry/early-exit vocabulary).
- **chosen approach:** the contract provides **no** sequencing construct and the
  item schema forbids any key but `skill_id`/`note`, so control flow cannot be
  written and cannot be smuggled in via a `note` (a `note` is a string, never
  interpreted). The rationale is recorded in the schema description: an interpreter
  would need loops, and a loop defeats `GATEWAY_BROWSER_FLOW_MAX_STEPS`, currently
  the only bound on an unlocked browser flow. A validation test pins that a
  composition carrying any unrecognized sequencing key (`if` / `loop` / `retry` /
  `on_fail`) is rejected, so `additionalProperties: false` staying true is asserted,
  not assumed.
- **alternatives rejected:** an explicit deny-list of sequencing keys — rejected:
  `additionalProperties: false` already forbids *every* key but the two allowed, so
  a deny-list would be a weaker, drift-prone restatement of a stronger invariant.

### R-4: A composition carries no authority; each sub-skill keeps its own gate

- **affected files:** **no src change.** Tests only: a new agent-platform purity
  test (e.g. `tests/test_skill_composition_purity.py`) and a rebind re-park test
  extending `tests/test_flow_approvals.py`; a tool-gateway grep assertion that the
  deviation guard (`tools/browser_connector.py`) never reads `sub_skills`.
- **chosen approach:** a **grep/AST purity test** asserts `sub_skills` never reaches
  `FlowContext`, `FLOW_APPROVALS`, the deviation guard, or the policy engine — i.e.
  it is absent from the agent-platform trust path (`runtime_kernel.py`,
  `flow_approvals.py`, `execution_signing.py`) and from the tool-gateway guard, and
  is not a field on `FlowContext` / `FlowApproval`. A **rebind re-park test**
  asserts that recording a second sub-skill's `(skill_id, origin)` over the first's
  armed approval leaves the identity non-matching, so the next write re-parks —
  extending the shipped `test_record_overwrites_previous_identity`
  (`test_flow_approvals.py:120`) from "the context overwrites" to "the armed
  authority therefore no longer applies". Browser legs gate exactly as today
  (`web.navigate(skill_id=…)` overwrites the single `FlowContext`; the identity no
  longer matches the recorded `FLOW_APPROVALS` entry; the next write-tier call
  re-parks); infra legs park per-action under SPEC-054 R-2 unchanged; every
  execution stays individually signed, persisted, audited and receipted with
  ADR-0010 provenance unchanged.
- **alternatives rejected:** a **composite-level gate** — rejected by ADR-0011: it
  would need the multi-identity authority store ADR-0007 removed. **Reading
  `sub_skills` to pre-approve or pre-bind** a sub-skill — rejected (R-6): the
  platform never issues `web.navigate` on the model's behalf and never enforces
  order.

### R-5: Not a transaction — report-and-stop, re-entry from a named step

- **affected files:** `skill-format.md` (the v3 section documents the
  report-and-stop convention and the 30-day re-entry window); the authored
  composition `body` (carries the "on failure, report which sub-skill failed and
  stop" instruction); `docs/guides/` operator documentation (the re-entry window);
  a purity test asserting no new state store. **No new store, no runtime code.**
- **chosen approach:** report-and-stop is a **grounding/documentation** property —
  the rendered runbook instructs the agent to report the failed sub-skill and stop
  rather than continue past a premise that no longer holds. **Re-entry derives from
  the existing `execution_records` signed receipts** for the session
  (`RETENTION_WINDOW_DAYS = 30`, `execution_records.py:31`) — no new
  composite-progress store and no persisted runbook-progress record. Because
  receipts are swept at 30 days, re-entry is only derivable inside that window;
  outside it the operator restarts from the beginning, stated in the operator docs
  rather than papered over. A purity test asserts no new state store is introduced
  for composition progress.
- **alternatives rejected:** a **composite-progress store** or an aggregate
  half-state surface — rejected (OQ-3, Non-Goals): the completed prefix is derivable
  from receipts, and nothing aggregates it per composition; R-5's report-and-stop
  message names the failed sub-skill in the transcript instead. **Rollback /
  compensation / saga semantics** — rejected (R-5): a stopped composition leaves its
  touched targets as-is and nothing claims otherwise.

### R-6: Delivery to the agent is grounded guidance, never platform sequencing

- **affected files:** `products/skills-hub/src/skills_hub/api/routes/skills.py`
  (`get_skill` read-path projection at `:184-214`). Both gateways unchanged.
- **chosen approach:** per Resolved At Plan Time 1, `get_skill` projects each
  `sub_skills` item to a display view — `{ skill_id, note?, resolved_title?,
  resolved_web_target? }` — by looking each sub-skill up in the store, exactly as
  `search_skills` projects `score`/`excerpt` beside the stored envelope. The
  projection is **read-path only**: the authored/stored item and the schema keep
  just `skill_id` + `note`, and nothing resolved is persisted. The composition's
  `body` carries the report-and-stop guidance (R-5). Because tool-gateway's
  `GetSkillTool` returns `response.json()` verbatim, the enriched view reaches the
  model through the existing SPEC-014 grounded-guidance path. The platform **never**
  pre-binds a sub-skill, never issues `web.navigate` on the model's behalf, and
  never enforces the declared order — order is guidance with the same standing as
  `steps[].expect`. The rendered guidance names each sub-skill's declared target so
  an operator reading a transcript sees which target each segment was scoped to.
- **alternatives rejected:** rendering in **agent-platform** — rejected (Resolved At
  Plan Time 1): it is not in the retrieval path. **Persisting the resolved view** —
  rejected: it would duplicate catalog state and go stale when a sub-skill is
  republished; a read-path projection is always current.

### R-7: Authorization posture and the Studio authoring surface

- **affected files:** `products/operator-portal/web-ui/app/src/chat/SkillContentViewer.tsx`
  (`SkillDetail` gains `sub_skills`; the Rendered view renders an ordered list —
  sub-skill title, declared target, note — reusing the SPEC-052 rendered/raw
  `Segmented` pattern; the Raw view shows the frontmatter verbatim);
  `views/control/SkillsView.tsx` (`SkillRecord` gains `risk_class`; a badge column
  renders the derived value that already flows from `summary()`);
  `docs/agentic-aiops-platform/authorization-matrix.md` (verify — compositions read
  under `skills:read`, authored under `session:skill_graduate`; **no new row**).
- **chosen approach:** **no new policy action and no new audit event type** — a
  composition is a skill, read under the existing `skills:read` and authored in
  Studio under the existing `session:skill_graduate` posture SPEC-056 established.
  `make policy-diff` must report **zero** outcome transitions across all
  (role, action) pairs. Studio is the authoring home (SPEC-056 Design B): a
  composition is a development artifact, created in a `development` session and
  never in Chat. Read-only observers and auditors see compositions under their
  existing read posture and gain no authoring power. Per Resolved At Plan Time 2,
  Phase 1 ships the viewer/read side and the authoring posture, **not** a bespoke
  composition-editor UI.
- **alternatives rejected:** a **new `skill:compose` action** — rejected: it would
  add policy vocabulary and a bundle content-hash bump for a capability the existing
  posture already covers, and R-7 requires zero transitions. A **bespoke composition
  editor** — deferred (Resolved At Plan Time 2): compositions are hand-authored `.md`
  like every other skill.

### R-8: Delivery traceability per ADR-0008

- **affected files:** `docs/specs/SPEC-057-…/tasks.md` (≥1 asserting test per
  R-1..R-7 criterion); `samples/acme-admin/composition/skill/<Name>.md` (the
  composition document) + `samples/acme-admin/composition/demo/demo.sh` (the demo) +
  `README.md`/`WALKTHROUGH.md` (the house sample docs); `samples/acme-admin/demo-suite.sh`
  (add `composition` to `DEMOS` and the composition id to the preflight `expected`
  set).
- **chosen approach:** every R-1..R-7 criterion maps to at least one automated test,
  recorded in `tasks.md` at delivery. The **required** `samples/` demo (OQ-5,
  ADR-0008 rule 2 — it exercises multi-binding re-park, otherwise unexercised)
  composes the two existing published single-target skills per Resolved At Plan Time
  5. Its `demo.sh` has **deterministic legs** (assert ingestion/validation: the
  composition resolves, a nested reference is rejected, the cap rejects, the derived
  `risk_class` is `write` because password-reset is `write`, the sub-skill ids are
  the mounted `samples/password-reset-resetacmepassword` +
  `samples/lock-unlock-user-lockunlockuser`) and an **opt-in live chat leg**
  (`RUN_CHAT_LEG=true`) asserting the multi-binding gate count (2 cards > any single
  sub-skill's 1) and that no card claims authority over a sub-skill it does not
  name. It is wired into `make e2e` through `demo-suite.sh` (already in the root
  `Makefile` e2e loop at `Makefile:215`), and `deploy-samples.sh`'s
  `find -type d -name skill` discovery (`deploy-samples.sh:97`) mounts it as
  `samples/composition-<name>` because it ships a `skill/` dir.
- **alternatives rejected:** shipping **no demo** — rejected (OQ-5, ADR-0008 rule
  2): a two-sub-skill composition is the first end-to-end multi-binding assertion in
  the suite, so a demo is owed. Composing two **browser write** flows for the live
  leg — rejected (Resolved At Plan Time 5): the repertoire has one.

## Sequencing And Dependencies

1. **Contract + mirrors** (R-1, R-3) — `skill.schema.json` (v3: `composition` kind,
   `sub_skills`), skills-hub `schemas/skill.py` (`SubSkillRef`, widened `kind`
   pattern), `ingestion.py` (`ALLOWED_KEYS`, `VALID_KINDS`), `skill_store.py` (the
   `sub_skills JSONB` column on both backends), `skill-format.md` v3, and the
   `test_contracts.py` drift guard extended. Depends on nothing; everything
   validates against it.
2. **Config knob + structural validation** (R-2 structural, R-3) —
   `core/config.py` `composition_max_sub_skills`, `_validate_composition` in
   `ingestion.py`, the cap threading, `runtime-config.env`, the
   configuration-reference row. Depends on stage 1.
3. **Resolution pass** (R-2 resolution, R-1 derived risk_class) —
   `_resolve_compositions` in `sync.py` + the `_rejection_category` bucket. Depends
   on stage 2.
4. **Read-path enrichment** (R-6) — `get_skill` projection in
   `api/routes/skills.py`. Depends on stages 1/3 (a stored, resolved composition).
5. **agent-platform purity + rebind tests** (R-4, R-5) — no src change. Depends on
   stage 1 (the `sub_skills` vocabulary to assert against); parallel with 2-4.
6. **Portal Skills viewer + list badge** (R-7) — `SkillContentViewer.tsx`,
   `SkillsView.tsx`. Depends on stage 4 (the enriched read path).
7. **Samples composition demo + `make e2e` wiring** (R-8) —
   `samples/acme-admin/composition/`, `demo-suite.sh`. Depends on stages 3/4.
8. **Living docs + release** — configuration-reference (stage 2), portal-user-guide,
   the skills guide, `CHANGELOG.md`, a dated release note + its README index, the
   spec index, `delivery-roadmap.md`, and the version bump **0.39.1 → 0.40.0** in
   lockstep. Depends on all.

## Test Strategy

- **skills-hub (`pytest`)**
  - `test_ingestion.py` (structural): a valid composition ingests; a duplicate
    `skill_id` is rejected; over-cap is rejected; `kind: composition` without
    `sub_skills` is rejected; a composition declaring its own `web_target` / `steps`
    / `risk_class` is rejected; a sequencing key (`if`/`loop`/`retry`/`on_fail`) on
    an item is rejected (R-3); a `note > 200` is rejected; `validate_document` and
    the `validate` CLI reject the same documents (the structural layer is shared).
  - `test_sync.py` (resolution): an unresolved sub-skill is dropped + a `Rejection`
    recorded; a sub-skill that is itself a `composition` is rejected (no nesting); a
    cross-source sub-skill is rejected on the cycle before its source syncs and
    accepted after (eventual consistency, Resolved At Plan Time 4); the derived
    `risk_class` is `write` when any sub-skill is `write`, else `read`, and is
    persisted; a rejection increments the `skills_synced` rejected count with no new
    event type.
  - `test_skill_store.py`: `sub_skills` round-trips on **both** backends (in-memory +
    Postgres, the `Jsonb` write + the `isinstance(list)` read); a NULL `sub_skills`
    (a knowledge/executable_flow skill) reads back omitted.
  - `test_routes.py`: `get_skill` on a composition projects each item's
    `resolved_title` + `resolved_web_target` (R-6); the authored item stays
    `skill_id` + `note`; a non-composition `get_skill` is byte-identical to today.
  - `test_contracts.py` (drift guard): a v3 composition validates against
    `skill.schema.json`; the property-set equality now includes `sub_skills`; the
    `kind` enum-parity assertion includes `composition`; the guard **fires** when a
    mirror drops `sub_skills` or `composition` (prove it is sensitive, not vacuous).
  - `test_config.py`: `SKILLS_COMPOSITION_MAX_SUB_SKILLS` parses; a value < 1 raises
    `SettingsError`; absent defaults to 8.
- **agent-platform (`pytest`)** — the R-4 purity test (`sub_skills` absent from
  `runtime_kernel.py` / `flow_approvals.py` / `execution_signing.py` and not a field
  on `FlowContext`/`FlowApproval`); the rebind re-park test (recording a second
  sub-skill identity leaves the armed approval non-matching → the next write
  re-parks); the R-5 no-new-store assertion.
- **tool-gateway (`pytest`)** — a grep assertion that the deviation guard
  (`tools/browser_connector.py`) never reads `sub_skills`; the bound-flow behavior is
  byte-for-byte unchanged.
- **operator-portal (`vitest`)** — `SkillContentViewer.test.tsx` renders the
  `sub_skills` ordered list (title, target, note) in the Rendered view and the raw
  frontmatter in the Raw view; `SkillsView.test.tsx` renders the derived `risk_class`
  badge.
- **policy** — `make policy-diff` reports **zero** outcome transitions; the policy
  rules/scenarios are unchanged (no new action).
- **integration** — `make verify` green (all product suites + 4 kustomize overlays +
  policy rules/scenarios unchanged + version lockstep + the secret-vocabulary leg
  unchanged); the new `samples/acme-admin/composition/demo.sh` exercised in the
  `make e2e` path via `demo-suite.sh`; the existing acme-admin demo legs stay green.

## Rollout And Migration

- **deployment / configuration changes:** one new skills-hub knob,
  `SKILLS_COMPOSITION_MAX_SUB_SKILLS` (default **8**), added to
  `dev-k8s/base/skills-hub/runtime-config.env` and documented in
  `docs/guides/configuration-reference.md`'s Feature Activation Matrix. **No** new
  policy action, **no** new audit event type, **no** bundle content-hash change,
  **no** stream/contract change to the confirmation frames.
- **backward compatibility:** additive and fail-safe throughout.
  - Skills without `kind`/`sub_skills` validate and ingest exactly as today; the
    `kind` enum only *gains* `composition`, so every existing skill is unchanged.
  - Existing `skills` rows get a NULL `sub_skills` → omitted (idempotent
    `ALTER TABLE … ADD COLUMN IF NOT EXISTS sub_skills JSONB`, the `steps`
    precedent).
  - A v2 consumer that ignores `kind`/`sub_skills` still ingests a composition's
    `body` as grounded guidance (Skill Format v3 is additive).
  - The `get_skill` enrichment is a read-path projection beside the stored envelope
    (the `search` `score`/`excerpt` precedent); the list/summary shape only gains the
    already-declared `risk_class`/`sub_skills` when present.
- **data migration:** none beyond the idempotent `skills.sub_skills` column add.
- **rollback:** revert the delivery commit. The `sub_skills` column is harmless if
  left in place (unused / NULL), so no destructive down-migration is required.
  Rolling back removes the `composition` kind, the resolution pass, and the read-path
  projection, and leaves every single-target skill and the SPEC-051/054/055 gate
  machinery intact — a composition simply stops ingesting (rejected as an unknown
  `kind`), which is the fail-closed posture.
- **version:** MINOR bump **0.39.1 → 0.40.0** at the delivery gate (a
  backward-compatible feature, per the house "release trains map to MINOR bumps"
  convention), with `VERSION` + every per-product lockstep constant (`pyproject.toml`,
  `metadata.py`, the `__init__.py` literals) + the `uv.lock` re-locks;
  `make validate-version` must report OK across every product and the portal.
