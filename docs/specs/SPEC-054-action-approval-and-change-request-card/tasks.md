# SPEC-054 Tasks: Action-Level HITL Approval and the Change-Request Confirmation Card

Task states: `[ ]` pending, `[x]` done. Keep tasks small and tied to requirement IDs.
Ordering follows `plan.md`'s Sequencing And Dependencies — stage 2 (the backstops)
must land before or with stage 4 (the gateway relaxation), never after.

## Stage 1: Contracts

- [x] `agent-stream-event.schema.json`: retro-fit the missing **v10** clause (SPEC-053 `flow_intent`) into the title + description ledger, then advance **v10 → v11** for this spec
- [x] `agent-stream-event.schema.json`: add optional `approval_kind` (`enum: ["flow", "action"]`) at the frame root (R-1)
- [x] `agent-stream-event.schema.json`: declare `change_request` (`{summary, fields[][{label, value, masked}]}`) **and** the already-shipped-but-undeclared `display_hint` on `pending_calls.items` (R-3; `additionalProperties: false` makes both mandatory)
- [x] `agent-session.schema.json`: add optional `approval_kind` and `message` on `confirmations.items` (R-1/R-4)
- [x] `execution-request.schema.json`: add optional `approval_kind` (`enum: ["action", "flow"]`), kept **out of** `required` so predating envelopes still verify (R-2 / ADR-0010)
- [x] `execution-request.schema.json`: correct the stale `tool_name` description — `pending_calls_payload` and `build_flow_request` both emit the gateway canonical **dotted** name, not a sanitized one

Stage 1 note: `agent-session.schema.json`'s nested `confirmations.items.pending_calls.items`
is loosely typed (`{"type": "object"}`, no `additionalProperties: false`) and has been since
SPEC-031, so there was nothing to declare there — the durable per-call entries already admit
`display_hint` and `change_request` without a contract violation. Tightening it would add a new
constraint this slice does not need; the strict declaration lives on the live frame schema, which
is where the latent violation actually was. Verified: `agent-session.schema.json`'s title stays
`(v2)` because that parenthetical is the ADR-0003 contract family, not the schema revision — its
additive history (SPEC-022/024/025/031/033/037/051/053) is recorded in the description ledgers,
and SPEC-054 follows the SPEC-033 precedent by extending the `confirmations` ledger.

## Stage 2: agent-platform — signing provenance + authority clearing (R-2 backstops)

- [x] `services/execution_signing.py`: `build_requests` stamps `"approval_kind": "action"` into the envelope dict **before** `sign_envelope`
- [x] `services/execution_signing.py`: `build_flow_request` stamps `"approval_kind": "flow"` **before** signing; `sign_envelope`/`canonical_digest` unchanged
- [x] `services/flow_approvals.py`: new `FLOW_KILLING_ERROR_CODES` vocabulary beside `BROWSER_WRITE_TOOLS`, naming its twin rationale (why `READ_ONLY`/`EXHAUSTED` are absent)
- [x] `runtime_kernel.py`: new clearing path drops **both** `FLOW_CONTEXTS` and `FLOW_APPROVALS` for the session on a flow-killing `tool_result` (sibling to `_observe_flow_binding`, wired into `_drain_trace_queue`, reading `frame["error"]["code"]` from the gateway `_denied` envelope)
- [x] clearing codes: `BROWSER_REDIRECT_NOT_ALLOWED`, `BROWSER_FLOW_DENIED`, `BROWSER_FLOW_ORIGIN_DEVIATED`, `BROWSER_FLOW_AUTHORITY_STALE`, plus a failed flow-binding `web.navigate`
- [x] `runtime_kernel.py`: `_record_flow_approval` additionally requires the bound flow's `risk_class == "write"` before arming
- [x] tests: `build_requests` → `action`, `build_flow_request` → `flow`; tampering with `approval_kind` invalidates the signature; an envelope without it still verifies
- [x] tests: each flow-killing code drops both stores; a failed `web.navigate` drops both; a successful navigate does not; after clearing the next `web.*` write does **not** auto-sign
- [x] tests: `_record_flow_approval` does not arm on an unbound batch or a read-class binding, and does arm on a `write`-class binding

