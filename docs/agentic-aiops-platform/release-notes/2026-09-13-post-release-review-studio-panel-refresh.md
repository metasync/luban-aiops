# Post-Release Review of the Studio Split: an Inbox Refresh Fix and Retired Promotion Wording (v0.37.1)

Date: 2026-09-13

A patch closing the in-depth *code and documentation* review that followed the
v0.37.0 delivery of SPEC-056. There is no credential leak, no contract, policy,
schema, or audit change: the stream contract stays at v11 and Skill at v2. One
shipped-code change (a portal callback that had stopped covering half the
sessions it was written to cover), two code-docstring corrections, and three
drifts in the Studio guide that landed in the same release it documents.

## How this batch differs from v0.37.0

v0.37.0 was written from a spec delivery and verified against its own
acceptance criteria. This batch is written from a review of that delivery, read
against the shipped source rather than against the spec or the delivery's own
claims. The organizing result is largely negative in the good sense: all six of
SPEC-056's load-bearing invariants were re-derived from code and every one
holds.

| Invariant re-checked | Where it is actually enforced |
|---|---|
| `session_type` written once at birth, never mutated | No setter exists on the `SessionStore` protocol; the only `UPDATE … SET session_type` statements in the tree are the two OQ-2 backfill lines; touch, title and model updates never name the column; the upsert's re-type is guarded by the expired-reclaim `WHERE` |
| List scope is server-side, not client-side | `AND (%(session_type)s::text IS NULL OR COALESCE(session_type,'operation') = %(session_type)s::text)` inside `_LIST_USER_SESSIONS`; the portal sends `?session_type=<mode>` and filters nothing itself |
| The create route dual-gates on an existing action | `session:create` always, plus `session:skill_graduate` for `development` — an action that predates the train (SPEC-055). No `policy-default.yaml`, `policy-scenarios.yaml` or bundle content-hash change |
| `mode` never reaches the trust path | In `ChatView.tsx` the prop appears only at the create-affordance branch, the `SessionPanel` prop and the header-control split — never in `useChatStream`, the masking renderer or the confirmation path |
| The OQ-2 backfill defers its relation reference | The `authoring_trace_target` reference sits *inside* the `EXECUTE $q$…$q$` string, so parse-analysis reaches it only when the `IF to_regclass(…)` branch runs; both `UPDATE`s are `WHERE session_type IS NULL`, hence idempotent |
| Development sessions are never shift material | The Documents picker reads the operation-scoped instance, **and** `build_digest` raises `DevelopmentSessionRejected` → 400 after the foreign gate and before any fact is read |

What the review surfaced instead was one regression the split introduced by
making a previously-complete statement incomplete, and a small set of
documentation drifts — including two copies of wording that v0.37.0 had already
corrected in one place and left standing in two others.

## What changed

### An approvals-inbox decision now refreshes the Studio session panel too

SPEC-034 R-2 wired the approvals inbox's decision callback so that a decision
refreshes the session panel immediately instead of at the next 30s poll tick. It
was written when `App` owned **one** workspace covering every session. SPEC-056
split that into two mode-scoped instances and left the callback refreshing only
the operation one:

```tsx
() => void operationWorkspace.refresh(),
```

so a decision on a *development* session no longer cleared the Studio panel's
amber **awaiting approval** tag until the next poll.

The review did not stop at the asymmetry, because an asymmetry is only a defect
if it is reachable. It is, and the chain is worth recording since each link is
something a reader might otherwise assume away:

- the tag derives from the session list's `pending_confirmation` flag
  (`ChatView.tsx`), so a workspace refresh is exactly what clears it — this is
  not a separate piece of state that happens to lag;
- `APPROVAL_DECIDER_ROLES` is `{approver, platform-admin}`, a **subset** of
  `STUDIO_ROLES` `{platform-admin, approver, operator}`, so every role that can
  decide from the inbox can also own a development session;
