# Post-Release Documentation Review and a Redaction Hot-Path Cache (v0.36.3)

Date: 2026-09-11

A patch closing the in-depth *documentation* review that followed the v0.36.2
code review, plus two low-severity code-quality items re-derived from
`agent_service/services/prose_redaction.py` while re-reading it for that
review. There is no credential leak, no behaviour change, and no contract,
policy, schema, or audit change: the stream contract stays at v11 and Skill at
v2. One shipped-code change (a hot-path cache), one module-docstring
correction, three tutorial-documentation drifts, and one recorded known
limitation in the generated repowiki. This release also carries the cluster
build/deploy batched out of v0.36.2, so the masking fixes from both patches go
live together.

## How this batch differs from v0.36.2

v0.36.1 was written from live runs, v0.36.2 from a code review of the masking
machinery those runs exposed. This batch is written from a *documentation*
review of the same surface — the three password-reset walkthroughs, their three
demo scripts, the two graduated skill files, the samples README, the release
notes and CHANGELOG, and the generated repowiki — read against the shipped code
rather than against each other. The organizing result is negative in the good
sense: every load-bearing claim in the tutorial docs checked out. The fifteen
`web.*` tools and their 9-read/6-write split, the 20-step budgets and both
env-var names, the `skill_graduate` grant, and the OIDC redirect mechanism are
all accurate as written. What the review surfaced instead were small drifts — a
summary line contradicting the detailed section beside it, a deploy-state
paragraph superseded by a sequencing decision, a module docstring that lagged
the class docstring it summarises — and two code-quality nits worth fixing
while the file was open. A documentation review that mostly confirms is still
worth running: it is what lets the next reader trust the docs without
re-deriving them.

## What changed

### A hot-path cache for the deferred secret-shape import

`prose_redaction._secret_shape_patterns()` reads the pinned secret-shape
vocabulary — `skill_draft.REDACTION_VALUE_PATTERNS`, the four compiled patterns
for a PEM header, a JWT, a `Bearer`/`Basic` token, and an AWS `AKIA` key id —
through an import deferred to call time. The deferral is not a
micro-optimisation: `prose_redaction` → `skill_draft` → `shift_summary` →
`session_transcript` → `redact_transcript` → back to `prose_redaction` is a
real import cycle, inert only because the edge that closes it runs at call time
rather than module load. But the resolver also sits on the streaming hot path:
`StreamingProseRedactor.feed` reaches it three times per delta, through
`_shape_hold`, `_match_spans`, and `redact_assistant_text`, so the deferred
import machinery ran on every chunk of every streamed reply.

It now resolves once into a module global, `_SECRET_SHAPE_PATTERNS`, and
returns the cached tuple on every later call. The tuple is immutable for the
process lifetime, so behaviour is identical; the deferral is preserved — the
first call still lands at runtime, where the cycle is inert — because the cache
is a module global rather than a default argument, which would resolve at
import. The only observable difference is that a runtime monkeypatch of
`REDACTION_VALUE_PATTERNS` after the first call is no longer seen, which no
production code does and which the regression test below pins deliberately.

### The module docstring's hold limit now names the anchor hold

`prose_redaction`'s module docstring keeps a "Known accepted limits" list, and
its `StreamingProseRedactor` entry named three holds: harvested literals, a
shape already present in the buffer, and a URL still arriving. The v0.36.2 fix
added a fourth guarantee — a pinned shape *still arriving* is held by its
`SHAPE_ANCHORS` prefix, up to `SHAPE_HOLD_MAX_CHARS` (512) back — which the
class docstring described but the module docstring did not, so the summary
lagged the thing it summarises. The two now agree, including the residual cap:
past 512 characters a large multi-line PEM key is best-effort in the stream and
falls back to the durable transcript for the unbounded guarantee. A docstring
that understates its own class's protection is a small thing, but it is the
first thing the next maintainer reads.

### Sample evidence wording corrected from `web.snapshot` to `web.extract`

The password-reset walkthrough's Step 6 summary and both demo scripts' evidence
banners called the `#reset-status` success read a "snapshot". That contradicts
the same files' detailed evidence sections, which are correct: a `web.snapshot`
enumerates *interactive* elements, and the reset confirmation is a plain
`<p role="status">` with nothing interactive in it, so the success sentence is
legitimately absent from every snapshot and has to be read with `web.extract`.
Three sites reworded to `web.extract`, matching the detailed sections and the
tool's actual behaviour. The drift is the ordinary kind — a summary line written
before the detail was nailed down and never reconciled — and harmless to a run
that follows the detail, but it would send a reader who trusts the summary
looking for a string that is not there.