Stage 2 note: the plan's "a failed flow-binding `web.navigate`" is implemented
**precisely** rather than as any failed navigate. `browser_connector.py` nulls
`entry.flow` on the navigation-error path only when `bound_here` is true — its own
comment reads "A pre-existing flow is left intact — the page did not move" — so a
plain in-flow navigation failure leaves the gateway binding untouched and the
kernel's reflection still truthful. Clearing there would have cost a legitimately
one-gated flow an extra approval card, regressing ADR-0007/SPEC-049 R-4. The
kernel therefore pairs the result with its `tool_call` frame by `call_id` (the
same backward walk `_extract_browser_element_map` already uses) and clears only
when the navigate carried a `skill_id`; an unpaired result declines to guess and
leaves the refusal to the gateway, which is the fail-closed boundary either way.
Also pinned from the negative side: `BROWSER_FLOW_READ_ONLY`,
`BROWSER_FLOW_EXHAUSTED`, `BROWSER_FLOW_TARGET_MISMATCH` and
`BROWSER_ORIGIN_NOT_ALLOWED` must **not** clear.
agent-platform suite: 801 → 834 passed.

## Stage 3: execution-runtime — forward the verified provenance (R-2)

- [x] `api/routes/handoff.py`: pass the verified `approval_kind` through to the executor; `verify_envelope` unchanged (it already covers every field except `signature`)
- [x] `services/executor.py`: add `approval_kind` to the invoke payload beside `session_id`, with a matching "provenance handle, not authority" comment
- [x] tests: the forwarded value reaches the invoke payload; verification accepts an envelope with and without it; a tampered value fails verification

Stage 3 note: also pinned that the **receipt** is unchanged by the field
(`build_receipt` never sees it), so provenance stays a browser-path concern the
worker does not evaluate. The approved spec's Impact bullet for this product was
factually wrong ("no code change; verify only") and is corrected in `spec.md`
with a changelog entry — see `plan.md` §"Resolved At Plan Time" 4.
execution-runtime suite: 66 → 73 passed.

## Stage 4: tool-gateway — park-not-deny + substitute guards + provenance enforcement (R-2)

- [x] `tools/browser_connector.py`: `gate_interaction` splits the `flow is None` branch — non-allowlisted origin still denied, allowlisted origin falls through to the unbound path
- [x] unbound path re-validates the **live** origin via `entry.active_target.url` (frame-aware) and halts on drift, mirroring `gate_capture`
- [x] `web.fill_credential` reachable unbound **by reference only** (`credential_set` + `field`); stays `risk_level = "read"` and stays in `DEFAULT_AUTO_ALLOWED_TOOLS`
- [x] browser write path: forwarded `approval_kind == "flow"` with `entry.flow is None` → `_denied(..., "BROWSER_FLOW_AUTHORITY_STALE", ...)`; one-directional (can only add a refusal)
- [x] replace `test_click_without_bound_flow_denied` with a park-then-execute expectation
- [x] tests: allowlisted unbound write no longer denied; non-allowlisted origin still denied; unbound write parks rather than executing unapproved; unbound `web.fill_credential` admitted
- [x] tests: origin drift between `web.navigate` and the interaction halts the unbound write
- [x] tests: `flow` + no bound flow → `BROWSER_FLOW_AUTHORITY_STALE`; `action` + bound flow → bound-flow guards unchanged; absent → today's behavior (fail-closed property pinned explicitly)
- [x] tests: bound-flow behavior byte-for-byte unchanged (origin match, `risk_class`, step budget, `BROWSER_FLOW_READ_ONLY`, `BROWSER_FLOW_EXHAUSTED`)
- [x] tests: the auto-allow invariant stays green and browser writes join no auto-allow list; with bridging off an unbound write is denied, never silently executed