- `policy_engine.effective_self_approval` returns the tier default when
  `allow_self_approval` is unset, and that default **permits** self-approval at
  `tier_1` while forbidding it at `tier_2`.

The third point is what makes the path reachable rather than theoretical. The
usual objection — a decider cannot decide a card on a session they own — holds
only for `tier_2`. Browser mutations are `tier_2`, which is why the
skill-graduation walkthrough's step 5 needs a second identity, and why the
regression went unnoticed there. A `tier_1` card on a development session the
decider owns is decided by the decider, in their own browser, firing
`onDecisionApplied` against a panel the callback no longer refreshed.

The blast radius is correspondingly small: one amber tag living up to 30s too
long. Cosmetic, self-healing, and with no effect on the trust path — the
decision itself was always applied server-side and the transcript always
resumed. It is still wrong, and it is the split that made it wrong, so it is
fixed rather than recorded.

Both instances now refresh. The second call cannot manufacture a request a
non-authoring role should not make: `refresh()` clears its list and returns
before fetching when the instance was never enabled, which covers both the
signed-out state and the non-Studio roles. The callback's own comment claimed an
immediacy that no longer held for Studio; it now names both panels and records
why the second call is needed and why it is safe.

A regression test in `App.studio.test.tsx` captures the callback `App` hands
`useApprovalsInbox` and asserts both stubs' `refresh` fire exactly once, for
each decider role. Written first, it fails against the previous form with
`expected "vi.fn()" to be called 1 times, but got 0 times` on the development
stub, so it pins the wiring rather than restating it. The suite had stubbed
`refresh` without ever invoking the callback, which is why the gap survived the
delivery's own verification.

### The removed in-place promotion no longer survives in code docstrings

v0.37.0 corrected the "becomes a development session" wording in the graduation
walkthrough, where a reader following it literally would have been misled. Two
copies were left standing in the agent-platform:

- `agent_service/api/v2/routes.py` — `declare_skill_target`'s docstring called
  itself "the path for a session that *becomes* a development session after it
  was opened". That is precisely the capability R-1 removed. It now agrees with
  the sibling `create_session` docstring that v0.37.0 had already corrected: the
  endpoint serves a *development* session opened unscoped, and "declare a
  target" is not "become a development session".
- `tests/test_skill_graduation.py` — the module docstring repeated the claim as
  "for a session that becomes a development session later".

Both are docstring-only and no route or test behaviour changes. The route has
never written `session_type`, which is exactly why the wording was harmless
enough to survive a delivery review — and why it was worth removing: a docstring
on the endpoint that *could* re-type a session, saying that it does, reads as a
guarantee the code does not make. A repo-wide sweep for the phrasing now returns
only negated uses ("there is no *Move to Studio*").

### Three `studio-guide.md` claims corrected against the shipped portal

The guide landed in v0.37.0 and three of its statements had drifted from what
they document. All three are the same failure mode: prose that sounds precise
and was not checked against the code it summarises.

- It claimed the two entries "differ in **exactly three** things: the type of
  session they create, the session list they show, and the authoring controls
  they offer". The "exactly three" was borrowed from `useSessionWorkspace.ts`,
  but the third item was substituted: the mode fixes the birth `session_type`,
  the list scope and the *active-session key namespace*. The authoring-control
  split is a separate conditional in `ChatView`, and the namespace — the reason
  a detour from Studio into Chat and back restores your place in both — was
  missing entirely. "Exactly" also contradicted the guide's own seven-row
  comparison table, which lists the create affordance and role visibility on
  top.
- It described Chat, Studio, Incidents, Documents and Settings as each keeping
  "their own view of the world", implying five workspaces. `App` creates two,
  and the operation instance is *reused* by Incidents, Documents and Settings —
  which matters, because it is the reason the shift-summary picker cannot see a
  development session.
- It attributed a missing **Studio** entry solely to a missing
  `session:skill_graduate` grant. `studioVisible` is
  `signedIn && hasAnyRole(roles, STUDIO_ROLES)`, so being signed out hides the
  entry too. Corrected in the prose and in the matching troubleshooting row.

