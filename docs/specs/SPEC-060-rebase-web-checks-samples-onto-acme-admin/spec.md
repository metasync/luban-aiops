# SPEC-060: Rebase the `web-checks` Samples onto `acme-admin`

## Status

- status: `delivered`
- owner: luban-platform-team
- created: 2026-09-18
- approved: 2026-09-18
- delivered: 2026-09-19 (samples-and-docs slice; ships in the v0.39.0 release
  train — no `VERSION` bump, so the `CHANGELOG.md` entry stays under `Unreleased`
  until that train is cut)
- release slice: R5 — Hardening and External Consumption (twenty-second R5
  slice, v0.39.0 — the rebase SPEC-059 deliberately deferred so `acme-admin`
  could ship first with R-2 "rebase compatibility"; sits between the delivered
  v0.38.0 SPEC-058/059 pair and SPEC-057, which moves to v0.40.0)
- related ADRs: **ADR-0008** (spec delivery requires requirement-to-test
  traceability and *exercised samples* — the two migrated demos are re-exercised
  against `acme-admin` in the verification path), ADR-0007 (one HITL gate per
  mutating browser flow — the migrated `password-reset` flow gate is unchanged),
  **ADR-0009** (graduate sessions into replayable executable skills — the
  `skill-graduation` sample is the demo asset graduation is taught against, now
  upgraded to verify against real store state), ADR-0011 (a composition carries
  no authority; each sub-skill keeps its own gate — unaffected, but this slice
  finishes consolidating the single-target repertoire SPEC-057 composes).
  lineage: executes the rebase **SPEC-059** R-2 engineered for and named as its
  follow-up slice ("the next slice (SPEC-060)"); extends SPEC-050 R-11 (samples
  install out-of-band so the base overlay never names a sample), SPEC-051 (the
  login-auto-submits / reset-does-not asymmetry the migrated flows preserve),
  SPEC-054 (`approval_kind: action` for the ad-hoc sample), SPEC-055
  (graduation, which the upgraded `skill-graduation` demo teaches).
- drafting: from the 2026-09-18 operator discussion that began as a
  password-reset walkthrough question and resolved into consolidating the
  browser samples onto the one target that really mutates. Decisions taken there
  and carried here: migrate `adhoc-password-reset` and `skill-graduation` onto
  `acme-admin` and **retire** `web-checks/password-reset` (superseded by the
  shipped `acme-admin/password-reset`, which already adds JSON-API
  verification); **keep `browser-check-target` shipped and untouched** because
  the platform `InventoryHealth` runbook and its e2e still drive it; **physically
  move** the two surviving samples under `samples/acme-admin/` and retire the
  `samples/web-checks/` category; and treat `skill-graduation` as a **full
  retarget plus upgrade** that leverages real store state for verification.
  Naming note carried from the same discussion: `acme` is the conventional
  fictional-company placeholder (Acme Corp), **not** the ACME certificate
  protocol (RFC 8555) — it complements SPEC-059's recorded rationale for the
  `-admin` suffix rather than "portal".

## Summary

Retire the static-mock `web-checks/password-reset` sample and rebase the two
surviving `web-checks` tutorials — `adhoc-password-reset` and `skill-graduation`
— onto the stateful `acme-admin` application, consolidating every browser sample
under `samples/acme-admin/` so all of them demonstrate against a target that
really mutates and can be verified. `browser-check-target` stays shipped for its
platform consumers; this is a samples-and-docs slice with no product code, no
contract, no policy, and no GitOps change.

## Motivation

- SPEC-059 built `acme-admin` with R-2 "rebase compatibility" — the same six URL
  shapes and all 28 element ids the static target serves — specifically so the
  three shipped `web-checks` samples could later be retargeted onto it "as a
  retarget, not a rewrite", and named that follow-up slice SPEC-060. This spec
  executes it.
- The static `browser-check-target` cannot teach verification: its login accepts
  any credentials, its reset page reports success for any user, and nothing it
  does persists. The `web-checks/password-reset` walkthrough says so out loud and
  then has to explain why the "Last reset" timestamp it just showed is a lie. A
  live tester following `skill-graduation` sees no state change because there is
  no server state to change.
- `acme-admin/password-reset` (`ResetAcmePassword`) already supersedes the static
  bound-flow reset sample: it drives the same page shapes against real state and
  adds a cross-surface verification step (`http.get /api/users/{u}` proving the
  `revision` bumped and `password_changed_at` moved). Keeping the static
  `web-checks/password-reset` alongside it is a redundant, weaker duplicate.
- Consolidating the two surviving samples onto `acme-admin` means one target that
  really mutates backs every browser tutorial, so the approval-model triad (flow
  gate ↔ per-action gate ↔ author/graduate) can be taught — and *verified* — end
  to end against real store state.
- This is the right slice now because SPEC-059 is delivered (v0.38.0) and
  SPEC-057's compositions consume the single-target repertoire this consolidation
  finishes tidying.

## Requirements

Each requirement is stable once the spec is `approved` and carries testable
acceptance criteria.