Stage 4 note: `approval_kind` threads from the invoke body → `identity_dict` →
`gate_interaction` exactly as `session_id` does (SPEC-049 R-1 precedent), and is
enum-validated to `{flow, action}` on the way in — an out-of-vocabulary value is
dropped, never trusted. `gate_interaction` became `async` and delegates the
`flow is None` branch to a new `_gate_unbound_interaction`: off-allowlist it
halts (`about:blank` + `reset_page_state`) and returns `BROWSER_REDIRECT_NOT_ALLOWED`
(status `error`, mirroring `gate_capture`), which **retires `BROWSER_FLOW_NOT_BOUND`
from the write path**; allowlisted + `approval_kind == "flow"` returns the new
`BROWSER_FLOW_AUTHORITY_STALE` (status `denied`); otherwise it proceeds. The
success-path builders (`_step_result`, `WebPressKeyTool.execute`) dropped their
`assert flow is not None` and made step accounting conditional so an approved
unbound write cannot crash — bound-flow output is byte-for-byte unchanged. The
"parks rather than executing unapproved" leg is an **agent-platform** property
(the gateway only ever sees an already-approved, signed envelope) and is
discharged by the Stage 5 card-assembly tests; the auto-allow invariant and the
`hitl_confirm_timeout == 0` deny both live in agent-platform `kernel_middleware`
(untouched here, `test_kernel_middleware.py` 47 passed). tool-gateway suite grew
from a 318-passed baseline to 330 passed (+12 net: 5 pre-relaxation
`BROWSER_FLOW_NOT_BOUND` assertions rewritten, unbound-interaction and
provenance coverage added).

## Stage 5: agent-platform — card assembly (R-1, R-3, R-4)

- [x] `runtime_kernel.py`: compute `approval_kind` at the confirmation-frame site from the parked batch (`_tool_names_have_browser_write` **and** a bound `FlowContext`), emitting `flow_summary` from the same branch so the two cannot disagree
- [x] `schemas/v2.py`: `AgentStreamEvent` gains `approval_kind`; docstring records **v10 → v11**
- [x] `schemas/v2.py`: `ConfirmationRecordModel` gains `approval_kind` and `message`
- [x] `services/hitl_confirmations.py`: `PendingConfirmation` gains `approval_kind`, set once at park time
- [x] `services/hitl_confirmations.py`: assemble `change_request` inside `pending_calls_payload()` beside `display_hint` — a **sibling** of `parameters`, so `canonical_digest(call["parameters"])` cannot see it
- [x] curated formatter table keyed by canonical dotted tool name: `k8s.delete_pod`, the write-tier `web.*` family, `web.fill_credential` (shows `credential_set` + `field`, **never** a value); generic label→value fallback for every other tool
- [x] `services/secret_params.py` (new): second copy of the masking vocabulary + `is_secret_param()` (same case-insensitive substring semantics), the by-default mask posture, and the per-tool opaque-value list starting with `web.type.text`
- [x] `runtime_kernel.py`: `_confirmation_message` sources the informative message from the curated effect sentence where one exists; the middleware ASK string is **not** wired verbatim (sanitized name + implementation detail)
- [x] `runtime_kernel.py`: compute the card message **once** at park time and feed both the live frame and the durable record from that single value (R-4)
- [x] `services/confirmation_records.py`: persist `approval_kind` and `message` — record-create parameters, `TEXT` columns, `ADD COLUMN IF NOT EXISTS` migrations, INSERT/SELECT, row→model, both backends
- [x] `api/v2/routes.py`: coerce `approval_kind` (accepting only `flow`/`action`), `message`, and the structured `change_request` onto the session-detail entries, mirroring the `display_hint` coercion
- [x] tests: `approval_kind == "flow"` iff browser write **and** bound flow; `flow_summary` present iff `flow` — including the exact v0.34.1 regression (a `k8s.delete_pod` card with a lingering flow context carries no headline)
- [x] tests: curated `summary` for `k8s.delete_pod` and a write-tier `web.*`; generic fallback for an uncurated tool; `web.fill_credential` never emits a value
- [x] tests: name-based masking on a secret-named parameter **and** opaque-value masking on `web.type.text`
- [x] tests: `args_digest` byte-identical with and without the projection
- [x] tests: durable `message` round-trips on both backends; live frame and durable record carry the same string; a NULL-message legacy row degrades with no empty artifact
- [x] tests: a realistic parked browser frame (carrying `flow_summary`, `display_hint`, `change_request`, `approval_kind`) validates against `agent-stream-event.schema.json` v11, and a record against `agent-session.schema.json`