## Untouched

No change to any contract, JSON schema, policy bundle, policy scenario, audit
event type, configuration knob, migration, or store protocol. The gateway, the
agent-platform's runtime behaviour, and every other product move on version
lockstep only. `samples/web-checks/skill-graduation/demo.sh` is unaffected: it
drives the API rather than the portal, so it never went through the inbox
callback. No `session_type` semantics changed — the discriminator remains
additive, birth-fixed and immutable.

## Verification

- `make verify` passes end to end: every product suite, all four Kustomize
  overlays (`dev-k8s`, `runtime-profiles/default`, `mutating-dev`,
  `browser-dev`), 18 policy rules against `policy-rule.schema.json`, 137 API
  and 19 tool policy scenarios with all granted pairs covered, version lockstep
  at `VERSION=0.37.1`, and all three secret-vocabulary parity checks.
- The portal suite is green at **402 tests across 32 files**, and
  `tsc --noEmit` is clean.
- The new regression test was confirmed to fail against the pre-fix callback
  before the fix was applied, for both decider roles.
- The version bump is surgical: 27 files, 27 insertions, 27 deletions — one line
  in `VERSION`, eight `pyproject.toml`, eight `metadata.py`, two `__init__.py`
  and eight `uv.lock`. Each `uv.lock` changed exactly one line, the editable
  package's own version; the replacement was anchored on
  `source = { editable = "." }` precisely so that the third-party `referencing`
  package, which coincidentally sits at 0.37.0, was left alone. A naive
  whole-file substitution would have corrupted every lockfile that depends on
  it.
- Documentation integrity re-checked after the guide corrections: 52 of 52
  relative links across the four affected guides resolve, and every Markdown
  table in them is pipe-consistent.
- The regenerated repowiki was accuracy-passed before being committed: no
  retired `Raw JSON` label naming current behaviour (the surviving mentions are
  historical "renamed from" narrative, which is kept deliberately), no stale
  current-version assertion, no mermaid block narrating a post-delivery step
  into a script-sourced diagram, and none of the three retired guide phrasings
  quoted forward. The rewritten Studio Guide page now states the dual-instance
  architecture correctly.

## Deployment state

The version bump and this note were committed before the cluster build, because
`make build` derives a clean `IMAGE_TAG` from `VERSION` plus the git SHA and
appends `-dirty-<timestamp>` on an uncommitted tree. The rebuild and redeploy
therefore followed the release commit, and this section records their outcome
rather than asserting it in advance.

With the tree clean at `b65b98b`, `make build` produced all nine images under
the coordinated tag **`0.37.1-dev-k8s-b65b98b`** — no `-dirty-` suffix — and
`make deploy` rolled them onto dev-k8s. Every luban deployment is `1/1 READY`
on that tag, and all nine pods report `ready=true` with `restartCount=0`
(`tool-gateway`'s two containers both so). The fresh `agent-service` pod came up
clean: application startup complete, model catalog refreshed to 9 models, and
zero lines matching `error|traceback|critical|exception|failed`.

The version constants the running services report agree with the tag they are
running. All eight Python services return `0.37.1` from
`importlib.metadata.version(<service>)` inside their own containers, and the
web-ui's served bundle carries the same `0.37.1` literal. The web-ui image build
also independently re-ran the portal's own gate — `tsc --noEmit && vite build`
— clean, so the `App.tsx` fix type-checks in the container path as well as in
the working tree.

Because this patch changes no contract, policy, schema, migration or store
protocol, the redeploy carried nothing to reconcile: unlike v0.37.0, whose
rebuild re-exercised the OQ-2 backfill against an already-migrated database, the
only content difference between the `0.37.0` and `0.37.1` images is the portal
bundle and the version constants, plus one docstring inside `agent-service` —
the Python images copy `src` alone, so the corrected `test_skill_graduation.py`
docstring ships in the repository and in no image.