### The v0.36.2 note's deploy state reflects the batched deploy

The v0.36.2 release note described a standalone `0.36.2-dev-k8s-<sha>` cluster
rebuild. The decision to batch the deploy — one coordinated build/deploy at
v0.36.3 rather than two a day apart — superseded that, so the paragraph now
says the rebuild was batched into this follow-up and no standalone v0.36.2
image tag exists; the release-notes index entry agrees. Correcting a superseded
forward-reference in a shipped note is exactly the kind of thing a
documentation review is for: the note was accurate when written and the plan
moved under it.

### Known limitation: the generated repowiki overstates the Identity Broker

Three IDE-generated articles under the repowiki's Identity Broker reference —
`API Reference/Identity Broker API/Identity Broker API.md`,
`API Reference/Identity Broker API/User Management Endpoints.md`, and
`Identity Broker Service/API Endpoints and Integration.md` — fabricate a
user-management CRUD surface the broker does not implement:
`/identity/register`, `/identity/profile/{user_id}`, `/api/v1/identity/profile`,
a `register_user` and an `update_user_profile` operation, a `UserProfile`
class, and a `user.updated` event. The broker's real surface is twelve routes —
`auth` login/login-url/callback/logout-url/token/exchange/refresh,
`jwks.json`, `health` live/ready, and `identity` normalize/me — minting RS256
JWTs and serving an RFC 7517 JWKS, with user management *delegated to Keycloak*
rather than implemented here. The sibling `Identity Broker Service/Identity
Broker Service.md` article is accurate.

This is recorded rather than patched, and the distinction matters. The repowiki
is a regenerable IDE cache, not authored source: a hand-edit to those three
articles reverts the next time the wiki is regenerated, so "fixing" them in
place would be a change that silently undoes itself and leaves the record
claiming a fix that is not durable. The honest posture is to name the
limitation, point at the source of truth — the route decorators and
`token_service.py` — and leave the cache to its generator. A reader who meets
the fabricated CRUD should treat this note as the correction.

## Untouched

The stream contract (v11) and the Skill contract (v2) are unchanged, as are the
policy bundles, the authorization matrix, the JSON schemas, the audit event
types, and SPEC-037 signed execution. No new knob, endpoint, or policy action.
The masking *vocabulary* is unchanged — `validate_secret_vocabulary.py` still
reports 20 secret-parameter substrings, the `<credential-reference>` hole
marker, and 4 shape patterns in order — because the one code change is a cache
of the existing vocabulary, not a change to it or to any detector.
Execution-runtime, incident-service, audit-service, identity-broker,
platform-gateway, skills-hub, and the portal take no change beyond the version
lockstep; agent-platform takes the cache and its test.

## Verification

`make verify` is green at 0.36.3: **2552 tests** across the eight Python
products with no failures (+1 over v0.36.2 — the cache regression test), all
four GitOps overlays rendering, 18 policy rules and 137 api + 19 tools
scenarios passing, version lockstep validated across every product and the
portal's vite wiring, and all three secret-vocabulary couplings agreeing. The
portal's own vitest suite runs separately, since `make verify` does not include
operator-portal.

The one shipped-code change is pinned by a test **confirmed to fail against the
uncached form**. `test_secret_shape_patterns_caches_the_deferred_import`
resolves the vocabulary once, then monkeypatches
`skill_draft.REDACTION_VALUE_PATTERNS` to an empty tuple and resolves again:
the cached resolver returns the identical real tuple it resolved first, while a
still-re-importing resolver would pick up the poisoned empty tuple — under
which every pinned shape would leak. Stashing the source fix and leaving the
test in place runs it red for exactly that reason, then green once restored. A
cache test with no teeth would only assert the happy path; poisoning the source
after the first call is what makes it protect the cache rather than merely
describe it.

## Deployment state

This release carries the cluster build/deploy **batched out of v0.36.2**: the
nine images are rebuilt and deployed once, at the v0.36.3 sha, and the masking
fixes from *both* patches go live together on that build. No
`0.36.2-dev-k8s-<sha>` tag was ever cut. Until this build lands the cluster
keeps serving the previously deployed v0.36.1 functional images, which is what
live testing has continued against throughout.

The coordinated tag cannot be recorded inside the commit that creates it — the
short sha is an input to the tag — so the authoritative record remains the
gitignored `shared/platform-ops/gitops/dev-k8s/.images.env`, which `make build`
writes and `make deploy` consumes, verifiable from the running pods. This is
the platform's traceability posture (ADR-0008): the tag is derived from a git
ref rather than asserted in prose. A rebuild resets in-flight agent state,
since redis runs on an `emptyDir`; persisted sessions and audit survive in
their own stores.