Stage 5 note: `approval_kind` is computed at the confirmation-frame site as
`"flow" if browser_flow else "action"`, where `browser_flow` is the bound
`FlowContext.summary()` gated on `_tool_names_have_browser_write(batch)` — the
**same branch** that emits `flow_summary`, so the declared kind and the headline
can never disagree (the v0.34.1 headline-leak becomes structurally impossible,
not merely gated; an ad-hoc browser write with no bound flow is an `action`).
`pending_calls` and the card `message` are assembled **once** in
`_build_confirmation_frame` and fed to both the live frame and the durable record
(R-4), so the operator card and the approver inbox / re-loaded transcript cannot
diverge. The `change_request` projection is a **sibling** of `parameters` gated
on `approval_kind == "action"`, so `canonical_digest(parameters)` — the signed
args_digest — is byte-identical with and without it (a flow/legacy kind carries
no projection, keeping the pre-v11 exact-shape payload assertions unchanged).
Curated formatters cover `k8s.delete_pod` + the write-tier `web.*` family
(`web.fill_credential` reference-only — `credential_set` + `field`, never a
value; `web.type.text` masked wholesale via the per-tool opaque-value list),
everything else takes a generic masked label→value fallback. `secret_params.py`
is the deliberate second copy of the gateway's `_SECRET_QUERY_PARAMS`
(byte-identical tuple; the Stage 6 validate leg pins them). `_confirmation_message`
sources from the curated effect sentence and never wires the middleware ASK
string verbatim. `routes.py` coerces `approval_kind` (flow/action only) onto the
frame and `change_request` (summary-bearing object only) onto each pending call,
mirroring `display_hint`; both durable-record construction sites carry the new
fields via `**record` splat. agent-platform suite grew from 832 passed / 2
failing (the Postgres row-mapping tuples) to **850 passed** (+16 new: the 2
tuples extended for the new columns, plus change-request/masking/digest-invariance/
round-trip/frame-record-parity/schema-validation coverage).

## Stage 6: Redaction-vocabulary lockstep leg

- [x] `shared/shared-contracts/scripts/validate_secret_vocabulary.py`: textual cross-product comparison of the agent-platform and tool-gateway tuples (the `validate_version.py` pattern), failing on divergence
- [x] root `Makefile`: add `validate-secret-vocabulary` to the `verify` target and a `.PHONY` entry
- [x] both source copies carry a comment naming their twin
- [x] tests: the leg fails when the tuples diverge and passes when they agree

Stage 6 note: `validate_secret_vocabulary.py` extracts each tuple **from source
by regex** (`VAR[: annotation] = ( ... )`) and diffs the two as sets — textual,
never import-based, so it honors the no-cross-product-import invariant and the
fail-closed posture (a mounted data file would fail *open*). It reports both
drift directions (`agent-platform only:` / `tool-gateway only:`) and treats a
missing file or unfindable tuple as a hard failure. The `Makefile` leg
(`cd products/agent-platform && uv run python …/validate_secret_vocabulary.py
../..`) mirrors `validate-version` and joins the `verify` dependency chain +
help text. `secret_params.py` already named the gateway twin; the reciprocal
`TWIN:` comment was added to `browser_connector._SECRET_QUERY_PARAMS`.
`products/agent-platform/tests/test_secret_vocabulary.py` (4 tests) runs the
script as a subprocess (the `test_policy_diff.py` pattern): the real repo agrees
(20 substrings), a synthetic tree agrees, a synthetic tree diverging in both
directions fails and names each side, and a missing twin fails. agent-platform
suite 850 → **854 passed**.

## Stage 7: operator-portal

- [x] `stream/models.ts`: `approvalKind?: "flow" | "action"` and `changeRequest?: { summary; fields?[] }` on the pending-call/card models
- [x] `stream/decoder.ts`: map `approval_kind` → `approvalKind` and `change_request` → `changeRequest`
- [x] `api/sessions.ts`: `ConfirmationRecord` gains `approval_kind`, `message`, and the per-call `change_request`
- [x] `chat/transcript.ts`: `confirmationRecordToCard` replays `approvalKind`, `changeRequest`, and `card.message` from the durable record
- [x] `chat/ChatView.tsx`: render the flow headline for `flow`, the change-request layout (`summary` lead line + optional `fields` table) for `action`, and today's tool-level rendering when both are absent; the "Technical details" expander stays
- [x] tests: decoder + transcript map all three fields; the card renders each of the three layouts; masked fields render `***`; a `summary` containing markup renders as escaped text; an absent projection produces no empty node