### R-1: Retire the static-mock `password-reset` sample

`samples/web-checks/password-reset/` is removed; `acme-admin/password-reset`
becomes the sole bound-flow reset sample. The shipped `ResetAcmePassword.md`
filename is **kept** (renaming it would re-id a delivered skill); its collision
rationale is updated from present-tense ("avoids colliding with
`samples/password-reset-resetuserpassword`") to historical.

Acceptance criteria:

- `samples/web-checks/password-reset/` no longer exists (README, WALKTHROUGH,
  `skill/ResetUserPassword.md`, `demo/`).
- Skill id `samples/password-reset-resetuserpassword` is no longer produced by
  `make deploy-samples`; `samples/acme-admin/password-reset` still produces
  `samples/password-reset-resetacmepassword`.
- `ResetAcmePassword.md`'s collision note reads as a historical remark, not a
  live constraint.

### R-2: Migrate `adhoc-password-reset` onto `acme-admin`

`samples/web-checks/adhoc-password-reset/` moves to
`samples/acme-admin/adhoc-password-reset/`, retargeted from
`browser-check-target` to `acme-admin`, while preserving its defining trait: the
skill declares **no `web_target` and no `risk_class`**, so the session stays
platform-enforced unbound and every browser write parks as its own
`approval_kind: action` card.

Acceptance criteria:

- The directory leaf name is unchanged, so skill id
  `samples/adhoc-password-reset-resetpasswordadhoc` is stable across the move.
- `skill/ResetPasswordAdHoc.md` targets `http://acme-admin:8080/admin/`, uses the
  `acme-admin` credential set, and still declares no `web_target`/`risk_class`.
- `demo/demo.sh` reseeds and drives `acme-admin`, and — the point of the move —
  asserts after approval that the reset actually landed in the store
  (`/api/users/{u}` `revision` bump and `password_changed_at`), while preserving
  the tool-agnostic one-card-per-write assertion.
- `WALKTHROUGH.md` and `README.md` reference the `acme-admin` origin, the
  `acme-admin` credential set, and the new sibling `../password-reset/`.

### R-3: Migrate and upgrade `skill-graduation` onto `acme-admin`

`samples/web-checks/skill-graduation/` moves to
`samples/acme-admin/skill-graduation/`, retargeted from `browser-check-target` to
`acme-admin`, and **upgraded** so the author→graduate→merge→replay story verifies
against real store state rather than a static page.

Acceptance criteria:

- The directory leaf name is unchanged; the sample ships no `skill/` of its own,
  so no skill id changes. The graduated demo id
  `samples/skill-graduation-batch-password-reset-graduation-demo` is unchanged.
- `demo/demo.sh` retargets `ADMIN_TARGET`, the credential set (leg 3, the act-1
  and act-4 prompts, and the `('Sup3rSecret','admin-portal')` regression guard),
  the leg-2 `kubectl exec` deployment, the pasted-target fixture host, and the
  end-of-run verification URLs to `acme-admin`; the R-2 element-id contract keeps
  the page greps valid.
- The demo reseeds before act 1 and adds store-verification legs proving the two
  resets landed (`/api/users/{alice,bob}` `revision` + `password_changed_at`),
  mirroring `ResetAcmePassword` step 9, while keeping the deterministic legs, the
  N-cards-to-1-gate contrast, and the tool-agnostic signed-receipt assertions
  intact.
- `WALKTHROUGH.md` rewrites the "static mock / URLs are NOT verification" lesson
  into "verify against real store state" and updates its approval-model
  cross-references to `acme-admin/password-reset` and the `adhoc-password-reset`
  sibling; `README.md` is retargeted.

### R-4: Consolidate the catalog and retire the `web-checks` category

`samples/web-checks/` ceases to exist as a category; the two surviving samples
live under `samples/acme-admin/` beside the four-skill ladder. The catalog,
suite, and every cross-reference are updated to match.

Acceptance criteria:

- No `samples/web-checks/` path remains in the repository outside historical
  records (`CHANGELOG.md`, release notes, delivered SPEC-054/055/059 docs).
- `samples/README.md` drops the "Web checks" section and folds
  `adhoc-password-reset` + `skill-graduation` into the ACME Admin section; the
  "both targets exist" paragraph is rewritten so `browser-check-target` is
  described as serving only `InventoryHealth` and the platform e2e.
- `samples/acme-admin/README.md`, `demo-suite.sh` (expected-id set six → five),
  and `demo-lib.sh` (header comment) no longer describe "the three shipped
  samples under `samples/web-checks/`".
- `docs/guides/studio-guide.md` (and `skills-guide.md` if it references a
  `web-checks` sample) point at `samples/acme-admin/skill-graduation/`.
- The approval-model triad entry-point framing lost with the retired walkthrough
  is restored in `samples/acme-admin/password-reset/WALKTHROUGH.md`.

### R-5: Leave `browser-check-target` and its platform consumers untouched

`browser-check-target` stays shipped. Its platform consumers are explicitly out of
this slice's blast radius.

Acceptance criteria:

- `shared/platform-ops/gitops/runtime-profiles/browser-dev/`
  (`browser-check-target` deployment, pages ConfigMap, allowlist) is unchanged.
- `platform-runbooks/web-checks/InventoryHealth.md` and
  `shared/platform-ops/e2e/browser-check-demo.sh` (which drives `InventoryHealth`,
  not the samples) are unchanged.
- The `browser-check-target` and `admin-portal` credential sets in
  `sync-browser-credentials.sh` are unchanged.
- A repo grep confirms no product, contract, policy, or GitOps manifest changed.

### R-6: Exercised-sample gate and naming clarification

Per ADR-0008, both migrated demos are exercised in the verification path against
`acme-admin`, and the `acme` naming rationale is documented where a reader will
look for it.

Acceptance criteria:

- `samples/acme-admin/demo-suite.sh` passes (four ladder rungs + cross-skill leg)
  and asserts exactly five distinct skill ids.
- `adhoc-password-reset/demo/demo.sh` and `skill-graduation/demo/demo.sh` pass
  their deterministic legs and, with `RUN_CHAT_LEG=true`, their chat acts against
  `acme-admin`, including store verification of each reset.
- `make verify` is green (docs link resolution, product suites, overlays render
  unchanged).
- `samples/acme-admin/README.md` and this spec record that `acme` is the
  fictional-company placeholder (Acme Corp), not the ACME certificate protocol.

## Non-Goals

- **Retiring `browser-check-target`** — it still backs the platform
  `InventoryHealth` runbook and `browser-check-demo.sh`; SPEC-059 named its
  retirement "SPEC-060's decision" and this slice decides to keep it.
- **Any product code, shared-contract, policy-bundle, or GitOps change** — the
  `acme-admin` origin is already allowlisted by SPEC-059 R-5 and the app already
  ships; this is a samples-and-docs slice.
- **Renaming `ResetAcmePassword.md`** — it is a delivered skill; renaming would
  re-id it.
- **Adding persistence (a database) to `acme-admin`** — in-memory state with
  `replicas: 1` + `Recreate` is SPEC-059's deliberate design, not a compromise;
  the reseed endpoint already gives demos deterministic state.
- **Compositions (SPEC-057)** — this slice only consolidates the single-target
  repertoire; it introduces no `kind: composition` skill.

## Impact

- products touched: none (samples and docs only).
- samples touched: `samples/web-checks/` (retired), `samples/acme-admin/`
  (`adhoc-password-reset` and `skill-graduation` moved in; `password-reset`,
  `README.md`, `demo-suite.sh`, `demo-lib.sh` updated), `samples/README.md`.
- docs touched: `docs/specs/README.md`,
  `docs/agentic-aiops-platform/delivery-roadmap.md`, `docs/guides/studio-guide.md`
  (and `skills-guide.md` if it references a `web-checks` sample), `CHANGELOG.md`.
- contracts touched: none.
- identity / policy / audit / execution safety impact: none. Skill ids for the two
  migrated samples are preserved by keeping their leaf directory names; one skill
  id (`samples/password-reset-resetuserpassword`) is intentionally removed with
  the retired sample.
- living state docs to update on delivery: `samples/README.md`,
  `samples/acme-admin/README.md`, `CHANGELOG.md`, the spec index and roadmap row.

## Open Questions

- none.

## Changelog

- 2026-09-18: created as `draft`.
- 2026-09-18: implemented — `samples/web-checks/` retired, `adhoc-password-reset`
  and `skill-graduation` migrated (and `skill-graduation` upgraded to verify both
  resets against real store state), catalog/suite/guides reframed, `CHANGELOG.md`
  entry added under `Unreleased` (targets v0.39.0). Status → `in-progress`; held
  short of `delivered` pending the ADR-0008 live dev-cluster pass over both
  migrated demos and a green `make verify`.
- 2026-09-19: delivered — the ADR-0008 exercised-sample gate passed on a live dev
  cluster: both migrated demos (`adhoc-password-reset` and `skill-graduation`,
  with `RUN_CHAT_LEG=true`) ran against the stateful `acme-admin` console and
  verified the resets landed in the store (`revision` + `password_changed_at`).
  Status → `delivered`; ships in the v0.39.0 release train (no `VERSION` bump for
  a samples-and-docs slice).
- 2026-09-19: follow-up — **SPEC-061** reverses this spec's *keep
  `browser-check-target`* decision. SPEC-060 deliberately left the static target
  shipped for its platform consumers (`InventoryHealth`, `browser-check-demo.sh`,
  the `browser-dev` allowlist, the `admin-portal`/`browser-check-target`
  credential sets) and named their retirement as the follow-up decision; SPEC-061
  retires all of them now that the `acme-admin` suite covers the browser flow
  gate against a target that really mutates. This spec's Requirements/Non-Goals
  are unchanged (delivered specs are not rewritten); the reversal is recorded
  here and specified in `docs/specs/SPEC-061-retire-browser-check-target/`.