Stage 7 note: the wire→view-model mapping is **data-driven** — `decoder.ts`
coerces `approval_kind` (only `"flow"`/`"action"` survive) onto the frame and
`change_request` (a `summary`-bearing object only, label-less field rows
dropped) onto each pending call, mirroring the kernel/`routes.py` coercion, so a
malformed or pre-v11 payload degrades to today's tool-level rendering rather
than an empty node. `ChangeRequest`/`ChangeRequestField` are new view-model
types; `approvalKind` rides the `ConfirmationCard` (in `useChatStream.ts`, where
the card view-model lives) and the live frame→card push, while
`confirmationRecordToCard` replays `approval_kind`/`message`/per-call
`change_request` from the durable record so a re-login and the approver inbox
render the same card the live stream showed. `ChatView.tsx` branches each call on
`changeRequest` presence: a projection renders the `summary` lead line + an
optional label→value `fields` table (masked values arrive pre-masked as `***`
from the kernel and every value renders as escaped JSX text, never markup),
otherwise the call keeps today's toolName+risk header; the flow headline
(SPEC-051/053) and the "Technical details" expander are unchanged. Portal suite
290 → **303 passed** (+13: 4 decoder, 3 transcript, 6 card-render), `tsc
--noEmit` clean.

## Stage 8: Samples

- [x] new interactive per-action browser-write sample under `samples/` demonstrating the unbound login-then-mutate scenario R-2 makes reachable (reference-only credential entry + one card per write)
- [x] the sample's own demo script exercises it in the verification path (ADR-0008)
- [x] password-reset `demo.sh` chat leg stays green **unchanged** (the bound-flow one-gate path does not move)

Stage 8 note: the new sample is `samples/web-checks/adhoc-password-reset/`
(`skill/ResetPasswordAdHoc.md` + `README.md` + `WALKTHROUGH.md` +
`demo/demo.sh`), the unbound counterpart to `web-checks/password-reset`. The
runbook deliberately declares **no `web_target`** (and no `risk_class`), so
`bind_flow` rejects `web.navigate(skill_id=…)` for it with `SKILL_NOT_WEB_FLOW`
— the session is platform-enforced unbound regardless of model behavior, and
every write-tier `web.*` parks its own `action`-kind change-request card. Login
uses reference-only `web.fill_credential` (R-2's read-tier relaxation); the sole
write is the "Confirm reset" click. `demo.sh` runs five deterministic legs
(connector + HITL bridging, admin pages served, credential sets loaded, the
runbook ingested **and** asserting no `web_target`, fifteen `web.*` tools with
risk tiers) plus an opt-in `RUN_CHAT_LEG=true` chat leg whose bounded
approve-loop asserts every parked frame is `approval_kind: action` with no
`flow_summary`, a non-empty `message`, and a `change_request.summary`, then
asserts the durable record replays the same and every write-tier execution
carries a signed receipt. Validated locally: `sh -n` clean, both chat-leg
Python assertion blocks pass against synthetic wire data, and skills-hub
ingestion returns `rejections: []` with `web_target=None`/`risk_class=None`
(after trimming the frontmatter to the 10-tag limit). `deploy-samples`
discovery derives skill id `samples/adhoc-password-reset-resetpasswordadhoc`,
matching the demo. The bound-flow `password-reset` sample and its `demo.sh` are
untouched; the one-gate path does not move (agent-platform suite green,
including `TestConfirmationFrameFlowHeadline`). The live `dev-k8s` exercise of
both demos rides the Delivery Gate browser live check below.

## Delivery Gate

- [x] all acceptance criteria in `spec.md` verified (R-1…R-5), each mapped to an asserting test above (ADR-0008)
- [x] `make verify` green (all product pytest; overlays; policy; scenarios; version lockstep; the new `validate-secret-vocabulary` leg)
- [x] portal `npm test` and `npm run build` green
- [x] version lockstep bumped: `VERSION` + 8 `pyproject.toml` + 8 `metadata.py` + 2 `__init__.py` + per-product `uv.lock` re-locks
- [x] `make build` produces the **clean** image that carries the deferred v0.34.1 headline-leak gate (dev-k8s now runs the clean `0.35.0-dev-k8s-a30354d`, no `-dirty` suffix)
- [x] living state docs updated: `CHANGELOG.md`, a dated release note + the notes README index, `docs/guides/configuration-reference.md` (only if a knob appeared — none planned), `docs/agentic-aiops-platform/authorization-matrix.md` (verify only — no new action), affected RepoWiki pages
- [x] `docs/specs/README.md` SPEC-054 row → `delivered`
- [x] `docs/agentic-aiops-platform/delivery-roadmap.md` SPEC-054 backlog row → `delivered` with the shipping version
- [x] spec.md Status block → `delivered`, release slice fixed to the shipping train, delivery changelog entry appended
- [x] browser live check on the canonical dev-k8s deployment: an unbound allowlisted browser write parks a change-request card and executes on approval; a bound flow still collapses to one gate; a flow-killing result leaves no stale auto-signing authority

Delivery Gate note (local legs, 2026-09-07): `make verify` green end to end
(all product pytest — agent-platform 854, tool-gateway 330, and the rest;
kustomize overlays; 17 policy rules; 131 api + 19 tools scenarios; version
lockstep; the new `validate-secret-vocabulary` leg agreeing on 20 substrings).
Portal `npm test` 303 green and `npm run build` clean (`tsc --noEmit` + vite).
Version lockstep bumped **0.34.1 → 0.35.0** (MINOR — a backward-compatible
feature train, matching the house "release trains map to MINOR bumps"
convention and the roadmap's forward anchor of 0.36.0 for the SPEC-055-era
infra work): `VERSION` + 8 `pyproject.toml` + 8 `metadata.py` + 2
`__init__.py` literals, plus 8 `uv.lock` canonical re-locks (`uv lock`, each
updating only its self-package version — no dependency drift); `git diff`
confirms exactly 27 files, one line each, and `make validate-version` reports
`OK: all product and portal versions match VERSION=0.35.0`. Living-state docs:
`CHANGELOG.md` gained a `## 0.35.0 — 2026-09-07` section (Added + Changed);
the dated release note
`docs/agentic-aiops-platform/release-notes/2026-09-07-action-approval-and-change-request-card.md`
was authored and indexed at the top of the notes README; `specs/README.md` and
the `delivery-roadmap.md` SPEC-054 rows flipped to `delivered` (the roadmap row
carrying the 0.35.0 shipping version); and spec.md's Status block went to
`delivered` with the release slice fixed to v0.35.0 and a delivery entry
appended to its Changelog. `configuration-reference.md` needs no change (no
config knob appeared — verified: no `os.getenv`/`os.environ` addition in the
diff); `authorization-matrix.md` needs no change (no new policy action); the
RepoWiki `SPEC-054_ Action-Level Approval and Change Request Card` page already
describes the delivered implementation and carries no stale status/version
marker (RepoWiki pages are regenerated via the dedicated "refresh repowiki"
tooling commit, not hand-flipped).

Delivery Gate note (cluster legs, 2026-09-07): `make build` cut the **clean**
arm64 image `0.35.0-dev-k8s-a30354d` (nine images, no `-dirty` suffix) and
`make deploy` rolled all nine products onto it in `dev-luban-aiops`. The first
`dev-k8s` browser live check then surfaced a real defect the local legs could
not see: when an approver's decision **resumes** a turn that re-parks *another*
per-action card, `resume_confirmation` attributed the re-parked card to the
approver (the decider) instead of the session's requester, so the
platform-gateway's SPEC-030 R-3 tier-2 check read `owner == approver` and
refused card 2 with a `self_approval` 403 — breaking R-2's "N interactive
writes park N cards" for any second action. The fix threads the session owner
through the resume path (`resume_confirmation(..., owner_user_name=…)`,
supplied from `session.user_id` by the confirm route) so a re-parked card is
owned by the requester while the decider still signs the resolution and its
executions; ownerless sessions fall back to the decider. Kernel + route only —
no contract, policy, audit, or portal change. Three regression tests cover it
(re-park under the session owner, default-to-decider fallback, confirm-route
wiring); `make verify` re-ran green (agent-platform 854 → 857). Because the
v0.35.0 train was still unpushed, the fix folded into v0.35.0 with `VERSION`
unchanged, shipped as its own `fix:` commit rather than a patch release. The
clean image was re-cut at `a30354d`, redeployed, and both chat legs re-ran
green: the **unbound** leg parks two `approval_kind=action` cards each carrying
a change-request projection and no flow summary, **both** approved by
`luban-approver` (no `self_approval` 403 — the fix confirmed live) with two
signed write-tier executions persisted; the **bound** leg collapses to one
`approval_kind=flow` gate ("resumed turn completed without parking a second
gate", SPEC-051 one-gate-per-flow) with three signed `web.click` executions.
